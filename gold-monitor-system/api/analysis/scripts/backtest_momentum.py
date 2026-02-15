"""Quick validation / backtest for the momentum engine.

Computes daily momentum scores from the DB over a date range and compares
against next-10-day gold forward returns.  Runs as a standalone script or
via the API admin endpoint.

Usage:
    python -m api.analysis.scripts.backtest_momentum --start 2024-01-01 --end 2025-12-31
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import statistics
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import AsyncSessionLocal
from api.analysis.models import AssetPriceDaily

logger = logging.getLogger("gold_monitor.backtest_momentum")


async def run_backtest_async(
    start: str = "2024-01-01",
    end: str | None = None,
    step_days: int = 7,
    forward_days: int = 10,
) -> dict:
    """Compute weekly momentum scores over the date range and correlate with
    forward gold returns.

    Args:
        start: Start date (ISO format)
        end: End date (ISO format, default=today)
        step_days: Days between evaluation points
        forward_days: Forward return horizon

    Returns:
        Dict with correlation, bucket analysis, score distribution.
    """
    from api.services.analysis.momentum_engine import compute_momentum

    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end) if end else date.today() - timedelta(days=forward_days + 1)

    async with AsyncSessionLocal() as session:
        # Pre-load gold prices
        gold_q = await session.execute(
            select(AssetPriceDaily.trade_date, AssetPriceDaily.close)
            .where(
                AssetPriceDaily.symbol == "GC=F",
                AssetPriceDaily.trade_date >= start_date - timedelta(days=5),
            )
            .order_by(AssetPriceDaily.trade_date)
        )
        gold_rows = gold_q.all()
        gold_map = {r.trade_date: float(r.close) for r in gold_rows}
        gold_dates = sorted(gold_map.keys())

        if len(gold_dates) < forward_days + 10:
            return {"error": "Insufficient gold price data for backtest"}

        results: list[dict] = []
        current = start_date

        while current <= end_date:
            try:
                as_of = datetime(current.year, current.month, current.day, tzinfo=timezone.utc)
                momentum_result = await compute_momentum(session, as_of=as_of)
                composite = momentum_result.get("composite_score")

                if composite is None:
                    current += timedelta(days=step_days)
                    continue

                # Find forward return
                # Find closest gold date >= current
                p0_date = None
                for gd in gold_dates:
                    if gd >= current:
                        p0_date = gd
                        break

                if p0_date is None:
                    current += timedelta(days=step_days)
                    continue

                # Find gold date >= p0 + forward_days
                target_date = p0_date + timedelta(days=forward_days)
                p1_date = None
                for gd in gold_dates:
                    if gd >= target_date:
                        p1_date = gd
                        break

                if p1_date is None or p0_date not in gold_map or p1_date not in gold_map:
                    current += timedelta(days=step_days)
                    continue

                p0 = gold_map[p0_date]
                p1 = gold_map[p1_date]
                if p0 > 0:
                    fwd_ret = (p1 - p0) / p0 * 100
                    results.append({
                        "date": str(current),
                        "composite_score": composite,
                        "fwd_return_pct": round(fwd_ret, 3),
                        "drivers": {
                            d["id"]: d["score"]
                            for d in momentum_result.get("drivers", [])
                        },
                    })
            except Exception as e:
                logger.debug("Backtest error on %s: %s", current, e)

            current += timedelta(days=step_days)

        # Rollback any changes from compute_momentum run logs
        await session.rollback()

    if not results:
        return {"error": "No results computed", "count": 0}

    # Analyze results
    scores = [r["composite_score"] for r in results]
    returns = [r["fwd_return_pct"] for r in results]

    # Pearson correlation
    if len(scores) >= 5:
        try:
            from statistics import correlation as stat_corr
            corr = stat_corr(scores, returns)
        except (ImportError, Exception):
            # Manual Pearson
            n = len(scores)
            mx = statistics.mean(scores)
            my = statistics.mean(returns)
            sx = statistics.stdev(scores)
            sy = statistics.stdev(returns)
            if sx > 0 and sy > 0:
                corr = sum((scores[i] - mx) * (returns[i] - my) for i in range(n)) / ((n - 1) * sx * sy)
            else:
                corr = 0.0
    else:
        corr = None

    # Bucket analysis
    buckets = {
        "very_bearish (0-30)": [],
        "bearish (30-45)": [],
        "neutral (45-55)": [],
        "bullish (55-70)": [],
        "very_bullish (70-100)": [],
    }
    for r in results:
        s = r["composite_score"]
        ret = r["fwd_return_pct"]
        if s < 30:
            buckets["very_bearish (0-30)"].append(ret)
        elif s < 45:
            buckets["bearish (30-45)"].append(ret)
        elif s < 55:
            buckets["neutral (45-55)"].append(ret)
        elif s < 70:
            buckets["bullish (55-70)"].append(ret)
        else:
            buckets["very_bullish (70-100)"].append(ret)

    bucket_summary = {}
    for label, rets in buckets.items():
        if rets:
            bucket_summary[label] = {
                "count": len(rets),
                "mean_return": round(statistics.mean(rets), 3),
                "median_return": round(statistics.median(rets), 3),
                "positive_pct": round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1),
            }
        else:
            bucket_summary[label] = {"count": 0}

    # Directional accuracy: bullish score (>55) followed by positive return
    bullish_correct = sum(1 for r in results if r["composite_score"] > 55 and r["fwd_return_pct"] > 0)
    bearish_correct = sum(1 for r in results if r["composite_score"] < 45 and r["fwd_return_pct"] < 0)
    total_directional = sum(1 for r in results if r["composite_score"] > 55 or r["composite_score"] < 45)
    hit_rate = round((bullish_correct + bearish_correct) / total_directional * 100, 1) if total_directional > 0 else None

    return {
        "period": {"start": start, "end": str(end_date)},
        "total_observations": len(results),
        "step_days": step_days,
        "forward_days": forward_days,
        "score_stats": {
            "mean": round(statistics.mean(scores), 1),
            "median": round(statistics.median(scores), 1),
            "stdev": round(statistics.stdev(scores), 1) if len(scores) >= 2 else None,
            "min": round(min(scores), 1),
            "max": round(max(scores), 1),
        },
        "correlation_with_forward_return": round(corr, 4) if corr is not None else None,
        "directional_hit_rate_pct": hit_rate,
        "bucket_analysis": bucket_summary,
        "sample_results": results[:20],
    }


def run_backtest(start: str = "2024-01-01", end: str | None = None) -> dict:
    """Sync wrapper for the async backtest."""
    return asyncio.run(run_backtest_async(start=start, end=end))


if __name__ == "__main__":
    import json

    parser = argparse.ArgumentParser(description="Momentum engine backtest")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--step", type=int, default=7)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    result = asyncio.run(run_backtest_async(start=args.start, end=args.end, step_days=args.step))
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
