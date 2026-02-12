"""AI-powered signal parser for the Signal Aggregator.

Picks up unparsed ``RawPost`` rows, sends them to the OpenRouter API for
structured extraction, and writes the results into ``ParsedSignal``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import and_, select, update

from api.database import AsyncSessionLocal
from api.signal_aggregator.config import (
    DEFAULT_VALID_HOURS,
    OPENROUTER_API_KEY,
    PARSE_BATCH_SIZE,
    PARSE_INTERVAL_SECONDS,
    PRICE_SANITY_MAX_DEVIATION,
    SIGNAL_PARSE_MODEL,
    SIGNAL_PARSER_SYSTEM_PROMPT,
)
from api.signal_aggregator.models import ParsedSignal, RawPost, SignalSource

logger = logging.getLogger("signal_aggregator.parser")

_MAX_PARSE_ATTEMPTS = 3
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


async def _fetch_unparsed(limit: int = PARSE_BATCH_SIZE) -> list[RawPost]:
    """Return up to ``limit`` unparsed raw posts with fewer than
    ``_MAX_PARSE_ATTEMPTS`` attempts."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(RawPost)
            .where(
                RawPost.parsed.is_(False),
                RawPost.parse_attempts < _MAX_PARSE_ATTEMPTS,
            )
            .order_by(RawPost.captured_at.asc())
            .limit(limit)
        )
        posts = result.scalars().all()
        # Eagerly detach so we can use them outside the session
        for p in posts:
            await session.refresh(p)
        return list(posts)


async def _call_openrouter(client: httpx.AsyncClient, raw_text: str) -> dict | None:
    """Send the raw text to OpenRouter and return the parsed JSON dict,
    or ``None`` on any failure."""
    try:
        response = await client.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://gold-monitor.local",
                "X-Title": "Gold Monitor Signal Parser",
            },
            json={
                "model": SIGNAL_PARSE_MODEL,
                "messages": [
                    {"role": "system", "content": SIGNAL_PARSER_SYSTEM_PROMPT},
                    {"role": "user", "content": raw_text},
                ],
                "temperature": 0.1,
                "max_tokens": 1024,
            },
        )

        if response.status_code != 200:
            logger.error(
                "OpenRouter API returned HTTP %d: %s",
                response.status_code,
                response.text[:500],
            )
            return None

        data = response.json()

        # Extract the assistant message content
        try:
            response_text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            logger.error(
                "OpenRouter response has unexpected structure: %s",
                json.dumps(data)[:500],
            )
            return None

        if not response_text or not response_text.strip():
            logger.warning("OpenRouter returned empty response")
            return None

        # OpenRouter/Claude may wrap JSON in markdown code fences — strip them
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (```json or ```)
            first_newline = cleaned.index("\n")
            cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[: -3]
        cleaned = cleaned.strip()

        parsed = json.loads(cleaned)
        return parsed

    except json.JSONDecodeError:
        logger.warning("OpenRouter response was not valid JSON: %s", response_text[:200])
        return None
    except httpx.TimeoutException:
        logger.error("OpenRouter API call timed out")
        return None
    except httpx.RequestError as exc:
        logger.error("OpenRouter API request failed: %s", exc)
        return None
    except Exception:
        logger.exception("Unexpected error calling OpenRouter API")
        return None


async def _increment_attempts(post_id) -> None:
    """Increment ``parse_attempts`` for a raw post."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(RawPost)
            .where(RawPost.id == post_id)
            .values(parse_attempts=RawPost.parse_attempts + 1)
        )
        await session.commit()


async def _mark_parsed(post_id) -> None:
    """Mark a raw post as parsed."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(RawPost)
            .where(RawPost.id == post_id)
            .values(parsed=True)
        )
        await session.commit()


async def _is_duplicate_signal(
    source_id, direction: str, entry_price: float | None, stop_loss: float | None,
) -> bool:
    """Check if a signal with the same source/direction/entry/SL already
    exists and is still active (not expired/closed)."""
    if entry_price is None:
        return False

    async with AsyncSessionLocal() as session:
        filters = [
            ParsedSignal.source_id == source_id,
            ParsedSignal.direction == direction,
            ParsedSignal.entry_price == entry_price,
            ParsedSignal.status == "active",
        ]
        if stop_loss is not None:
            filters.append(ParsedSignal.stop_loss == stop_loss)

        result = await session.execute(
            select(ParsedSignal.id).where(and_(*filters)).limit(1)
        )
        return result.scalar_one_or_none() is not None


