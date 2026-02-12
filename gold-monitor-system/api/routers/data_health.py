"""Admin data-health API — 6 endpoints for monitoring data collection.

All endpoints require admin authentication.
Registered at ``/api/admin/data-health``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select, text

from api.auth import get_current_admin
from api.database import AsyncSessionLocal
from api.data_collection.models import (
    AlertMarketSnapshot,
    AlertOutcome,
    PriceHistory,
    SentimentTimeline,
)

router = APIRouter(
    tags=["data-health"],
    dependencies=[Depends(get_current_admin)],
)
logger = logging.getLogger("gold_monitor.data_health")


# ══════════════════════════════════════════════════════════════════════════
#  1. GET /overview — top-level data health summary
# ══════════════════════════════════════════════════════════════════════════

@router.get("/overview")
async def data_health_overview():
    """Top-level data health: completeness, freshness, error counts."""
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        # Snapshot completeness
        total_alerts_24h = (await session.execute(
            text("SELECT COUNT(*) FROM alerts WHERE timestamp_utc >= :since"),
            {"since": now - timedelta(hours=24)},
        )).scalar() or 0

        total_snapshots_24h = (await session.execute(
            select(func.count(AlertMarketSnapshot.id)).where(
                AlertMarketSnapshot.created_at >= now - timedelta(hours=24)
            )
        )).scalar() or 0

        complete_snapshots_24h = (await session.execute(
            select(func.count(AlertMarketSnapshot.id)).where(
                AlertMarketSnapshot.created_at >= now - timedelta(hours=24),
                AlertMarketSnapshot.snapshot_complete == True,  # noqa: E712
            )
        )).scalar() or 0

        snapshot_pct = (
            round(total_snapshots_24h / total_alerts_24h * 100)
            if total_alerts_24h > 0 else None
        )

        # Outcome pipeline
        outcome_counts = {}
        for status in ["pending_30min", "pending_1h", "pending_4h", "pending_24h", "pending_48h", "pending_7d", "complete"]:
            cnt = (await session.execute(
                select(func.count(AlertOutcome.id)).where(
                    AlertOutcome.status == status
                )
            )).scalar() or 0
            outcome_counts[status] = cnt

        # Sentiment timeline last recorded
        last_sentiment = (await session.execute(
            select(SentimentTimeline.recorded_at)
            .order_by(desc(SentimentTimeline.recorded_at))
            .limit(1)
        )).scalar()

        # Price data freshness
        last_price = (await session.execute(
            select(PriceHistory.datetime_utc)
            .order_by(desc(PriceHistory.datetime_utc))
            .limit(1)
        )).scalar()

        # Error counts (outcomes with errors)
        error_count = (await session.execute(
            select(func.count(AlertOutcome.id)).where(
                AlertOutcome.errors != None,  # noqa: E711
            )
        )).scalar() or 0

        return {
            "snapshot_coverage_pct": snapshot_pct,
            "alerts_24h": total_alerts_24h,
            "snapshots_24h": total_snapshots_24h,
            "complete_snapshots_24h": complete_snapshots_24h,
            "outcome_pipeline": outcome_counts,
            "sentiment_last_recorded": last_sentiment.isoformat() if last_sentiment else None,
            "price_data_last_update": last_price.isoformat() if last_price else None,
            "outcome_errors": error_count,
        }


# ══════════════════════════════════════════════════════════════════════════
#  2. GET /snapshot-stats — snapshot completeness details
# ══════════════════════════════════════════════════════════════════════════

@router.get("/snapshot-stats")
async def snapshot_stats(
    period: str = Query("today", regex="^(today|week|month)$"),
):
    """Snapshot completeness stats for a given period."""
    now = datetime.now(timezone.utc)
    if period == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        since = now - timedelta(days=7)
    else:
        since = now - timedelta(days=30)

    async with AsyncSessionLocal() as session:
        alerts_count = (await session.execute(
            text("SELECT COUNT(*) FROM alerts WHERE timestamp_utc >= :since"),
            {"since": since},
        )).scalar() or 0

        snapshots_count = (await session.execute(
            select(func.count(AlertMarketSnapshot.id)).where(
                AlertMarketSnapshot.created_at >= since
            )
        )).scalar() or 0

        complete_count = (await session.execute(
            select(func.count(AlertMarketSnapshot.id)).where(
                AlertMarketSnapshot.created_at >= since,
                AlertMarketSnapshot.snapshot_complete == True,  # noqa: E712
            )
        )).scalar() or 0

        # Top missing fields
        missing_q = await session.execute(
            text(
                "SELECT jsonb_array_elements_text(missing_fields) AS field, "
                "COUNT(*) AS cnt "
                "FROM alert_market_snapshots "
                "WHERE created_at >= :since AND missing_fields IS NOT NULL "
                "GROUP BY field ORDER BY cnt DESC LIMIT 10"
            ),
            {"since": since},
        )
        top_missing = [{"field": r[0], "count": r[1]} for r in missing_q]

        return {
            "period": period,
            "alerts_count": alerts_count,
            "snapshots_count": snapshots_count,
            "complete_count": complete_count,
            "missing_count": alerts_count - snapshots_count,
            "completeness_pct": round(snapshots_count / alerts_count * 100) if alerts_count > 0 else None,
            "top_missing_fields": top_missing,
        }


# ══════════════════════════════════════════════════════════════════════════
#  3. GET /outcome-pipeline — funnel counts and errors
# ══════════════════════════════════════════════════════════════════════════

@router.get("/outcome-pipeline")
async def outcome_pipeline():
    """Outcome pipeline: count per status stage, completion rate, recent errors."""
    async with AsyncSessionLocal() as session:
        # Counts per status
        status_q = await session.execute(
            text(
                "SELECT status, COUNT(*) FROM alert_outcomes "
                "GROUP BY status ORDER BY status"
            )
        )
        counts = {r[0]: r[1] for r in status_q}

        total = sum(counts.values())
        completed = counts.get("complete", 0)
        completion_rate = round(completed / total * 100, 1) if total > 0 else None

        # Recent errors
        errors_q = await session.execute(
            select(AlertOutcome)
            .where(AlertOutcome.errors != None)  # noqa: E711
            .order_by(desc(AlertOutcome.updated_at))
            .limit(10)
        )
        recent_errors = []
        for o in errors_q.scalars():
            recent_errors.append({
                "alert_id": str(o.alert_id),
                "status": o.status,
                "errors": o.errors,
                "updated_at": o.updated_at.isoformat() if o.updated_at else None,
            })

        return {
            "counts": counts,
            "total": total,
            "completed": completed,
            "completion_rate": completion_rate,
            "recent_errors": recent_errors,
        }


# ══════════════════════════════════════════════════════════════════════════
#  4. GET /sentiment-timeline — time series for charting
# ══════════════════════════════════════════════════════════════════════════

@router.get("/sentiment-timeline")
async def sentiment_timeline_data(
    hours: int = Query(168, ge=1, le=720),
):
    """Sentiment + gold price time series for charting."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    async with AsyncSessionLocal() as session:
        q = await session.execute(
            select(SentimentTimeline)
            .where(SentimentTimeline.recorded_at >= since)
            .order_by(SentimentTimeline.recorded_at)
        )
        rows = q.scalars().all()

        data = []
        for r in rows:
            data.append({
                "recorded_at": r.recorded_at.isoformat(),
                "composite_score": r.composite_score,
                "direction": r.direction,
                "gold_price": r.gold_price,
                "gold_change_1h_pct": r.gold_change_1h_pct,
                "alerts_active_24h": r.alerts_active_24h,
            })

        return {
            "data": data,
            "count": len(data),
            "period_hours": hours,
        }


