"""Price history candle aggregation.

Two functions:
- ``build_5min_candles()`` — aggregates signal_price_ticks into 5min OHLCV
- ``sync_daily_candles()``  — copies asset_prices_daily → price_history (1d)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, text

from api.database import AsyncSessionLocal
from api.data_collection.models import PriceHistory

logger = logging.getLogger("analysis.candle_builder")

RETENTION_5MIN_DAYS = 30


async def build_5min_candles() -> dict:
    """Aggregate signal_price_ticks into 5-min OHLCV candles for XAUUSD.

    Reads ticks from the last 6 minutes, builds a candle for the
    nearest 5-min bucket, and inserts if not already present.
    """
    now = datetime.now(timezone.utc)
    # Compute the 5-min bucket that just closed
    bucket = now.replace(second=0, microsecond=0)
    bucket = bucket.replace(minute=(bucket.minute // 5) * 5)
    bucket_start = bucket - timedelta(minutes=5)

    inserted = 0

    async with AsyncSessionLocal() as session:
        # Check if candle already exists
        existing = await session.execute(
            select(PriceHistory).where(
                PriceHistory.symbol == "XAUUSD",
                PriceHistory.timeframe == "5min",
                PriceHistory.datetime_utc == bucket_start,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return {"status": "skipped", "reason": "already_exists"}

        # Fetch ticks for this 5-min window
        ticks_q = await session.execute(
            text(
                "SELECT price, checked_at FROM signal_price_ticks "
                "WHERE checked_at >= :start AND checked_at < :end "
                "ORDER BY checked_at ASC"
            ),
            {"start": bucket_start, "end": bucket},
        )
        ticks = ticks_q.all()

        if not ticks:
            return {"status": "skipped", "reason": "no_ticks"}

        prices = [float(t[0]) for t in ticks if t[0]]
        if not prices:
            return {"status": "skipped", "reason": "no_valid_prices"}

        candle = PriceHistory(
            symbol="XAUUSD",
            timeframe="5min",
            datetime_utc=bucket_start,
            open=prices[0],
            high=max(prices),
            low=min(prices),
            close=prices[-1],
            volume=float(len(prices)),
            source="signal_price_ticks",
        )
        session.add(candle)
        inserted = 1

        # Cleanup old 5min candles
        cutoff = now - timedelta(days=RETENTION_5MIN_DAYS)
        await session.execute(
            delete(PriceHistory).where(
                PriceHistory.timeframe == "5min",
                PriceHistory.datetime_utc < cutoff,
            )
        )

        await session.commit()

    if inserted:
        logger.info(
            "5min candle: XAUUSD %s O=%.2f H=%.2f L=%.2f C=%.2f ticks=%d",
            bucket_start.strftime("%H:%M"),
            prices[0], max(prices), min(prices), prices[-1], len(prices),
        )
    return {"status": "ok", "inserted": inserted}


async def sync_daily_candles() -> dict:
    """Copy/sync from asset_prices_daily → price_history (timeframe=1d).

    All 7 tracked symbols. INSERT ON CONFLICT DO NOTHING.
    """
    inserted = 0

    async with AsyncSessionLocal() as session:
        # Read all asset_prices_daily rows
        rows_q = await session.execute(
            text(
                "SELECT symbol, trade_date, open, high, low, close, volume, source "
                "FROM asset_prices_daily"
            )
        )
        rows = rows_q.all()

        for row in rows:
            symbol, trade_date, open_, high, low, close, volume, source = row
            dt_utc = datetime.combine(trade_date, datetime.min.time()).replace(
                tzinfo=timezone.utc
            )

            # Check existence
            existing = await session.execute(
                select(PriceHistory).where(
                    PriceHistory.symbol == symbol,
                    PriceHistory.timeframe == "1d",
                    PriceHistory.datetime_utc == dt_utc,
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue

            session.add(PriceHistory(
                symbol=symbol,
                timeframe="1d",
                datetime_utc=dt_utc,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                source=source or "yahoo",
            ))
            inserted += 1

        await session.commit()

    if inserted:
        logger.info("Daily candle sync: inserted %d rows", inserted)
    return {"status": "ok", "inserted": inserted}
