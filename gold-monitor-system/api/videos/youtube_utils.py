"""YouTube URL parsing and formatting utilities."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse


def extract_youtube_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats.

    Handles: youtu.be, watch?v=, /live/, /embed/, /shorts/, /v/
    """
    if not url:
        return None

    url = url.strip()

    # Direct ID (11 chars, alphanumeric + dash + underscore)
    if re.match(r"^[A-Za-z0-9_-]{11}$", url):
        return url

    parsed = urlparse(url)

    # youtu.be/VIDEO_ID
    if parsed.hostname in ("youtu.be",):
        vid = parsed.path.lstrip("/").split("/")[0]
        if vid and len(vid) == 11:
            return vid

    # youtube.com/watch?v=VIDEO_ID
    if parsed.hostname in ("www.youtube.com", "youtube.com", "m.youtube.com"):
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            v = qs.get("v", [None])[0]
            if v and len(v) == 11:
                return v

        # /live/VIDEO_ID, /embed/VIDEO_ID, /shorts/VIDEO_ID, /v/VIDEO_ID
        for prefix in ("/live/", "/embed/", "/shorts/", "/v/"):
            if parsed.path.startswith(prefix):
                vid = parsed.path[len(prefix):].split("/")[0].split("?")[0]
                if vid and len(vid) == 11:
                    return vid

    return None


def get_thumbnail_url(youtube_id: str, quality: str = "maxresdefault") -> str:
    """Get YouTube thumbnail URL for a video ID.

    quality: maxresdefault, sddefault, hqdefault, mqdefault, default
    """
    return f"https://img.youtube.com/vi/{youtube_id}/{quality}.jpg"


def get_embed_url(youtube_id: str) -> str:
    """Get YouTube embed URL for a video ID."""
    return f"https://www.youtube.com/embed/{youtube_id}"


def get_channel_rss_url(channel_id: str) -> str:
    """Get YouTube channel RSS feed URL."""
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def get_watch_url(youtube_id: str) -> str:
    """Get YouTube watch URL for a video ID."""
    return f"https://www.youtube.com/watch?v={youtube_id}"


def format_duration(seconds: int | None) -> str:
    """Format duration in seconds to HH:MM:SS or MM:SS."""
    if not seconds or seconds <= 0:
        return ""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_view_count(count: int | None) -> str:
    """Format view count to Persian-friendly short format."""
    if not count or count <= 0:
        return ""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)
