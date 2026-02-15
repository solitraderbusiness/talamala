"""Standalone entry point for the video background worker.

Can be run directly or integrated into the analysis worker main loop.

Pipeline: scanner → metadata → transcript
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
logger = logging.getLogger("videos.worker")

INTERVAL_1H = 60 * 60


async def run_video_pipeline() -> str:
    """Run the full video pipeline: scan channels, fetch metadata, process transcripts."""
    from api.videos.workers import channel_scanner, metadata_fetcher, transcript_processor

    scan_result = await channel_scanner.run()
    logger.info("Scanner: %s", scan_result)

    meta_result = await metadata_fetcher.run()
    logger.info("Metadata: %s", meta_result)

    transcript_result = await transcript_processor.run()
    logger.info("Transcript: %s", transcript_result)

    return f"scan({scan_result}), meta({meta_result}), transcript({transcript_result})"


async def _run_loop() -> None:
    """Run the video pipeline on a fixed interval."""
    while True:
        try:
            logger.info("Running video pipeline ...")
            result = await run_video_pipeline()
            logger.info("Video pipeline complete: %s", result)
        except Exception:
            logger.exception("Error in video pipeline")

        await asyncio.sleep(INTERVAL_1H)


async def main() -> None:
    """Start the video worker."""
    logger.info("Starting video worker ...")

    try:
        result = await run_video_pipeline()
        logger.info("Initial video run: %s", result)
    except Exception:
        logger.exception("Initial video run failed")

    logger.info("Starting periodic video worker (every 1h) ...")
    await _run_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Video worker stopped.")
        sys.exit(0)
