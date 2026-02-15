"""Channel scanner — discovers new videos from monitored YouTube channels via RSS.

Fetches RSS from https://www.youtube.com/feeds/videos.xml?channel_id=...
Uses feedparser (already in requirements).
Deduplicates by youtube_id unique constraint.
Applies gold relevance filter for general channels.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import feedparser
import httpx
from sqlalchemy import select, update

from api.database import AsyncSessionLocal
from api.videos.config import GOLD_KEYWORDS
from api.videos.models import CuratedVideo, MonitoredYoutubeChannel
from api.videos.youtube_utils import extract_youtube_id, get_channel_rss_url

logger = logging.getLogger("videos.scanner")

_HTTP_TIMEOUT = httpx.Timeout(20.0)
_USER_AGENT = "GoldMonitor/1.0 (Video Scanner)"


def _is_gold_related(title: str) -> bool:
    """Check if video title is related to gold/economics."""
    title_lower = title.lower()
    return any(kw in title_lower for kw in GOLD_KEYWORDS)


async def run() -> str:
    """Scan monitored channels for new videos.

    Returns a summary string.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MonitoredYoutubeChannel)
            .where(MonitoredYoutubeChannel.is_active.is_(True))
        )
        channels = result.scalars().all()

    if not channels:
        return "no active monitored channels"

    total_discovered = 0
    total_saved = 0
    total_skipped = 0

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        for channel in channels:
            rss_url = channel.rss_url or get_channel_rss_url(channel.youtube_channel_id)

            try:
                response = await client.get(
                    rss_url,
                    headers={"User-Agent": _USER_AGENT},
                    follow_redirects=True,
                )
                if response.status_code != 200:
                    logger.warning(
                        "RSS fetch failed for %s: HTTP %d",
                        channel.name, response.status_code,
                    )
                    continue

                feed = feedparser.parse(response.text)

            except Exception:
                logger.exception("Error fetching RSS for %s", channel.name)
                continue

            # Calculate age cutoff
            max_age_days = channel.max_age_days or 14
            cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

            for entry in feed.entries[:15]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                if not title or not link:
                    continue

                youtube_id = extract_youtube_id(link)
                if not youtube_id:
                    # Try yt:videoId tag
                    youtube_id = entry.get("yt_videoid", "").strip()
                if not youtube_id:
                    continue

                total_discovered += 1

                # Parse published date
                published_at = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published_at = datetime(
                            *entry.published_parsed[:6], tzinfo=timezone.utc
                        )
                    except (ValueError, TypeError):
                        pass

                # Skip old videos
                if published_at and published_at < cutoff:
                    total_skipped += 1
                    continue

                # Gold relevance filter (skip for always_relevant channels)
                if not channel.always_relevant and not _is_gold_related(title):
                    total_skipped += 1
                    continue

                # Check if already exists
                async with AsyncSessionLocal() as session:
                    existing = await session.execute(
                        select(CuratedVideo).where(
                            CuratedVideo.youtube_id == youtube_id
                        )
                    )
                    if existing.scalar_one_or_none() is not None:
                        total_skipped += 1
                        continue

                # Save new video (store RSS title so transcript processor can
                # pick it up immediately without waiting for metadata fetcher)
                async with AsyncSessionLocal() as session:
                    new_video = CuratedVideo(
                        youtube_id=youtube_id,
                        title_original=title[:1024] if title else None,
                        channel_name=channel.name,
                        channel_id=channel.youtube_channel_id,
                        published_at=published_at,
                        is_published=False,
                        llm_processed=False,
                        added_by="auto",
                    )
                    session.add(new_video)
                    try:
                        await session.commit()
                        total_saved += 1
                    except Exception:
                        await session.rollback()
                        logger.debug(
                            "Duplicate or error saving video: %s", youtube_id,
                        )

            # Update last_checked_at
            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(MonitoredYoutubeChannel)
                    .where(MonitoredYoutubeChannel.id == channel.id)
                    .values(last_checked_at=datetime.now(timezone.utc))
                )
                await session.commit()

    return (
        f"channels={len(channels)}, discovered={total_discovered}, "
        f"saved={total_saved}, skipped={total_skipped}"
    )
