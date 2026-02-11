"""Daily journal generator for the Signal Aggregator.

Builds a human-readable daily analysis summary from performance data
using templates (no external API calls) to keep costs at zero.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import func, select

from api.database import AsyncSessionLocal
from api.signal_aggregator.models import (
    ConsensusSnapshot,
    DailyPerformance,
    ParsedSignal,
    SignalSource,
)

logger = logging.getLogger("signal_aggregator.journal")


def _trend_emoji(value: float) -> str:
    """Return a plain-text trend indicator."""
    if value > 0:
        return "(+)"
    elif value < 0:
        return "(-)"
    return "(=)"


def _pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


async def _get_top_sources(target_date: date, limit: int = 5) -> list[dict]:
    """Return the top sources by accuracy for the period ending on
    *target_date*."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SignalSource)
            .where(SignalSource.active.is_(True))
            .order_by(SignalSource.accuracy_rate.desc().nullslast())
            .limit(limit)
        )
        sources = result.scalars().all()

    return [
        {
            "name": s.name,
            "type": s.type,
            "accuracy": s.accuracy_rate,
            "total": s.total_signals,
            "correct": s.correct_signals,
            "wrong": s.wrong_signals,
            "weight": s.current_weight,
        }
        for s in sources
    ]


async def _get_consensus_summary(
    target_date: date,
) -> list[dict]:
    """Return the latest consensus snapshot for each view on
    *target_date*."""
    day_start = datetime(
        target_date.year, target_date.month, target_date.day,
        tzinfo=timezone.utc,
    )
    day_end = datetime(
        target_date.year, target_date.month, target_date.day,
        23, 59, 59, tzinfo=timezone.utc,
    )

    views = ["scalp", "intraday", "swing", "position"]
    summaries: list[dict] = []

    async with AsyncSessionLocal() as session:
        for view in views:
            result = await session.execute(
                select(ConsensusSnapshot)
                .where(
                    ConsensusSnapshot.consensus_view == view,
                    ConsensusSnapshot.generated_at >= day_start,
                    ConsensusSnapshot.generated_at <= day_end,
                )
                .order_by(ConsensusSnapshot.generated_at.desc())
                .limit(1)
            )
            snap = result.scalars().first()
            if snap:
                summaries.append(
                    {
                        "view": view,
                        "direction": snap.consensus_direction,
                        "strength": snap.consensus_strength,
                        "signals_count": snap.signals_count,
                        "buy_count": snap.buy_count,
                        "sell_count": snap.sell_count,
                        "dominant_reasons": snap.dominant_reasons or [],
                    }
                )
    return summaries


def _build_observations(perf: DailyPerformance, consensus: list[dict]) -> list[str]:
    """Generate a list of human-readable key observations."""
    obs: list[str] = []

    # Win rate commentary
    if perf.win_rate is not None:
        if perf.win_rate >= 0.7:
            obs.append(
                f"Strong day with a {_pct(perf.win_rate)} win rate across "
                f"{perf.closed_signals} closed signal(s)."
            )
        elif perf.win_rate >= 0.5:
            obs.append(
                f"Moderate performance with a {_pct(perf.win_rate)} win rate."
            )
        elif perf.win_rate > 0:
            obs.append(
                f"Below-average day at {_pct(perf.win_rate)} win rate — "
                "review signal quality."
            )
        else:
            obs.append(
                "No winning signals today — all closed signals hit stop-loss "
                "or expired."
            )

    # Net pips
    if perf.net_pips > 0:
        obs.append(
            f"Net positive {perf.net_pips:.1f} pips — "
            f"profit {perf.total_profit_pips:.1f}, loss {perf.total_loss_pips:.1f}."
        )
    elif perf.net_pips < 0:
        obs.append(
            f"Net negative {perf.net_pips:.1f} pips — review risk management."
        )

    # Best / worst
    if perf.best_signal_pips is not None:
        obs.append(f"Best signal: {perf.best_signal_pips:+.1f} pips.")
    if perf.worst_signal_pips is not None:
        obs.append(f"Worst signal: {perf.worst_signal_pips:+.1f} pips.")

    # Consensus alignment
    directions = {c["view"]: c["direction"] for c in consensus}
    unique_dirs = set(directions.values())
    if len(unique_dirs) == 1 and "NEUTRAL" not in unique_dirs:
        obs.append(
            f"Full timeframe alignment: all views point {unique_dirs.pop()}."
        )
    elif len(unique_dirs) > 1:
        parts = [f"{v}={d}" for v, d in directions.items()]
        obs.append(f"Mixed alignment: {', '.join(parts)}.")

    # Timeframe breakdown highlights
    for view in ("scalp", "intraday", "swing", "position"):
        count_attr = f"{view}_signals"
        wr_attr = f"{view}_win_rate"
        count_val = getattr(perf, count_attr, 0)
        wr_val = getattr(perf, wr_attr, None)
        if count_val > 0 and wr_val is not None:
            obs.append(f"  {view.capitalize()}: {count_val} signal(s), {_pct(wr_val)} win rate.")

    return obs


