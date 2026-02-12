"""Article LLM scorer — scores and summarizes articles using OpenRouter.

Picks up unprocessed articles, sends content to the LLM for scoring and
Persian summarization, then updates the article with results and publishes
those that pass the quality threshold.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import and_, desc, func, select, update

from api.articles.config import (
    ARTICLE_CONTENT_MAX_CHARS,
    ARTICLE_LLM_MAX_TOKENS,
    ARTICLE_LLM_MODEL,
    ARTICLE_LLM_TEMPERATURE,
    ARTICLE_SCORING_SYSTEM_PROMPT,
    ARTICLE_SCORING_USER_TEMPLATE,
    AUTO_BOOST_SOURCES,
    MIN_WORD_COUNT,
    OPENROUTER_API_KEY,
    PUBLISH_THRESHOLD,
)
from api.articles.models import GoldArticle
from api.database import AsyncSessionLocal

logger = logging.getLogger("articles.scorer")

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_MAX_BATCH_SIZE = 50
_MAX_RETRIES = 3


async def _fetch_article_content_for_scoring(article: GoldArticle) -> str:
    """Fetch the article page content for LLM scoring.

    If we didn't store the content during fetching, re-fetch it now.
    Uses the article URL to fetch content.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            response = await client.get(
                article.source_url,
                headers={"User-Agent": "GoldMonitor/1.0 (Article Scorer)"},
                follow_redirects=True,
            )
            if response.status_code != 200:
                return ""

            from api.articles.workers.fetcher import _extract_text_from_html
            text = _extract_text_from_html(response.text)
            return text[:ARTICLE_CONTENT_MAX_CHARS]

    except Exception:
        logger.warning("Failed to fetch content for scoring: %s", article.source_url[:80])
        return ""