# ══════════════════════════════════════════════════════════════════════════
#  5. GET /price-status — per-symbol data freshness
# ══════════════════════════════════════════════════════════════════════════

@router.get("/price-status")
async def price_status():
    """Per-symbol price data freshness and record counts."""
    async with AsyncSessionLocal() as session:
        q = await session.execute(
            text(
                "SELECT symbol, timeframe, "
                "MAX(datetime_utc) AS last_update, "
                "COUNT(*) AS record_count, "
                "(SELECT close FROM price_history ph2 "
                " WHERE ph2.symbol = ph.symbol AND ph2.timeframe = ph.timeframe "
                " ORDER BY datetime_utc DESC LIMIT 1) AS last_price "
                "FROM price_history ph "
                "GROUP BY symbol, timeframe "
                "ORDER BY symbol, timeframe"
            )
        )
        rows = q.all()

        symbols = []
        for r in rows:
            symbols.append({
                "symbol": r[0],
                "timeframe": r[1],
                "last_update": r[2].isoformat() if r[2] else None,
                "record_count": r[3],
                "last_price": r[4],
            })

        return {"symbols": symbols}


# ══════════════════════════════════════════════════════════════════════════
#  6. GET /correlation — sentiment vs gold price correlation
# ══════════════════════════════════════════════════════════════════════════

