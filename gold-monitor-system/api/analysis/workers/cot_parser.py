"""Parse CFTC Commitment of Traders report for gold futures.

Downloads the disaggregated short-format file from CFTC and extracts
gold futures (contract code 088691) positioning data.
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from datetime import date, datetime, timezone

import aiohttp
from sqlalchemy import desc, select

from api.database import AsyncSessionLocal
from api.analysis.models import CotData

logger = logging.getLogger("analysis.cot")

# CFTC disaggregated futures-only short format
COT_URL = "https://www.cftc.gov/dea/newcot/deacmxsf.htm"
# Alternative: direct zip download for current year
COT_ZIP_URL = "https://www.cftc.gov/dea/newcot/deacmxsf.zip"
COT_CSV_URL = "https://www.cftc.gov/dea/newcot/deacmxsf.csv"

# Gold contract code in CFTC reports
GOLD_CONTRACT_CODE = "088691"
GOLD_MARKET_NAME = "GOLD"


async def run() -> dict:
    """Fetch and parse latest COT report for gold."""
    inserted = 0
    errors = 0

    try:
        async with aiohttp.ClientSession() as http:
            # Try CSV first
            async with http.get(
                COT_CSV_URL,
                timeout=aiohttp.ClientTimeout(total=60),
                headers={"User-Agent": "Mozilla/5.0"},
            ) as resp:
                if resp.status != 200:
                    logger.warning("CFTC CSV returned %d", resp.status)
                    return {"status": "error", "reason": f"HTTP {resp.status}"}

                text = await resp.text()

            reader = csv.DictReader(io.StringIO(text))

            async with AsyncSessionLocal() as session:
                for row in reader:
                    # Find gold rows by contract code or market name
                    market_code = row.get("CFTC_Contract_Market_Code", "").strip()
                    market_name = (row.get("Market_and_Exchange_Names", "") or "").upper()

                    if GOLD_CONTRACT_CODE not in market_code and GOLD_MARKET_NAME not in market_name:
                        continue

                    # Parse date
                    date_str = row.get("As_of_Date_In_Form_YYMMDD", "")
                    if not date_str:
                        date_str = row.get("Report_Date_as_YYYY-MM-DD", "")
                    if not date_str:
                        continue

                    try:
                        if len(date_str) == 6:
                            report_date = datetime.strptime(date_str, "%y%m%d").date()
                        else:
                            report_date = date.fromisoformat(date_str)
                    except ValueError:
                        continue

                    # Check if exists
                    existing = await session.execute(
                        select(CotData).where(
                            CotData.asset == "gold",
                            CotData.report_date == report_date,
                        )
                    )
                    if existing.scalar_one_or_none() is not None:
                        continue

                    # Parse positions
                    def _float(key: str) -> float | None:
                        val = row.get(key, "").strip()
                        try:
                            return float(val) if val else None
                        except ValueError:
                            return None

                    nc_long = _float("NonComm_Positions_Long_All")
                    nc_short = _float("NonComm_Positions_Short_All")
                    c_long = _float("Comm_Positions_Long_All")
                    c_short = _float("Comm_Positions_Short_All")
                    oi = _float("Open_Interest_All")

                    nc_net = (nc_long - nc_short) if nc_long is not None and nc_short is not None else None

                    # Get previous for change calculation
                    prev_q = await session.execute(
                        select(CotData)
                        .where(CotData.asset == "gold")
                        .order_by(desc(CotData.report_date))
                        .limit(1)
                    )
                    prev = prev_q.scalar_one_or_none()
                    change_net = (nc_net - prev.non_commercial_net) if nc_net is not None and prev and prev.non_commercial_net is not None else None

                    session.add(CotData(
                        report_date=report_date,
                        asset="gold",
                        commercial_long=c_long,
                        commercial_short=c_short,
                        non_commercial_long=nc_long,
                        non_commercial_short=nc_short,
                        non_commercial_net=nc_net,
                        open_interest=oi,
                        change_non_commercial_net=change_net,
                        source="cftc",
                        fetched_at=datetime.now(timezone.utc),
                    ))
                    inserted += 1

                await session.commit()

    except Exception:
        logger.exception("Error parsing COT report")
        errors += 1

    result = {"status": "ok", "inserted": inserted, "errors": errors}
    logger.info("COT parser: %s", result)
    return result
