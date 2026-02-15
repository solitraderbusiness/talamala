"""Fetch daily price data from Yahoo Finance via yfinance.

Tracked symbols: GC=F (gold), DX-Y.NYB (DXY), ^GSPC (S&P 500),
^TNX (10Y yield), ^VIX, BTC-USD, SI=F (silver), HYG (high yield), IEF (treasury).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from api.database import AsyncSessionLocal
from api.analysis.models import AssetPriceDaily

logger = logging.getLogger("analysis.yahoo")

SYMBOLS = ["GC=F", "DX-Y.NYB", "^GSPC", "^TNX", "^VIX", "BTC-USD", "SI=F", "HYG", "IEF"]

SYMBOL_METRIC_MAP = {
    "GC=F": "price_gc_f",
    "DX-Y.NYB": "price_dxy",
    "^GSPC": "price_sp500",
    "^TNX": "price_tnx",
    "^VIX": "price_vix",
    "BTC-USD": "price_btc",
    "SI=F": "price_silver",
    "HYG": "price_hyg",
    "IEF": "price_ief",
}

YAHOO_LOOKBACK_DAYS = int(os.environ.get("YAHOO_LOOKBACK_DAYS", "400"))


async def run() -> dict:
    """Fetch latest daily prices from Yahoo Finance."""
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        logger.warning("yfinance or pandas not installed — skipping Yahoo fetcher")
        return {"status": "skipped", "reason": "yfinance not installed"}

    end = date.today()
    start = end - timedelta(days=YAHOO_LOOKBACK_DAYS)

    inserted = 0
    skipped = 0
    errors = 0

    for symbol in SYMBOLS:
        metric_id = SYMBOL_METRIC_MAP.get(symbol)
        try:
            t0 = time.monotonic()
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=str(start), end=str(end), interval="1d")
            latency_ms = int((time.monotonic() - t0) * 1000)

            if hist.empty:
                logger.warning("No data returned for %s", symbol)
                continue

            latest_close = None
            latest_date = None

            async with AsyncSessionLocal() as session:
                # Provenance: start run
                run_obj = None
                if metric_id:
                    try:
                        from api.data_reliability.logger import start_run, log_ingest, log_transform, finish_run
                        from api.data_reliability.validator import validate_metric, create_alert_if_needed
                        run_obj = await start_run(session, metric_id)
                        await log_ingest(
                            session, run_obj.id, "yahoo_finance",
                            url=f"yfinance.Ticker({symbol}).history()",
                            params={"start": str(start), "end": str(end), "interval": "1d"},
                            status=200,
                            payload_sample={"rows": len(hist), "columns": list(hist.columns)},
                            latency_ms=latency_ms,
                        )
                    except Exception:
                        logger.debug("Provenance logging not available yet", exc_info=True)
                        run_obj = None

                sym_inserted = 0
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

                    close_val = float(row["Close"]) if pd.notna(row.get("Close")) else 0
                    session.add(AssetPriceDaily(
                        symbol=symbol,
                        trade_date=trade_date,
                        open=float(row.get("Open", 0)) if pd.notna(row.get("Open")) else None,
                        high=float(row.get("High", 0)) if pd.notna(row.get("High")) else None,
                        low=float(row.get("Low", 0)) if pd.notna(row.get("Low")) else None,
                        close=close_val,
                        volume=float(row.get("Volume", 0)) if pd.notna(row.get("Volume")) else None,
                        source="yahoo",
                        fetched_at=datetime.now(timezone.utc),
                    ))
                    sym_inserted += 1
                    latest_close = close_val
                    latest_date = trade_date

                inserted += sym_inserted

                # Provenance: finish run with validation
                if run_obj and latest_close is not None:
                    try:
                        data_ts = datetime(latest_date.year, latest_date.month, latest_date.day, tzinfo=timezone.utc) if latest_date else None
                        await log_transform(
                            session, run_obj.id, 1, "store",
                            output_value={"inserted": sym_inserted, "latest_close": latest_close},
                            notes=f"Stored {sym_inserted} new rows for {symbol}",
                        )
                        qa = await validate_metric(session, run_obj.id, metric_id, latest_close, data_ts)
                        await finish_run(session, run_obj, final_value=latest_close, data_timestamp=data_ts, qa_result=qa)
                        await create_alert_if_needed(session, metric_id, qa)
                    except Exception:
                        logger.debug("Provenance finish failed", exc_info=True)

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


async def backfill(start_date: str = "2014-01-01") -> dict:
    """Backfill Yahoo Finance data from start_date to today.

    Downloads 10+ years of daily prices for all symbols.
    Uses the same upsert logic as run() but without provenance logging.
    """
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        return {"status": "skipped", "reason": "yfinance not installed"}

    end = date.today()
    inserted = 0
    skipped = 0
    errors = 0

    for symbol in SYMBOLS:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=str(end), interval="1d")

            if hist.empty:
                logger.warning("Backfill: No data returned for %s", symbol)
                continue

            async with AsyncSessionLocal() as session:
                sym_inserted = 0
                for idx, row in hist.iterrows():
                    trade_date = idx.date() if hasattr(idx, 'date') else idx

                    existing = await session.execute(
                        select(AssetPriceDaily).where(
                            AssetPriceDaily.symbol == symbol,
                            AssetPriceDaily.trade_date == trade_date,
                        )
                    )
                    if existing.scalar_one_or_none() is not None:
                        skipped += 1
                        continue

                    close_val = float(row["Close"]) if pd.notna(row.get("Close")) else 0
                    session.add(AssetPriceDaily(
                        symbol=symbol,
                        trade_date=trade_date,
                        open=float(row.get("Open", 0)) if pd.notna(row.get("Open")) else None,
                        high=float(row.get("High", 0)) if pd.notna(row.get("High")) else None,
                        low=float(row.get("Low", 0)) if pd.notna(row.get("Low")) else None,
                        close=close_val,
                        volume=float(row.get("Volume", 0)) if pd.notna(row.get("Volume")) else None,
                        source="yahoo",
                        fetched_at=datetime.now(timezone.utc),
                    ))
                    sym_inserted += 1

                inserted += sym_inserted
                await session.commit()

            logger.info("Yahoo backfill %s: %d rows fetched, %d inserted", symbol, len(hist), sym_inserted)

        except Exception:
            logger.exception("Error backfilling %s from Yahoo Finance", symbol)
            errors += 1

    result = {
        "status": "ok",
        "symbols": len(SYMBOLS),
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
    }
    logger.info("Yahoo backfill: %s", result)
    return result
