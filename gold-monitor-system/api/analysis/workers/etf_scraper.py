"""Scrape daily gold ETF holdings (GLD, IAU).

GLD: Uses SPDR Gold Trust's official archive CSV for both historical
backfill and daily updates.  The CSV contains ~5500 rows from Nov 2004
with exact Total Tonnes, Total Ounces, and Total Value.

IAU: Uses Yahoo Finance ``sharesOutstanding`` for daily snapshots
(no free historical source available).
"""

from __future__ import annotations

import csv
import io
import logging
import time
from datetime import date, datetime, timedelta, timezone

import aiohttp
from sqlalchemy import select, desc, func

from api.database import AsyncSessionLocal
from api.analysis.models import EtfHolding

logger = logging.getLogger("analysis.etf")

SPDR_CSV_URL = (
    "https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv"
)

# IAU: each share represents ~1/100 of an ounce
IAU_OZ_PER_SHARE = 0.01

FUND_METRIC_MAP = {"GLD": "etf_gld", "IAU": "etf_iau"}


# ---------------------------------------------------------------------------
# GLD: SPDR archive CSV helpers
# ---------------------------------------------------------------------------

def _parse_spdr_date(raw: str) -> date | None:
    """Parse date string like '18-Nov-2004' from the SPDR CSV."""
    for fmt in ("%d-%b-%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _clean_number(raw: str) -> float | None:
    """Strip $, commas, %, whitespace and return float or None."""
    cleaned = raw.strip().replace("$", "").replace(",", "").replace("%", "")
    if not cleaned or cleaned == "-":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


async def _download_spdr_csv() -> str | None:
    """Download the SPDR GLD archive CSV.  Returns text or None on failure."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(SPDR_CSV_URL, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status != 200:
                    logger.warning("SPDR CSV download failed: HTTP %s", resp.status)
                    return None
                return await resp.text()
    except Exception:
        logger.exception("Failed to download SPDR CSV")
        return None


def _parse_spdr_rows(csv_text: str) -> list[dict]:
    """Parse the SPDR CSV into a list of dicts sorted by date ascending.

    Expected columns (order may vary, matched by header keywords):
      Date, GLD Close, ..., <ounces col>, <tonnes col>, <value col>
    """
    reader = csv.reader(io.StringIO(csv_text))

    # Find header row – look for a row containing "Date"
    header: list[str] = []
    for row in reader:
        if any("date" in cell.lower() for cell in row):
            header = [c.strip() for c in row]
            break

    if not header:
        logger.warning("Could not find header row in SPDR CSV")
        return []

    # Identify column indices by keywords
    date_idx: int | None = None
    oz_idx: int | None = None
    tonnes_idx: int | None = None
    value_idx: int | None = None

    for i, col in enumerate(header):
        cl = col.lower()
        if cl.startswith("date"):
            date_idx = i
        elif "ounces" in cl and "trust" in cl:
            oz_idx = i
        elif "tonnes" in cl and "trust" in cl:
            tonnes_idx = i
        elif "net asset value" in cl and "trust" in cl and "ounces" not in cl and "tonnes" not in cl:
            value_idx = i
        # Fallback: positional for the known layout
    # If keyword matching failed, use known positional layout
    if date_idx is None:
        date_idx = 0
    if oz_idx is None and len(header) > 8:
        oz_idx = 8
    if tonnes_idx is None and len(header) > 9:
        tonnes_idx = 9
    if value_idx is None and len(header) > 10:
        value_idx = 10

    rows: list[dict] = []
    for row in reader:
        if len(row) <= max(date_idx, tonnes_idx or 0):
            continue
        d = _parse_spdr_date(row[date_idx])
        if d is None:
            continue
        tonnes = _clean_number(row[tonnes_idx]) if tonnes_idx is not None and tonnes_idx < len(row) else None
        if tonnes is None or tonnes <= 0:
            continue
        oz = _clean_number(row[oz_idx]) if oz_idx is not None and oz_idx < len(row) else None
        val = _clean_number(row[value_idx]) if value_idx is not None and value_idx < len(row) else None
        rows.append({
            "date": d,
            "total_tonnes": round(tonnes, 2),
            "total_oz": round(oz, 2) if oz else None,
            "total_value_usd": round(val, 2) if val else None,
        })

    rows.sort(key=lambda r: r["date"])
    return rows


async def backfill_gld_from_spdr() -> dict:
    """Download the full SPDR GLD archive and backfill etf_holdings."""
    logger.info("Backfilling GLD from SPDR archive ...")
    csv_text = await _download_spdr_csv()
    if not csv_text:
        return {"status": "error", "reason": "CSV download failed"}

    rows = _parse_spdr_rows(csv_text)
    if not rows:
        return {"status": "error", "reason": "No rows parsed from CSV"}

    logger.info("Parsed %d rows from SPDR CSV (range %s to %s)",
                len(rows), rows[0]["date"], rows[-1]["date"])

    inserted = 0
    skipped = 0
    batch_size = 500
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        # Load existing GLD dates for fast dedup
        existing_q = await session.execute(
            select(EtfHolding.holding_date).where(EtfHolding.fund == "GLD")
        )
        existing_dates: set[date] = {r[0] for r in existing_q.all()}

        # Calculate change_tonnes from consecutive rows
        prev_tonnes: float | None = None
        for i, row in enumerate(rows):
            if row["date"] in existing_dates:
                prev_tonnes = row["total_tonnes"]
                skipped += 1
                continue

            change = round(row["total_tonnes"] - prev_tonnes, 2) if prev_tonnes is not None else None

            session.add(EtfHolding(
                fund="GLD",
                holding_date=row["date"],
                total_tonnes=row["total_tonnes"],
                change_tonnes=change,
                total_oz=row["total_oz"],
                total_value_usd=row["total_value_usd"],
                source="spdr_archive",
                source_url=SPDR_CSV_URL,
                fetched_at=now,
            ))
            inserted += 1
            prev_tonnes = row["total_tonnes"]

            if inserted % batch_size == 0:
                await session.commit()
                logger.info("  ... committed %d rows so far", inserted)

        if inserted % batch_size != 0:
            await session.commit()

    result = {"status": "ok", "inserted": inserted, "skipped": skipped, "total_parsed": len(rows)}
    logger.info("GLD backfill complete: %s", result)
    return result


async def _fetch_gld_from_spdr_daily() -> dict:
    """Fetch today's GLD data from the SPDR CSV (last row)."""
    csv_text = await _download_spdr_csv()
    if not csv_text:
        return {"status": "error", "reason": "CSV download failed"}

    rows = _parse_spdr_rows(csv_text)
    if not rows:
        return {"status": "error", "reason": "No rows parsed"}

    latest = rows[-1]
    today = latest["date"]

    async with AsyncSessionLocal() as session:
        # Provenance
        run_obj = None
        metric_id = FUND_METRIC_MAP["GLD"]
        try:
            from api.data_reliability.logger import start_run, log_ingest, log_transform, finish_run
            from api.data_reliability.validator import validate_metric, create_alert_if_needed
            run_obj = await start_run(session, metric_id)
            await log_ingest(
                session, run_obj.id, "spdr_csv",
                url=SPDR_CSV_URL,
                params={"rows": len(rows)},
                status=200,
                payload_sample=latest,
                latency_ms=0,
            )
        except Exception:
            logger.debug("Provenance logging not available", exc_info=True)
            run_obj = None

        # Check if date already exists
        existing = await session.execute(
            select(EtfHolding).where(
                EtfHolding.fund == "GLD",
                EtfHolding.holding_date == today,
            )
        )
        if existing.scalar_one_or_none() is not None:
            if run_obj:
                try:
                    await finish_run(session, run_obj, final_value=latest["total_tonnes"],
                                     status="success",
                                     data_timestamp=datetime(today.year, today.month, today.day, tzinfo=timezone.utc))
                    await session.commit()
                except Exception:
                    pass
            return {"status": "ok", "gld": "already exists", "date": str(today)}

        # Get previous record for change calculation
        prev_q = await session.execute(
            select(EtfHolding)
            .where(EtfHolding.fund == "GLD")
            .order_by(desc(EtfHolding.holding_date))
            .limit(1)
        )
        prev = prev_q.scalar_one_or_none()
        change = round(latest["total_tonnes"] - prev.total_tonnes, 2) if prev else None

        session.add(EtfHolding(
            fund="GLD",
            holding_date=today,
            total_tonnes=latest["total_tonnes"],
            change_tonnes=change,
            total_oz=latest["total_oz"],
            total_value_usd=latest["total_value_usd"],
            source="spdr_csv",
            source_url=SPDR_CSV_URL,
            fetched_at=datetime.now(timezone.utc),
        ))

        # Provenance finish
        if run_obj:
            try:
                data_ts = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
                await log_transform(
                    session, run_obj.id, 1, "parse_csv_last_row",
                    output_value={"total_tonnes": latest["total_tonnes"], "total_oz": latest.get("total_oz")},
                    notes="Last row of SPDR archive CSV",
                )
                if change is not None:
                    await log_transform(
                        session, run_obj.id, 2, "delta",
                        output_value={"change_tonnes": change},
                    )
                qa = await validate_metric(session, run_obj.id, metric_id, latest["total_tonnes"], data_ts)
                await finish_run(session, run_obj, final_value=latest["total_tonnes"],
                                 data_timestamp=data_ts, qa_result=qa)
                await create_alert_if_needed(session, metric_id, qa)
            except Exception:
                logger.debug("Provenance finish failed", exc_info=True)

        await session.commit()

    return {"status": "ok", "gld": "inserted", "date": str(today), "tonnes": latest["total_tonnes"]}


async def _fetch_iau_from_yfinance() -> dict:
    """IAU fetching is DISABLED — yfinance sharesOutstanding is unreliable for ETFs.

    Confirmed ~37% underestimate: yfinance shows ~301t vs real ~483t.
    No free authoritative CSV source exists for IAU (unlike GLD/SPDR).
    This function is kept as a placeholder for when a reliable source is found.
    """
    logger.info("IAU fetching disabled — yfinance sharesOutstanding unreliable for ETFs "
                "(shows ~301t vs real ~483t). Awaiting authoritative data source.")
    return {"status": "skipped", "reason": "yfinance unreliable for IAU, disabled until authoritative source found"}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run() -> dict:
    """Fetch ETF holdings: GLD from SPDR archive, IAU from Yahoo Finance."""

    # Step 1: Auto-backfill GLD if fewer than 30 records
    try:
        async with AsyncSessionLocal() as session:
            count_q = await session.execute(
                select(func.count()).select_from(EtfHolding).where(EtfHolding.fund == "GLD")
            )
            gld_count = count_q.scalar()
        if gld_count < 30:
            await backfill_gld_from_spdr()
    except Exception:
        logger.exception("GLD backfill check failed")

    # Step 2: Daily GLD from SPDR CSV
    gld_result = await _fetch_gld_from_spdr_daily()

    # Step 3: Daily IAU from yfinance
    iau_result = await _fetch_iau_from_yfinance()

    result = {"status": "ok", "gld": gld_result, "iau": iau_result}
    logger.info("ETF scraper: %s", result)
    return result
