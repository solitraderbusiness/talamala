"""Admin API routes for backfill and unified backtest.

Endpoints
---------
- ``POST /backfill``         — Start full historical backfill (async)
- ``GET  /backfill/status``  — Poll backfill progress from Redis
- ``POST /run``              — Run unified validation backtest
- ``GET  /history``          — Past backtest runs
- ``GET  /data-depth``       — Current row counts + date ranges per table
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select

from api.auth import get_current_admin
from api.config import settings
from api.database import AsyncSessionLocal
from api.analysis.models import (
    AssetPriceDaily,
    BacktestRun,
    CorrelationCache,
    CotData,
    EtfHolding,
    MacroIndicator,
    MarketEventAnalysis,
    RegimeScore,
)
from api.data_collection.models import SentimentTimeline

logger = logging.getLogger("backtest.routes")

router = APIRouter(tags=["backtest"])

# Keep track of running backfill task
_backfill_task: asyncio.Task | None = None
_backfill_job_id: str | None = None


@router.post("/backfill", dependencies=[Depends(get_current_admin)])
async def start_backfill(start_date: str = "2014-01-01"):
    """Start full historical backfill (runs in background).

    Returns a job_id that can be polled via ``GET /backfill/status``.
    """
    global _backfill_task, _backfill_job_id

    # Check if already running
    if _backfill_task is not None and not _backfill_task.done():
        return {
            "status": "already_running",
            "job_id": _backfill_job_id,
            "message": "A backfill is already in progress",
        }

    import uuid
    job_id = str(uuid.uuid4())[:8]
    _backfill_job_id = job_id

    async def _run_backfill():
        try:
            from api.analysis.scripts.backfill_orchestrator import run_backfill
            await run_backfill(job_id=job_id, start_date=start_date)
        except Exception:
            logger.exception("Backfill task failed")

    _backfill_task = asyncio.create_task(_run_backfill())

    return {
        "status": "started",
        "job_id": job_id,
        "message": "Backfill started in background",
    }


@router.get("/backfill/status", dependencies=[Depends(get_current_admin)])
async def get_backfill_status():
    """Poll backfill progress from Redis."""
    if _backfill_job_id is None:
        return {"status": "idle", "message": "No backfill has been started"}

    try:
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        data = await r.hgetall(f"backfill:{_backfill_job_id}")
        await r.aclose()

        if not data:
            # Check if task is done
            if _backfill_task is not None and _backfill_task.done():
                return {"status": "completed", "job_id": _backfill_job_id}
            return {"status": "starting", "job_id": _backfill_job_id}

        return {
            "job_id": _backfill_job_id,
            **data,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post("/run", dependencies=[Depends(get_current_admin)])
async def run_backtest():
    """Run unified validation backtest across 4 categories.

    Validates regime, correlation, sentiment, and event benchmarks
    against historical data stored in the DB.
    """
    from api.analysis.scripts.backtest_unified import run_unified_backtest

    try:
        result = await run_unified_backtest(triggered_by="admin")
        return result
    except Exception as exc:
        logger.exception("Unified backtest failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history", dependencies=[Depends(get_current_admin)])
async def get_backtest_history(
    limit: int = Query(default=20, ge=1, le=100),
):
    """Return past backtest runs, newest first."""
    async with AsyncSessionLocal() as session:
        q = await session.execute(
            select(BacktestRun)
            .order_by(desc(BacktestRun.created_at))
            .limit(limit)
        )
        rows = q.scalars().all()
        return [
            {
                "id": str(r.id),
                "run_type": r.run_type,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "status": r.status,
                "total_benchmarks": r.total_benchmarks,
                "passed_benchmarks": r.passed_benchmarks,
                "failed_benchmarks": r.failed_benchmarks,
                "summary": r.summary,
                "triggered_by": r.triggered_by,
                "error_message": r.error_message,
            }
            for r in rows
        ]


@router.get("/data-depth", dependencies=[Depends(get_current_admin)])
async def get_data_depth():
    """Return row counts and date ranges for all data tables."""
    async with AsyncSessionLocal() as session:
        tables = []

        # Asset prices
        q = await session.execute(
            select(
                func.count(AssetPriceDaily.id),
                func.min(AssetPriceDaily.trade_date),
                func.max(AssetPriceDaily.trade_date),
            )
        )
        row = q.one()
        tables.append({
            "table": "asset_prices_daily",
            "label_fa": "قیمت دارایی‌ها",
            "rows": row[0],
            "earliest": str(row[1]) if row[1] else None,
            "latest": str(row[2]) if row[2] else None,
        })

        # FRED macro
        q = await session.execute(
            select(
                func.count(MacroIndicator.id),
                func.min(MacroIndicator.observation_date),
                func.max(MacroIndicator.observation_date),
            )
        )
        row = q.one()
        tables.append({
            "table": "macro_indicators",
            "label_fa": "شاخص‌های کلان (FRED)",
            "rows": row[0],
            "earliest": str(row[1]) if row[1] else None,
            "latest": str(row[2]) if row[2] else None,
        })

        # ETF holdings
        q = await session.execute(
            select(
                func.count(EtfHolding.id),
                func.min(EtfHolding.holding_date),
                func.max(EtfHolding.holding_date),
            )
        )
        row = q.one()
        tables.append({
            "table": "etf_holdings",
            "label_fa": "موجودی ETF",
            "rows": row[0],
            "earliest": str(row[1]) if row[1] else None,
            "latest": str(row[2]) if row[2] else None,
        })

        # COT data
        q = await session.execute(
            select(
                func.count(CotData.id),
                func.min(CotData.report_date),
                func.max(CotData.report_date),
            )
        )
        row = q.one()
        tables.append({
            "table": "cot_data",
            "label_fa": "گزارش COT",
            "rows": row[0],
            "earliest": str(row[1]) if row[1] else None,
            "latest": str(row[2]) if row[2] else None,
        })

        # Correlations
        q = await session.execute(
            select(
                func.count(CorrelationCache.id),
                func.min(CorrelationCache.computed_date),
                func.max(CorrelationCache.computed_date),
            )
        )
        row = q.one()
        tables.append({
            "table": "correlation_cache",
            "label_fa": "همبستگی‌ها",
            "rows": row[0],
            "earliest": str(row[1]) if row[1] else None,
            "latest": str(row[2]) if row[2] else None,
        })

        # Regime scores
        q = await session.execute(
            select(
                func.count(RegimeScore.id),
                func.min(RegimeScore.ts),
                func.max(RegimeScore.ts),
            )
        )
        row = q.one()
        tables.append({
            "table": "regime_scores",
            "label_fa": "رژیم نقدینگی",
            "rows": row[0],
            "earliest": str(row[1]) if row[1] else None,
            "latest": str(row[2]) if row[2] else None,
        })

        # Events
        q = await session.execute(
            select(
                func.count(MarketEventAnalysis.id),
                func.min(MarketEventAnalysis.created_at),
                func.max(MarketEventAnalysis.created_at),
            )
        )
        row = q.one()
        tables.append({
            "table": "market_events_analysis",
            "label_fa": "رویدادهای بازار",
            "rows": row[0],
            "earliest": row[1].isoformat() if row[1] else None,
            "latest": row[2].isoformat() if row[2] else None,
        })

        # Sentiment timeline
        q = await session.execute(
            select(
                func.count(SentimentTimeline.id),
                func.min(SentimentTimeline.recorded_at),
                func.max(SentimentTimeline.recorded_at),
            )
        )
        row = q.one()
        tables.append({
            "table": "sentiment_timeline",
            "label_fa": "احساسات بازار",
            "rows": row[0],
            "earliest": row[1].isoformat() if row[1] else None,
            "latest": row[2].isoformat() if row[2] else None,
        })

        return {"tables": tables}
