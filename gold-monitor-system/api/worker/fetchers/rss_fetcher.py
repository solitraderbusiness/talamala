"""
RSS / Atom feed fetcher.

Uses ``aiohttp`` to download the feed and ``feedparser`` to parse it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser

from api.worker.fetchers.base import BaseFetcher, RawItem

logger = logging.getLogger(__name__)


class RSSFetcher(BaseFetcher):
    """Fetch and parse RSS/Atom feeds."""

    async def fetch(self, source: dict, http_session) -> list[RawItem]:
        endpoints = _normalise_endpoints(source.get("endpoints", []))
        items: list[RawItem] = []

        for url in endpoints:
            try:
                raw_items = await self._fetch_feed(url, http_session)
                items.extend(raw_items)
            except Exception:
                logger.exception("RSS fetch failed for endpoint %s", url)

        return items

    # ------------------------------------------------------------------

    async def _fetch_feed(
        self, url: str, http_session
    ) -> list[RawItem]:
        async with http_session.get(url) as resp:
            resp.raise_for_status()
            body = await resp.text()

        feed = feedparser.parse(body)
        if feed.bozo and not feed.entries:
            logger.warning(
                "feedparser reported an error for %s: %s",
                url,
                feed.bozo_exception,
            )

        items: list[RawItem] = []
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", url).strip()
            content_text = _extract_content(entry)
            published_at = _parse_date(entry)

            metadata: dict[str, Any] = {}
            if entry.get("author"):
                metadata["author"] = entry["author"]
            if entry.get("tags"):
                metadata["tags"] = [
                    t.get("term", "") for t in entry["tags"]
                ]

            items.append(
                RawItem(
                    title=title,
                    url=link,
                    content_text=content_text,
                    published_at=published_at,
                    metadata=metadata,
                )
            )

        logger.debug(
            "Parsed %d entries from RSS feed %s", len(items), url
        )
        return items


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _normalise_endpoints(endpoints: Any) -> list[str]:
    """Accept a list of strings or a single string and return a list."""
    if isinstance(endpoints, str):
        return [endpoints]
    if isinstance(endpoints, list):
        result: list[str] = []
        for ep in endpoints:
            if isinstance(ep, str):
                result.append(ep)
            elif isinstance(ep, dict) and "url" in ep:
                result.append(ep["url"])
        return result
    return []


def _extract_content(entry: dict) -> str:
    """Pull the best available text from an RSS/Atom entry."""
    # Prefer content (Atom full content), then summary, then description
    if entry.get("content"):
        parts = entry["content"]
        if isinstance(parts, list) and parts:
            return parts[0].get("value", "").strip()
    if entry.get("summary"):
        return entry["summary"].strip()
    if entry.get("description"):
        return entry["description"].strip()
    return ""


def _parse_date(entry: dict) -> datetime | None:
    """Try to extract a timezone-aware datetime from the entry."""
    for field in ("published_parsed", "updated_parsed"):
        time_struct = entry.get(field)
        if time_struct is not None:
            try:
                from time import mktime

                ts = mktime(time_struct)
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                continue

    for field in ("published", "updated"):
        raw = entry.get(field, "")
        if raw:
            try:
                return parsedate_to_datetime(raw).astimezone(timezone.utc)
            except (TypeError, ValueError):
                continue

    return None
