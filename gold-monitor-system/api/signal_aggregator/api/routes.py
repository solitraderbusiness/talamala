"""
Signal Aggregator API routes — consensus, signals, performance, sources,
price ticks, and journal endpoints for the AI-analysis dashboard.

Prefix is set to "" here; the parent ``main.py`` includes this router
under ``/api/ai-analysis``.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, case, cast, func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.signal_aggregator.models import (
    ConsensusSnapshot,
    ConsensusView,
    DailyPerformance,
    MonthlyPerformance,
    ParsedSignal,
    SignalPriceTick,
    SignalSource,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["signal-aggregator"])


# ── Serialisation helpers ────────────────────────────────────────────────

def _ser(value: Any) -> Any:
    """Convert a single value to a JSON-safe primitive."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _row_to_dict(row: Any, columns: list[str] | None = None) -> dict[str, Any]:
    """Convert an ORM model instance to a JSON-serialisable dict.

    If *columns* is supplied only those attributes are included;
    otherwise every column from ``__table__`` is used.
    """
    if columns:
        return {col: _ser(getattr(row, col, None)) for col in columns}
    return {
        col.name: _ser(getattr(row, col.name, None))
        for col in row.__table__.columns
    }


# ── 1.  GET /consensus/latest ───────────────────────────────────────────

