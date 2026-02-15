"""Parse CFTC Commitment of Traders report for gold futures.

Downloads the legacy short-format file from CFTC and extracts
gold futures (contract code 088691) positioning data.

The file at ``deafut.txt`` is headerless comma-delimited with one
row per commodity per week.  Column positions follow the CFTC legacy
short-format layout (documented in the code below).
"""

from __future__ import annotations

import csv
import io
import logging
import time
from datetime import date, datetime, timezone

import aiohttp
from sqlalchemy import desc, select

from api.database import AsyncSessionLocal
from api.analysis.models import CotData

logger = logging.getLogger("analysis.cot")

# Working CFTC URL — legacy futures-only, all commodities, comma-delimited
COT_TXT_URL = "https://www.cftc.gov/dea/newcot/deafut.txt"

# Gold contract code in CFTC reports
GOLD_CONTRACT_CODE = "088691"

# Column indices in the legacy short-format file (0-based)
# Ref: https://www.cftc.gov/MarketReports/CommitmentsofTraders/ExplanatoryNotes/index.htm
COL_MARKET_NAME = 0          # "GOLD - COMMODITY EXCHANGE INC."
COL_DATE_YYMMDD = 1          # 260203
COL_DATE_ISO = 2             # 2026-02-03
COL_CONTRACT_CODE = 3        # 088691
COL_OPEN_INTEREST = 7        # Open Interest (All)
COL_NC_LONG = 8              # Non-Commercial Long (All)
COL_NC_SHORT = 9             # Non-Commercial Short (All)
COL_NC_SPREADING = 10        # Non-Commercial Spreading (All)
COL_COMM_LONG = 11           # Commercial Long (All)
COL_COMM_SHORT = 12          # Commercial Short (All)


def _safe_float(fields: list[str], idx: int) -> float | None:
    """Extract a float from a field list by index, or None."""
    if idx >= len(fields):
        return None
    val = fields[idx].strip()
    try:
        return float(val) if val else None
    except ValueError:
        return None


async def run() -> dict:
    """Fetch and parse latest COT report for gold."""
    inserted = 0
    errors = 0

    try:
        async with aiohttp.ClientSession() as http:
            t0 = time.monotonic()
            async with http.get(
                COT_TXT_URL,
                timeout=aiohttp.ClientTimeout(total=60),
                headers={"User-Agent": "Mozilla/5.0"},
            ) as resp:
                latency_ms = int((time.monotonic() - t0) * 1000)
                if resp.status != 200:
                    logger.warning("CFTC TXT returned %d", resp.status)
                    return {"status": "error", "reason": f"HTTP {resp.status}"}

                text = await resp.text()

            reader = csv.reader(io.StringIO(text))

            async with AsyncSessionLocal() as session:
                # Provenance
                run_obj = None
                try:
                    from api.data_reliability.logger import start_run, log_ingest, log_transform, finish_run
                    from api.data_reliability.validator import validate_metric, create_alert_if_needed
                    run_obj = await start_run(session, "cot_gold")
                    await log_ingest(
                        session, run_obj.id, "cftc",
                        url=COT_TXT_URL,
                        status=resp.status,
                        payload_sample={"size_bytes": len(text)},
                        latency_ms=latency_ms,
                        response_size=len(text),
                    )
                except Exception:
                    logger.debug("Provenance logging not available yet", exc_info=True)
                    run_obj = None

                latest_nc_net = None
                latest_report_date = None

                for fields in reader:
                    if len(fields) < COL_COMM_SHORT + 1:
                        continue

                    # Filter for gold by contract code
                    contract_code = fields[COL_CONTRACT_CODE].strip()
                    if GOLD_CONTRACT_CODE not in contract_code:
                        continue

                    # Parse date — prefer ISO format (col 2), fall back to YYMMDD (col 1)
                    date_iso = fields[COL_DATE_ISO].strip()
                    date_yymmdd = fields[COL_DATE_YYMMDD].strip()

                    report_date = None
                    try:
                        report_date = date.fromisoformat(date_iso)
                    except (ValueError, IndexError):
                        pass
                    if report_date is None:
                        try:
                            report_date = datetime.strptime(date_yymmdd, "%y%m%d").date()
                        except (ValueError, IndexError):
                            continue
                    if report_date is None:
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
                    nc_long = _safe_float(fields, COL_NC_LONG)
                    nc_short = _safe_float(fields, COL_NC_SHORT)
                    c_long = _safe_float(fields, COL_COMM_LONG)
                    c_short = _safe_float(fields, COL_COMM_SHORT)
                    oi = _safe_float(fields, COL_OPEN_INTEREST)

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
                        source_url=COT_TXT_URL,
                        fetched_at=datetime.now(timezone.utc),
                    ))
                    inserted += 1

                    if nc_net is not None:
                        if latest_report_date is None or report_date > latest_report_date:
                            latest_nc_net = nc_net
                            latest_report_date = report_date

                    logger.info("COT gold: date=%s, OI=%s, NC_net=%s", report_date, oi, nc_net)

                # Provenance: finish run
                if run_obj:
                    try:
                        data_ts = datetime(latest_report_date.year, latest_report_date.month, latest_report_date.day, tzinfo=timezone.utc) if latest_report_date else None
                        await log_transform(
                            session, run_obj.id, 1, "parse_and_store",
                            output_value={"inserted": inserted, "latest_nc_net": latest_nc_net},
                        )
                        qa = await validate_metric(session, run_obj.id, "cot_gold", latest_nc_net, data_ts)
                        await finish_run(session, run_obj, final_value=latest_nc_net, data_timestamp=data_ts, qa_result=qa)
                        await create_alert_if_needed(session, "cot_gold", qa)
                    except Exception:
                        logger.debug("Provenance finish failed", exc_info=True)

                await session.commit()

    except Exception:
        logger.exception("Error parsing COT report")
        errors += 1

    result = {"status": "ok", "inserted": inserted, "errors": errors}
    logger.info("COT parser: %s", result)
    return result


