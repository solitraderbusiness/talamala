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

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import Date, case, cast, func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_admin
from api.database import get_db
from api.signal_aggregator.models import (
    ConsensusSnapshot,
    ConsensusView,
    DailyPerformance,
    MonthlyPerformance,
    ParsedSignal,
    RawPost,
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

    # Current price — try live fetch first so it matches the dashboard
    current_price: float | None = None
    try:
        from api.signal_aggregator.workers.price_checker import fetch_current_price
        price, _ = await fetch_current_price()
        current_price = price
    except Exception:
        pass

    if current_price is None:
        # Fallback: latest DB tick
        price_stmt = (
            select(SignalPriceTick)
            .where(SignalPriceTick.asset == "XAUUSD")
            .order_by(desc(SignalPriceTick.checked_at))
            .limit(1)
        )
        price_result = await db.execute(price_stmt)
        tick = price_result.scalar_one_or_none()
        current_price = tick.price if tick else None

    now_iso = datetime.now(timezone.utc).isoformat()

    return {
        "consensuses": consensuses,
        "updated_at": consensuses[0]["generated_at"] if consensuses else now_iso,
        "current_price": current_price,
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
    # Base query — join to get source name / accuracy / type / post URL
    base = (
        select(
            ParsedSignal,
            SignalSource.name.label("source_name"),
            SignalSource.accuracy_rate.label("source_accuracy"),
            SignalSource.type.label("source_type"),
            RawPost.url.label("post_url"),
        )
        .join(SignalSource, ParsedSignal.source_id == SignalSource.id)
        .outerjoin(RawPost, ParsedSignal.raw_post_id == RawPost.id)
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
        d["source_type"] = row.source_type
        d["url"] = row.post_url
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
    """Return the current XAUUSD price.

    Tries a live BrsAPI fetch first (same source as the dashboard) so
    both pages always show the same number.  Falls back to the most
    recent ``signal_price_ticks`` row if the live call fails.
    """
    from api.signal_aggregator.workers.price_checker import fetch_current_price

    # Try live price first (same source as dashboard /api/prices)
    try:
        price, source = await fetch_current_price()
        if price is not None:
            return {
                "asset": "XAUUSD",
                "price": price,
                "source": source,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
    except Exception:
        logger.debug("Live price fetch failed — falling back to DB tick")

    # Fallback: latest DB tick
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


# ── Pydantic schemas for signal source admin ──────────────────────────

class SignalSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., pattern=r"^(telegram|tradingview|website|forum)$")
    telegram_channel_id: str | None = None
    telegram_channel_name: str | None = None
    url: str | None = None
    active: bool = True

class SignalSourceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    type: str | None = Field(None, pattern=r"^(telegram|tradingview|website|forum)$")
    telegram_channel_id: str | None = None
    telegram_channel_name: str | None = None
    url: str | None = None
    active: bool | None = None
    current_weight: float | None = Field(None, ge=0.0, le=1.0)


# ── 9.  Admin CRUD for signal sources ─────────────────────────────────

_SOURCE_COLUMNS = [
    "id", "name", "type", "telegram_channel_id", "telegram_channel_name",
    "url", "active", "added_at", "total_signals", "correct_signals",
    "wrong_signals", "expired_signals", "accuracy_rate", "avg_profit_pips",
    "avg_loss_pips", "profit_factor", "current_weight", "last_signal_at",
]


@router.get("/sources/admin", dependencies=[Depends(get_current_admin)])
async def list_signal_sources_admin(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List all signal sources with full details (admin only)."""
    stmt = select(SignalSource).order_by(desc(SignalSource.current_weight))
    result = await db.execute(stmt)
    rows = result.scalars().all()

    items = [_row_to_dict(src, columns=_SOURCE_COLUMNS) for src in rows]
    return {"items": items, "total": len(items)}


@router.get("/sources/admin/{source_id}", dependencies=[Depends(get_current_admin)])
async def get_signal_source_admin(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a single signal source by ID (admin only)."""
    result = await db.execute(
        select(SignalSource).where(SignalSource.id == source_id)
    )
    src = result.scalar_one_or_none()
    if src is None:
        raise HTTPException(status_code=404, detail="Signal source not found")

    data = _row_to_dict(src, columns=_SOURCE_COLUMNS)

    # Include signal counts by status
    status_q = (
        select(
            ParsedSignal.status,
            func.count(ParsedSignal.id),
        )
        .where(ParsedSignal.source_id == source_id)
        .group_by(ParsedSignal.status)
    )
    status_result = await db.execute(status_q)
    data["signal_counts_by_status"] = {
        row[0]: row[1] for row in status_result.all()
    }

    return data


@router.post("/sources/admin", dependencies=[Depends(get_current_admin)])
async def create_signal_source(
    body: SignalSourceCreate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new signal source (admin only)."""
    src = SignalSource(
        name=body.name,
        type=body.type,
        telegram_channel_id=body.telegram_channel_id,
        telegram_channel_name=body.telegram_channel_name,
        url=body.url,
        active=body.active,
    )
    db.add(src)
    await db.flush()
    await db.refresh(src)
    await db.commit()

    return _row_to_dict(src, columns=_SOURCE_COLUMNS)


@router.put("/sources/admin/{source_id}", dependencies=[Depends(get_current_admin)])
async def update_signal_source(
    source_id: UUID,
    body: SignalSourceUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update a signal source (admin only)."""
    result = await db.execute(
        select(SignalSource).where(SignalSource.id == source_id)
    )
    src = result.scalar_one_or_none()
    if src is None:
        raise HTTPException(status_code=404, detail="Signal source not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(src, field, value)

    await db.flush()
    await db.refresh(src)
    await db.commit()

    return _row_to_dict(src, columns=_SOURCE_COLUMNS)


# ── 10. GET /sources/deep-stats/{source_id} ─────────────────────────

@router.get("/sources/deep-stats/{source_id}")
async def get_source_deep_stats(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return deep statistics for a specific signal source:
    accuracy by timeframe, risk/reward ratio, streak, best/worst trades.
    """
    # Verify source exists
    src_result = await db.execute(
        select(SignalSource).where(SignalSource.id == source_id)
    )
    src = src_result.scalar_one_or_none()
    if src is None:
        raise HTTPException(status_code=404, detail="Signal source not found")

    # All closed signals for this source
    closed_statuses = ("tp1_hit", "tp2_hit", "tp3_hit", "sl_hit", "expired")
    win_statuses = ("tp1_hit", "tp2_hit", "tp3_hit")

    signals_q = (
        select(ParsedSignal)
        .where(
            ParsedSignal.source_id == source_id,
            ParsedSignal.status.in_(closed_statuses),
        )
        .order_by(desc(ParsedSignal.parsed_at))
    )
    signals_result = await db.execute(signals_q)
    closed_signals = signals_result.scalars().all()

    # Accuracy by timeframe
    timeframe_stats: dict[str, dict] = {}
    for sig in closed_signals:
        tf = sig.timeframe or "unknown"
        if tf not in timeframe_stats:
            timeframe_stats[tf] = {"wins": 0, "total": 0, "pips": []}
        timeframe_stats[tf]["total"] += 1
        if sig.status in win_statuses:
            timeframe_stats[tf]["wins"] += 1
        if sig.outcome_pips is not None:
            timeframe_stats[tf]["pips"].append(float(sig.outcome_pips))

    timeframe_accuracy = []
    for tf, stats in timeframe_stats.items():
        accuracy = round(stats["wins"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0
        avg_pips = round(sum(stats["pips"]) / len(stats["pips"]), 1) if stats["pips"] else 0
        timeframe_accuracy.append({
            "timeframe": tf,
            "accuracy_pct": accuracy,
            "total_signals": stats["total"],
            "wins": stats["wins"],
            "avg_pips": avg_pips,
        })
    timeframe_accuracy.sort(key=lambda x: x["total_signals"], reverse=True)

    # Risk/reward ratio
    profits = [float(s.outcome_pips) for s in closed_signals if s.outcome_pips and s.outcome_pips > 0]
    losses = [abs(float(s.outcome_pips)) for s in closed_signals if s.outcome_pips and s.outcome_pips < 0]
    avg_profit = round(sum(profits) / len(profits), 1) if profits else 0
    avg_loss = round(sum(losses) / len(losses), 1) if losses else 0
    risk_reward = round(avg_profit / avg_loss, 2) if avg_loss > 0 else None

    # Current streak (consecutive wins or losses from most recent)
    streak_count = 0
    streak_type = None
    for sig in closed_signals:
        is_win = sig.status in win_statuses
        current_type = "win" if is_win else "loss"
        if streak_type is None:
            streak_type = current_type
            streak_count = 1
        elif current_type == streak_type:
            streak_count += 1
        else:
            break

    # Best and worst trades
    sorted_by_pips = sorted(
        [s for s in closed_signals if s.outcome_pips is not None],
        key=lambda s: float(s.outcome_pips),
        reverse=True,
    )
    best_trades = [
        {
            "pips": round(float(s.outcome_pips), 1),
            "direction": s.direction,
            "timeframe": s.timeframe,
            "parsed_at": s.parsed_at.isoformat() if s.parsed_at else None,
        }
        for s in sorted_by_pips[:3]
    ]
    worst_trades = [
        {
            "pips": round(float(s.outcome_pips), 1),
            "direction": s.direction,
            "timeframe": s.timeframe,
            "parsed_at": s.parsed_at.isoformat() if s.parsed_at else None,
        }
        for s in sorted_by_pips[-3:] if s.outcome_pips and float(s.outcome_pips) < 0
    ]

    return {
        "source_id": str(source_id),
        "source_name": src.name,
        "timeframe_accuracy": timeframe_accuracy,
        "risk_reward_ratio": risk_reward,
        "avg_profit_pips": avg_profit,
        "avg_loss_pips": avg_loss,
        "streak": {"count": streak_count, "type": streak_type},
        "best_trades": best_trades,
        "worst_trades": worst_trades,
        "total_closed": len(closed_signals),
    }


# ── 11. GET /consensus/agreement ─────────────────────────────────────

@router.get("/consensus/agreement")
async def get_consensus_agreement(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """When top N analysts agree on direction, what is the historical accuracy?

    Looks at periods where the top-weighted sources all issued the same
    direction signal, and measures the outcome.
    """
    # Get top 5 sources by weight
    top_src_q = (
        select(SignalSource)
        .where(SignalSource.active.is_(True))
        .order_by(desc(SignalSource.current_weight))
        .limit(5)
    )
    top_result = await db.execute(top_src_q)
    top_sources = top_result.scalars().all()

    if len(top_sources) < 2:
        return {
            "agreement_levels": [],
            "message": "Not enough active sources for agreement analysis",
        }

    top_ids = [s.id for s in top_sources]

    # Get all closed signals from top sources grouped by date
    closed_statuses = ("tp1_hit", "tp2_hit", "tp3_hit", "sl_hit", "expired")
    win_statuses = ("tp1_hit", "tp2_hit", "tp3_hit")

    signals_q = (
        select(ParsedSignal)
        .where(
            ParsedSignal.source_id.in_(top_ids),
            ParsedSignal.status.in_(closed_statuses),
        )
        .order_by(ParsedSignal.parsed_at)
    )
    signals_result = await db.execute(signals_q)
    all_signals = signals_result.scalars().all()

    # Group signals by date
    from collections import defaultdict
    daily_signals: dict[str, list] = defaultdict(list)
    for sig in all_signals:
        if sig.parsed_at:
            day_key = sig.parsed_at.strftime("%Y-%m-%d")
            daily_signals[day_key].append(sig)

    # For each threshold (2, 3, 4, 5 agreeing), compute accuracy
    agreement_levels = []
    for threshold in range(2, min(6, len(top_sources) + 1)):
        matching_days = 0
        correct_days = 0

        for day_key, signals in daily_signals.items():
            # Count BUY vs SELL among top sources for this day
            buy_count = sum(1 for s in signals if s.direction == "BUY")
            sell_count = sum(1 for s in signals if s.direction == "SELL")

            agreed_direction = None
            if buy_count >= threshold:
                agreed_direction = "BUY"
            elif sell_count >= threshold:
                agreed_direction = "SELL"

            if agreed_direction is None:
                continue

            matching_days += 1
            # Check if the agreed direction was correct
            day_wins = sum(1 for s in signals if s.status in win_statuses and s.direction == agreed_direction)
            day_total = sum(1 for s in signals if s.direction == agreed_direction)
            if day_total > 0 and day_wins / day_total >= 0.5:
                correct_days += 1

        accuracy = round(correct_days / matching_days * 100, 1) if matching_days > 0 else 0
        agreement_levels.append({
            "min_agree": threshold,
            "occurrences": matching_days,
            "accuracy_pct": accuracy,
        })

    return {
        "top_sources": [{"id": str(s.id), "name": s.name, "weight": s.current_weight} for s in top_sources],
        "agreement_levels": agreement_levels,
    }


@router.delete("/sources/admin/{source_id}", dependencies=[Depends(get_current_admin)])
async def delete_signal_source(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete a signal source and all related data (admin only).

    CASCADE will remove raw_posts and parsed_signals linked to this source.
    """
    result = await db.execute(
        select(SignalSource).where(SignalSource.id == source_id)
    )
    src = result.scalar_one_or_none()
    if src is None:
        raise HTTPException(status_code=404, detail="Signal source not found")

    await db.delete(src)
    await db.commit()

    return {"status": "deleted"}
