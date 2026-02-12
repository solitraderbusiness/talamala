"""Article fetcher — discovers and saves new articles from configured sources.

Fetches RSS feeds and web pages to discover new articles, extracts content,
deduplicates, and stores raw articles in the database for LLM scoring.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone

import feedparser
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from api.articles.config import (
    ARTICLE_SOURCES,
    GOLD_KEYWORDS,
    MAX_ARTICLE_AGE_DAYS,
    MIN_WORD_COUNT,
)
from api.articles.models import GoldArticle
from api.database import AsyncSessionLocal

logger = logging.getLogger("articles.fetcher")

_HTTP_TIMEOUT = httpx.Timeout(30.0)
_USER_AGENT = "GoldMonitor/1.0 (Article Fetcher)"


def _make_dedupe_hash(title: str, source_url: str) -> str:
    """Create a deduplication hash from title and source URL."""
    raw = f"{title.strip().lower()}|{source_url.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def _extract_text_from_html(html: str) -> str:
    """Extract readable text from HTML using BeautifulSoup."""
    soup = BeautifulSoup(html, "lxml")

    # Remove script, style, nav, footer, aside
    for tag in soup.find_all(["script", "style", "nav", "footer", "aside", "header"]):
        tag.decompose()

    # Try to find the main article content
    article = soup.find("article") or soup.find("main") or soup.find(
        "div", class_=re.compile(r"article|content|post|entry", re.I)
    )
    if article:
        text = article.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)

    # Clean up whitespace
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines)


def _is_gold_related(title: str, content: str = "") -> bool:
    """Check if article is related to gold markets."""
    combined = (title + " " + content).lower()
    return any(kw in combined for kw in GOLD_KEYWORDS)


def _is_price_recap(title: str, content: str) -> bool:
    """Detect shallow price recap articles."""
    title_lower = title.lower()
    recap_patterns = [
        r"gold (closes?|closed|ends?|ended) at",
        r"gold (rises?|fell|drops?|gains?) \$?\d",
        r"gold price (today|update|recap)",
        r"weekly (gold )?price (recap|review|summary)",
    ]
    for pattern in recap_patterns:
        if re.search(pattern, title_lower):
            return True
    return False


def _is_sponsored(title: str, content: str) -> bool:
    """Detect sponsored/advertorial content."""
    combined = (title + " " + content[:500]).lower()
    return any(kw in combined for kw in [
        "sponsored", "advertorial", "partner content", "paid post",
        "promoted", "advertisement",
    ])


async def _fetch_rss_articles(
    source: dict, client: httpx.AsyncClient
) -> list[dict]:
    """Fetch articles from an RSS feed."""
    rss_url = source.get("rss_url") or source["url"]
    articles = []

    try:
        response = await client.get(
            rss_url,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        )
        if response.status_code != 200:
            logger.warning(
                "RSS fetch failed for %s: HTTP %d", source["name"], response.status_code
            )
            return []

        feed = feedparser.parse(response.text)

        for entry in feed.entries[:20]:  # max 20 per source
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue

            # Parse published date
            published_at = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass

            # Get summary/description
            summary = ""
            if hasattr(entry, "summary"):
                summary = BeautifulSoup(entry.summary, "lxml").get_text(strip=True)
            elif hasattr(entry, "description"):
                summary = BeautifulSoup(entry.description, "lxml").get_text(strip=True)

            author = entry.get("author", None)

            articles.append({
                "title": title,
                "url": link,
                "published_at": published_at,
                "summary_text": summary,
                "author": author,
                "source_name": source["name"],
                "source_name_fa": source["name_fa"],
                "default_importance_boost": source["default_importance_boost"],
            })

    except Exception:
        logger.exception("Error fetching RSS for %s", source["name"])

    return articles


async def _fetch_article_content(
    url: str, client: httpx.AsyncClient
) -> tuple[str, bool]:
    """Fetch full article content. Returns (text, is_partial)."""
    try:
        response = await client.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        )
        if response.status_code != 200:
            return "", True

        html = response.text
        text = _extract_text_from_html(html)

        # Check if behind paywall
        is_partial = False
        paywall_markers = [
            "subscribe to continue", "sign up to read", "premium content",
            "paywall", "members only", "to continue reading",
        ]
        if any(marker in text.lower()[:1000] for marker in paywall_markers):
            is_partial = True

        return text, is_partial

    except httpx.TimeoutException:
        logger.warning("Timeout fetching article: %s", url[:100])
        return "", True
    except Exception:
        logger.warning("Error fetching article content: %s", url[:100], exc_info=True)
        return "", True


async def run() -> str:
    """Fetch new articles from all configured sources.

    Returns a summary string.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_ARTICLE_AGE_DAYS)
    total_discovered = 0
    total_saved = 0
    total_skipped = 0

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        for source in ARTICLE_SOURCES:
            source_type = source.get("type", "rss")

            # Fetch from RSS if available
            if source_type in ("rss", "rss_or_scrape") and source.get("rss_url"):
                articles = await _fetch_rss_articles(source, client)
            else:
                # Scrape-only sources — skip for now, only RSS supported initially
                logger.debug("Skipping scrape-only source: %s", source["name"])
                continue

            total_discovered += len(articles)

            for article in articles:
                # Skip old articles
                if article["published_at"] and article["published_at"] < cutoff:
                    total_skipped += 1
                    continue

                # Check dedup hash
                dedupe_hash = _make_dedupe_hash(article["title"], article["url"])

                async with AsyncSessionLocal() as session:
                    existing = await session.execute(
                        select(GoldArticle).where(GoldArticle.dedupe_hash == dedupe_hash)
                    )
                    if existing.scalar_one_or_none() is not None:
                        total_skipped += 1
                        continue

                # Filter non-gold articles from generic feeds
                if not _is_gold_related(article["title"], article.get("summary_text", "")):
                    total_skipped += 1
                    continue

                # Fetch full content
                content, is_partial = await _fetch_article_content(article["url"], client)

                # Count words
                word_count = len(content.split()) if content else 0

                # Apply quality filters on title + content
                if _is_price_recap(article["title"], content):
                    total_skipped += 1
                    continue

                if _is_sponsored(article["title"], content):
                    total_skipped += 1
                    continue

                # Save to database
                async with AsyncSessionLocal() as session:
                    new_article = GoldArticle(
                        title_original=article["title"][:1024],
                        source_name=article["source_name"],
                        source_url=article["url"][:2048],
                        author=article.get("author"),
                        published_at=article.get("published_at"),
                        dedupe_hash=dedupe_hash,
                        word_count_original=word_count,
                        partial_content=is_partial,
                        source_boost=article["default_importance_boost"],
                        original_language="en",
                        llm_processed=False,
                        is_published=False,
                        is_featured=False,
                    )
                    session.add(new_article)
                    try:
                        await session.commit()
                        total_saved += 1
                    except Exception:
                        await session.rollback()
                        logger.warning(
                            "Failed to save article: %s", article["title"][:80],
                            exc_info=True,
                        )

    return (
        f"discovered={total_discovered}, saved={total_saved}, "
        f"skipped={total_skipped}"
    )
