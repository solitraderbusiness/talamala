"""Fetch daily price data from Yahoo Finance via yfinance.

Tracked symbols: GC=F (gold), DX-Y.NYB (DXY), ^GSPC (S&P 500),
^TNX (10Y yield), ^VIX, BTC-USD, SI=F (silver).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from api.database import AsyncSessionLocal
from api.analysis.models import AssetPriceDaily

logger = logging.getLogger("analysis.yahoo")

SYMBOLS = ["GC=F", "DX-Y.NYB", "^GSPC", "^TNX", "^VIX", "BTC-USD", "SI=F"]


async def run() -> dict:
    """Fetch latest daily prices from Yahoo Finance."""
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        logger.warning("yfinance or pandas not installed — skipping Yahoo fetcher")
        return {"status": "skipped", "reason": "yfinance not installed"}

    end = date.today()
    start = end - timedelta(days=260)  # Fetch 260 days for MA200 calculation

    inserted = 0
    skipped = 0
    errors = 0

    for symbol in SYMBOLS:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=str(start), end=str(end), interval="1d")

            if hist.empty:
                logger.warning("No data returned for %s", symbol)
                continue

            async with AsyncSessionLocal() as session:
                for idx, row in hist.iterrows():
                    trade_date = idx.date() if hasattr(idx, 'date') else idx

                    # Check if already exists
                    existing = await session.execute(
                        select(AssetPriceDaily).where(
                            AssetPriceDaily.symbol == symbol,
                            AssetPriceDaily.trade_date == trade_date,
                        )
                    )
                    if existing.scalar_one_or_none() is not None:
                        skipped += 1
                        continue

                    session.add(AssetPriceDaily(
                        symbol=symbol,
                        trade_date=trade_date,
                        open=float(row.get("Open", 0)) if pd.notna(row.get("Open")) else None,
                        high=float(row.get("High", 0)) if pd.notna(row.get("High")) else None,
                        low=float(row.get("Low", 0)) if pd.notna(row.get("Low")) else None,
                        close=float(row["Close"]) if pd.notna(row.get("Close")) else 0,
                        volume=float(row.get("Volume", 0)) if pd.notna(row.get("Volume")) else None,
                        source="yahoo",
                        fetched_at=datetime.now(timezone.utc),
                    ))
                    inserted += 1

                await session.commit()

        except Exception:
            logger.exception("Error fetching %s from Yahoo Finance", symbol)
            errors += 1

    result = {
        "status": "ok",
        "symbols": len(SYMBOLS),
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
    }
    logger.info("Yahoo fetcher: %s", result)
    return result
