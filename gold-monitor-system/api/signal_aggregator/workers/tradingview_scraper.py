"""TradingView XAUUSD ideas scraper for the Signal Aggregator.

Periodically fetches XAUUSD trading ideas from TradingView's ideas page
and saves new ones as ``RawPost`` rows for subsequent parsing.

TradingView removed their public ideas API, so we scrape the HTML page at
``/symbols/XAUUSD/ideas/?sort=recent`` and extract ideas from the embedded
JSON blob in a ``<script>`` tag.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from api.database import AsyncSessionLocal
from api.signal_aggregator.config import (
    TRADINGVIEW_COOKIE,
    TRADINGVIEW_INTERVAL_SECONDS,
)
from api.signal_aggregator.models import RawPost, SignalSource
from api.signal_aggregator.utils.deduplication import is_duplicate

logger = logging.getLogger("signal_aggregator.tradingview")

# TradingView ideas page for XAUUSD (sorted by most recent)
_TV_IDEAS_URL = "https://www.tradingview.com/symbols/XAUUSD/ideas/?sort=recent"
_TV_SYMBOL = "XAUUSD"
_REQUEST_TIMEOUT = 30.0
_MAX_IDEAS_PER_FETCH = 50

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def _get_tradingview_source() -> SignalSource | None:
    """Return the first active TradingView signal source, or ``None``."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SignalSource).where(
                SignalSource.type == "tradingview",
                SignalSource.active.is_(True),
            )
        )
        return result.scalars().first()


def _extract_ideas_from_html(html: str) -> list[dict]:
    """Extract idea objects from TradingView's server-rendered HTML.

    TradingView embeds a large JSON blob in an inline ``<script>`` tag.
    The ideas are nested under a dynamic hash key at the path:
    ``{hash_key}.data.ideas.data.items[]``.
    """
    # Find all inline <script> tags (no src attribute) with substantial content
    script_pattern = re.compile(
        r"<script[^>]*>(\{.+?\})</script>", re.DOTALL
    )

    for match in script_pattern.finditer(html):
        blob_text = match.group(1)
        # Quick sanity check — must contain "ideas" and be large enough
        if '"ideas"' not in blob_text or len(blob_text) < 500:
            continue

        try:
            blob = json.loads(blob_text)
        except (json.JSONDecodeError, ValueError):
            continue

        # Navigate the dynamic structure: {hash_key}.data.ideas.data.items[]
        if not isinstance(blob, dict):
            continue

        for key, value in blob.items():
            if not isinstance(value, dict):
                continue
            data = value.get("data")
            if not isinstance(data, dict):
                continue
            ideas_container = data.get("ideas")
            if not isinstance(ideas_container, dict):
                continue
            ideas_data = ideas_container.get("data")
            if not isinstance(ideas_data, dict):
                continue
            items = ideas_data.get("items")
            if isinstance(items, list) and items:
                logger.info(
                    "Extracted %d ideas from TradingView HTML (key=%s).",
                    len(items),
                    key,
                )
                return items[:_MAX_IDEAS_PER_FETCH]

    logger.warning("Could not extract ideas from TradingView HTML.")
    return []


