"""Compute rolling Pearson correlations on log-returns between gold and other assets.

Uses data from the asset_prices_daily table. Gold (GC=F) is always pair_a.
Correlations are computed on log-returns (not price levels) for statistical
correctness — this avoids spurious correlations driven by shared trends.
"""

from __future__ import annotations

import logging
import math
import os
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from api.database import AsyncSessionLocal
from api.analysis.models import AssetPriceDaily, CorrelationCache

logger = logging.getLogger("analysis.correlation")

GOLD_SYMBOL = "GC=F"
OTHER_SYMBOLS = ["DX-Y.NYB", "^GSPC", "^TNX", "^VIX", "BTC-USD", "SI=F"]
WINDOW_DAYS = int(os.environ.get("CORRELATION_WINDOW_DAYS", "90"))
MIN_OBSERVATIONS = 20  # Minimum overlapping return observations
CORRELATION_METHOD = "pearson_log_returns"
CORRELATION_FREQUENCY = "daily"


def _log_returns(prices: list[float]) -> list[float]:
    """Compute log-returns ln(p[t]/p[t-1]) from a price series."""
    returns = []
    for i in range(1, len(prices)):
        if prices[i - 1] > 0 and prices[i] > 0:
            returns.append(math.log(prices[i] / prices[i - 1]))
    return returns


def _pearson(x: list[float], y: list[float]) -> float | None:
    """Compute Pearson correlation coefficient between two lists."""
    n = len(x)
    if n < MIN_OBSERVATIONS or len(y) != n:
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
    """Compute and store latest correlations using log-returns."""
    today = date.today()
    since = today - timedelta(days=WINDOW_DAYS + 10)  # Extra buffer for weekends/holidays

    # Lazy import provenance helpers (may not be available on first run)
    _prov_available = True
    try:
        from api.data_reliability.logger import start_run, log_transform, finish_run
        from api.data_reliability.validator import validate_metric, create_alert_if_needed
    except Exception:
        _prov_available = False

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

        if len(gold_rows) < MIN_OBSERVATIONS + 1:
            logger.info("Not enough gold data for correlation (%d rows, need %d)", len(gold_rows), MIN_OBSERVATIONS + 1)
            return {"status": "skipped", "reason": "insufficient data"}

        gold_by_date = {r.trade_date: r.close for r in gold_rows if r.close and r.close > 0}

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

            # Find common dates (sorted by date for correct return ordering)
            common_dates = sorted(
                d for d in (r.trade_date for r in other_rows)
                if d in gold_by_date and any(
                    r.trade_date == d and r.close and r.close > 0
                    for r in other_rows
                )
            )

            other_by_date = {
                r.trade_date: r.close for r in other_rows
                if r.close and r.close > 0
            }

            gold_prices = [gold_by_date[d] for d in common_dates if d in gold_by_date and d in other_by_date]
            other_prices = [other_by_date[d] for d in common_dates if d in gold_by_date and d in other_by_date]

            # Compute log-returns
            gold_returns = _log_returns(gold_prices)
            other_returns = _log_returns(other_prices)

            corr = _pearson(gold_returns, other_returns)
            if corr is None:
                continue

            # Determine metric_id for this pair
            symbol_suffix = {
                "DX-Y.NYB": "dxy", "^GSPC": "sp500", "^TNX": "tnx",
                "^VIX": "vix", "BTC-USD": "btc", "SI=F": "silver",
            }
            pair_metric_id = f"corr_gold_{symbol_suffix.get(symbol, symbol)}"

            # Provenance logging per pair
            if _prov_available:
                try:
                    run_obj = await start_run(session, pair_metric_id)
                    await log_transform(
                        session, run_obj.id, 1, "align_dates",
                        output_value={"common_dates": len(common_dates), "return_observations": len(gold_returns)},
                    )
                    await log_transform(
                        session, run_obj.id, 2, "log_returns",
                        output_value={"gold_returns_count": len(gold_returns), "other_returns_count": len(other_returns)},
                        normalization_method="log_return",
                        notes="ln(p[t]/p[t-1])",
                    )
                    await log_transform(
                        session, run_obj.id, 3, "pearson",
                        output_value=round(corr, 4),
                        notes=f"window={WINDOW_DAYS}d, method={CORRELATION_METHOD}",
                    )
                    data_ts = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
                    qa = await validate_metric(session, run_obj.id, pair_metric_id, round(corr, 4), data_ts)
                    await finish_run(session, run_obj, final_value=round(corr, 4), data_timestamp=data_ts, qa_result=qa)
                    await create_alert_if_needed(session, pair_metric_id, qa)
                except Exception:
                    logger.debug("Provenance logging failed for %s", pair_metric_id, exc_info=True)

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
                row.window_days = WINDOW_DAYS
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

    result = {
        "status": "ok",
        "computed": computed,
        "method": CORRELATION_METHOD,
        "window_days": WINDOW_DAYS,
    }
    logger.info("Correlation calc: %s", result)
    return result