@router.get("/correlation")
async def sentiment_price_correlation(
    days: int = Query(7, ge=1, le=90),
):
    """Pearson correlation between sentiment and gold price at multiple lags."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    async with AsyncSessionLocal() as session:
        # Get sentiment timeline data
        q = await session.execute(
            select(SentimentTimeline)
            .where(SentimentTimeline.recorded_at >= since)
            .order_by(SentimentTimeline.recorded_at)
        )
        rows = q.scalars().all()

        if len(rows) < 10:
            return {
                "correlations": [],
                "data_points": len(rows),
                "message_fa": "داده کافی برای محاسبه همبستگی وجود ندارد",
            }

        # Build time-aligned arrays
        scores = [r.composite_score for r in rows if r.composite_score is not None]
        prices = [r.gold_price for r in rows if r.gold_price is not None]

        if len(scores) < 10 or len(prices) < 10:
            return {
                "correlations": [],
                "data_points": min(len(scores), len(prices)),
                "message_fa": "داده کافی برای محاسبه همبستگی وجود ندارد",
            }

        # Compute correlations at different lags (using min of both arrays)
        n = min(len(scores), len(prices))
        scores = scores[:n]
        prices = prices[:n]

        lags = [0, 12, 24, 48, 96, 144, 288]  # in 5-min intervals: 0h,1h,2h,4h,8h,12h,24h
        lag_labels = ["0h", "1h", "2h", "4h", "8h", "12h", "24h"]
        correlations = []

        for lag, label in zip(lags, lag_labels):
            if lag >= n:
                continue
            s = scores[:n - lag] if lag > 0 else scores
            p = prices[lag:] if lag > 0 else prices
            ln = min(len(s), len(p))
            if ln < 5:
                continue

            s = s[:ln]
            p = p[:ln]
            corr = _pearson(s, p)
            if corr is not None:
                correlations.append({
                    "lag": label,
                    "correlation": round(corr, 3),
                    "interpretation": _interpret_correlation(corr, label),
                })

        return {
            "correlations": correlations,
            "data_points": n,
            "period_days": days,
        }


def _pearson(x: list, y: list) -> float | None:
    """Simple Pearson correlation coefficient."""
    n = len(x)
    if n < 2:
        return None

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    std_x = sum((xi - mean_x) ** 2 for xi in x) ** 0.5
    std_y = sum((yi - mean_y) ** 2 for yi in y) ** 0.5

    if std_x == 0 or std_y == 0:
        return None

    return cov / (std_x * std_y)


def _interpret_correlation(corr: float, lag: str) -> str:
    """Persian interpretation of correlation value."""
    strength = abs(corr)
    if strength < 0.2:
        rel = "بسیار ضعیف"
    elif strength < 0.4:
        rel = "ضعیف"
    elif strength < 0.6:
        rel = "متوسط"
    elif strength < 0.8:
        rel = "قوی"
    else:
        rel = "بسیار قوی"

    direction = "مثبت" if corr > 0 else "منفی"
    if lag == "0h":
        return f"همبستگی {rel} {direction} (هم‌زمان)"
    else:
        return f"همبستگی {rel} {direction} (سنتیمنت {lag} قبل از قیمت)"
