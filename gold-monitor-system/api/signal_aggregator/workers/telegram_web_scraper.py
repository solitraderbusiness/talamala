"""Web-based Telegram channel scraper for the Signal Aggregator.

Scrapes public Telegram channels via their web preview at
``https://t.me/s/<channel_name>`` — no API credentials required.

This runs alongside (or instead of) the Telethon-based listener,
covering channels whose web preview is publicly accessible.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from api.database import AsyncSessionLocal
from api.signal_aggregator.models import RawPost, SignalSource
from api.signal_aggregator.utils.deduplication import is_duplicate

logger = logging.getLogger("signal_aggregator.telegram_web")

_REQUEST_TIMEOUT = 30.0
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
# Only accept messages posted within the last N hours
_MAX_AGE_HOURS = 6


def _content_hash(text: str) -> str:
    """Return a short hash of normalised text for content-based dedup."""
    # Strip whitespace/emoji variation, lowercase, collapse spaces
    normalised = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalised.encode()).hexdigest()[:16]


async def _get_active_telegram_sources() -> list[SignalSource]:
    """Return all active Telegram sources that have a channel name."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SignalSource).where(
                SignalSource.type == "telegram",
                SignalSource.active.is_(True),
                SignalSource.telegram_channel_name.is_not(None),
            )
        )
        sources = result.scalars().all()
        for s in sources:
            await session.refresh(s)
        return list(sources)


async def _get_recent_content_hashes(source_id, since: datetime) -> set[str]:
    """Return content hashes of recent raw posts for a source."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(RawPost.raw_text)
            .where(
                RawPost.source_id == source_id,
                RawPost.posted_at >= since,
            )
        )
        return {_content_hash(row[0]) for row in result.all()}


def _parse_channel_messages(html: str) -> list[dict]:
    """Parse messages from Telegram's web preview HTML.

    Returns a list of dicts with keys: external_id, text, posted_at.
    """
    soup = BeautifulSoup(html, "lxml")
    messages: list[dict] = []

    for widget in soup.select(".tgme_widget_message"):
        # External ID from data-post attribute (format: "channel/123")
        data_post = widget.get("data-post", "")
        if "/" in data_post:
            external_id = data_post.split("/")[-1]
        else:
            continue

        # Message text
        text_div = widget.select_one(".tgme_widget_message_text")
        if not text_div:
            continue

        text = text_div.get_text(separator="\n").strip()
        if not text:
            continue

        # Timestamp
        time_tag = widget.select_one("time[datetime]")
        posted_at = None
        if time_tag and time_tag.get("datetime"):
            try:
                posted_at = datetime.fromisoformat(
                    time_tag["datetime"].replace("+00:00", "+00:00")
                )
                if posted_at.tzinfo is None:
                    posted_at = posted_at.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                posted_at = None

        messages.append({
            "external_id": external_id,
            "text": text,
            "posted_at": posted_at,
        })

    return messages


async def _scrape_channel(
    client: httpx.AsyncClient,
    source: SignalSource,
) -> int:
    """Scrape a single Telegram channel via web preview.

    Returns the number of new posts saved.
    """
    channel_name = (source.telegram_channel_name or "").lstrip("@").strip()
    if not channel_name:
        return 0

    url = f"https://t.me/s/{channel_name}"

    try:
        resp = await client.get(
            url,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "text/html",
            },
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Telegram web for %s returned HTTP %s — skipping",
            channel_name,
            exc.response.status_code,
        )
        return 0
    except Exception:
        logger.exception("Error fetching Telegram web for %s", channel_name)
        return 0

    html = resp.text

    # Check if this is actually a channel preview (has messages)
    # vs a "Send Message" redirect page (private channel / bot)
    if "tgme_widget_message" not in html:
        logger.debug(
            "Channel %s has no web preview (possibly private) — skipping",
            channel_name,
        )
        return 0

    messages = _parse_channel_messages(html)
    if not messages:
        logger.debug("No messages parsed from %s web preview.", channel_name)
        return 0

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=_MAX_AGE_HOURS)

    # Content-based dedup: load hashes of recent posts for this source
    existing_hashes = await _get_recent_content_hashes(source.id, cutoff)

    saved = 0
    skipped_old = 0
    skipped_dup = 0

    async with AsyncSessionLocal() as session:
        for msg in messages:
            # Skip old messages
            posted_at = msg.get("posted_at")
            if posted_at and posted_at < cutoff:
                skipped_old += 1
                continue

            ext_id = f"web_{msg['external_id']}"

            # ID-based dedup
            if await is_duplicate(session, source.id, ext_id):
                continue

            # Content-based dedup
            c_hash = _content_hash(msg["text"])
            if c_hash in existing_hashes:
                skipped_dup += 1
                continue
            existing_hashes.add(c_hash)

            post = RawPost(
                source_id=source.id,
                raw_text=msg["text"],
                external_id=ext_id,
                posted_at=posted_at or now,
            )
            session.add(post)
            saved += 1

        if saved:
            await session.commit()

    if saved or skipped_old or skipped_dup:
        logger.info(
            "@%s: saved %d, skipped %d old, skipped %d duplicate content",
            channel_name,
            saved,
            skipped_old,
            skipped_dup,
        )
    return saved


async def run_telegram_web_scraper() -> None:
    """Scrape all active Telegram channels via web preview once."""
    sources = await _get_active_telegram_sources()
    if not sources:
        logger.debug("No active Telegram sources — skipping web scrape.")
        return

    total_saved = 0
    async with httpx.AsyncClient() as client:
        for source in sources:
            try:
                saved = await _scrape_channel(client, source)
                total_saved += saved
            except Exception:
                logger.exception(
                    "Error scraping channel %s", source.telegram_channel_name
                )
            # Small delay between channels to be polite
            await asyncio.sleep(2)

    if total_saved:
        logger.info(
            "Telegram web scrape complete — %d new message(s) total.", total_saved
        )