@router.get("/consensus/latest")
async def get_consensus_latest(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return the most recent consensus snapshot for each of the four
    timeframe views (scalp, intraday, swing, position).
    """
    views = [v.value for v in ConsensusView]
    consensuses: list[dict[str, Any]] = []

    for view in views:
        # Sub-query: most recent generated_at for this view
        sub = (
            select(func.max(ConsensusSnapshot.generated_at))
            .where(ConsensusSnapshot.consensus_view == view)
            .scalar_subquery()
        )
        stmt = (
            select(ConsensusSnapshot)
            .where(
                ConsensusSnapshot.consensus_view == view,
                ConsensusSnapshot.generated_at == sub,
            )
            .limit(1)
        )
        result = await db.execute(stmt)
        snap = result.scalar_one_or_none()
        if snap is not None:
            consensuses.append(_row_to_dict(snap))

    # Current price from most recent tick
    price_stmt = (
        select(SignalPriceTick)
        .where(SignalPriceTick.asset == "XAUUSD")
        .order_by(desc(SignalPriceTick.checked_at))
        .limit(1)
    )
    price_result = await db.execute(price_stmt)
    tick = price_result.scalar_one_or_none()

    now_iso = datetime.now(timezone.utc).isoformat()

    return {
        "consensuses": consensuses,
        "updated_at": consensuses[0]["generated_at"] if consensuses else now_iso,
        "current_price": tick.price if tick else None,
    }


# ── 2.  GET /signals/recent ─────────────────────────────────────────────

@router.get("/signals/recent")
async def get_signals_recent(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str = Query("all"),
    timeframe: str = Query("all"),
    source_id: str = Query("all"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return recent parsed signals with optional filters, joined with
    source name and accuracy.
    """
    # Base query — join to get source name / accuracy
    base = (
        select(
            ParsedSignal,
            SignalSource.name.label("source_name"),
            SignalSource.accuracy_rate.label("source_accuracy"),
        )
        .join(SignalSource, ParsedSignal.source_id == SignalSource.id)
    )

    # Apply filters
    if status != "all":
        base = base.where(ParsedSignal.status == status)
    if timeframe != "all":
        base = base.where(ParsedSignal.timeframe == timeframe)
    if source_id != "all":
        base = base.where(ParsedSignal.source_id == source_id)

    # Count total (before pagination)
    count_stmt = select(func.count()).select_from(base.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Fetch page
    items_stmt = (
        base
        .order_by(desc(ParsedSignal.parsed_at))
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(items_stmt)
    rows = result.all()

    items: list[dict[str, Any]] = []
    for row in rows:
        signal = row[0]  # ParsedSignal instance
        d = _row_to_dict(signal)
        d["source_name"] = row.source_name
        d["source_accuracy"] = row.source_accuracy
        items.append(d)

    return {"items": items, "total": total}


# ── 3.  GET /performance/summary ────────────────────────────────────────

@router.get("/performance/summary")
async def get_performance_summary(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Aggregate key performance metrics across all parsed signals and
    signal sources.
    """
    # Total signals
    total_q = select(func.count(ParsedSignal.id))
    total_result = await db.execute(total_q)
    total_signals = total_result.scalar_one()

    # Win / loss counts (non-active, non-cancelled signals that have an outcome)
    closed_statuses = ("tp1_hit", "tp2_hit", "tp3_hit", "sl_hit", "expired")
    win_statuses = ("tp1_hit", "tp2_hit", "tp3_hit")

    closed_q = (
        select(func.count(ParsedSignal.id))
        .where(ParsedSignal.status.in_(closed_statuses))
    )
    closed_result = await db.execute(closed_q)
    closed_signals = closed_result.scalar_one()

    win_q = (
        select(func.count(ParsedSignal.id))
        .where(ParsedSignal.status.in_(win_statuses))
    )
    win_result = await db.execute(win_q)
    winning_signals = win_result.scalar_one()

    overall_win_rate = (
        round(winning_signals / closed_signals * 100, 2)
        if closed_signals > 0
        else 0.0
    )

    # Net pips (all time) and avg pips per signal
    pips_q = select(
        func.coalesce(func.sum(ParsedSignal.outcome_pips), 0.0),
        func.coalesce(func.avg(ParsedSignal.outcome_pips), 0.0),
    ).where(ParsedSignal.outcome_pips.is_not(None))
    pips_result = await db.execute(pips_q)
    pips_row = pips_result.one()
    net_pips_all_time = round(float(pips_row[0]), 2)
    avg_pips_per_signal = round(float(pips_row[1]), 2)

    # Profit factor = gross profit / gross loss
    profit_q = (
        select(func.coalesce(func.sum(ParsedSignal.outcome_pips), 0.0))
        .where(ParsedSignal.outcome_pips > 0)
    )
    loss_q = (
        select(func.coalesce(func.abs(func.sum(ParsedSignal.outcome_pips)), 0.0))
        .where(ParsedSignal.outcome_pips < 0)
    )
    profit_result = await db.execute(profit_q)
    loss_result = await db.execute(loss_q)
    gross_profit = float(profit_result.scalar_one())
    gross_loss = float(loss_result.scalar_one())
    profit_factor = (
        round(gross_profit / gross_loss, 2) if gross_loss > 0 else None
    )

    # Max drawdown from daily performance
    drawdown_q = select(
        func.coalesce(func.min(DailyPerformance.cumulative_pips), 0.0),
    )
    drawdown_result = await db.execute(drawdown_q)
    # max_drawdown is the lowest cumulative point (most negative)
    max_drawdown_pips = round(float(drawdown_result.scalar_one()), 2)

    # Active sources
    active_src_q = select(func.count(SignalSource.id)).where(
        SignalSource.active.is_(True),
    )
    active_result = await db.execute(active_src_q)
    active_sources = active_result.scalar_one()

    # Average signals per day
    day_count_q = select(func.count(func.distinct(DailyPerformance.date)))
    day_count_result = await db.execute(day_count_q)
    day_count = day_count_result.scalar_one()
    avg_signals_per_day = (
        round(total_signals / day_count, 2) if day_count > 0 else 0.0
    )

    return {
        "total_signals": total_signals,
        "overall_win_rate": overall_win_rate,
        "net_pips_all_time": net_pips_all_time,
        "profit_factor": profit_factor,
        "avg_pips_per_signal": avg_pips_per_signal,
        "max_drawdown_pips": max_drawdown_pips,
        "active_sources": active_sources,
        "avg_signals_per_day": avg_signals_per_day,
    }


# ── 4.  GET /performance/daily ──────────────────────────────────────────

@router.get("/performance/daily")
async def get_performance_daily(
    from_date: date = Query(alias="from", default=None),
    to_date: date = Query(alias="to", default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return ``signal_daily_performance`` rows for a date range."""
    stmt = select(DailyPerformance).order_by(DailyPerformance.date)

    if from_date is not None:
        stmt = stmt.where(DailyPerformance.date >= from_date)
    if to_date is not None:
        stmt = stmt.where(DailyPerformance.date <= to_date)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    return {"items": [_row_to_dict(r) for r in rows]}


# ── 5.  GET /performance/monthly ────────────────────────────────────────

@router.get("/performance/monthly")
async def get_performance_monthly(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return all ``signal_monthly_performance`` rows."""
    stmt = (
        select(MonthlyPerformance)
        .order_by(MonthlyPerformance.year, MonthlyPerformance.month)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return {"items": [_row_to_dict(r) for r in rows]}


# ── 6.  GET /sources/leaderboard ────────────────────────────────────────

@router.get("/sources/leaderboard")
async def get_sources_leaderboard(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return signal sources ranked by ``current_weight`` descending."""
    stmt = (
        select(SignalSource)
        .order_by(desc(SignalSource.current_weight))
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    items: list[dict[str, Any]] = []
    for src in rows:
        d = _row_to_dict(src, columns=[
            "id",
            "name",
            "type",
            "active",
            "total_signals",
            "correct_signals",
            "wrong_signals",
            "expired_signals",
            "accuracy_rate",
            "avg_profit_pips",
            "avg_loss_pips",
            "profit_factor",
            "current_weight",
            "last_signal_at",
            "added_at",
        ])
        items.append(d)

    return {"items": items}


# ── 7.  GET /price/current ──────────────────────────────────────────────

@router.get("/price/current")
async def get_price_current(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return the most recent XAUUSD price tick."""
    stmt = (
        select(SignalPriceTick)
        .where(SignalPriceTick.asset == "XAUUSD")
        .order_by(desc(SignalPriceTick.checked_at))
        .limit(1)
    )
    result = await db.execute(stmt)
    tick = result.scalar_one_or_none()

    if tick is None:
        return {
            "asset": "XAUUSD",
            "price": None,
            "source": None,
            "checked_at": None,
        }

    return {
        "asset": tick.asset,
        "price": tick.price,
        "source": tick.source,
        "checked_at": tick.checked_at.isoformat() if tick.checked_at else None,
    }


# ── 8.  GET /journal/recent ─────────────────────────────────────────────

@router.get("/journal/recent")
async def get_journal_recent(
    limit: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return recent daily journal summaries generated from
    ``signal_daily_performance`` data.

    Each entry includes the day's stats and a short textual summary.
    """
    stmt = (
        select(DailyPerformance)
        .order_by(desc(DailyPerformance.date))
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    items: list[dict[str, Any]] = []
    for day in rows:
        closed = day.closed_signals or 0
        wins = day.winning_signals or 0
        losses = day.losing_signals or 0
        net = day.net_pips or 0.0
        win_rate = day.win_rate

        # Build a concise human-readable summary line
        if closed == 0:
            summary = "No closed signals on this day."
        else:
            direction = "positive" if net >= 0 else "negative"
            summary = (
                f"{closed} signals closed — {wins}W / {losses}L"
                f" — net {net:+.1f} pips ({direction} day)"
            )
            if win_rate is not None:
                summary += f" — win rate {win_rate:.0f}%"

        entry = _row_to_dict(day, columns=[
            "id",
            "date",
            "asset",
            "total_signals",
            "closed_signals",
            "winning_signals",
            "losing_signals",
            "expired_signals",
            "win_rate",
            "total_profit_pips",
            "total_loss_pips",
            "net_pips",
            "cumulative_pips",
            "best_signal_pips",
            "worst_signal_pips",
            "avg_signal_pips",
            "consensus_accuracy",
            "scalp_signals",
            "scalp_win_rate",
            "intraday_signals",
            "intraday_win_rate",
            "swing_signals",
            "swing_win_rate",
            "position_signals",
            "position_win_rate",
        ])
        entry["summary"] = summary
        items.append(entry)

    return {"items": items}
