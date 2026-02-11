"""Performance tracker for the Signal Aggregator.

Provides daily and monthly aggregation of signal outcomes.  The daily
aggregator is designed to run at 22:00 UTC; the monthly aggregator
rolls up daily rows at month-end.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, delete, func, select

from api.database import AsyncSessionLocal
from api.signal_aggregator.config import CONSENSUS_TIMEFRAMES
from api.signal_aggregator.models import (
    ConsensusSnapshot,
    DailyPerformance,
    MonthlyPerformance,
    ParsedSignal,
    SignalSource,
)

logger = logging.getLogger("signal_aggregator.performance")

# Mapping from consensus view -> signal timeframes it covers, used to
# bucket signals into view-level stats.
_VIEW_TIMEFRAMES: dict[str, list[str]] = CONSENSUS_TIMEFRAMES

_WINNING_STATUSES = {"tp1_hit", "tp2_hit", "tp3_hit"}
_LOSING_STATUSES = {"sl_hit"}
_CLOSED_STATUSES = _WINNING_STATUSES | _LOSING_STATUSES | {"expired"}


async def aggregate_daily(
    target_date: date | None = None,
    asset: str = "XAUUSD",
) -> DailyPerformance | None:
    """Compute daily performance for *target_date* (defaults to today
    UTC) and upsert into ``signal_daily_performance``.

    Returns the persisted ``DailyPerformance`` row."""
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    day_start = datetime(
        target_date.year, target_date.month, target_date.day,
        tzinfo=timezone.utc,
    )
    day_end = day_start + timedelta(days=1)

    async with AsyncSessionLocal() as session:
        # All signals that were parsed on this day
        result = await session.execute(
            select(ParsedSignal).where(
                ParsedSignal.asset == asset,
                ParsedSignal.parsed_at >= day_start,
                ParsedSignal.parsed_at < day_end,
            )
        )
        all_signals = result.scalars().all()

        # Signals that closed (outcome_at) on this day
        result_closed = await session.execute(
            select(ParsedSignal).where(
                ParsedSignal.asset == asset,
                ParsedSignal.outcome_at >= day_start,
                ParsedSignal.outcome_at < day_end,
                ParsedSignal.status.in_(_CLOSED_STATUSES),
            )
        )
        closed_signals = result_closed.scalars().all()

    total_signals = len(all_signals)
    closed_count = len(closed_signals)

    winning = [s for s in closed_signals if s.status in _WINNING_STATUSES]
    losing = [s for s in closed_signals if s.status in _LOSING_STATUSES]
    expired = [s for s in closed_signals if s.status == "expired"]

    win_rate: float | None = None
    if (len(winning) + len(losing)) > 0:
        win_rate = len(winning) / (len(winning) + len(losing))

    # Pips
    profit_pips_list = [
        s.outcome_pips for s in winning if s.outcome_pips is not None
    ]
    loss_pips_list = [
        s.outcome_pips for s in losing if s.outcome_pips is not None
    ]
    all_pips = [
        s.outcome_pips for s in closed_signals if s.outcome_pips is not None
    ]

    total_profit_pips = sum(profit_pips_list)
    total_loss_pips = sum(abs(p) for p in loss_pips_list)
    net_pips = total_profit_pips - total_loss_pips

    best_pips = max(all_pips) if all_pips else None
    worst_pips = min(all_pips) if all_pips else None
    avg_pips = (sum(all_pips) / len(all_pips)) if all_pips else None

    # Cumulative pips — add to previous day's cumulative
    cumulative_pips = net_pips
    async with AsyncSessionLocal() as session:
        prev_result = await session.execute(
            select(DailyPerformance.cumulative_pips)
            .where(
                DailyPerformance.asset == asset,
                DailyPerformance.date < target_date,
            )
            .order_by(DailyPerformance.date.desc())
            .limit(1)
        )
        prev_row = prev_result.scalar_one_or_none()
        if prev_row is not None:
            cumulative_pips += prev_row

    # Consensus accuracy — how many consensus calls were correct today
    consensus_accuracy = await _consensus_accuracy_for_day(
        asset, day_start, day_end
    )

    # ── Timeframe view breakdown ────────────────────────────────────
    view_stats: dict[str, dict] = {}
    for view, timeframes in _VIEW_TIMEFRAMES.items():
        view_sigs = [s for s in closed_signals if s.timeframe in timeframes]
        view_wins = [s for s in view_sigs if s.status in _WINNING_STATUSES]
        view_losses = [s for s in view_sigs if s.status in _LOSING_STATUSES]
        v_total = len(view_wins) + len(view_losses)
        view_stats[view] = {
            "count": len(view_sigs),
            "win_rate": (len(view_wins) / v_total) if v_total > 0 else None,
        }

    # ── Upsert ──────────────────────────────────────────────────────
    async with AsyncSessionLocal() as session:
        # Remove existing row for this date+asset to allow re-run
        await session.execute(
            delete(DailyPerformance).where(
                DailyPerformance.date == target_date,
                DailyPerformance.asset == asset,
            )
        )

        perf = DailyPerformance(
            date=target_date,
            asset=asset,
            total_signals=total_signals,
            closed_signals=closed_count,
            winning_signals=len(winning),
            losing_signals=len(losing),
            expired_signals=len(expired),
            win_rate=win_rate,
            total_profit_pips=round(total_profit_pips, 2),
            total_loss_pips=round(total_loss_pips, 2),
            net_pips=round(net_pips, 2),
            cumulative_pips=round(cumulative_pips, 2),
            best_signal_pips=round(best_pips, 2) if best_pips is not None else None,
            worst_signal_pips=round(worst_pips, 2) if worst_pips is not None else None,
            avg_signal_pips=round(avg_pips, 2) if avg_pips is not None else None,
            consensus_accuracy=consensus_accuracy,
            scalp_signals=view_stats["scalp"]["count"],
            scalp_win_rate=view_stats["scalp"]["win_rate"],
            intraday_signals=view_stats["intraday"]["count"],
            intraday_win_rate=view_stats["intraday"]["win_rate"],
            swing_signals=view_stats["swing"]["count"],
            swing_win_rate=view_stats["swing"]["win_rate"],
            position_signals=view_stats["position"]["count"],
            position_win_rate=view_stats["position"]["win_rate"],
        )

        session.add(perf)
        await session.commit()
        await session.refresh(perf)

    logger.info(
        "Daily performance for %s: signals=%d, closed=%d, win_rate=%.2f, net_pips=%.1f",
        target_date.isoformat(),
        total_signals,
        closed_count,
        win_rate or 0.0,
        net_pips,
    )
    return perf


async def _consensus_accuracy_for_day(
    asset: str, day_start: datetime, day_end: datetime
) -> float | None:
    """Calculate what percentage of consensus snapshots generated today
    correctly predicted the eventual market direction (based on closed
    signals within the same view)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ConsensusSnapshot).where(
                ConsensusSnapshot.asset == asset,
                ConsensusSnapshot.generated_at >= day_start,
                ConsensusSnapshot.generated_at < day_end,
            )
        )
        snapshots = result.scalars().all()

    if not snapshots:
        return None

    correct = 0
    total_with_outcome = 0

    async with AsyncSessionLocal() as session:
        for snap in snapshots:
            if snap.consensus_direction == "NEUTRAL":
                continue
            timeframes = snap.timeframes_included or []
            if not timeframes:
                continue

            # Count closed signals from this view's timeframes today
            result = await session.execute(
                select(ParsedSignal).where(
                    ParsedSignal.asset == asset,
                    ParsedSignal.timeframe.in_(timeframes),
                    ParsedSignal.outcome_at >= day_start,
                    ParsedSignal.outcome_at < day_end,
                    ParsedSignal.status.in_(_CLOSED_STATUSES),
                )
            )
            closed = result.scalars().all()
            if not closed:
                continue

            wins = sum(1 for s in closed if s.status in _WINNING_STATUSES)
            losses = sum(1 for s in closed if s.status in _LOSING_STATUSES)

            if wins + losses == 0:
                continue

            # If consensus was BUY and more wins than losses among BUY
            # signals => correct (and vice versa for SELL).
            buy_wins = sum(
                1 for s in closed
                if s.direction == "BUY" and s.status in _WINNING_STATUSES
            )
            sell_wins = sum(
                1 for s in closed
                if s.direction == "SELL" and s.status in _WINNING_STATUSES
            )

            total_with_outcome += 1
            if snap.consensus_direction == "BUY" and buy_wins >= sell_wins:
                correct += 1
            elif snap.consensus_direction == "SELL" and sell_wins >= buy_wins:
                correct += 1

    if total_with_outcome == 0:
        return None
    return round(correct / total_with_outcome, 4)