async def _call_openrouter(
    title: str, source_name: str, content: str
) -> dict | None:
    """Send article to OpenRouter for scoring and summarization."""
    if not OPENROUTER_API_KEY:
        logger.warning("OPENROUTER_API_KEY not set; skipping LLM scoring.")
        return None

    user_prompt = ARTICLE_SCORING_USER_TEMPLATE.format(
        title=title,
        source_name=source_name,
        content=content[:ARTICLE_CONTENT_MAX_CHARS] if content else "(no content available)",
    )

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://gold-monitor.local",
        "X-Title": "Gold Monitor Article Scorer",
    }

    payload = {
        "model": ARTICLE_LLM_MODEL,
        "messages": [
            {"role": "system", "content": ARTICLE_SCORING_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": ARTICLE_LLM_TEMPERATURE,
        "max_tokens": ARTICLE_LLM_MAX_TOKENS,
    }

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                response = await client.post(
                    _OPENROUTER_URL, headers=headers, json=payload,
                )

            if response.status_code != 200:
                logger.error(
                    "OpenRouter HTTP %d (attempt %d): %s",
                    response.status_code, attempt, response.text[:300],
                )
                if attempt < _MAX_RETRIES:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None

            data = response.json()
            raw_text = data["choices"][0]["message"]["content"].strip()

            # Strip markdown fences
            if raw_text.startswith("```"):
                first_nl = raw_text.find("\n")
                if first_nl != -1:
                    raw_text = raw_text[first_nl + 1:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                raw_text = raw_text.strip()

            return json.loads(raw_text)

        except json.JSONDecodeError:
            logger.error("Failed to parse LLM response as JSON (attempt %d)", attempt)
            if attempt < _MAX_RETRIES:
                import asyncio
                await asyncio.sleep(2 ** attempt)
                continue
            return None
        except httpx.TimeoutException:
            logger.error("OpenRouter timeout (attempt %d)", attempt)
            if attempt < _MAX_RETRIES:
                import asyncio
                await asyncio.sleep(2 ** attempt)
                continue
            return None
        except Exception:
            logger.exception("Unexpected error calling OpenRouter (attempt %d)", attempt)
            return None

    return None


async def _update_featured_article() -> None:
    """Mark the single highest-scoring published article today as featured."""
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    async with AsyncSessionLocal() as session:
        # Clear today's featured flags
        await session.execute(
            update(GoldArticle)
            .where(
                GoldArticle.is_featured.is_(True),
                GoldArticle.created_at >= today_start,
            )
            .values(is_featured=False)
        )

        # Find highest scoring published article today
        result = await session.execute(
            select(GoldArticle)
            .where(
                GoldArticle.is_published.is_(True),
                GoldArticle.created_at >= today_start,
            )
            .order_by(desc(GoldArticle.importance_score))
            .limit(1)
        )
        top_article = result.scalar_one_or_none()

        if top_article:
            top_article.is_featured = True

        await session.commit()


async def run() -> str:
    """Score unprocessed articles with LLM and publish qualifying ones.

    Returns a summary string.
    """
    scored = 0
    published = 0
    errors = 0

    async with AsyncSessionLocal() as session:
        # Get unprocessed articles (limit batch size)
        result = await session.execute(
            select(GoldArticle)
            .where(GoldArticle.llm_processed.is_(False))
            .order_by(GoldArticle.created_at.asc())
            .limit(_MAX_BATCH_SIZE)
        )
        articles = result.scalars().all()

    if not articles:
        return "no unprocessed articles"

    for article in articles:
        # Fetch content for scoring
        content = await _fetch_article_content_for_scoring(article)

        # Use fetched content word count (not RSS snippet word count)
        content_word_count = len(content.split()) if content else 0

        # Skip too-short articles (content must meet minimum)
        if content_word_count < MIN_WORD_COUNT and not article.partial_content:
            logger.info("Skipping short article (%d words): %s", content_word_count, article.title_original[:60])
            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(GoldArticle)
                    .where(GoldArticle.id == article.id)
                    .values(llm_processed=True, is_published=False)
                )
                await session.commit()
            continue

        # Call LLM
        llm_result = await _call_openrouter(
            article.title_original, article.source_name, content
        )

        if llm_result is None:
            errors += 1
            continue

        # Extract fields
        raw_score = float(llm_result.get("importance_score", 0))
        source_boost = float(article.source_boost or 0)

        # Extra boost for known high-quality sources
        if any(name in article.source_name for name in AUTO_BOOST_SOURCES):
            source_boost = max(source_boost, 15)

        # Auto-boost for specific price forecasts with data
        content_lower = (content or "").lower()
        if any(kw in content_lower for kw in ["price target", "forecast", "predict"]):
            if any(c.isdigit() for c in content_lower[:2000]):
                source_boost += 5

        final_score = min(100, raw_score + source_boost)
        should_publish = final_score >= PUBLISH_THRESHOLD

        # Validate topics
        valid_topics = {
            "fed_policy", "ecb_policy", "china_demand", "india_demand",
            "central_banks", "etf_flows", "mine_supply", "geopolitics",
            "sanctions", "inflation", "dollar", "technical_analysis",
            "price_forecast", "investment_strategy", "silver", "oil",
            "crypto_correlation", "de_dollarization",
        }
        topics = [t for t in (llm_result.get("topics") or []) if t in valid_topics]

        valid_assets = {"xauusd", "iran_gold", "usd_irr", "silver", "dxy", "oil", "btc"}
        assets = [a for a in (llm_result.get("affected_assets") or []) if a in valid_assets]

        # Validate outlook
        outlook = llm_result.get("gold_outlook", "neutral")
        if outlook not in ("bullish", "bearish", "neutral", "mixed"):
            outlook = "neutral"

        horizon = llm_result.get("time_horizon", "medium_term")
        if horizon not in ("short_term", "medium_term", "long_term"):
            horizon = "medium_term"

        # Update article
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(GoldArticle)
                .where(GoldArticle.id == article.id)
                .values(
                    title_fa=llm_result.get("title_fa", "")[:1024] or None,
                    summary_fa=llm_result.get("summary_fa", "") or None,
                    key_takeaways_fa=llm_result.get("key_takeaways_fa") or [],
                    gold_outlook=outlook,
                    time_horizon=horizon,
                    topics=topics,
                    affected_assets=assets,
                    raw_importance_score=raw_score,
                    source_boost=source_boost,
                    importance_score=final_score,
                    is_published=should_publish,
                    llm_processed=True,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

        scored += 1
        if should_publish:
            published += 1

        logger.info(
            "Scored article: %s [%.0f → %.0f] %s",
            article.title_original[:60],
            raw_score,
            final_score,
            "PUBLISHED" if should_publish else "filtered",
        )

    # Update featured article
    await _update_featured_article()

    return f"scored={scored}, published={published}, errors={errors}"