async def generate_daily_journal(
    target_date: date | None = None,
    asset: str = "XAUUSD",
) -> str:
    """Generate and return a daily journal entry as a formatted string.

    This is template-based (no external AI calls) to save costs.
    """
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    # Fetch daily performance
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DailyPerformance).where(
                DailyPerformance.date == target_date,
                DailyPerformance.asset == asset,
            )
        )
        perf = result.scalars().first()

    if perf is None:
        msg = (
            f"# Signal Aggregator Daily Journal - {target_date.isoformat()}\n\n"
            "No performance data available for this date. "
            "Run the daily performance aggregator first."
        )
        logger.warning("No daily performance data for %s", target_date)
        return msg

    # Supporting data
    top_sources = await _get_top_sources(target_date)
    consensus = await _get_consensus_summary(target_date)
    observations = _build_observations(perf, consensus)

    # ── Build the journal ───────────────────────────────────────────
    lines: list[str] = []

    lines.append(f"# XAUUSD Signal Aggregator — Daily Journal")
    lines.append(f"## {target_date.isoformat()}")
    lines.append("")

    # ── Summary ─────────────────────────────────────────────────────
    lines.append("### Summary")
    lines.append(f"- Total signals received: {perf.total_signals}")
    lines.append(f"- Closed signals: {perf.closed_signals}")
    lines.append(
        f"  - Winning: {perf.winning_signals} | "
        f"Losing: {perf.losing_signals} | "
        f"Expired: {perf.expired_signals}"
    )
    lines.append(f"- Win rate: {_pct(perf.win_rate)}")
    lines.append(f"- Net pips: {perf.net_pips:+.1f} {_trend_emoji(perf.net_pips)}")
    lines.append(f"- Cumulative pips (all-time): {perf.cumulative_pips:+.1f}")
    lines.append("")

    # ── Pips Breakdown ──────────────────────────────────────────────
    lines.append("### Pips Breakdown")
    lines.append(f"- Total profit: {perf.total_profit_pips:.1f}")
    lines.append(f"- Total loss: {perf.total_loss_pips:.1f}")
    lines.append(f"- Best signal: {perf.best_signal_pips:+.1f}" if perf.best_signal_pips is not None else "- Best signal: N/A")
    lines.append(f"- Worst signal: {perf.worst_signal_pips:+.1f}" if perf.worst_signal_pips is not None else "- Worst signal: N/A")
    lines.append(f"- Average per signal: {perf.avg_signal_pips:+.1f}" if perf.avg_signal_pips is not None else "- Average per signal: N/A")
    lines.append("")

    # ── Consensus View ──────────────────────────────────────────────
    if consensus:
        lines.append("### Consensus Views")
        for c in consensus:
            reasons_str = ", ".join(c["dominant_reasons"][:3]) if c["dominant_reasons"] else "none"
            lines.append(
                f"- **{c['view'].capitalize()}**: {c['direction']} "
                f"(strength {c['strength']}/100, "
                f"{c['buy_count']}B/{c['sell_count']}S, "
                f"reasons: {reasons_str})"
            )
        if perf.consensus_accuracy is not None:
            lines.append(f"- Consensus accuracy today: {_pct(perf.consensus_accuracy)}")
        lines.append("")

    # ── Source Performance ──────────────────────────────────────────
    if top_sources:
        lines.append("### Top Sources (by accuracy)")
        for i, src in enumerate(top_sources, 1):
            lines.append(
                f"{i}. **{src['name']}** ({src['type']}) — "
                f"accuracy {_pct(src['accuracy'])}, "
                f"{src['correct']}W/{src['wrong']}L of {src['total']} total, "
                f"weight {src['weight']:.3f}"
            )
        lines.append("")

    # ── Key Observations ────────────────────────────────────────────
    if observations:
        lines.append("### Key Observations")
        for obs in observations:
            lines.append(f"- {obs}")
        lines.append("")

    # ── Footer ──────────────────────────────────────────────────────
    lines.append("---")
    lines.append(
        f"_Generated automatically by Signal Aggregator at "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_"
    )

    journal = "\n".join(lines)
    logger.info(
        "Generated daily journal for %s (%d lines)",
        target_date.isoformat(),
        len(lines),
    )
    return journal