async def backfill_historical(start_date: date | None = None) -> dict:
    """Backfill historical correlations from all available price data.

    Loads all prices into memory, iterates each trading date, computes
    90-day rolling Pearson correlation for each pair, and upserts.
    """
    async with AsyncSessionLocal() as session:
        # Load ALL price data for all relevant symbols
        all_symbols = [GOLD_SYMBOL] + list(OTHER_SYMBOLS)
        price_data: dict[str, dict[date, float]] = {}

        for symbol in all_symbols:
            q = await session.execute(
                select(AssetPriceDaily.trade_date, AssetPriceDaily.close)
                .where(
                    AssetPriceDaily.symbol == symbol,
                    AssetPriceDaily.close > 0,
                )
                .order_by(AssetPriceDaily.trade_date)
            )
            price_data[symbol] = {r.trade_date: r.close for r in q}

        if not price_data.get(GOLD_SYMBOL):
            return {"status": "skipped", "reason": "no gold price data"}

        # Get all unique trading dates from gold
        gold_dates = sorted(price_data[GOLD_SYMBOL].keys())
        if start_date:
            gold_dates = [d for d in gold_dates if d >= start_date]

        computed = 0
        batch_count = 0

        for target_date in gold_dates:
            # Need WINDOW_DAYS of data before target_date
            window_start = target_date - timedelta(days=WINDOW_DAYS + 30)

            for symbol in OTHER_SYMBOLS:
                # Build price lists for gold and other within the window
                common_dates = sorted(
                    d for d in gold_dates
                    if window_start <= d <= target_date
                    and d in price_data.get(symbol, {})
                )

                if len(common_dates) < MIN_OBSERVATIONS + 1:
                    continue

                gold_prices = [price_data[GOLD_SYMBOL][d] for d in common_dates]
                other_prices = [price_data[symbol][d] for d in common_dates]

                gold_returns = _log_returns(gold_prices)
                other_returns = _log_returns(other_prices)

                corr = _pearson(gold_returns, other_returns)
                if corr is None:
                    continue

                # Upsert
                existing = await session.execute(
                    select(CorrelationCache).where(
                        CorrelationCache.pair_a == GOLD_SYMBOL,
                        CorrelationCache.pair_b == symbol,
                        CorrelationCache.computed_date == target_date,
                    )
                )
                row = existing.scalar_one_or_none()
                if row:
                    row.correlation = round(corr, 4)
                    row.window_days = WINDOW_DAYS
                    row.computed_at = datetime.now(timezone.utc)
                else:
                    session.add(CorrelationCache(
                        pair_a=GOLD_SYMBOL,
                        pair_b=symbol,
                        correlation=round(corr, 4),
                        window_days=WINDOW_DAYS,
                        computed_date=target_date,
                        computed_at=datetime.now(timezone.utc),
                    ))
                computed += 1

            batch_count += 1
            # Commit in batches of 100 dates
            if batch_count % 100 == 0:
                await session.commit()
                logger.info("Correlation backfill: processed %d dates, %d correlations", batch_count, computed)

        await session.commit()

    result = {
        "status": "ok",
        "dates_processed": batch_count,
        "correlations_computed": computed,
        "window_days": WINDOW_DAYS,
    }
    logger.info("Correlation backfill: %s", result)
    return result