async def aggregate_monthly(
    year: int,
    month: int,
    asset: str = "XAUUSD",
) -> MonthlyPerformance | None:
    """Roll up daily performance rows for a given month into a single
    ``MonthlyPerformance`` row."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DailyPerformance).where(
                DailyPerformance.asset == asset,
                func.extract("year", DailyPerformance.date) == year,
                func.extract("month", DailyPerformance.date) == month,
            ).order_by(DailyPerformance.date.asc())
        )
        daily_rows = result.scalars().all()

    if not daily_rows:
        logger.info("No daily performance rows for %04d-%02d", year, month)
        return None

    total_signals = sum(d.total_signals for d in daily_rows)
    closed_signals = sum(d.closed_signals for d in daily_rows)
    total_winning = sum(d.winning_signals for d in daily_rows)
    total_losing = sum(d.losing_signals for d in daily_rows)
    net_pips_list = [d.net_pips for d in daily_rows]
    net_pips = sum(net_pips_list)

    win_rate: float | None = None
    if (total_winning + total_losing) > 0:
        win_rate = total_winning / (total_winning + total_losing)

    best_day = max(net_pips_list) if net_pips_list else None
    worst_day = min(net_pips_list) if net_pips_list else None
    avg_daily = (net_pips / len(daily_rows)) if daily_rows else None

    # Max drawdown: largest peak-to-trough in cumulative pips within
    # the month
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for d in daily_rows:
        cumulative += d.net_pips
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd

    # Profit factor
    total_profit = sum(d.total_profit_pips for d in daily_rows)
    total_loss = sum(d.total_loss_pips for d in daily_rows)
    profit_factor = (total_profit / total_loss) if total_loss > 0 else None

    # Simple Sharpe approximation (daily net pips)
    sharpe: float | None = None
    if len(net_pips_list) > 1:
        import statistics

        mean_daily = statistics.mean(net_pips_list)
        std_daily = statistics.stdev(net_pips_list)
        if std_daily > 0:
            sharpe = round(mean_daily / std_daily * (252 ** 0.5), 4)

    # Cumulative pips (end of month)
    cumulative_pips = daily_rows[-1].cumulative_pips if daily_rows else 0.0

    # Consensus accuracy average
    ca_values = [d.consensus_accuracy for d in daily_rows if d.consensus_accuracy is not None]
    consensus_accuracy = (sum(ca_values) / len(ca_values)) if ca_values else None

    # Active sources count
    async with AsyncSessionLocal() as session:
        src_result = await session.execute(
            select(func.count(SignalSource.id)).where(
                SignalSource.active.is_(True),
            )
        )
        active_sources = src_result.scalar_one_or_none() or 0

    # Total consensus calls this month
    month_start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        month_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        month_end = datetime(year, month + 1, 1, tzinfo=timezone.utc)

    async with AsyncSessionLocal() as session:
        cc_result = await session.execute(
            select(func.count(ConsensusSnapshot.id)).where(
                ConsensusSnapshot.asset == asset,
                ConsensusSnapshot.generated_at >= month_start,
                ConsensusSnapshot.generated_at < month_end,
            )
        )
        total_consensus = cc_result.scalar_one_or_none() or 0

    # ── Upsert ──────────────────────────────────────────────────────
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(MonthlyPerformance).where(
                MonthlyPerformance.year == year,
                MonthlyPerformance.month == month,
                MonthlyPerformance.asset == asset,
            )
        )

        perf = MonthlyPerformance(
            year=year,
            month=month,
            asset=asset,
            total_signals=total_signals,
            closed_signals=closed_signals,
            win_rate=win_rate,
            net_pips=round(net_pips, 2),
            cumulative_pips=round(cumulative_pips, 2),
            best_day_pips=round(best_day, 2) if best_day is not None else None,
            worst_day_pips=round(worst_day, 2) if worst_day is not None else None,
            avg_daily_pips=round(avg_daily, 2) if avg_daily is not None else None,
            max_drawdown_pips=round(max_dd, 2),
            profit_factor=round(profit_factor, 4) if profit_factor is not None else None,
            sharpe_ratio=sharpe,
            total_consensus_calls=total_consensus,
            consensus_accuracy=round(consensus_accuracy, 4) if consensus_accuracy is not None else None,
            active_sources=active_sources,
        )

        session.add(perf)
        await session.commit()
        await session.refresh(perf)

    logger.info(
        "Monthly performance for %04d-%02d: signals=%d, closed=%d, "
        "win_rate=%.2f, net_pips=%.1f, sharpe=%s",
        year,
        month,
        total_signals,
        closed_signals,
        win_rate or 0.0,
        net_pips,
        sharpe,
    )
    return perf
