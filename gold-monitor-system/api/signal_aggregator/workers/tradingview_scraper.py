"""TradingView XAUUSD ideas scraper for the Signal Aggregator.

Periodically fetches XAUUSD trading ideas from TradingView's public API
endpoint and saves new ones as ``RawPost`` rows for subsequent parsing.
"""

from __future__ import annotations

import asyncio
import logging
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

# TradingView public ideas API for XAUUSD
_TV_IDEAS_URL = "https://www.tradingview.com/ideas/xauusd/"
_TV_API_URL = (
    "https://www.tradingview.com/pubapi/v1/ideas/search"
)
_TV_SYMBOL = "XAUUSD"
_REQUEST_TIMEOUT = 30.0
_MAX_IDEAS_PER_FETCH = 50


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


async def _fetch_ideas(client: httpx.AsyncClient) -> list[dict]:
    """Fetch XAUUSD ideas from TradingView's public API."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Referer": "https://www.tradingview.com/ideas/xauusd/",
    }
    if TRADINGVIEW_COOKIE:
        headers["Cookie"] = TRADINGVIEW_COOKIE

    params = {
        "filter": "recent",
        "category": "",
        "symbol": _TV_SYMBOL,
        "sort": "recent_first",
        "page_size": str(_MAX_IDEAS_PER_FETCH),
        "locale": "en",
    }

    try:
        resp = await client.get(
            _TV_API_URL,
            headers=headers,
            params=params,
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        # The API may return results under "results" or at the top level
        if isinstance(data, dict) and "results" in data:
            return data["results"]
        if isinstance(data, list):
            return data

        logger.warning("Unexpected TradingView API response shape: %s", type(data))
        return []

    except httpx.HTTPStatusError as exc:
        logger.warning(
            "TradingView API returned HTTP %s — falling back to HTML scrape",
            exc.response.status_code,
        )
        return await _fetch_ideas_html_fallback(client, headers)
    except Exception:
        logger.exception("Error fetching TradingView ideas from API")
        return []


async def _fetch_ideas_html_fallback(
    client: httpx.AsyncClient, headers: dict
) -> list[dict]:
    """Fallback: scrape the TradingView ideas HTML page and extract ideas
    from the embedded ``__NEXT_DATA__`` JSON or ``<script>`` blocks."""
    import json
    import re

    try:
        resp = await client.get(
            _TV_IDEAS_URL,
            headers=headers,
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()
        html = resp.text

        # Attempt 1: __NEXT_DATA__ JSON blob
        match = re.search(
            r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        if match:
            try:
                next_data = json.loads(match.group(1))
                # Navigate into the typical Next.js structure
                props = next_data.get("props", {}).get("pageProps", {})
                ideas = props.get("ideas", props.get("data", []))
                if isinstance(ideas, list) and ideas:
                    return ideas
            except json.JSONDecodeError:
                logger.debug("Failed to parse __NEXT_DATA__ JSON")

        # Attempt 2: look for inline JSON array of ideas
        idea_pattern = re.findall(
            r'"id"\s*:\s*"(\w+)".*?"name"\s*:\s*"(.*?)".*?"description"\s*:\s*"(.*?)"',
            html,
        )
        ideas_from_html: list[dict] = []
        for idea_id, name, description in idea_pattern:
            ideas_from_html.append(
                {
                    "id": idea_id,
                    "name": name,
                    "description": description,
                }
            )
        if ideas_from_html:
            return ideas_from_html[:_MAX_IDEAS_PER_FETCH]

        logger.warning("HTML fallback could not extract any ideas")
        return []

    except Exception:
        logger.exception("Error in TradingView HTML fallback scrape")
        return []


def _idea_to_text(idea: dict) -> str:
    """Build a human-readable text blob from a TradingView idea dict."""
    parts: list[str] = []

    title = idea.get("name") or idea.get("title") or ""
    if title:
        parts.append(f"Title: {title}")

    author = idea.get("username") or idea.get("author", {}).get("username", "")
    if author:
        parts.append(f"Author: {author}")

    description = idea.get("description") or idea.get("text") or ""
    if description:
        # TradingView descriptions can be HTML-like; strip basic tags
        import re

        clean = re.sub(r"<[^>]+>", " ", description)
        clean = re.sub(r"\s+", " ", clean).strip()
        parts.append(f"Description: {clean}")

    symbol = idea.get("symbol") or _TV_SYMBOL
    parts.append(f"Symbol: {symbol}")

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
            image_url = idea.get("image_url") or idea.get("image", {}).get("big", "")
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

            post = RawPost(
                source_id=source.id,
                raw_text=raw_text,
                media_urls=media_urls if media_urls else None,
                external_id=external_id,
                posted_at=posted_at or datetime.now(timezone.utc),
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
