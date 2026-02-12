"""Scrape daily gold ETF holdings (GLD, IAU).

Uses Yahoo Finance as the data source — the ETF closing price multiplied
by shares outstanding gives a good approximation.  For GLD specifically,
we use the known conversion factor: GLD NAV ~= 1/10th of a troy ounce
per share, so total_shares * 0.09375 / 1000 = approximate tonnes.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, desc

from api.database import AsyncSessionLocal
from api.analysis.models import EtfHolding

logger = logging.getLogger("analysis.etf")

# GLD: each share represents ~1/10 of an ounce
# To approximate tonnes: total_oz / 32150.75
GLD_OZ_PER_SHARE = 0.09375


async def run() -> dict:
    """Fetch ETF holdings data from Yahoo Finance."""
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed — skipping ETF scraper")
        return {"status": "skipped", "reason": "yfinance not installed"}

    inserted = 0
    errors = 0

    for fund, ticker_symbol in [("GLD", "GLD"), ("IAU", "IAU")]:
        try:
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info or {}

            # Get shares outstanding
            shares = info.get("sharesOutstanding")
            if not shares:
                logger.warning("No sharesOutstanding for %s", fund)
                errors += 1
                continue

            # Calculate holdings
            if fund == "GLD":
                total_oz = shares * GLD_OZ_PER_SHARE
            else:
                # IAU: each share ~1/100 of an oz
                total_oz = shares * 0.01

            total_tonnes = total_oz / 32150.75

            # Get latest price for total value
            hist = ticker.history(period="1d")
            price = float(hist["Close"].iloc[-1]) if not hist.empty else None
            total_value = shares * price if price else None

            today = date.today()

            async with AsyncSessionLocal() as session:
                # Check if today already exists
                existing = await session.execute(
                    select(EtfHolding).where(
                        EtfHolding.fund == fund,
                        EtfHolding.holding_date == today,
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    continue

                # Get previous day for change calculation
                prev_q = await session.execute(
                    select(EtfHolding)
                    .where(EtfHolding.fund == fund)
                    .order_by(desc(EtfHolding.holding_date))
                    .limit(1)
                )
                prev = prev_q.scalar_one_or_none()
                change_tonnes = total_tonnes - prev.total_tonnes if prev else None

                session.add(EtfHolding(
                    fund=fund,
                    holding_date=today,
                    total_tonnes=round(total_tonnes, 2),
                    change_tonnes=round(change_tonnes, 2) if change_tonnes is not None else None,
                    total_oz=round(total_oz, 2),
                    total_value_usd=round(total_value, 2) if total_value else None,
                    source="yahoo_finance",
                    fetched_at=datetime.now(timezone.utc),
                ))
                await session.commit()
                inserted += 1

        except Exception:
            logger.exception("Error fetching ETF data for %s", fund)
            errors += 1

    result = {"status": "ok", "inserted": inserted, "errors": errors}
    logger.info("ETF scraper: %s", result)
    return result
