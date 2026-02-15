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
from api.config import settings
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

        # Outcomes seeded in last 24h
        outcomes_seeded_24h = (await session.execute(
            select(func.count(AlertOutcome.id)).where(
                AlertOutcome.created_at >= now - timedelta(hours=24)
            )
        )).scalar() or 0

        outcome_seed_pct = (
            round(outcomes_seeded_24h / total_alerts_24h * 100)
            if total_alerts_24h > 0 else None
        )

        # Live (non-reconciled) snapshots in 24h
        # missing_fields is JSONB array of strings; use @> containment check
        live_snapshots_24h = (await session.execute(
            text(
                "SELECT COUNT(*) FROM alert_market_snapshots "
                "WHERE created_at >= :since "
                "  AND (missing_fields IS NULL "
                "       OR NOT (missing_fields @> '\"reconciled\"'::jsonb))"
            ),
            {"since": now - timedelta(hours=24)},
        )).scalar() or 0

        complete_snapshot_coverage_pct = (
            round(complete_snapshots_24h / total_alerts_24h * 100)
            if total_alerts_24h > 0 else None
        )

        live_snapshot_coverage_pct = (
            round(live_snapshots_24h / total_alerts_24h * 100)
            if total_alerts_24h > 0 else None
        )

        # Outcome completion rate (all time — outcomes take 7d to finish)
        total_outcomes = sum(outcome_counts.values())
        completed_outcomes = outcome_counts.get("complete", 0)
        outcomes_complete_pct = (
            round(completed_outcomes / total_outcomes * 100, 1)
            if total_outcomes > 0 else None
        )

        # 7-day coverage: alerts missing snapshot or outcome
        since_7d = now - timedelta(days=7)

        total_alerts_7d = (await session.execute(
            text("SELECT COUNT(*) FROM alerts WHERE timestamp_utc >= :since"),
            {"since": since_7d},
        )).scalar() or 0

        missing_snapshots_7d = (await session.execute(
            text(
                "SELECT COUNT(*) FROM alerts a "
                "LEFT JOIN alert_market_snapshots ams ON ams.alert_id = a.id "
                "WHERE a.timestamp_utc >= :since AND ams.id IS NULL"
            ),
            {"since": since_7d},
        )).scalar() or 0

        missing_outcomes_7d = (await session.execute(
            text(
                "SELECT COUNT(*) FROM alerts a "
                "LEFT JOIN alert_outcomes ao ON ao.alert_id = a.id "
                "WHERE a.timestamp_utc >= :since AND ao.id IS NULL"
            ),
            {"since": since_7d},
        )).scalar() or 0

        # Reconciliation backlog & ETA
        # Each run processes up to batch_size outcomes AND batch_size snapshots
        # in parallel, so ETA = max(ceil(outcomes/batch), ceil(snapshots/batch))
        reconciliation_backlog = missing_snapshots_7d + missing_outcomes_7d
        batch_size = settings.RECONCILE_BATCH_SIZE
        interval = settings.RECONCILE_INTERVAL_SECONDS
        if reconciliation_backlog > 0 and batch_size > 0:
            runs_outcomes = (missing_outcomes_7d + batch_size - 1) // batch_size
            runs_snapshots = (missing_snapshots_7d + batch_size - 1) // batch_size
            runs_needed = max(runs_outcomes, runs_snapshots)
            reconciliation_eta_minutes = round(runs_needed * interval / 60, 1)
        else:
            reconciliation_eta_minutes = 0

        return {
            # Snapshot coverage (24h) — 3 tiers
            "snapshot_coverage_pct": snapshot_pct,           # any row exists
            "complete_snapshot_coverage_pct": complete_snapshot_coverage_pct,  # snapshot_complete=true
            "live_snapshot_coverage_pct": live_snapshot_coverage_pct,          # not reconciled
            "alerts_24h": total_alerts_24h,
            "snapshots_24h": total_snapshots_24h,
            "complete_snapshots_24h": complete_snapshots_24h,
            "live_snapshots_24h": live_snapshots_24h,
            # Outcome coverage (24h)
            "outcomes_seeded_24h": outcomes_seeded_24h,
            "outcome_seed_coverage_pct": outcome_seed_pct,  # any row exists
            "outcomes_complete_pct": outcomes_complete_pct,  # status='complete'
            "outcome_pipeline": outcome_counts,
            # Freshness
            "sentiment_last_recorded": last_sentiment.isoformat() if last_sentiment else None,
            "price_data_last_update": last_price.isoformat() if last_price else None,
            "outcome_errors": error_count,
            # 7-day gap counts
            "alerts_7d": total_alerts_7d,
            "missing_snapshots_7d": missing_snapshots_7d,
            "missing_outcomes_7d": missing_outcomes_7d,
            # Reconciliation status
            "reconciliation_backlog": reconciliation_backlog,
            "reconciliation_eta_minutes": reconciliation_eta_minutes,
            "reconciliation_batch_size": batch_size,
            "reconciliation_interval_seconds": interval,
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


# ══════════════════════════════════════════════════════════════════════════
#  7. GET /verification — trust-but-verify pipeline health
# ══════════════════════════════════════════════════════════════════════════

@router.get("/verification")
async def pipeline_verification():
    """Quick verification queries for production pipeline correctness.

    A) Are reconciled snapshots getting upgraded to live?
    B) Are outcomes progressing through windows (not stuck)?
    """
    async with AsyncSessionLocal() as session:
        # A) Snapshot upgrade status (last 24h)
        snap_q = await session.execute(
            text(
                "SELECT "
                "  COUNT(*) FILTER ("
                "    WHERE missing_fields @> '\"reconciled\"'::jsonb"
                "  ) AS still_reconciled, "
                "  COUNT(*) FILTER ("
                "    WHERE missing_fields IS NULL "
                "      OR NOT (missing_fields @> '\"reconciled\"'::jsonb)"
                "  ) AS live_or_upgraded "
                "FROM alert_market_snapshots "
                "WHERE created_at >= NOW() - INTERVAL '24 hours'"
            )
        )
        snap_row = snap_q.one()
        still_reconciled = snap_row[0] or 0
        live_or_upgraded = snap_row[1] or 0

        # B) Outcome progression: alerts >2h old should not be pending_30min
        outcome_q = await session.execute(
            text(
                "SELECT status, COUNT(*) "
                "FROM alert_outcomes "
                "WHERE alert_created_at <= NOW() - INTERVAL '2 hours' "
                "GROUP BY status "
                "ORDER BY COUNT(*) DESC"
            )
        )
        outcome_rows = outcome_q.all()
        by_status = {r[0]: r[1] for r in outcome_rows}
        stuck_30min = by_status.get("pending_30min", 0)

        return {
            "snapshot_upgrade_24h": {
                "still_reconciled": still_reconciled,
                "live_or_upgraded": live_or_upgraded,
                "verdict": (
                    "HEALTHY" if still_reconciled == 0
                    else "OK" if still_reconciled < live_or_upgraded
                    else "STALE"
                ),
            },
            "outcome_progression_2h_plus": {
                "by_status": by_status,
                "stuck_at_30min": stuck_30min,
                "verdict": "HEALTHY" if stuck_30min == 0 else "STUCK",
            },
        }


# ══════════════════════════════════════════════════════════════════════════
#  8. GET /snapshot-live-status — live vs reconciled snapshot breakdown
# ══════════════════════════════════════════════════════════════════════════

@router.get("/snapshot-live-status")
async def snapshot_live_status():
    """24h snapshot breakdown + last 20 snapshots with source label."""
    async with AsyncSessionLocal() as session:
        # Summary: 24h counts
        summary_q = await session.execute(
            text(
                "SELECT "
                "  (SELECT COUNT(*) FROM alerts "
                "   WHERE timestamp_utc >= NOW() - INTERVAL '24 hours') AS total_alerts, "
                "  COUNT(*) FILTER ("
                "    WHERE missing_fields IS NULL "
                "      OR NOT (missing_fields @> '\"reconciled\"'::jsonb)"
                "  ) AS live_count, "
                "  COUNT(*) FILTER ("
                "    WHERE missing_fields @> '\"reconciled\"'::jsonb"
                "  ) AS reconciled_count, "
                "  MAX(created_at) FILTER ("
                "    WHERE missing_fields IS NULL "
                "      OR NOT (missing_fields @> '\"reconciled\"'::jsonb)"
                "  ) AS last_live_at, "
                "  MAX(created_at) FILTER ("
                "    WHERE missing_fields @> '\"reconciled\"'::jsonb"
                "  ) AS last_reconciled_at "
                "FROM alert_market_snapshots "
                "WHERE created_at >= NOW() - INTERVAL '24 hours'"
            )
        )
        row = summary_q.one()
        total_alerts = row[0] or 0
        live_count = row[1] or 0
        reconciled_count = row[2] or 0
        total_snapshots = live_count + reconciled_count
        live_pct = (
            round(live_count / total_alerts * 100, 1)
            if total_alerts > 0 else None
        )

        # Last 20 snapshots
        recent_q = await session.execute(
            text(
                "SELECT "
                "  ams.alert_id::text, ams.created_at, ams.snapshot_complete, "
                "  ams.missing_fields, ams.xauusd, ams.gold_rsi_14, "
                "  ams.sentiment_composite, ams.fetch_duration_ms "
                "FROM alert_market_snapshots ams "
                "ORDER BY ams.created_at DESC "
                "LIMIT 20"
            )
        )
        recent = []
        for r in recent_q:
            mf = r[3]  # JSONB
            is_reconciled = (
                isinstance(mf, list) and "reconciled" in mf
            )
            recent.append({
                "alert_id": r[0],
                "created_at": r[1].isoformat() if r[1] else None,
                "snapshot_complete": r[2],
                "missing_fields": mf,
                "source": "reconciled" if is_reconciled else "live",
                "xauusd": r[4],
                "gold_rsi_14": round(r[5], 2) if r[5] is not None else None,
                "sentiment_composite": r[6],
                "fetch_duration_ms": r[7],
            })

        return {
            "summary_24h": {
                "total_alerts": total_alerts,
                "live_count": live_count,
                "reconciled_count": reconciled_count,
                "total_snapshots": total_snapshots,
                "live_snapshot_coverage_pct": live_pct,
                "last_live_snapshot_at": (
                    row[3].isoformat() if row[3] else None
                ),
                "last_reconciled_snapshot_at": (
                    row[4].isoformat() if row[4] else None
                ),
            },
            "recent_snapshots": recent,
        }


# ══════════════════════════════════════════════════════════════════════════
#  9. GET /live-throughput — hourly live snapshot + alert creation rates
# ══════════════════════════════════════════════════════════════════════════

@router.get("/live-throughput")
async def live_throughput(
    hours: int = Query(24, ge=1, le=168),
):
    """Hourly breakdown of alerts created vs live snapshots created."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    hour_start = since.replace(minute=0, second=0, microsecond=0)

    async with AsyncSessionLocal() as session:
        q = await session.execute(
            text(
                "WITH hours AS ( "
                "  SELECT generate_series( "
                "    :hour_start, "
                "    DATE_TRUNC('hour', NOW()), "
                "    '1 hour'::interval "
                "  ) AS hour_bucket "
                "), "
                "alert_counts AS ( "
                "  SELECT DATE_TRUNC('hour', timestamp_utc) AS hb, COUNT(*) AS cnt "
                "  FROM alerts "
                "  WHERE timestamp_utc >= :since "
                "  GROUP BY 1 "
                "), "
                "live_snap_counts AS ( "
                "  SELECT DATE_TRUNC('hour', s.created_at) AS hb, COUNT(*) AS cnt "
                "  FROM alert_market_snapshots s "
                "  JOIN alerts a ON a.id = s.alert_id "
                "  WHERE a.timestamp_utc >= :since "
                "    AND (s.missing_fields IS NULL "
                "         OR NOT (s.missing_fields @> '\"reconciled\"'::jsonb)) "
                "  GROUP BY 1 "
                ") "
                "SELECT h.hour_bucket, "
                "  COALESCE(ac.cnt, 0) AS alerts_created, "
                "  COALESCE(ls.cnt, 0) AS live_snapshots_created "
                "FROM hours h "
                "LEFT JOIN alert_counts ac ON ac.hb = h.hour_bucket "
                "LEFT JOIN live_snap_counts ls ON ls.hb = h.hour_bucket "
                "ORDER BY h.hour_bucket ASC"
            ),
            {"since": since, "hour_start": hour_start},
        )
        rows = q.all()
        return {
            "hours": hours,
            "data": [
                {
                    "hour_bucket": r[0].isoformat() if r[0] else None,
                    "alerts_created": r[1],
                    "live_snapshots_created": r[2],
                }
                for r in rows
            ],
        }


# ══════════════════════════════════════════════════════════════════════════
#  10. GET /quality-tiers — 4 quality metrics for cockpit cards
# ══════════════════════════════════════════════════════════════════════════

@router.get("/quality-tiers")
async def quality_tiers(
    hours: int = Query(24, ge=1, le=168),
):
    """Four quality metrics: live coverage, complete %, outcome seed %, outcome complete %."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    async with AsyncSessionLocal() as session:
        q = await session.execute(
            text(
                "SELECT "
                "  (SELECT COUNT(*) FROM alerts "
                "   WHERE timestamp_utc >= :since) AS total_alerts, "
                "  (SELECT COUNT(*) FROM alert_market_snapshots s "
                "   JOIN alerts a ON a.id = s.alert_id "
                "   WHERE a.timestamp_utc >= :since "
                "     AND (s.missing_fields IS NULL "
                "          OR NOT (s.missing_fields @> '\"reconciled\"'::jsonb))) AS live_count, "
                "  (SELECT COUNT(*) FROM alert_market_snapshots s "
                "   JOIN alerts a ON a.id = s.alert_id "
                "   WHERE a.timestamp_utc >= :since "
                "     AND (s.missing_fields IS NULL "
                "          OR NOT (s.missing_fields @> '\"reconciled\"'::jsonb)) "
                "     AND s.snapshot_complete = true) AS live_complete_count, "
                "  (SELECT COUNT(*) FROM alert_outcomes o "
                "   JOIN alerts a ON a.id = o.alert_id "
                "   WHERE a.timestamp_utc >= :since) AS outcomes_seeded, "
                "  (SELECT COUNT(*) FROM alert_outcomes WHERE status = 'complete') AS outcomes_complete, "
                "  (SELECT COUNT(*) FROM alert_outcomes) AS outcomes_total"
            ),
            {"since": since},
        )
        row = q.one()
        total_alerts = row[0] or 0
        live_count = row[1] or 0
        live_complete = row[2] or 0
        outcomes_seeded = row[3] or 0
        outcomes_complete = row[4] or 0
        outcomes_total = row[5] or 0

        def pct(n: int, d: int) -> float | None:
            return round(n / d * 100, 1) if d > 0 else None

        return {
            "hours": hours,
            "live_snapshot_coverage": {
                "pct": pct(live_count, total_alerts),
                "numerator": live_count,
                "denominator": total_alerts,
            },
            "live_complete_snapshot_coverage": {
                "pct": pct(live_complete, total_alerts),
                "numerator": live_complete,
                "denominator": total_alerts,
            },
            "outcome_seed_coverage": {
                "pct": pct(outcomes_seeded, total_alerts),
                "numerator": outcomes_seeded,
                "denominator": total_alerts,
            },
            "outcome_completion": {
                "pct": pct(outcomes_complete, outcomes_total),
                "numerator": outcomes_complete,
                "denominator": outcomes_total,
            },
        }


# ══════════════════════════════════════════════════════════════════════════
#  11. GET /missing-fields — breakdown for LIVE snapshots only
# ══════════════════════════════════════════════════════════════════════════

@router.get("/missing-fields")
async def missing_fields_breakdown(
    days: int = Query(7, ge=1, le=90),
):
    """Missing field breakdown for LIVE snapshots (excludes reconciled)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    async with AsyncSessionLocal() as session:
        # Total live snapshots in window
        total_live = (await session.execute(
            text(
                "SELECT COUNT(*) FROM alert_market_snapshots s "
                "JOIN alerts a ON a.id = s.alert_id "
                "WHERE a.timestamp_utc >= :since "
                "  AND (s.missing_fields IS NULL "
                "       OR NOT (s.missing_fields @> '\"reconciled\"'::jsonb))"
            ),
            {"since": since},
        )).scalar() or 0

        # Field-level breakdown (safe expansion)
        fields_q = await session.execute(
            text(
                "SELECT mf.value AS field, COUNT(*) AS cnt "
                "FROM alert_market_snapshots s "
                "JOIN alerts a ON a.id = s.alert_id, "
                "LATERAL jsonb_array_elements_text( "
                "  CASE "
                "    WHEN s.missing_fields IS NULL THEN '[]'::jsonb "
                "    WHEN jsonb_typeof(s.missing_fields) = 'array' THEN s.missing_fields "
                "    ELSE '[]'::jsonb "
                "  END "
                ") mf(value) "
                "WHERE a.timestamp_utc >= :since "
                "  AND (s.missing_fields IS NULL "
                "       OR NOT (s.missing_fields @> '\"reconciled\"'::jsonb)) "
                "GROUP BY 1 "
                "ORDER BY 2 DESC"
            ),
            {"since": since},
        )
        fields = []
        for r in fields_q:
            fields.append({
                "field": r[0],
                "count": r[1],
                "pct": round(r[1] / total_live * 100, 1) if total_live > 0 else 0,
            })

        return {
            "days": days,
            "total_live_snapshots": total_live,
            "fields": fields,
        }


# ══════════════════════════════════════════════════════════════════════════
#  12. GET /guardrails — 3 pipeline integrity checks with PASS/FAIL
# ══════════════════════════════════════════════════════════════════════════

@router.get("/guardrails")
async def guardrails():
    """Three guardrail checks: missing data, misclassification, field failures."""
    async with AsyncSessionLocal() as session:
        # 1) Live alerts missing snapshot or outcome (24h)
        g1 = await session.execute(
            text(
                "SELECT "
                "  COUNT(*) FILTER (WHERE s.alert_id IS NULL) AS missing_snapshot, "
                "  COUNT(*) FILTER (WHERE o.alert_id IS NULL) AS missing_outcome "
                "FROM alerts a "
                "LEFT JOIN alert_market_snapshots s ON s.alert_id = a.id "
                "LEFT JOIN alert_outcomes o ON o.alert_id = a.id "
                "WHERE a.timestamp_utc >= NOW() - INTERVAL '24 hours' "
                "  AND a.id IN ( "
                "    SELECT s2.alert_id "
                "    FROM alert_market_snapshots s2 "
                "    WHERE s2.missing_fields IS NULL "
                "       OR NOT (s2.missing_fields @> '\"reconciled\"'::jsonb) "
                "  )"
            )
        )
        g1_row = g1.one()
        g1_snap = g1_row[0] or 0
        g1_out = g1_row[1] or 0

        # 2) Live snapshots accidentally marked reconciled (24h)
        g2_val = (await session.execute(
            text(
                "SELECT COUNT(*) FROM alert_market_snapshots s "
                "JOIN alerts a ON a.id = s.alert_id "
                "WHERE a.timestamp_utc >= NOW() - INTERVAL '24 hours' "
                "  AND (s.missing_fields @> '\"reconciled\"'::jsonb) "
                "  AND s.snapshot_complete = true"
            )
        )).scalar() or 0

        # 3) Missing field count in LIVE snapshots (7d) — non-zero = has failures
        g3_val = (await session.execute(
            text(
                "SELECT COUNT(DISTINCT mf.value) "
                "FROM alert_market_snapshots s "
                "JOIN alerts a ON a.id = s.alert_id, "
                "LATERAL jsonb_array_elements_text( "
                "  CASE "
                "    WHEN s.missing_fields IS NULL THEN '[]'::jsonb "
                "    WHEN jsonb_typeof(s.missing_fields) = 'array' THEN s.missing_fields "
                "    ELSE '[]'::jsonb "
                "  END "
                ") mf(value) "
                "WHERE a.timestamp_utc >= NOW() - INTERVAL '7 days' "
                "  AND (s.missing_fields IS NULL "
                "       OR NOT (s.missing_fields @> '\"reconciled\"'::jsonb))"
            )
        )).scalar() or 0

        return {
            "checks": [
                {
                    "id": "live_missing_data",
                    "label_fa": "هشدارهای زنده بدون اسنپ‌شات/نتیجه (۲۴ ساعت)",
                    "label_en": "Live alerts missing snapshot/outcome (24h)",
                    "missing_snapshot": g1_snap,
                    "missing_outcome": g1_out,
                    "verdict": "PASS" if (g1_snap == 0 and g1_out == 0) else "FAIL",
                },
                {
                    "id": "misclassified_reconciled",
                    "label_fa": "اسنپ‌شات‌های زنده اشتباهاً بازسازی‌شده علامت‌گذاری شده (۲۴ ساعت)",
                    "label_en": "Live snapshots marked reconciled (24h)",
                    "count": g2_val,
                    "verdict": "PASS" if g2_val == 0 else "FAIL",
                },
                {
                    "id": "missing_field_types",
                    "label_fa": "انواع فیلدهای گمشده در اسنپ‌شات‌های زنده (۷ روز)",
                    "label_en": "Missing field types in live snapshots (7d)",
                    "count": g3_val,
                    "verdict": "PASS" if g3_val == 0 else "WARN",
                },
            ],
        }
