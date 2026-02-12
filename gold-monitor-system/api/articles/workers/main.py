"""Standalone entry point for the articles background worker.

Can be run directly with ``python -m api.articles.workers.main`` or
integrated into the analysis worker main loop.

Schedule
--------
- Article fetcher:  every 4 hours
- Article scorer:   every 4 hours (after fetcher)
"""

from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("articles.worker")

INTERVAL_4H = 4 * 60 * 60


async def run_articles_pipeline() -> str:
    """Run the full articles pipeline: fetch then score."""
    from api.articles.workers import fetcher, scorer

    fetch_result = await fetcher.run()
    logger.info("Fetcher: %s", fetch_result)

    score_result = await scorer.run()
    logger.info("Scorer: %s", score_result)

    return f"fetch({fetch_result}), score({score_result})"


async def _run_loop() -> None:
    """Run the articles pipeline on a fixed interval."""
    while True:
        try:
            logger.info("Running articles pipeline ...")
            result = await run_articles_pipeline()
            logger.info("Articles pipeline complete: %s", result)
        except Exception:
            logger.exception("Error in articles pipeline")

        await asyncio.sleep(INTERVAL_4H)


async def main() -> None:
    """Start the articles worker."""
    logger.info("Starting articles worker ...")

    # Run initial fetch immediately
    try:
        result = await run_articles_pipeline()
        logger.info("Initial articles run: %s", result)
    except Exception:
        logger.exception("Initial articles run failed")

    logger.info("Starting periodic articles worker (every 4h) ...")
    await _run_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Articles worker stopped.")
        sys.exit(0)
