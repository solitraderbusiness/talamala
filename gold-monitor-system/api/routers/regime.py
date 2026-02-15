"""Public API routes for the liquidity regime engine.

Endpoints
---------
- ``GET /latest``            — latest regime score row
- ``GET /history``           — last N days of regime history
- ``POST /backtest``         — run historical backtest (admin only)
- ``GET /gold-performance``  — gold return stats per regime
- ``GET /transitions``       — what happens when regime changes
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from functools import partial

from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy import select, desc, asc

from api.auth import get_current_admin
from api.database import AsyncSessionLocal
from api.analysis.models import AssetPriceDaily, RegimeAuditLog, RegimeScore

logger = logging.getLogger("regime.routes")

router = APIRouter(tags=["regime"])


def _row_to_dict(row: RegimeScore) -> dict:
    return {
        "ts": str(row.ts),
        "liquidity_stress_index": row.liquidity_stress_index,
        "usd_pressure_index": row.usd_pressure_index,
        "real_yield_pressure_index": row.real_yield_pressure_index,
        "p_expansion": row.p_expansion,
        "p_tightening": row.p_tightening,
        "p_stress": row.p_stress,
        "p_recovery": row.p_recovery,
        "smoothed_p_expansion": row.smoothed_p_expansion,
        "smoothed_p_tightening": row.smoothed_p_tightening,
        "smoothed_p_stress": row.smoothed_p_stress,
        "smoothed_p_recovery": row.smoothed_p_recovery,
        "chosen_regime": row.chosen_regime,
        "chosen_regime_raw": getattr(row, "chosen_regime_raw", None),
        "chosen_note_fa": getattr(row, "chosen_note_fa", None),
        "score_semantics": getattr(row, "score_semantics", None) or "relative_regime_scores",
        "lookahead_safe": bool(getattr(row, "lookahead_safe", True)),
        "real_yield_source": row.real_yield_source,
        "credit_proxy_source": row.credit_proxy_source,
        "days_skipped": row.days_skipped,
        "metadata": row.metadata_,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/latest")
async def get_latest_regime():
    """Return the most recent regime score."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(RegimeScore)
            .order_by(desc(RegimeScore.ts))
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return {"status": "pending", "message": "No regime data computed yet"}
        return _row_to_dict(row)


