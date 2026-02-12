"""Unified entry point for analysis background workers.

Schedule
--------
- Yahoo Finance prices:  every 6 hours
- FRED indicators:       every 6 hours
- ETF holdings:          every 6 hours
- COT report:            every Saturday (weekly)
- Correlations:          every 6 hours (after prices)
- Event generator:       every 30 minutes
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("analysis.worker")

# Intervals in seconds
INTERVAL_6H = 6 * 60 * 60
INTERVAL_4H = 4 * 60 * 60
INTERVAL_30M = 30 * 60
INTERVAL_5M = 5 * 60
INTERVAL_1H = 60 * 60


async def _run_worker(name: str, coro_fn, interval: int) -> None:
    """Run a worker function on a fixed interval."""
    while True:
        try:
            logger.info("Running %s ...", name)
            result = await coro_fn()
            logger.info("%s completed: %s", name, result)
        except Exception:
            logger.exception("Error in %s", name)

        await asyncio.sleep(interval)


async def _run_weekly_worker(name: str, coro_fn, day_of_week: int = 5) -> None:
    """Run a worker only on a specific day of the week (0=Mon, 5=Sat)."""
    while True:
        now = datetime.now(timezone.utc)
        if now.weekday() == day_of_week:
            try:
                logger.info("Running %s (weekly) ...", name)
                result = await coro_fn()
                logger.info("%s completed: %s", name, result)
            except Exception:
                logger.exception("Error in %s", name)
            # Sleep until tomorrow to avoid re-running today
            await asyncio.sleep(24 * 60 * 60)
        else:
            # Check again in 6 hours
            await asyncio.sleep(INTERVAL_6H)


async def main() -> None:
    """Start all analysis workers as concurrent tasks."""
    logger.info("Starting analysis worker ...")

    # Import workers
    from api.analysis.workers import (
        yahoo_fetcher,
        fred_fetcher,
        etf_scraper,
        cot_parser,
        correlation_calc,
        event_generator,
    )
    from api.data_collection import sentiment_recorder, candle_builder
    from api.articles.workers.main import run_articles_pipeline

    # Run initial batch immediately
    logger.info("Running initial data fetch ...")
    initial_tasks = [
        yahoo_fetcher.run(),
        fred_fetcher.run(),
        etf_scraper.run(),
        cot_parser.run(),
    ]
    results = await asyncio.gather(*initial_tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            logger.error("Initial fetch error: %s", r)

    # Run correlation after initial price data
    try:
        await correlation_calc.run()
    except Exception:
        logger.exception("Initial correlation calc error")

    # Run event generator after initial data
    try:
        await event_generator.run()
    except Exception:
        logger.exception("Initial event generation error")

    # Run initial articles fetch
    try:
        result = await run_articles_pipeline()
        logger.info("Initial articles pipeline: %s", result)
    except Exception:
        logger.exception("Initial articles pipeline error")

    logger.info("Initial fetch complete. Starting periodic workers ...")

    # Start periodic tasks
    tasks = [
        asyncio.create_task(_run_worker("yahoo_fetcher", yahoo_fetcher.run, INTERVAL_6H)),
        asyncio.create_task(_run_worker("fred_fetcher", fred_fetcher.run, INTERVAL_6H)),
        asyncio.create_task(_run_worker("etf_scraper", etf_scraper.run, INTERVAL_6H)),
        asyncio.create_task(_run_weekly_worker("cot_parser", cot_parser.run, day_of_week=5)),
        asyncio.create_task(_run_worker("correlation_calc", correlation_calc.run, INTERVAL_6H)),
        asyncio.create_task(_run_worker("event_generator", event_generator.run, INTERVAL_30M)),
        asyncio.create_task(_run_worker("sentiment_recorder", sentiment_recorder.run, INTERVAL_5M)),
        asyncio.create_task(_run_worker("candle_builder_5min", candle_builder.build_5min_candles, INTERVAL_5M)),
        asyncio.create_task(_run_worker("daily_candle_sync", candle_builder.sync_daily_candles, INTERVAL_6H)),
        asyncio.create_task(_run_worker("articles_pipeline", run_articles_pipeline, INTERVAL_4H)),
    ]

    logger.info("Analysis worker running with %d periodic tasks.", len(tasks))
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Analysis worker stopped.")
        sys.exit(0)
