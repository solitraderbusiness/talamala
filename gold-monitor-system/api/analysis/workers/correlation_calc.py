"""Compute 30-day rolling Pearson correlations between gold and other assets.

Uses data from the asset_prices_daily table. Gold (GC=F) is always pair_a.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from api.database import AsyncSessionLocal
from api.analysis.models import AssetPriceDaily, CorrelationCache

logger = logging.getLogger("analysis.correlation")

GOLD_SYMBOL = "GC=F"
OTHER_SYMBOLS = ["DX-Y.NYB", "^GSPC", "^TNX", "^VIX", "BTC-USD", "SI=F"]
WINDOW_DAYS = 30


def _pearson(x: list[float], y: list[float]) -> float | None:
    """Compute Pearson correlation coefficient between two lists."""
    n = len(x)
    if n < 5 or len(y) != n:
        return None

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    denom_x = sum((xi - mean_x) ** 2 for xi in x) ** 0.5
    denom_y = sum((yi - mean_y) ** 2 for yi in y) ** 0.5

    if denom_x == 0 or denom_y == 0:
        return None

    return numerator / (denom_x * denom_y)


async def run() -> dict:
    """Compute and store latest correlations."""
    today = date.today()
    since = today - timedelta(days=WINDOW_DAYS + 5)  # Extra buffer for weekends

    async with AsyncSessionLocal() as session:
        # Load gold prices
        gold_q = await session.execute(
            select(AssetPriceDaily)
            .where(
                AssetPriceDaily.symbol == GOLD_SYMBOL,
                AssetPriceDaily.trade_date >= since,
            )
            .order_by(AssetPriceDaily.trade_date)
        )
        gold_rows = gold_q.scalars().all()

        if len(gold_rows) < 5:
            logger.info("Not enough gold data for correlation (%d rows)", len(gold_rows))
            return {"status": "skipped", "reason": "insufficient data"}

        gold_by_date = {r.trade_date: r.close for r in gold_rows}

        computed = 0
        for symbol in OTHER_SYMBOLS:
            other_q = await session.execute(
                select(AssetPriceDaily)
                .where(
                    AssetPriceDaily.symbol == symbol,
                    AssetPriceDaily.trade_date >= since,
                )
                .order_by(AssetPriceDaily.trade_date)
            )
            other_rows = other_q.scalars().all()

            # Find common dates
            gold_vals = []
            other_vals = []
            for r in other_rows:
                if r.trade_date in gold_by_date and r.close is not None:
                    gold_vals.append(gold_by_date[r.trade_date])
                    other_vals.append(r.close)

            corr = _pearson(gold_vals, other_vals)
            if corr is None:
                continue

            # Upsert correlation
            existing = await session.execute(
                select(CorrelationCache).where(
                    CorrelationCache.pair_a == GOLD_SYMBOL,
                    CorrelationCache.pair_b == symbol,
                    CorrelationCache.computed_date == today,
                )
            )
            row = existing.scalar_one_or_none()
            if row:
                row.correlation = round(corr, 4)
                row.computed_at = datetime.now(timezone.utc)
            else:
                session.add(CorrelationCache(
                    pair_a=GOLD_SYMBOL,
                    pair_b=symbol,
                    correlation=round(corr, 4),
                    window_days=WINDOW_DAYS,
                    computed_date=today,
                    computed_at=datetime.now(timezone.utc),
                ))
            computed += 1

        await session.commit()

    result = {"status": "ok", "computed": computed}
    logger.info("Correlation calc: %s", result)
    return result