async def _fetch_ideas(client: httpx.AsyncClient) -> list[dict]:
    """Fetch XAUUSD ideas by scraping the TradingView ideas HTML page."""
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.tradingview.com/",
    }
    if TRADINGVIEW_COOKIE:
        headers["Cookie"] = TRADINGVIEW_COOKIE

    try:
        resp = await client.get(
            _TV_IDEAS_URL,
            headers=headers,
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()

        # Verify we landed on the ideas page (not the chart page)
        if "/ideas" not in str(resp.url):
            logger.warning(
                "TradingView redirected away from ideas page to %s",
                resp.url,
            )
            return []

        return _extract_ideas_from_html(resp.text)

    except httpx.HTTPStatusError as exc:
        logger.warning(
            "TradingView ideas page returned HTTP %s",
            exc.response.status_code,
        )
        return []
    except Exception:
        logger.exception("Error fetching TradingView ideas page")
        return []


def _idea_to_text(idea: dict) -> str:
    """Build a human-readable text blob from a TradingView idea dict."""
    parts: list[str] = []

    title = idea.get("name") or idea.get("title") or ""
    if title:
        parts.append(f"Title: {title}")

    # Author: may be nested under "user" dict or flat "username"
    user = idea.get("user")
    if isinstance(user, dict):
        author = user.get("username", "")
    else:
        author = idea.get("username", "")
    if author:
        parts.append(f"Author: {author}")

    description = idea.get("description") or idea.get("text") or ""
    if description:
        clean = re.sub(r"<[^>]+>", " ", description)
        clean = re.sub(r"\s+", " ", clean).strip()
        parts.append(f"Description: {clean}")

    # Symbol info: may be nested dict or flat string
    symbol_data = idea.get("symbol")
    if isinstance(symbol_data, dict):
        symbol_name = symbol_data.get("short_name") or symbol_data.get("name", _TV_SYMBOL)
        # direction: 1=Long/Bullish, 2=Short/Bearish, 0=Neutral
        direction_code = symbol_data.get("direction")
        if direction_code == 1:
            parts.append(f"Symbol: {symbol_name} (Long/Bullish)")
        elif direction_code == 2:
            parts.append(f"Symbol: {symbol_name} (Short/Bearish)")
        else:
            parts.append(f"Symbol: {symbol_name}")

        interval = symbol_data.get("interval")
        if interval:
            parts.append(f"Timeframe: {interval}")
    else:
        parts.append(f"Symbol: {symbol_data or _TV_SYMBOL}")

    labels = idea.get("labels") or []
    if labels:
        parts.append(f"Labels: {', '.join(str(l) for l in labels)}")

    return "\n".join(parts)


async def _scrape_once() -> int:
    """Run a single scrape cycle and return the number of new posts saved."""
    source = await _get_tradingview_source()
    if source is None:
        logger.warning("No active TradingView source configured — skipping scrape.")
        return 0

    async with httpx.AsyncClient() as client:
        ideas = await _fetch_ideas(client)

    if not ideas:
        logger.info("No ideas returned from TradingView.")
        return 0

    saved = 0
    async with AsyncSessionLocal() as session:
        for idea in ideas:
            # Determine external_id from the idea payload
            external_id = str(
                idea.get("id") or idea.get("idea_id") or idea.get("slug") or ""
            )
            if not external_id:
                continue

            if await is_duplicate(session, source.id, external_id):
                continue

            raw_text = _idea_to_text(idea)
            if not raw_text.strip():
                continue

            # Extract media / image URL if present
            media_urls: list[str] = []
            image_url = idea.get("image_url") or ""
            if not image_url:
                image = idea.get("image")
                if isinstance(image, dict):
                    image_url = image.get("big", "")
            if image_url:
                media_urls.append(image_url)

            # Published timestamp
            published = idea.get("published") or idea.get("date_timestamp")
            posted_at: datetime | None = None
            if published:
                try:
                    if isinstance(published, (int, float)):
                        posted_at = datetime.fromtimestamp(published, tz=timezone.utc)
                    else:
                        posted_at = datetime.fromisoformat(str(published))
                except Exception:
                    posted_at = None

            # TradingView provides the full idea URL in chart_url
            idea_url = idea.get("chart_url") or None

            post = RawPost(
                source_id=source.id,
                raw_text=raw_text,
                media_urls=media_urls if media_urls else None,
                external_id=external_id,
                posted_at=posted_at or datetime.now(timezone.utc),
                url=idea_url,
            )
            session.add(post)
            saved += 1

        if saved:
            await session.commit()

    logger.info("TradingView scrape complete — saved %d new idea(s).", saved)
    return saved


async def run_tradingview_scraper() -> None:
    """Main entry-point.  Runs the scraper on a fixed schedule
    (``TRADINGVIEW_INTERVAL_SECONDS``) until cancelled."""
    logger.info(
        "Starting TradingView scraper — interval %d s",
        TRADINGVIEW_INTERVAL_SECONDS,
    )

    while True:
        try:
            await _scrape_once()
        except Exception:
            logger.exception("TradingView scraper cycle failed")

        await asyncio.sleep(TRADINGVIEW_INTERVAL_SECONDS)