@router.get("/history")
async def get_regime_history(
    days: int = Query(default=90, ge=1, le=730),
):
    """Return regime scores for the last N days, newest first."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(RegimeScore)
            .order_by(desc(RegimeScore.ts))
            .limit(days)
        )
        rows = result.scalars().all()
        return [_row_to_dict(r) for r in rows]


@router.post("/backtest", dependencies=[Depends(get_current_admin)])
async def run_regime_backtest():
    """Run a 10+ year historical backtest of the regime engine.

    Downloads data from Yahoo Finance and FRED, runs regime computation,
    and validates against known macro events.  Takes ~30-60 seconds.
    """
    from api.analysis.scripts.backtest_regime import run_backtest

    fred_key = os.environ.get("FRED_API_KEY", "")
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, partial(run_backtest, fred_api_key=fred_key),
        )
    except Exception as exc:
        logger.exception("Backtest failed")
        raise HTTPException(status_code=500, detail=str(exc))
    return result


@router.get("/gold-performance")
async def regime_gold_performance():
    """Gold return statistics grouped by macro regime."""
    async with AsyncSessionLocal() as session:
        # Fetch all regime scores ordered by date ascending
        regime_result = await session.execute(
            select(RegimeScore).order_by(asc(RegimeScore.ts))
        )
        regime_rows = regime_result.scalars().all()

        # Fetch all gold prices ordered by date ascending
        gold_result = await session.execute(
            select(AssetPriceDaily)
            .where(AssetPriceDaily.symbol == "GC=F")
            .order_by(asc(AssetPriceDaily.trade_date))
        )
        gold_rows = gold_result.scalars().all()

    if not regime_rows or len(gold_rows) < 2:
        return {"regimes": [], "total_days": 0}

    # Build lookup maps
    regime_by_date: dict[date, str] = {
        r.ts: r.chosen_regime for r in regime_rows if r.chosen_regime
    }
    gold_by_date: dict[date, float] = {
        g.trade_date: g.close for g in gold_rows
    }

    # Compute daily returns tagged with regime
    returns_by_regime: dict[str, list[float]] = defaultdict(list)
    sorted_gold_dates = sorted(gold_by_date.keys())

    for i in range(1, len(sorted_gold_dates)):
        d = sorted_gold_dates[i]
        d_prev = sorted_gold_dates[i - 1]
        regime = regime_by_date.get(d)
        if regime is None:
            continue
        prev_close = gold_by_date[d_prev]
        if prev_close == 0:
            continue
        daily_ret = (gold_by_date[d] - prev_close) / prev_close * 100
        returns_by_regime[regime].append(daily_ret)

    # Compute stats per regime
    regime_stats = []
    total_days = 0
    for regime, rets in sorted(returns_by_regime.items()):
        n = len(rets)
        total_days += n
        if n == 0:
            continue
        avg_ret = sum(rets) / n
        win_count = sum(1 for r in rets if r > 0)
        win_rate = win_count / n * 100

        # Max drawdown: track cumulative return, find largest peak-to-trough
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for r in rets:
            cumulative += r
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd

        regime_stats.append({
            "regime": regime,
            "avg_daily_return_pct": round(avg_ret, 3),
            "win_rate": round(win_rate, 3),
            "max_drawdown_pct": round(max_dd, 3),
            "best_day_pct": round(max(rets), 3),
            "worst_day_pct": round(min(rets), 3),
            "total_days": n,
        })

    return {"regimes": regime_stats, "total_days": total_days}


@router.get("/transitions")
async def regime_transitions():
    """Gold price behaviour around regime transition points."""
    async with AsyncSessionLocal() as session:
        # Fetch all regime scores ordered by date ascending
        regime_result = await session.execute(
            select(RegimeScore).order_by(asc(RegimeScore.ts))
        )
        regime_rows = regime_result.scalars().all()

        # Fetch all gold prices ordered by date ascending
        gold_result = await session.execute(
            select(AssetPriceDaily)
            .where(AssetPriceDaily.symbol == "GC=F")
            .order_by(asc(AssetPriceDaily.trade_date))
        )
        gold_rows = gold_result.scalars().all()

    if len(regime_rows) < 2 or not gold_rows:
        return {"transitions": [], "total_transitions": 0}

    # Build gold price lookup: date -> close
    gold_by_date: dict[date, float] = {
        g.trade_date: g.close for g in gold_rows
    }
    sorted_gold_dates = sorted(gold_by_date.keys())

    # Build a mapping from date to its index in sorted_gold_dates for
    # quick forward-looking horizon searches
    date_to_idx: dict[date, int] = {
        d: i for i, d in enumerate(sorted_gold_dates)
    }

    # Detect transitions
    transition_data: dict[tuple[str, str], list[dict]] = defaultdict(list)
    total_transitions = 0

    for i in range(1, len(regime_rows)):
        prev_regime = regime_rows[i - 1].chosen_regime
        curr_regime = regime_rows[i].chosen_regime
        if not prev_regime or not curr_regime:
            continue
        if prev_regime == curr_regime:
            continue

        transition_date = regime_rows[i].ts
        base_idx = date_to_idx.get(transition_date)
        if base_idx is None:
            continue
        base_price = gold_by_date[transition_date]
        if base_price == 0:
            continue

        # Look ahead 5, 10, 20 trading days
        changes: dict[str, float | None] = {}
        for horizon, label in [(5, "5d"), (10, "10d"), (20, "20d")]:
            target_idx = base_idx + horizon
            if target_idx < len(sorted_gold_dates):
                future_price = gold_by_date[sorted_gold_dates[target_idx]]
                changes[label] = (future_price - base_price) / base_price * 100
            else:
                changes[label] = None

        key = (prev_regime, curr_regime)
        transition_data[key].append(changes)
        total_transitions += 1

    # Aggregate by (from_regime, to_regime)
    transitions_out = []
    for (from_r, to_r), items in sorted(transition_data.items()):
        n = len(items)
        avg_5d = _safe_avg([it["5d"] for it in items])
        avg_10d = _safe_avg([it["10d"] for it in items])
        avg_20d = _safe_avg([it["20d"] for it in items])

        transitions_out.append({
            "from_regime": from_r,
            "to_regime": to_r,
            "count": n,
            "avg_change_5d_pct": round(avg_5d, 3) if avg_5d is not None else None,
            "avg_change_10d_pct": round(avg_10d, 3) if avg_10d is not None else None,
            "avg_change_20d_pct": round(avg_20d, 3) if avg_20d is not None else None,
        })

    return {"transitions": transitions_out, "total_transitions": total_transitions}


@router.get("/audit-logs")
async def get_regime_audit_logs(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=500),
):
    """Return regime audit log entries for the last N days."""
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                *[
                    c
                    for c in RegimeAuditLog.__table__.columns
                ]
            )
            .where(RegimeAuditLog.computed_at >= cutoff)
            .order_by(desc(RegimeAuditLog.computed_at))
            .limit(limit)
        )
        rows = result.mappings().all()
        return {
            "logs": [
                {
                    "id": str(r["id"]),
                    "computed_at": r["computed_at"].isoformat() if r["computed_at"] else None,
                    "ts": str(r["ts"]) if r["ts"] else None,
                    "inputs_json": r["inputs_json"],
                    "indices_json": r["indices_json"],
                    "scores_json": r["scores_json"],
                    "raw_probs": r["raw_probs"],
                    "smoothed_probs": r["smoothed_probs"],
                    "chosen_regime": r["chosen_regime"],
                    "chosen_regime_raw": r["chosen_regime_raw"],
                    "chosen_note_fa": r["chosen_note_fa"],
                    "sources": r["sources"],
                    "staleness": r["staleness"],
                }
                for r in rows
            ],
            "count": len(rows),
        }


def _safe_avg(values: list[float | None]) -> float | None:
    """Compute average ignoring None values. Returns None if all are None."""
    filtered = [v for v in values if v is not None]
    if not filtered:
        return None
    return sum(filtered) / len(filtered)
