"""Fetch macro indicators from FRED API.

Tracked series: FEDFUNDS, CPIAUCSL, DFII10, DGS10, T10YIE.
Requires FRED_API_KEY env var.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import aiohttp
from sqlalchemy import select

from api.config import settings
from api.database import AsyncSessionLocal
from api.analysis.models import MacroIndicator

logger = logging.getLogger("analysis.fred")

SERIES = ["FEDFUNDS", "CPIAUCSL", "DFII10", "DGS10", "T10YIE"]
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"


async def run() -> dict:
    """Fetch latest FRED observations for each series."""
    if not settings.FRED_API_KEY:
        logger.info("FRED_API_KEY not set — skipping FRED fetcher")
        return {"status": "skipped", "reason": "FRED_API_KEY not configured"}

    inserted = 0
    skipped = 0
    errors = 0

    end_date = date.today()
    start_date = end_date - timedelta(days=120)

    async with aiohttp.ClientSession() as http:
        for series_id in SERIES:
            try:
                params = {
                    "series_id": series_id,
                    "api_key": settings.FRED_API_KEY,
                    "file_type": "json",
                    "observation_start": str(start_date),
                    "observation_end": str(end_date),
                    "sort_order": "desc",
                    "limit": "100",
                }
                async with http.get(FRED_BASE, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        logger.warning("FRED API returned %d for %s", resp.status, series_id)
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
                            inserted += 1

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
