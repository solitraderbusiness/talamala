"""Signal Aggregator — unified worker entry point.

Runs all background workers in a single process:
- TradingView scraper (every 30 min)
- Signal parser (every 2 min)
- Price checker + outcome tracker (every 5 min)
- Consensus builder (every 15 min)
- Daily performance aggregator (at 22:00 UTC)
- Telegram listener (persistent connection)

Usage:
    python -m api.signal_aggregator.workers.main
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("signal_aggregator")

# Ensure the parent package is importable when run as __main__
if __name__ == "__main__":
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from api.signal_aggregator.config import (
    CONSENSUS_INTERVAL_SECONDS,
    DAILY_PERF_HOUR_UTC,
    PARSE_INTERVAL_SECONDS,
    PRICE_CHECK_INTERVAL_SECONDS,
    TELEGRAM_API_ID,
    TRADINGVIEW_INTERVAL_SECONDS,
)

_shutdown = asyncio.Event()


def _handle_signal(sig: int, _frame: object) -> None:
    logger.info("Received signal %s — shutting down ...", sig)
    _shutdown.set()


async def _run_periodic(name: str, coro_fn, interval: int) -> None:
    """Run a coroutine function periodically until shutdown."""
    while not _shutdown.is_set():
        try:
            logger.info("Running %s ...", name)
            await coro_fn()
            logger.info("%s completed.", name)
        except Exception:
            logger.exception("%s failed.", name)
        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=interval)
            break  # shutdown signalled
        except asyncio.TimeoutError:
            pass  # interval elapsed, loop again


async def _run_daily_at_hour(name: str, coro_fn, hour_utc: int) -> None:
    """Run a coroutine once per day at a specific UTC hour."""
    while not _shutdown.is_set():
        now = datetime.now(timezone.utc)
        next_run = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
        if now >= next_run:
            # Already past the target hour today, schedule for tomorrow
            next_run = next_run.replace(day=now.day + 1)
        wait_seconds = (next_run - now).total_seconds()
        logger.info("%s scheduled in %.0f seconds (at %02d:00 UTC).", name, wait_seconds, hour_utc)
        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=wait_seconds)
            break
        except asyncio.TimeoutError:
            pass
        try:
            logger.info("Running %s ...", name)
            await coro_fn()
            logger.info("%s completed.", name)
        except Exception:
            logger.exception("%s failed.", name)


async def _create_tables() -> None:
    """Ensure signal aggregator tables exist."""
    from api.database import sync_engine
    from api.signal_aggregator.models import (
        ConsensusSnapshot,
        DailyPerformance,
        MonthlyPerformance,
        ParsedSignal,
        RawPost,
        SignalPriceTick,
        SignalSource,
    )
    for model in [SignalSource, RawPost, ParsedSignal, ConsensusSnapshot,
                  SignalPriceTick, DailyPerformance, MonthlyPerformance]:
        try:
            model.__table__.create(bind=sync_engine, checkfirst=True)
        except Exception:
            logger.warning("Could not create table %s", model.__tablename__, exc_info=True)
    logger.info("Signal aggregator tables ensured.")


async def _seed_sources() -> None:
    """Seed initial signal sources if table is empty."""
    from sqlalchemy import select
    from api.database import AsyncSessionLocal
    from api.signal_aggregator.models import SignalSource

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(SignalSource).limit(1))
        if result.scalar_one_or_none() is not None:
            logger.info("Signal sources already exist — skipping seed.")
            return

        sources = [
            SignalSource(
                name="SureShotFX Gold", type="telegram",
                telegram_channel_name="@SureShotFXGold",
                active=True, current_weight=0.5,
            ),
            SignalSource(
                name="UnitedSignals", type="telegram",
                telegram_channel_name="@UnitedSignals",
                active=True, current_weight=0.5,
            ),
            SignalSource(
                name="GoldSignalsDaily", type="telegram",
                telegram_channel_name="@GoldSignalsDaily",
                active=True, current_weight=0.5,
            ),
            SignalSource(
                name="FXPremiere", type="telegram",
                telegram_channel_name="@FXPremiere",
                active=True, current_weight=0.5,
            ),
            SignalSource(
                name="XAUUSD Gold Signals", type="telegram",
                telegram_channel_name="@XAUUSDGOLDsignals",
                active=True, current_weight=0.5,
            ),
            SignalSource(
                name="AltSignals", type="telegram",
                telegram_channel_name="@AltSignals",
                active=True, current_weight=0.5,
            ),
            SignalSource(
                name="TradingView XAUUSD Ideas", type="tradingview",
                url="https://www.tradingview.com/symbols/XAUUSD/ideas/",
                active=True, current_weight=0.5,
            ),
        ]
        for src in sources:
            session.add(src)
        await session.commit()
        logger.info("Seeded %d signal sources.", len(sources))


async def main() -> None:
    logger.info("Signal Aggregator worker starting ...")

    # Ensure tables and seed data
    await _create_tables()
    await _seed_sources()

    tasks: list[asyncio.Task] = []

    # Import worker functions
    from api.signal_aggregator.workers.tradingview_scraper import run_tradingview_scraper
    from api.signal_aggregator.workers.signal_parser import run_signal_parser
    from api.signal_aggregator.workers.price_checker import run_price_checker
    from api.signal_aggregator.workers.consensus_builder import generate_all_consensus
    from api.signal_aggregator.workers.performance_tracker import aggregate_daily

    # Periodic workers
    tasks.append(asyncio.create_task(
        _run_periodic("TradingView Scraper", run_tradingview_scraper, TRADINGVIEW_INTERVAL_SECONDS),
    ))
    tasks.append(asyncio.create_task(
        _run_periodic("Signal Parser", run_signal_parser, PARSE_INTERVAL_SECONDS),
    ))
    tasks.append(asyncio.create_task(
        _run_periodic("Price Checker", run_price_checker, PRICE_CHECK_INTERVAL_SECONDS),
    ))
    tasks.append(asyncio.create_task(
        _run_periodic("Consensus Builder", generate_all_consensus, CONSENSUS_INTERVAL_SECONDS),
    ))

    # Daily aggregation at 22:00 UTC
    tasks.append(asyncio.create_task(
        _run_daily_at_hour("Daily Performance", aggregate_daily, DAILY_PERF_HOUR_UTC),
    ))

    # Telegram listener (persistent — only if credentials are configured)
    if TELEGRAM_API_ID:
        try:
            from api.signal_aggregator.workers.telegram_listener import run_telegram_listener
            tasks.append(asyncio.create_task(run_telegram_listener()))
            logger.info("Telegram listener started.")
        except Exception:
            logger.warning("Telegram listener could not start.", exc_info=True)
    else:
        logger.info("Telegram not configured — skipping listener.")

    logger.info("All signal aggregator workers running. Waiting for shutdown ...")
    await _shutdown.wait()

    # Cancel all tasks
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Signal Aggregator worker stopped.")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    asyncio.run(main())
