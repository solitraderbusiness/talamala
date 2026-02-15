"""8-phase backfill pipeline with Redis progress tracking.

Phases:
1. Yahoo prices backfill (10+ years)
2. FRED macro backfill (10+ years)
3. COT historical archives (10+ years)
4. Correlation backfill (derived from prices)
5. Regime engine (re-run with full history)
6. Event generation (derived from prices/ETF/COT)
7. Sentiment backfill (derived from all data)
8. Validation (quick sanity check)

Progress tracked via Redis hash ``backfill:{job_id}`` with fields:
status, phase, phase_name, phase_progress, phase_total, detail, updated_at
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis

from api.config import settings

logger = logging.getLogger("analysis.backfill")

PHASES = [
    {"id": 1, "name": "yahoo_prices", "label_fa": "قیمت‌های Yahoo Finance"},
    {"id": 2, "name": "fred_macro", "label_fa": "شاخص‌های FRED"},
    {"id": 3, "name": "cot_history", "label_fa": "آرشیو COT"},
    {"id": 4, "name": "correlations", "label_fa": "همبستگی‌ها"},
    {"id": 5, "name": "regime_scores", "label_fa": "رژیم نقدینگی"},
    {"id": 6, "name": "events", "label_fa": "رویدادها"},
    {"id": 7, "name": "sentiment", "label_fa": "احساسات بازار"},
    {"id": 8, "name": "validation", "label_fa": "اعتبارسنجی"},
]


async def _update_progress(
    redis_conn: aioredis.Redis,
    job_id: str,
    phase: int,
    phase_name: str,
    status: str = "running",
    detail: str = "",
) -> None:
    """Update Redis hash with current progress."""
    key = f"backfill:{job_id}"
    await redis_conn.hset(key, mapping={
        "status": status,
        "phase": str(phase),
        "phase_name": phase_name,
        "phase_total": str(len(PHASES)),
        "detail": detail,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    await redis_conn.expire(key, 3600)  # 1 hour TTL


async def run_backfill(
    job_id: str | None = None,
    start_date: str = "2014-01-01",
) -> dict:
    """Execute the 8-phase backfill pipeline.

    Args:
        job_id: Unique identifier for this job (for Redis progress).
        start_date: Start date for historical backfill.

    Returns:
        Summary dict with results from each phase.
    """
    if job_id is None:
        job_id = str(uuid.uuid4())[:8]

    redis_conn = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    results: dict[str, dict] = {}

    try:
        # Phase 1: Yahoo prices
        await _update_progress(redis_conn, job_id, 1, "yahoo_prices", detail="Downloading 10+ years of prices...")
        try:
            from api.analysis.workers.yahoo_fetcher import backfill as yahoo_backfill
            results["yahoo_prices"] = await yahoo_backfill(start_date=start_date)
        except Exception as e:
            logger.exception("Yahoo backfill failed")
            results["yahoo_prices"] = {"status": "error", "error": str(e)}

        # Phase 2: FRED macro
        await _update_progress(redis_conn, job_id, 2, "fred_macro", detail="Downloading FRED indicators...")
        try:
            from api.analysis.workers.fred_fetcher import backfill as fred_backfill
            results["fred_macro"] = await fred_backfill(start_date=start_date)
        except Exception as e:
            logger.exception("FRED backfill failed")
            results["fred_macro"] = {"status": "error", "error": str(e)}

        # Phase 3: COT history
        await _update_progress(redis_conn, job_id, 3, "cot_history", detail="Downloading CFTC yearly archives...")
        try:
            from api.analysis.workers.cot_parser import backfill_cot_history
            results["cot_history"] = await backfill_cot_history(start_year=int(start_date[:4]))
        except Exception as e:
            logger.exception("COT backfill failed")
            results["cot_history"] = {"status": "error", "error": str(e)}

        # Phase 4: Correlations
        await _update_progress(redis_conn, job_id, 4, "correlations", detail="Computing historical correlations...")
        try:
            from api.analysis.workers.correlation_calc import backfill_historical
            from datetime import date
            results["correlations"] = await backfill_historical(
                start_date=date.fromisoformat(start_date)
            )
        except Exception as e:
            logger.exception("Correlation backfill failed")
            results["correlations"] = {"status": "error", "error": str(e)}

        # Phase 5: Regime scores
        await _update_progress(redis_conn, job_id, 5, "regime_scores", detail="Computing regime history...")
        try:
            from api.analysis.workers.regime_engine import run as regime_run
            results["regime_scores"] = await regime_run()
        except Exception as e:
            logger.exception("Regime computation failed")
            results["regime_scores"] = {"status": "error", "error": str(e)}

        # Phase 6: Events
        await _update_progress(redis_conn, job_id, 6, "events", detail="Generating historical events...")
        try:
            from api.analysis.workers.event_generator import backfill_historical_events
            from datetime import date
            results["events"] = await backfill_historical_events(
                start_date=date.fromisoformat(start_date)
            )
        except Exception as e:
            logger.exception("Event backfill failed")
            results["events"] = {"status": "error", "error": str(e)}

        # Phase 7: Sentiment
        await _update_progress(redis_conn, job_id, 7, "sentiment", detail="Computing historical sentiment...")
        try:
            from api.analysis.workers.sentiment_backfill import backfill_daily_sentiment
            results["sentiment"] = await backfill_daily_sentiment(start_date=start_date)
        except Exception as e:
            logger.exception("Sentiment backfill failed")
            results["sentiment"] = {"status": "error", "error": str(e)}

        # Phase 8: Validation
        await _update_progress(redis_conn, job_id, 8, "validation", detail="Running sanity checks...")
        try:
            from api.database import AsyncSessionLocal
            from sqlalchemy import func, select
            from api.analysis.models import AssetPriceDaily, MacroIndicator, CotData, CorrelationCache, RegimeScore

            async with AsyncSessionLocal() as session:
                counts = {}
                for model, name in [
                    (AssetPriceDaily, "prices"),
                    (MacroIndicator, "fred"),
                    (CotData, "cot"),
                    (CorrelationCache, "correlations"),
                    (RegimeScore, "regime_scores"),
                ]:
                    q = await session.execute(select(func.count(model.id)))
                    counts[name] = q.scalar() or 0

            results["validation"] = {"status": "ok", "row_counts": counts}
        except Exception as e:
            logger.exception("Validation failed")
            results["validation"] = {"status": "error", "error": str(e)}

        # Done
        await _update_progress(redis_conn, job_id, 8, "validation", status="completed", detail="Backfill complete")

    except Exception as e:
        await _update_progress(redis_conn, job_id, 0, "error", status="failed", detail=str(e))
        raise
    finally:
        await redis_conn.aclose()

    return {
        "job_id": job_id,
        "status": "completed",
        "phases": results,
    }