async def _get_reference_price() -> float | None:
    """Return the latest known XAUUSD price for sanity checking.

    Tries: (1) latest price tick in DB, (2) live fetch via price_checker.
    """
    from api.signal_aggregator.models import SignalPriceTick

    # Try latest price tick from DB first (fast, no external call)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SignalPriceTick.price)
            .where(SignalPriceTick.asset == "XAUUSD")
            .order_by(SignalPriceTick.checked_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return float(row)

    # No ticks yet — try a live fetch
    try:
        from api.signal_aggregator.workers.price_checker import fetch_current_price
        price, _ = await fetch_current_price()
        return price
    except Exception:
        logger.debug("Could not fetch live price for sanity check")
        return None


def _price_is_sane(entry_price: float | None, reference_price: float) -> bool:
    """Return True if entry_price is within the allowed deviation from
    the reference price."""
    if entry_price is None:
        return True  # no price to validate
    deviation = abs(entry_price - reference_price) / reference_price
    return deviation <= PRICE_SANITY_MAX_DEVIATION


async def _save_signal(post: RawPost, data: dict) -> None:
    """Insert a ``ParsedSignal`` from the Claude-parsed data and mark
    the post as parsed."""
    direction = data.get("direction", "BUY")
    timeframe = data.get("timeframe", "1h")
    entry_price = data.get("entry_price")
    stop_loss = data.get("stop_loss")
    valid_hours = data.get("valid_hours") or DEFAULT_VALID_HOURS.get(timeframe, 12)

    # Fall back to current market price when analyst didn't specify an entry
    if entry_price is None:
        entry_price = await _get_reference_price()

    # Price sanity check — reject signals with unreasonable prices
    # Check entry, TP, and SL against the reference price to catch
    # non-XAUUSD signals (e.g. GBPAUD with TP=1.92 slipping through)
    ref_price = await _get_reference_price()
    if ref_price is not None:
        prices_to_check = [
            ("entry", entry_price),
            ("stop_loss", stop_loss),
            ("take_profit_1", data.get("take_profit_1")),
        ]
        for label, price in prices_to_check:
            if not _price_is_sane(price, ref_price):
                await _mark_parsed(post.id)
                logger.warning(
                    "Signal %s=%.2f too far from market (%.2f, deviation %.1f%%) "
                    "— post %s rejected (likely non-XAUUSD).",
                    label, price, ref_price,
                    abs(price - ref_price) / ref_price * 100,
                    post.id,
                )
                return

    # Skip if an identical active signal already exists from this source
    if await _is_duplicate_signal(post.source_id, direction, entry_price, stop_loss):
        await _mark_parsed(post.id)
        logger.info(
            "Duplicate signal %s entry=%s from post %s — skipped.",
            direction, entry_price, post.id,
        )
        return

    valid_until = datetime.now(timezone.utc) + timedelta(hours=valid_hours)

    signal = ParsedSignal(
        raw_post_id=post.id,
        source_id=post.source_id,
        asset="XAUUSD",
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit_1=data.get("take_profit_1"),
        take_profit_2=data.get("take_profit_2"),
        take_profit_3=data.get("take_profit_3"),
        timeframe=timeframe,
        timeframe_confidence=data.get("timeframe_confidence", "inferred"),
        analysis_type=data.get("analysis_type", "mixed"),
        confidence_raw=data.get("confidence", 5),
        key_reasons=data.get("key_reasons"),
        valid_until=valid_until,
    )

    async with AsyncSessionLocal() as session:
        session.add(signal)
        await session.commit()

    # Update source last_signal_at
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(SignalSource)
            .where(SignalSource.id == post.source_id)
            .values(
                last_signal_at=datetime.now(timezone.utc),
                total_signals=SignalSource.total_signals + 1,
            )
        )
        await session.commit()

    await _mark_parsed(post.id)
    logger.info(
        "Saved parsed signal: %s %s (tf=%s, entry=%s) from post %s",
        direction,
        "XAUUSD",
        timeframe,
        data.get("entry_price"),
        post.id,
    )


async def _process_batch() -> int:
    """Process one batch of unparsed posts.  Returns the number
    successfully parsed."""
    posts = await _fetch_unparsed()
    if not posts:
        logger.debug("No unparsed posts to process.")
        return 0

    processed = 0

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        for post in posts:
            try:
                data = await _call_openrouter(client, post.raw_text)

                if data is None:
                    await _increment_attempts(post.id)
                    continue

                has_signal = data.get("has_signal", False)
                if not has_signal:
                    # Post is not a signal — mark as parsed but don't create
                    # a ParsedSignal row.
                    await _mark_parsed(post.id)
                    logger.info("Post %s has no signal — marked parsed.", post.id)
                    processed += 1
                    continue

                await _save_signal(post, data)
                processed += 1

            except Exception:
                logger.exception("Error processing post %s", post.id)
                await _increment_attempts(post.id)

    return processed


async def run_signal_parser() -> None:
    """Main entry-point.  Runs the parser on a fixed schedule
    (``PARSE_INTERVAL_SECONDS``) until cancelled."""
    if not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY is not set — aborting signal parser.")
        return

    logger.info(
        "Starting signal parser — interval %d s, batch size %d, model %s",
        PARSE_INTERVAL_SECONDS,
        PARSE_BATCH_SIZE,
        SIGNAL_PARSE_MODEL,
    )

    while True:
        try:
            count = await _process_batch()
            if count:
                logger.info("Parsed %d post(s) this cycle.", count)
        except Exception:
            logger.exception("Signal parser cycle failed")

        await asyncio.sleep(PARSE_INTERVAL_SECONDS)
