"""Fetch macro indicators from FRED API.

Tracked series: FEDFUNDS, CPIAUCSL, DFII10, DGS10, T10YIE.
Requires FRED_API_KEY env var.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, timedelta, timezone

import aiohttp
from sqlalchemy import select

from api.config import settings
from api.database import AsyncSessionLocal
from api.analysis.models import MacroIndicator

logger = logging.getLogger("analysis.fred")

SERIES = ["FEDFUNDS", "CPIAUCSL", "DFII10", "DGS10", "T10YIE"]
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
FRED_LOOKBACK_DAYS = int(os.environ.get("FRED_LOOKBACK_DAYS", "400"))

SERIES_METRIC_MAP = {
    "FEDFUNDS": "fred_fedfunds",
    "CPIAUCSL": "fred_cpi",
    "DFII10": "fred_dfii10",
    "DGS10": "fred_dgs10",
    "T10YIE": "fred_t10yie",
}


async def run() -> dict:
    """Fetch latest FRED observations for each series."""
    if not settings.FRED_API_KEY:
        logger.info("FRED_API_KEY not set — skipping FRED fetcher")
        return {"status": "skipped", "reason": "FRED_API_KEY not configured"}

    inserted = 0
    skipped = 0
    errors = 0

    end_date = date.today()
    start_date = end_date - timedelta(days=FRED_LOOKBACK_DAYS)

    async with aiohttp.ClientSession() as http:
        for series_id in SERIES:
            metric_id = SERIES_METRIC_MAP.get(series_id)
            try:
                params = {
                    "series_id": series_id,
                    "api_key": settings.FRED_API_KEY,
                    "file_type": "json",
                    "observation_start": str(start_date),
                    "observation_end": str(end_date),
                    "sort_order": "desc",
                    "limit": "1000",
                }

                t0 = time.monotonic()
                async with http.get(FRED_BASE, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    latency_ms = int((time.monotonic() - t0) * 1000)

                    if resp.status != 200:
                        logger.warning("FRED API returned %d for %s", resp.status, series_id)
                        errors += 1
                        continue

                    data = await resp.json()
                    observations = data.get("observations", [])

                    async with AsyncSessionLocal() as session:
                        # Provenance: start run
                        run_obj = None
                        if metric_id:
                            try:
                                from api.data_reliability.logger import start_run, log_ingest, log_transform, finish_run
                                from api.data_reliability.validator import validate_metric, create_alert_if_needed
                                run_obj = await start_run(session, metric_id)
                                await log_ingest(
                                    session, run_obj.id, "fred_api",
                                    url=FRED_BASE,
                                    params={"series_id": series_id, "observation_start": str(start_date)},
                                    status=resp.status,
                                    payload_sample={"observation_count": len(observations)},
                                    latency_ms=latency_ms,
                                )
                            except Exception:
                                logger.debug("Provenance logging not available yet", exc_info=True)
                                run_obj = None

                        latest_value = None
                        latest_date = None
                        series_inserted = 0

                        for obs in observations:
                            obs_date_str = obs.get("date")
                            value_str = obs.get("value", ".")

                            if not obs_date_str or value_str == ".":
                                continue

                            try:
                                obs_date = date.fromisoformat(obs_date_str)
                                value = float(value_str)
                            except (ValueError, TypeError):
                                continue

                            if latest_value is None:
                                latest_value = value
                                latest_date = obs_date

                            # Check if exists
                            existing = await session.execute(
                                select(MacroIndicator).where(
                                    MacroIndicator.series_id == series_id,
                                    MacroIndicator.observation_date == obs_date,
                                )
                            )
                            if existing.scalar_one_or_none() is not None:
                                skipped += 1
                                continue

                            session.add(MacroIndicator(
                                series_id=series_id,
                                observation_date=obs_date,
                                value=value,
                                source="fred",
                                fetched_at=datetime.now(timezone.utc),
                            ))
                            series_inserted += 1

                        inserted += series_inserted

                        # Provenance: finish run
                        if run_obj and latest_value is not None:
                            try:
                                data_ts = datetime(latest_date.year, latest_date.month, latest_date.day, tzinfo=timezone.utc) if latest_date else None
                                await log_transform(
                                    session, run_obj.id, 1, "store",
                                    output_value={"inserted": series_inserted, "latest_value": latest_value},
                                )
                                qa = await validate_metric(session, run_obj.id, metric_id, latest_value, data_ts)
                                await finish_run(session, run_obj, final_value=latest_value, data_timestamp=data_ts, qa_result=qa)
                                await create_alert_if_needed(session, metric_id, qa)
                            except Exception:
                                logger.debug("Provenance finish failed", exc_info=True)

                        await session.commit()

            except Exception:
                logger.exception("Error fetching FRED series %s", series_id)
                errors += 1

    result = {
        "status": "ok",
        "series": len(SERIES),
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
    }
    logger.info("FRED fetcher: %s", result)
    return result


async def backfill(start_date: str = "2014-01-01") -> dict:
    """Backfill FRED data from start_date to today.

    Downloads all series with a wide date range for historical backfill.
    Uses the same upsert logic as run() but without provenance logging.
    """
    if not settings.FRED_API_KEY:
        return {"status": "skipped", "reason": "FRED_API_KEY not configured"}

    inserted = 0
    skipped = 0
    errors = 0
    end_str = str(date.today())

    async with aiohttp.ClientSession() as http:
        for series_id in SERIES:
            try:
                params = {
                    "series_id": series_id,
                    "api_key": settings.FRED_API_KEY,
                    "file_type": "json",
                    "observation_start": start_date,
                    "observation_end": end_str,
                    "sort_order": "asc",
                    "limit": "100000",
                }

                async with http.get(FRED_BASE, params=params, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status != 200:
                        logger.warning("FRED backfill returned %d for %s", resp.status, series_id)
                        errors += 1
                        continue

                    data = await resp.json()
                    observations = data.get("observations", [])

                    async with AsyncSessionLocal() as session:
                        for obs in observations:
                            obs_date_str = obs.get("date")
                            value_str = obs.get("value", ".")
                            if not obs_date_str or value_str == ".":
                                continue
                            try:
                                obs_date = date.fromisoformat(obs_date_str)
                                value = float(value_str)
                            except (ValueError, TypeError):
                                continue

                            existing = await session.execute(
                                select(MacroIndicator).where(
                                    MacroIndicator.series_id == series_id,
                                    MacroIndicator.observation_date == obs_date,
                                )
                            )
                            if existing.scalar_one_or_none() is not None:
                                skipped += 1
                                continue

                            session.add(MacroIndicator(
                                series_id=series_id,
                                observation_date=obs_date,
                                value=value,
                                source="fred",
                                fetched_at=datetime.now(timezone.utc),
                            ))
                            inserted += 1

                        await session.commit()

                logger.info("FRED backfill %s: %d observations fetched", series_id, len(observations))

            except Exception:
                logger.exception("Error backfilling FRED series %s", series_id)
                errors += 1

    result = {
        "status": "ok",
        "series": len(SERIES),
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
    }
    logger.info("FRED backfill: %s", result)
    return result
