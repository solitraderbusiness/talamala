"""
Price Outcome Tracker — background job that records what happened to
prices 1h, 4h, and 24h after each alert was created.

Runs every 15 minutes in the API process (alongside calendar_sync_loop).
For each interval, finds alerts that:
  - Have a non-null price_xauusd_at_alert (stamped at creation)
  - Are older than the interval threshold
  - Don't yet have an outcome row for that interval

Then fetches current prices, calculates change %, and determines
whether the alert's predicted direction was correct.

This data enables:
  - Accuracy scoring ("our high alerts are 78% correct at 4h")
  - Source reliability ("Reuters has 73% directional accuracy")
  - Category analysis ("Fed policy alerts are 82% accurate for gold")
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from sqlalchemy import text

from api.config import settings
from api.database import AsyncSessionLocal
from api.price_snapshot import get_price_snapshot

logger = logging.getLogger(__name__)

# How often the tracker runs (seconds)
TRACKER_INTERVAL = 900  # 15 minutes

# Intervals to check (label, hours_offset, tolerance_minutes)
INTERVALS = [
    ("1h", 1, 15),   # 1 hour ± 15 min
    ("4h", 4, 30),   # 4 hours ± 30 min
    ("24h", 24, 60),  # 24 hours ± 60 min
]

# Max alerts to process per run (avoid overloading)
MAX_ALERTS_PER_RUN = 50


def _pct_change(old: float | None, new: float | None) -> float | None:
    """Calculate percentage change, returning None if either value is missing."""
    if old is None or new is None or old == 0:
        return None
    return round((new - old) / old * 100, 4)


def _check_direction(
    predicted: str | None, price_at_alert: float | None, price_now: float | None,
) -> bool | None:
    """Was the predicted direction correct?

    Returns True/False for bullish/bearish, None for neutral/unknown.
    """
    if not predicted or predicted == "neutral" or predicted == "pending_llm":
        return None
    if price_at_alert is None or price_now is None or price_at_alert == 0:
        return None

    actual_up = price_now > price_at_alert
    if predicted == "bullish":
        return actual_up
    if predicted == "bearish":
        return not actual_up
    return None


async def _track_outcomes() -> dict[str, int]:
    """Find alerts that need outcome tracking and record results.

    Returns a dict of {interval: count} processed.
    """
    results: dict[str, int] = {}

    # Fetch current prices once
    try:
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        prices = await get_price_snapshot(r)
        await r.aclose()
    except Exception:
        logger.warning("Price tracker: could not fetch prices", exc_info=True)
        return results

    # Skip if no prices available
    if all(v is None for v in prices.values()):
        logger.debug("Price tracker: no prices available, skipping")
        return results

    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        for interval_label, hours, tolerance_min in INTERVALS:
            try:
                count = await _process_interval(
                    db, interval_label, hours, tolerance_min, now, prices,
                )
                results[interval_label] = count
            except Exception:
                logger.warning(
                    "Price tracker: error processing %s interval",
                    interval_label,
                    exc_info=True,
                )

    return results


async def _process_interval(
    db,
    interval_label: str,
    hours: int,
    tolerance_min: int,
    now: datetime,
    prices: dict[str, float | None],
) -> int:
    """Process a single interval (e.g. '1h', '4h', '24h').

    Finds alerts that were created between (hours + tolerance) and (hours - tolerance)
    ago and don't have an outcome row yet. Records the outcome.
    """
    # Window: alerts older than (hours - tolerance) but not too old
    window_start = now - timedelta(hours=hours, minutes=tolerance_min)
    window_end = now - timedelta(hours=hours, minutes=-tolerance_min)
    # Don't track alerts older than 48h (they've had their chance)
    cutoff = now - timedelta(hours=48)

    # Find alerts that need tracking for this interval
    result = await db.execute(
        text(
            "SELECT a.id, a.price_xauusd_at_alert, a.price_usdirr_at_alert, "
            "       a.price_coin_at_alert, a.price_18k_at_alert, "
            "       a.match_evidence "
            "FROM alerts a "
            "WHERE a.price_xauusd_at_alert IS NOT NULL "
            "  AND a.timestamp_utc BETWEEN :cutoff AND :window_end "
            "  AND a.timestamp_utc <= :window_start "
            "  AND NOT EXISTS ("
            "    SELECT 1 FROM alert_price_outcomes o "
            "    WHERE o.alert_id = a.id AND o.check_interval = :interval"
            "  ) "
            "ORDER BY a.timestamp_utc DESC "
            "LIMIT :limit"
        ),
        {
            "cutoff": cutoff,
            "window_start": window_start,
            "window_end": window_end,
            "interval": interval_label,
            "limit": MAX_ALERTS_PER_RUN,
        },
    )
    rows = result.mappings().all()

    if not rows:
        return 0

    count = 0
    for row in rows:
        alert_id = row["id"]
        evidence = row["match_evidence"] or {}
        if isinstance(evidence, str):
            import json
            try:
                evidence = json.loads(evidence)
            except Exception:
                evidence = {}

        direction = evidence.get("direction", "neutral")

        # Calculate changes
        chg_xauusd = _pct_change(row["price_xauusd_at_alert"], prices.get("xauusd"))
        chg_usdirr = _pct_change(row["price_usdirr_at_alert"], prices.get("usdirr"))
        chg_coin = _pct_change(row["price_coin_at_alert"], prices.get("coin"))
        chg_18k = _pct_change(row["price_18k_at_alert"], prices.get("gold_18k"))

        # Check direction against XAUUSD (primary gold indicator)
        dir_correct = _check_direction(
            direction,
            row["price_xauusd_at_alert"],
            prices.get("xauusd"),
        )

        try:
            await db.execute(
                text(
                    "INSERT INTO alert_price_outcomes "
                    "  (id, alert_id, check_interval, "
                    "   price_xauusd, price_usdirr, price_coin, price_18k, "
                    "   change_pct_xauusd, change_pct_usdirr, "
                    "   change_pct_coin, change_pct_18k, "
                    "   direction_correct, checked_at, created_at) "
                    "VALUES "
                    "  (:id, :alert_id, :interval, "
                    "   :p_xauusd, :p_usdirr, :p_coin, :p_18k, "
                    "   :chg_xauusd, :chg_usdirr, :chg_coin, :chg_18k, "
                    "   :dir_correct, :now, :now)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "alert_id": alert_id,
                    "interval": interval_label,
                    "p_xauusd": prices.get("xauusd"),
                    "p_usdirr": prices.get("usdirr"),
                    "p_coin": prices.get("coin"),
                    "p_18k": prices.get("gold_18k"),
                    "chg_xauusd": chg_xauusd,
                    "chg_usdirr": chg_usdirr,
                    "chg_coin": chg_coin,
                    "chg_18k": chg_18k,
                    "dir_correct": dir_correct,
                    "now": datetime.now(timezone.utc),
                },
            )
            count += 1
        except Exception:
            logger.debug(
                "Failed to insert outcome for alert %s/%s",
                alert_id, interval_label, exc_info=True,
            )

    await db.commit()
    return count


async def price_tracker_loop() -> None:
    """Background loop that runs every 15 minutes to track price outcomes."""
    from api.worker.job_tracker import track_job

    logger.info(
        "Price tracker started (interval=%ds, checks=%s)",
        TRACKER_INTERVAL,
        [i[0] for i in INTERVALS],
    )

    while True:
        await asyncio.sleep(TRACKER_INTERVAL)
        try:
            async with track_job(
                job_name="price_outcome_tracker",
                category="price_tracking",
                expected_interval_minutes=max(1, TRACKER_INTERVAL // 60),
                label_fa="پیگیری نتایج قیمتی هشدارها",
                schedule=f"every {TRACKER_INTERVAL}s",
            ) as jl:
                results = await _track_outcomes()
                total = sum(results.values())
                jl.set_items_processed(total)
                jl.add_metadata(results)
                if total > 0:
                    logger.info(
                        "Price tracker: recorded %d outcomes (%s)",
                        total,
                        ", ".join(f"{k}={v}" for k, v in results.items() if v),
                    )
                else:
                    logger.debug("Price tracker: no alerts to track this cycle")
        except Exception:
            logger.warning("Price tracker cycle failed", exc_info=True)