async def backfill_cot_history(start_year: int = 2014) -> dict:
    """Download CFTC yearly archive ZIPs and backfill gold COT data.

    CFTC yearly archives: https://www.cftc.gov/files/dea/history/deafut_txt_{YEAR}.zip
    Each ZIP contains a text file with the same format as the weekly deafut.txt.
    """
    import zipfile

    current_year = date.today().year
    inserted = 0
    skipped = 0
    errors = 0
    years_processed = 0

    async with aiohttp.ClientSession() as http:
        for year in range(start_year, current_year + 1):
            url = f"https://www.cftc.gov/files/dea/history/deafut_txt_{year}.zip"
            try:
                async with http.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=120),
                    headers={"User-Agent": "Mozilla/5.0"},
                ) as resp:
                    if resp.status != 200:
                        logger.warning("CFTC archive %d returned %d", year, resp.status)
                        errors += 1
                        continue

                    zip_bytes = await resp.read()

                # Extract and parse
                zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
                # Find the data file (usually named annual.txt or similar)
                txt_names = [n for n in zf.namelist() if n.endswith(".txt")]
                if not txt_names:
                    logger.warning("No .txt file in CFTC archive for %d", year)
                    errors += 1
                    continue

                text = zf.read(txt_names[0]).decode("utf-8", errors="replace")
                reader = csv.reader(io.StringIO(text))

                # Collect all gold rows for this year, sorted by date
                gold_rows: list[tuple[date, dict]] = []
                for fields in reader:
                    if len(fields) < COL_COMM_SHORT + 1:
                        continue
                    contract_code = fields[COL_CONTRACT_CODE].strip()
                    if GOLD_CONTRACT_CODE not in contract_code:
                        continue

                    # Parse date
                    date_iso = fields[COL_DATE_ISO].strip()
                    date_yymmdd = fields[COL_DATE_YYMMDD].strip()
                    report_date = None
                    try:
                        report_date = date.fromisoformat(date_iso)
                    except (ValueError, IndexError):
                        pass
                    if report_date is None:
                        try:
                            report_date = datetime.strptime(date_yymmdd, "%y%m%d").date()
                        except (ValueError, IndexError):
                            continue
                    if report_date is None:
                        continue

                    nc_long = _safe_float(fields, COL_NC_LONG)
                    nc_short = _safe_float(fields, COL_NC_SHORT)
                    c_long = _safe_float(fields, COL_COMM_LONG)
                    c_short = _safe_float(fields, COL_COMM_SHORT)
                    oi = _safe_float(fields, COL_OPEN_INTEREST)
                    nc_net = (nc_long - nc_short) if nc_long is not None and nc_short is not None else None

                    gold_rows.append((report_date, {
                        "nc_long": nc_long, "nc_short": nc_short,
                        "c_long": c_long, "c_short": c_short,
                        "oi": oi, "nc_net": nc_net,
                    }))

                # Sort by date and insert with change calculation
                gold_rows.sort(key=lambda x: x[0])

                async with AsyncSessionLocal() as session:
                    prev_nc_net: float | None = None
                    # Get the last known nc_net before this year's data
                    prev_q = await session.execute(
                        select(CotData)
                        .where(CotData.asset == "gold")
                        .order_by(desc(CotData.report_date))
                        .limit(1)
                    )
                    prev_row = prev_q.scalar_one_or_none()
                    if prev_row and prev_row.non_commercial_net is not None:
                        prev_nc_net = prev_row.non_commercial_net

                    for report_date, data in gold_rows:
                        existing = await session.execute(
                            select(CotData).where(
                                CotData.asset == "gold",
                                CotData.report_date == report_date,
                            )
                        )
                        if existing.scalar_one_or_none() is not None:
                            # Update prev_nc_net for next iteration
                            if data["nc_net"] is not None:
                                prev_nc_net = data["nc_net"]
                            skipped += 1
                            continue

                        change_net = None
                        if data["nc_net"] is not None and prev_nc_net is not None:
                            change_net = data["nc_net"] - prev_nc_net

                        session.add(CotData(
                            report_date=report_date,
                            asset="gold",
                            commercial_long=data["c_long"],
                            commercial_short=data["c_short"],
                            non_commercial_long=data["nc_long"],
                            non_commercial_short=data["nc_short"],
                            non_commercial_net=data["nc_net"],
                            open_interest=data["oi"],
                            change_non_commercial_net=change_net,
                            source="cftc_archive",
                            source_url=f"https://www.cftc.gov/files/dea/history/deafut_txt_{report_date.year}.zip",
                            fetched_at=datetime.now(timezone.utc),
                        ))
                        inserted += 1

                        if data["nc_net"] is not None:
                            prev_nc_net = data["nc_net"]

                    await session.commit()

                years_processed += 1
                logger.info("COT backfill %d: %d gold rows found", year, len(gold_rows))

            except Exception:
                logger.exception("Error backfilling COT data for year %d", year)
                errors += 1

    result = {
        "status": "ok",
        "years_processed": years_processed,
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
    }
    logger.info("COT backfill: %s", result)
    return result
