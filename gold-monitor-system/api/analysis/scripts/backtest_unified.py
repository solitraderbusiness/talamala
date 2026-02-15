"""Unified backtest validator — validates 4 metric categories against benchmarks.

Categories:
1. Regime (7 benchmarks) — reuses existing regime benchmarks from DB data
2. Correlation (5 benchmarks) — validates known correlation behaviors
3. Sentiment (3 benchmarks) — validates composite score during known periods
4. Events (3 benchmarks) — validates auto-generated event counts
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import func, select

from api.database import AsyncSessionLocal
from api.analysis.models import (
    BacktestRun,
    CorrelationCache,
    MarketEventAnalysis,
    RegimeScore,
)
from api.data_collection.models import SentimentTimeline

logger = logging.getLogger("analysis.backtest_unified")


# ── Regime benchmarks (same as backtest_regime.py) ────────────────────

REGIME_BENCHMARKS = [
    {
        "name": "2018 Q4 Sell-off",
        "start": "2018-10-01", "end": "2018-12-31",
        "expected": ["stress"], "threshold": 0.35,
    },
    {
        "name": "COVID Crash",
        "start": "2020-02-20", "end": "2020-03-31",
        "expected": ["stress"], "threshold": 0.45,
    },
    {
        "name": "Post-COVID QE",
        "start": "2020-06-01", "end": "2021-06-30",
        "expected": ["expansion", "recovery"], "threshold": 0.35,
    },
    {
        "name": "2022 H1 Rate Hikes",
        "start": "2022-01-01", "end": "2022-06-30",
        "expected": ["tightening"], "threshold": 0.35,
    },
    {
        "name": "SVB Crisis",
        "start": "2023-03-01", "end": "2023-03-31",
        "expected": ["stress"], "threshold": 0.30,
    },
    {
        "name": "Late 2023 Pivot",
        "start": "2023-11-01", "end": "2024-01-31",
        "expected": ["expansion"], "threshold": 0.30,
    },
    {
        "name": "2025-2026 Current",
        "start": "2025-06-01", "end": "2026-02-28",
        "expected": ["expansion"], "threshold": 0.35,
    },
]

# ── Correlation benchmarks ────────────────────────────────────────────

CORRELATION_BENCHMARKS = [
    {
        "name": "COVID gold-DXY breakdown",
        "start": "2020-03-01", "end": "2020-04-30",
        "pair_b": "DX-Y.NYB",
        "condition": "gt", "threshold": -0.2,
        "description": "Gold-DXY inverse breaks during flight to cash",
    },
    {
        "name": "2022 tightening gold-DXY",
        "start": "2022-01-01", "end": "2022-06-30",
        "pair_b": "DX-Y.NYB",
        "condition": "lt", "threshold": -0.2,
        "description": "Gold-DXY inverse correlation restored during hikes",
    },
    {
        "name": "COVID gold-VIX spike",
        "start": "2020-02-01", "end": "2020-03-31",
        "pair_b": "^VIX",
        "condition": "gt", "threshold": 0.2,
        "description": "Gold and VIX both spike during crisis",
    },
    {
        "name": "Gold-silver normal state",
        "start": "2019-01-01", "end": "2019-12-31",
        "pair_b": "SI=F",
        "condition": "gt", "threshold": 0.6,
        "description": "Precious metals track closely in calm markets",
    },
    {
        "name": "Gold-BTC divergence 2022",
        "start": "2022-01-01", "end": "2022-06-30",
        "pair_b": "BTC-USD",
        "condition": "lt", "threshold": 0.2,
        "description": "Digital gold narrative breaks during crypto winter",
    },
]

# ── Sentiment benchmarks ─────────────────────────────────────────────

SENTIMENT_BENCHMARKS = [
    {
        "name": "COVID rally setup",
        "start": "2020-06-01", "end": "2020-08-31",
        "condition": "gt", "threshold": 55,
        "description": "Bullish sentiment during QE-driven gold rally",
    },
    {
        "name": "2022 bearish period",
        "start": "2022-06-01", "end": "2022-09-30",
        "condition": "lt", "threshold": 45,
        "description": "Bearish sentiment during rate hike cycle",
    },
    {
        "name": "2023 gold rally",
        "start": "2023-10-01", "end": "2024-01-31",
        "condition": "gt", "threshold": 50,
        "description": "Bullish sentiment during pivot expectations",
    },
]

# ── Event benchmarks ──────────────────────────────────────────────────

EVENT_BENCHMARKS = [
    {
        "name": "COVID March 2020",
        "start": "2020-03-01", "end": "2020-03-31",
        "event_type": "price_move",
        "condition": "gte", "threshold": 3,
        "description": "Multiple large price moves during COVID crash",
    },
    {
        "name": "2020 ETF accumulation",
        "start": "2020-04-01", "end": "2020-08-31",
        "event_type": "etf_flow",
        "condition": "gte", "threshold": 10,
        "description": "Heavy ETF inflows during gold rally",
    },
    {
        "name": "2022 H1 mixed",
        "start": "2022-01-01", "end": "2022-06-30",
        "event_type": None,  # Any type
        "condition": "gte", "threshold": 5,
        "description": "Mixed events during volatile tightening period",
    },
]


# ── Validation functions ──────────────────────────────────────────────

async def _validate_regime(session) -> list[dict]:
    """Validate regime benchmarks from DB data."""
    results = []

    for bm in REGIME_BENCHMARKS:
        start_d = date.fromisoformat(bm["start"])
        end_d = date.fromisoformat(bm["end"])
        expected_regimes: list[str] = bm["expected"]
        threshold: float = bm["threshold"]

        q = await session.execute(
            select(RegimeScore)
            .where(RegimeScore.ts >= start_d, RegimeScore.ts <= end_d)
            .order_by(RegimeScore.ts)
        )
        rows = q.scalars().all()

        if not rows:
            results.append({
                "name": bm["name"],
                "start": bm["start"], "end": bm["end"],
                "expected": ", ".join(expected_regimes),
                "actual": "No data",
                "passed": False,
                "reason": "No regime data in period",
            })
            continue

        # Average smoothed prob for best expected regime
        best_avg = 0.0
        best_regime = expected_regimes[0]
        for regime in expected_regimes:
            attr = f"smoothed_p_{regime}"
            avg = sum(getattr(r, attr, 0) or 0 for r in rows) / len(rows)
            if avg > best_avg:
                best_avg = avg
                best_regime = regime

        # % of days dominant
        days_correct = sum(1 for r in rows if r.chosen_regime in expected_regimes)
        pct_correct = days_correct / len(rows)

        passed = best_avg >= threshold or pct_correct > 0.5
        reason = f"{best_regime} avg={best_avg:.1%}, dominant {pct_correct:.0%} of days"

        results.append({
            "name": bm["name"],
            "start": bm["start"], "end": bm["end"],
            "expected": ", ".join(expected_regimes),
            "actual": f"{best_regime} ({best_avg:.1%})",
            "passed": passed,
            "reason": reason,
        })

    return results


async def _validate_correlations(session) -> list[dict]:
    """Validate correlation benchmarks from DB data."""
    results = []

    for bm in CORRELATION_BENCHMARKS:
        start_d = date.fromisoformat(bm["start"])
        end_d = date.fromisoformat(bm["end"])

        q = await session.execute(
            select(func.avg(CorrelationCache.correlation))
            .where(
                CorrelationCache.pair_a == "GC=F",
                CorrelationCache.pair_b == bm["pair_b"],
                CorrelationCache.computed_date >= start_d,
                CorrelationCache.computed_date <= end_d,
            )
        )
        avg_corr = q.scalar()

        if avg_corr is None:
            results.append({
                "name": bm["name"],
                "start": bm["start"], "end": bm["end"],
                "expected": f"{bm['condition']} {bm['threshold']}",
                "actual": "No data",
                "passed": False,
                "reason": "No correlation data in period",
            })
            continue

        if bm["condition"] == "gt":
            passed = avg_corr > bm["threshold"]
        elif bm["condition"] == "lt":
            passed = avg_corr < bm["threshold"]
        else:
            passed = avg_corr >= bm["threshold"]

        results.append({
            "name": bm["name"],
            "start": bm["start"], "end": bm["end"],
            "expected": f"{bm['condition']} {bm['threshold']}",
            "actual": f"{avg_corr:.4f}",
            "passed": passed,
            "reason": f"Avg correlation = {avg_corr:.4f} ({bm['pair_b']})",
        })

    return results


async def _validate_sentiment(session) -> list[dict]:
    """Validate sentiment benchmarks from DB data."""
    results = []

    for bm in SENTIMENT_BENCHMARKS:
        start_dt = datetime(
            *[int(x) for x in bm["start"].split("-")], tzinfo=timezone.utc
        )
        end_dt = datetime(
            *[int(x) for x in bm["end"].split("-")], 23, 59, 59, tzinfo=timezone.utc
        )

        q = await session.execute(
            select(func.avg(SentimentTimeline.composite_score))
            .where(
                SentimentTimeline.recorded_at >= start_dt,
                SentimentTimeline.recorded_at <= end_dt,
                SentimentTimeline.composite_score.isnot(None),
            )
        )
        avg_score = q.scalar()

        if avg_score is None:
            results.append({
                "name": bm["name"],
                "start": bm["start"], "end": bm["end"],
                "expected": f"{bm['condition']} {bm['threshold']}",
                "actual": "No data",
                "passed": False,
                "reason": "No sentiment data in period",
            })
            continue

        if bm["condition"] == "gt":
            passed = avg_score > bm["threshold"]
        elif bm["condition"] == "lt":
            passed = avg_score < bm["threshold"]
        else:
            passed = avg_score >= bm["threshold"]

        results.append({
            "name": bm["name"],
            "start": bm["start"], "end": bm["end"],
            "expected": f"{bm['condition']} {bm['threshold']}",
            "actual": f"{avg_score:.1f}",
            "passed": passed,
            "reason": f"Avg sentiment = {avg_score:.1f}",
        })

    return results


async def _validate_events(session) -> list[dict]:
    """Validate event benchmarks from DB data."""
    results = []

    for bm in EVENT_BENCHMARKS:
        start_dt = datetime(
            *[int(x) for x in bm["start"].split("-")], tzinfo=timezone.utc
        )
        end_dt = datetime(
            *[int(x) for x in bm["end"].split("-")], 23, 59, 59, tzinfo=timezone.utc
        )

        query = select(func.count(MarketEventAnalysis.id)).where(
            MarketEventAnalysis.created_at >= start_dt,
            MarketEventAnalysis.created_at <= end_dt,
        )
        if bm["event_type"]:
            query = query.where(MarketEventAnalysis.event_type == bm["event_type"])

        q = await session.execute(query)
        count = q.scalar() or 0

        if bm["condition"] == "gte":
            passed = count >= bm["threshold"]
        elif bm["condition"] == "gt":
            passed = count > bm["threshold"]
        else:
            passed = count >= bm["threshold"]

        evt_desc = bm["event_type"] or "all types"
        results.append({
            "name": bm["name"],
            "start": bm["start"], "end": bm["end"],
            "expected": f">= {bm['threshold']} {evt_desc} events",
            "actual": f"{count} events",
            "passed": passed,
            "reason": f"{count} {evt_desc} events found",
        })

    return results


# ── Main entry point ──────────────────────────────────────────────────

async def run_unified_backtest(triggered_by: str = "admin") -> dict:
    """Run unified backtest across all 4 categories, store results in DB.

    Returns structured results with PASS/FAIL per benchmark per category.
    """
    started_at = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        # Create run record
        run = BacktestRun(
            run_type="unified",
            started_at=started_at,
            status="running",
            triggered_by=triggered_by,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        run_id = run.id

    # Run all validations
    all_results = {}
    try:
        async with AsyncSessionLocal() as session:
            regime_results = await _validate_regime(session)
            all_results["regime"] = regime_results

            correlation_results = await _validate_correlations(session)
            all_results["correlation"] = correlation_results

            sentiment_results = await _validate_sentiment(session)
            all_results["sentiment"] = sentiment_results

            event_results = await _validate_events(session)
            all_results["events"] = event_results

        # Count totals
        all_benchmarks = []
        for category_results in all_results.values():
            all_benchmarks.extend(category_results)

        total = len(all_benchmarks)
        passed = sum(1 for b in all_benchmarks if b["passed"])
        failed = total - passed

        # Update run record
        async with AsyncSessionLocal() as session:
            q = await session.execute(
                select(BacktestRun).where(BacktestRun.id == run_id)
            )
            run = q.scalar_one()
            run.finished_at = datetime.now(timezone.utc)
            run.status = "completed"
            run.total_benchmarks = total
            run.passed_benchmarks = passed
            run.failed_benchmarks = failed
            run.benchmark_results = all_results
            run.summary = {
                "total": total,
                "passed": passed,
                "failed": failed,
                "categories": {
                    k: {
                        "total": len(v),
                        "passed": sum(1 for b in v if b["passed"]),
                    }
                    for k, v in all_results.items()
                },
            }
            await session.commit()

        return {
            "run_id": str(run_id),
            "status": "completed",
            "total_benchmarks": total,
            "passed": passed,
            "failed": failed,
            "results": all_results,
        }

    except Exception as e:
        # Mark as failed
        async with AsyncSessionLocal() as session:
            q = await session.execute(
                select(BacktestRun).where(BacktestRun.id == run_id)
            )
            run = q.scalar_one()
            run.finished_at = datetime.now(timezone.utc)
            run.status = "failed"
            run.error_message = str(e)
            await session.commit()

        raise
