"""AI-powered signal parser for the Signal Aggregator.

Picks up unparsed ``RawPost`` rows, sends them to the Claude API for
structured extraction, and writes the results into ``ParsedSignal``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import anthropic
from sqlalchemy import select, update

from api.database import AsyncSessionLocal
from api.signal_aggregator.config import (
    ANTHROPIC_API_KEY,
    DEFAULT_VALID_HOURS,
    PARSE_BATCH_SIZE,
    PARSE_INTERVAL_SECONDS,
    SIGNAL_PARSE_MODEL,
    SIGNAL_PARSER_SYSTEM_PROMPT,
)
from api.signal_aggregator.models import ParsedSignal, RawPost, SignalSource

logger = logging.getLogger("signal_aggregator.parser")

_MAX_PARSE_ATTEMPTS = 3


def _build_client() -> anthropic.AsyncAnthropic:
    """Create an Anthropic async client."""
    return anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)


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


async def _call_claude(client: anthropic.AsyncAnthropic, raw_text: str) -> dict | None:
    """Send the raw text to Claude and return the parsed JSON dict,
    or ``None`` on any failure."""
    try:
        message = await client.messages.create(
            model=SIGNAL_PARSE_MODEL,
            max_tokens=1024,
            system=SIGNAL_PARSER_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": raw_text,
                }
            ],
        )

        # Extract the text content from the response
        response_text = ""
        for block in message.content:
            if hasattr(block, "text"):
                response_text += block.text

        if not response_text.strip():
            logger.warning("Claude returned empty response")
            return None

        # Claude may wrap JSON in markdown code fences — strip them
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
        logger.warning("Claude response was not valid JSON: %s", response_text[:200])
        return None
    except anthropic.APIError as exc:
        logger.error("Anthropic API error: %s", exc)
        return None
    except Exception:
        logger.exception("Unexpected error calling Claude API")
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


async def _save_signal(post: RawPost, data: dict) -> None:
    """Insert a ``ParsedSignal`` from the Claude-parsed data and mark
    the post as parsed."""
    direction = data.get("direction", "BUY")
    timeframe = data.get("timeframe", "1h")
    valid_hours = data.get("valid_hours") or DEFAULT_VALID_HOURS.get(timeframe, 12)

    valid_until = datetime.now(timezone.utc) + timedelta(hours=valid_hours)

    signal = ParsedSignal(
        raw_post_id=post.id,
        source_id=post.source_id,
        asset="XAUUSD",
        direction=direction,
        entry_price=data.get("entry_price"),
        stop_loss=data.get("stop_loss"),
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

    client = _build_client()
    processed = 0

    for post in posts:
        try:
            data = await _call_claude(client, post.raw_text)

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
    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY is not set — aborting signal parser.")
        return

    logger.info(
        "Starting signal parser — interval %d s, batch size %d",
        PARSE_INTERVAL_SECONDS,
        PARSE_BATCH_SIZE,
    )

    while True:
        try:
            count = await _process_batch()
            if count:
                logger.info("Parsed %d post(s) this cycle.", count)
        except Exception:
            logger.exception("Signal parser cycle failed")

        await asyncio.sleep(PARSE_INTERVAL_SECONDS)
