"""Composite sentiment scorer — computed from all analysis tables.

This worker doesn't store data; the score is computed on-the-fly by the
/api/analysis/sentiment-gauge endpoint. This module exists only for the
event generator to call when generating sentiment-shift events.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("analysis.sentiment")


async def run() -> dict:
    """Sentinel run — sentiment is computed on-the-fly by the API endpoint.

    This worker is a placeholder for future enhancements like caching
    historical sentiment scores.
    """
    logger.info("Sentiment scorer: scores computed on-the-fly by API endpoint")
    return {"status": "ok", "note": "computed_on_the_fly"}
