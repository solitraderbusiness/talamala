"""Video transcript processor — fetches transcripts and scores via LLM.

Uses youtube-transcript-api to fetch English/auto transcripts,
then calls OpenRouter LLM for Persian summary, key points, topics,
category, and relevance score.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update

from api.database import AsyncSessionLocal
from api.videos.config import (
    OPENROUTER_API_KEY,
    PUBLISH_THRESHOLD,
    TRANSCRIPT_MAX_CHARS,
    VIDEO_LLM_MAX_TOKENS,
    VIDEO_LLM_MODEL,
    VIDEO_LLM_TEMPERATURE,
    VIDEO_SCORING_SYSTEM_PROMPT,
    VIDEO_SCORING_USER_TEMPLATE_TITLE_ONLY,
    VIDEO_SCORING_USER_TEMPLATE_WITH_TRANSCRIPT,
)
from api.videos.models import CuratedVideo

logger = logging.getLogger("videos.transcript")

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_MAX_BATCH_SIZE = 20
_MAX_RETRIES = 3


def _fetch_transcript_sync(youtube_id: str) -> str | None:
    """Fetch transcript synchronously (run in executor).

    Uses youtube-transcript-api v1.2+ API:
    - Instantiate YouTubeTranscriptApi() (no static methods)
    - Call ytt_api.fetch(video_id, languages=[...])
    - Access snippet.text attribute on each FetchedTranscriptSnippet
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(youtube_id, languages=["en"])
        text = " ".join(snippet.text for snippet in transcript)
        return text.strip() if text.strip() else None

    except Exception:
        logger.warning("No transcript for %s", youtube_id, exc_info=True)
        return None


async def _fetch_transcript(youtube_id: str) -> str | None:
    """Fetch transcript asynchronously."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_transcript_sync, youtube_id)


async def _call_openrouter(
    title: str, channel: str, transcript: str
) -> dict | None:
    """Send transcript (or title-only) to OpenRouter for scoring and summarization."""
    if not OPENROUTER_API_KEY:
        logger.warning("OPENROUTER_API_KEY not set; skipping LLM scoring.")
        return None

    if transcript:
        user_prompt = VIDEO_SCORING_USER_TEMPLATE_WITH_TRANSCRIPT.format(
            title=title,
            channel=channel,
            transcript=transcript[:TRANSCRIPT_MAX_CHARS],
            max_chars=TRANSCRIPT_MAX_CHARS,
        )
    else:
        user_prompt = VIDEO_SCORING_USER_TEMPLATE_TITLE_ONLY.format(
            title=title,
            channel=channel,
        )

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://gold-monitor.local",
        "X-Title": "Gold Monitor Video Scorer",
    }

    payload = {
        "model": VIDEO_LLM_MODEL,
        "messages": [
            {"role": "system", "content": VIDEO_SCORING_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": VIDEO_LLM_TEMPERATURE,
        "max_tokens": VIDEO_LLM_MAX_TOKENS,
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
                await asyncio.sleep(2 ** attempt)
                continue
            return None
        except httpx.TimeoutException:
            logger.error("OpenRouter timeout (attempt %d)", attempt)
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)
                continue
            return None
        except Exception:
            logger.exception("Unexpected error calling OpenRouter (attempt %d)", attempt)
            return None

    return None


async def run() -> str:
    """Fetch transcripts and score unprocessed videos.

    Returns a summary string.
    """
    scored = 0
    published = 0
    errors = 0

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CuratedVideo)
            .where(CuratedVideo.llm_processed.is_(False))
            .where(CuratedVideo.title_original.isnot(None))
            .order_by(CuratedVideo.created_at.asc())
            .limit(_MAX_BATCH_SIZE)
        )
        videos = result.scalars().all()

    if not videos:
        return "no unprocessed videos"

    for video in videos:
        # Fetch transcript if not already stored
        transcript = video.transcript
        if not transcript:
            transcript = await _fetch_transcript(video.youtube_id)
            if transcript:
                async with AsyncSessionLocal() as session:
                    await session.execute(
                        update(CuratedVideo)
                        .where(CuratedVideo.id == video.id)
                        .values(transcript=transcript)
                    )
                    await session.commit()

        if not transcript:
            logger.info(
                "No transcript for %s — using title-only scoring",
                video.youtube_id,
            )

        # Call LLM (with transcript or title-only fallback)
        llm_result = await _call_openrouter(
            video.title_original or video.youtube_id,
            video.channel_name or "Unknown",
            transcript or "",
        )

        if llm_result is None:
            errors += 1
            continue

        # Extract and validate fields
        relevance = float(llm_result.get("relevance_score", 0))
        should_publish = relevance >= PUBLISH_THRESHOLD

        valid_categories = {"analysis", "news", "education", "interview", "documentary", "podcast"}
        category = llm_result.get("category", "analysis")
        if category not in valid_categories:
            category = "analysis"

        valid_topics = {
            "gold_price", "fed_policy", "central_banks", "geopolitics",
            "inflation", "dollar", "technical_analysis", "market_outlook",
            "silver", "mining", "etf_flows", "recession", "debt_crisis",
            "de_dollarization", "supply_demand", "crypto", "oil", "china",
            "investment_strategy",
        }
        topics = [t for t in (llm_result.get("topics") or []) if t in valid_topics]

        outlook = llm_result.get("gold_outlook", "neutral")
        if outlook not in ("bullish", "bearish", "neutral", "mixed"):
            outlook = "neutral"

        # Update video
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(CuratedVideo)
                .where(CuratedVideo.id == video.id)
                .values(
                    title_fa=llm_result.get("title_fa", "")[:1024] or None,
                    summary_fa=llm_result.get("summary_fa", "") or None,
                    key_points_fa=llm_result.get("key_points_fa") or [],
                    topics=topics,
                    category=category,
                    gold_outlook=outlook,
                    relevance_score=relevance,
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
            "Scored video: %s [%.0f] %s",
            (video.title_original or video.youtube_id)[:60],
            relevance,
            "PUBLISHED" if should_publish else "filtered",
        )

    return f"scored={scored}, published={published}, errors={errors}"
