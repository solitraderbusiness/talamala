"""Seed initial signal sources into the signal_sources table.

Usage:
    python -m api.signal_aggregator.scripts.setup_sources

Inserts Telegram channels and TradingView sources used by the Signal
Aggregator.  Each source is checked by name before insertion so the script
is safe to run multiple times (idempotent).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select

from api.database import AsyncSessionLocal
from api.signal_aggregator.models import SignalSource

logger = logging.getLogger(__name__)

# ── Source definitions ───────────────────────────────────────────────────

TELEGRAM_SOURCES: list[dict[str, Any]] = [
    # ── Verified public channels with XAUUSD BUY/SELL signals ──
    {
        "name": "Gold Signals",
        "type": "telegram",
        "telegram_channel_name": "@gold_signals",
        "notes": "Structured signals with entry/SL/TP, weekly performance",
    },
    {
        "name": "Sure Gold Signals",
        "type": "telegram",
        "telegram_channel_name": "@suregoldsignais",
        "notes": "Excellent format: entry zones, 10-level TPs, very active",
    },
    {
        "name": "Gold Signal Free",
        "type": "telegram",
        "telegram_channel_name": "@GoldSignalFree",
        "notes": "Clean dual-TP format, active daily, pure gold focus",
    },
    {
        "name": "XAUUSD Gold Signals",
        "type": "telegram",
        "telegram_channel_name": "@XAUUSDGOLDsignals",
        "notes": "BUY/SELL with entry/SL/TP, weekly pip summaries",
    },
    {
        "name": "Anabel Signals",
        "type": "telegram",
        "telegram_channel_name": "@AnabelSignals",
        "notes": "Structured with timeframe info, pivot-based signals",
    },
    {
        "name": "Forex Gold Room",
        "type": "telegram",
        "telegram_channel_name": "@ForexGoldRoom",
        "notes": "Entry zones with SL/TP, copier results",
    },
    {
        "name": "Gold Signal Trading",
        "type": "telegram",
        "telegram_channel_name": "@gold_signal_trading",
        "notes": "Active with running updates, #GOLD #SELL/#BUY format",
    },
    {
        "name": "Gold Trading Room",
        "type": "telegram",
        "telegram_channel_name": "@gold_trading_room",
        "notes": "Multi-level TP signals, active daily",
    },
    {
        "name": "Vasily Trading",
        "type": "telegram",
        "telegram_channel_name": "@VasilyTrading",
        "notes": "XAUUSD analysis, support/resistance zones, directional forecasts",
    },
]

TRADINGVIEW_SOURCES: list[dict[str, Any]] = [
    {
        "name": "TradingView XAUUSD Ideas",
        "type": "tradingview",
        "url": "https://www.tradingview.com/symbols/XAUUSD/ideas/",
        "notes": "Community ideas",
    },
]

ALL_SOURCES: list[dict[str, Any]] = TELEGRAM_SOURCES + TRADINGVIEW_SOURCES


# ── Telegram channel verification (optional) ────────────────────────────

async def verify_telegram_channels(
    channel_usernames: list[str],
) -> dict[str, bool]:
    """Try to verify that the listed Telegram channels exist.

    Uses the Telethon library if it is installed and Telegram API
    credentials are configured.  Returns a mapping of channel username to
    a boolean indicating whether the channel was reachable.

    If Telethon is unavailable or credentials are missing the function
    logs a warning and returns an empty dict (verification is skipped).
    """
    results: dict[str, bool] = {}

    try:
        from telethon import TelegramClient  # type: ignore[import-untyped]
        from api.signal_aggregator.config import (
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH,
            TELEGRAM_SESSION_PATH,
        )
    except ImportError:
        logger.warning(
            "Telethon is not installed -- skipping Telegram channel "
            "verification.  Install with: pip install telethon"
        )
        return results

    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        logger.warning(
            "TELEGRAM_API_ID / TELEGRAM_API_HASH not set -- skipping "
            "Telegram channel verification."
        )
        return results

    client = TelegramClient(
        TELEGRAM_SESSION_PATH,
        int(TELEGRAM_API_ID),
        TELEGRAM_API_HASH,
    )

    try:
        await client.start()
        for username in channel_usernames:
            try:
                entity = await client.get_entity(username)
                results[username] = True
                logger.info(
                    "Verified channel %s (id=%s, title=%s)",
                    username,
                    entity.id,
                    getattr(entity, "title", "N/A"),
                )
            except Exception as exc:
                results[username] = False
                logger.warning(
                    "Could not verify channel %s: %s", username, exc,
                )
    except Exception as exc:
        logger.warning(
            "Failed to connect to Telegram for verification: %s", exc,
        )
    finally:
        await client.disconnect()

    return results


# ── Seeder ───────────────────────────────────────────────────────────────

async def seed_sources(*, verify: bool = False) -> None:
    """Insert seed sources into *signal_sources* if they do not yet exist.

    Parameters
    ----------
    verify:
        When ``True``, attempt to verify Telegram channels before
        inserting (requires Telethon + API credentials).
    """
    # Optional verification step
    if verify:
        telegram_usernames = [
            src["telegram_channel_name"]
            for src in TELEGRAM_SOURCES
        ]
        verification = await verify_telegram_channels(telegram_usernames)
        if verification:
            unreachable = [u for u, ok in verification.items() if not ok]
            if unreachable:
                logger.warning(
                    "The following channels could not be verified and will "
                    "still be inserted: %s",
                    ", ".join(unreachable),
                )
        else:
            logger.info("Channel verification was skipped.")

    added = 0
    skipped = 0

    async with AsyncSessionLocal() as session:
        for src_def in ALL_SOURCES:
            name = src_def["name"]

            # Check whether this source already exists
            stmt = select(SignalSource).where(SignalSource.name == name)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing is not None:
                logger.info("SKIP  (already exists): %s", name)
                skipped += 1
                continue

            # Build the model instance from the definition dict.
            # Only pass keys that are actual column names on SignalSource;
            # 'notes' is not a column -- we drop it here.
            model_kwargs: dict[str, Any] = {
                k: v for k, v in src_def.items() if k != "notes"
            }
            source = SignalSource(**model_kwargs)

            session.add(source)
            logger.info("ADD   %s (%s)", name, src_def["type"])
            added += 1

        try:
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Failed to commit seed sources.")
            raise

    logger.info(
        "Seeding complete: %d added, %d skipped, %d total defined.",
        added,
        skipped,
        len(ALL_SOURCES),
    )


# ── Entry point ──────────────────────────────────────────────────────────

async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Starting signal source seeder...")

    try:
        await seed_sources(verify=False)
    except Exception:
        logger.exception("Signal source seeding failed.")
        raise

    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
