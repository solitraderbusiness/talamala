"""Video metadata fetcher — populates title, channel, thumbnail via oEmbed or YouTube API.

Option 1: YouTube Data API v3 (if YOUTUBE_API_KEY is set)
Option 2: oEmbed API (no key needed) — gets title, channel, thumbnail
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update

from api.database import AsyncSessionLocal
from api.videos.models import CuratedVideo
from api.videos.youtube_utils import get_thumbnail_url

logger = logging.getLogger("videos.metadata")

_YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
_OEMBED_URL = "https://www.youtube.com/oembed"
_YT_API_URL = "https://www.googleapis.com/youtube/v3/videos"
_HTTP_TIMEOUT = httpx.Timeout(15.0)
_MAX_BATCH_SIZE = 20


async def _fetch_via_oembed(youtube_id: str, client: httpx.AsyncClient) -> dict | None:
    """Fetch metadata via YouTube oEmbed API (no key required)."""
    try:
        url = f"https://www.youtube.com/watch?v={youtube_id}"
        response = await client.get(
            _OEMBED_URL,
            params={"url": url, "format": "json"},
            follow_redirects=True,
        )
        if response.status_code != 200:
            logger.warning("oEmbed fetch failed for %s: HTTP %d", youtube_id, response.status_code)
            return None

        data = response.json()
        return {
            "title": data.get("title", ""),
            "channel_name": data.get("author_name", ""),
            "thumbnail_url": get_thumbnail_url(youtube_id, "hqdefault"),
        }
    except Exception:
        logger.warning("oEmbed error for %s", youtube_id, exc_info=True)
        return None


async def _fetch_via_youtube_api(
    youtube_ids: list[str], client: httpx.AsyncClient
) -> dict[str, dict]:
    """Fetch metadata via YouTube Data API v3 (requires key)."""
    results: dict[str, dict] = {}
    try:
        response = await client.get(
            _YT_API_URL,
            params={
                "id": ",".join(youtube_ids),
                "part": "snippet,contentDetails,statistics",
                "key": _YOUTUBE_API_KEY,
            },
        )
        if response.status_code != 200:
            logger.warning("YouTube API failed: HTTP %d", response.status_code)
            return results

        data = response.json()
        for item in data.get("items", []):
            vid = item["id"]
            snippet = item.get("snippet", {})
            content = item.get("contentDetails", {})
            stats = item.get("statistics", {})

            # Parse ISO 8601 duration (PT1H2M3S)
            duration = _parse_iso_duration(content.get("duration", ""))

            # Parse published date
            published_at = None
            if snippet.get("publishedAt"):
                try:
                    published_at = datetime.fromisoformat(
                        snippet["publishedAt"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            results[vid] = {
                "title": snippet.get("title", ""),
                "channel_name": snippet.get("channelTitle", ""),
                "channel_id": snippet.get("channelId", ""),
                "thumbnail_url": (
                    snippet.get("thumbnails", {}).get("high", {}).get("url")
                    or get_thumbnail_url(vid, "hqdefault")
                ),
                "duration_seconds": duration,
                "view_count": int(stats.get("viewCount", 0)) or None,
                "published_at": published_at,
            }
    except Exception:
        logger.exception("YouTube API error")

    return results


def _parse_iso_duration(duration: str) -> int | None:
    """Parse ISO 8601 duration string (PT1H2M3S) to seconds."""
    if not duration:
        return None
    import re
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    total = hours * 3600 + minutes * 60 + seconds
    return total if total > 0 else None


async def run() -> str:
    """Fetch metadata for videos missing title/channel info.

    Returns a summary string.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CuratedVideo)
            .where(CuratedVideo.thumbnail_url.is_(None))
            .where(CuratedVideo.metadata_errors < 5)
            .limit(_MAX_BATCH_SIZE)
        )
        videos = result.scalars().all()

    if not videos:
        return "no videos need metadata"

    updated = 0
    errors = 0

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        if _YOUTUBE_API_KEY:
            # Batch fetch via YouTube API
            ids = [v.youtube_id for v in videos]
            api_results = await _fetch_via_youtube_api(ids, client)

            for video in videos:
                meta = api_results.get(video.youtube_id)
                if not meta:
                    errors += 1
                    async with AsyncSessionLocal() as session:
                        await session.execute(
                            update(CuratedVideo)
                            .where(CuratedVideo.id == video.id)
                            .values(metadata_errors=CuratedVideo.metadata_errors + 1)
                        )
                        await session.commit()
                    continue

                values: dict = {
                    "thumbnail_url": meta.get("thumbnail_url"),
                    "duration_seconds": meta.get("duration_seconds"),
                    "view_count": meta.get("view_count"),
                    "published_at": meta.get("published_at"),
                    "updated_at": datetime.now(timezone.utc),
                }
                # Only overwrite title/channel if not already set (e.g. from RSS)
                if not video.title_original and meta.get("title"):
                    values["title_original"] = meta["title"][:1024]
                if not video.channel_name and meta.get("channel_name"):
                    values["channel_name"] = meta["channel_name"]
                if not video.channel_id and meta.get("channel_id"):
                    values["channel_id"] = meta["channel_id"]

                async with AsyncSessionLocal() as session:
                    await session.execute(
                        update(CuratedVideo)
                        .where(CuratedVideo.id == video.id)
                        .values(**values)
                    )
                    await session.commit()
                updated += 1
        else:
            # Fall back to oEmbed (one at a time)
            for video in videos:
                meta = await _fetch_via_oembed(video.youtube_id, client)
                if not meta:
                    errors += 1
                    async with AsyncSessionLocal() as session:
                        await session.execute(
                            update(CuratedVideo)
                            .where(CuratedVideo.id == video.id)
                            .values(metadata_errors=CuratedVideo.metadata_errors + 1)
                        )
                        await session.commit()
                    continue

                values: dict = {
                    "thumbnail_url": meta.get("thumbnail_url"),
                    "updated_at": datetime.now(timezone.utc),
                }
                # Only overwrite title/channel if not already set (e.g. from RSS)
                if not video.title_original and meta.get("title"):
                    values["title_original"] = meta["title"][:1024]
                if not video.channel_name and meta.get("channel_name"):
                    values["channel_name"] = meta["channel_name"]

                async with AsyncSessionLocal() as session:
                    await session.execute(
                        update(CuratedVideo)
                        .where(CuratedVideo.id == video.id)
                        .values(**values)
                    )
                    await session.commit()
                updated += 1

    return f"updated={updated}, errors={errors}"
