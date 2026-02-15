"""Background task that periodically updates data_freshness table.

Runs every 15 minutes in the API lifespan. For each metric in
metric_registry, queries the latest timestamp from its source table
and updates data_freshness with age and staleness flag.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.copilot.models import DataFreshness, TABLE_MODEL_MAP
from api.copilot.queries import get_all_registry, query_metric_latest

logger = logging.getLogger("gold_monitor.copilot.freshness")


async def _check_all_freshness(session: AsyncSession) -> None:
    """Compute and upsert freshness for all registered metrics."""
    registry = await get_all_registry(session)
    now = datetime.now(timezone.utc)

    for reg in registry:
        last_ts = None

        if reg.source_table == "calc_runs" or not reg.source_table:
            # Skip computed metrics for now
            continue

        if reg.source_table in TABLE_MODEL_MAP:
            try:
                latest = await query_metric_latest(session, reg)
                if latest and latest.get("ts"):
                    ts_str = latest["ts"]
                    try:
                        last_ts = datetime.fromisoformat(ts_str)
                    except (ValueError, TypeError):
                        try:
                            last_ts = datetime.strptime(ts_str, "%Y-%m-%d").replace(
                                tzinfo=timezone.utc
                            )
                        except (ValueError, TypeError):
                            last_ts = None
            except Exception:
                logger.debug("Freshness check failed for %s", reg.key, exc_info=True)

        if last_ts and not (hasattr(last_ts, "tzinfo") and last_ts.tzinfo):
            last_ts = last_ts.replace(tzinfo=timezone.utc)

        age_hours = (
            (now - last_ts).total_seconds() / 3600 if last_ts else None
        )
        is_stale = (
            age_hours is not None and age_hours > (reg.staleness_hours or 96)
        ) or (age_hours is None)

        max_age_seconds = int((reg.staleness_hours or 96) * 3600)

        await session.execute(
            text("""
                INSERT INTO data_freshness (key, expected_frequency, max_age_seconds, last_seen_ts, is_stale, updated_at)
                VALUES (:key, :freq, :max_age, :last_ts, :is_stale, NOW())
                ON CONFLICT (key) DO UPDATE SET
                    expected_frequency = EXCLUDED.expected_frequency,
                    max_age_seconds = EXCLUDED.max_age_seconds,
                    last_seen_ts = EXCLUDED.last_seen_ts,
                    is_stale = EXCLUDED.is_stale,
                    updated_at = NOW()
            """),
            {
                "key": reg.key,
                "freq": reg.frequency,
                "max_age": max_age_seconds,
                "last_ts": last_ts,
                "is_stale": is_stale,
            },
        )

    await session.commit()
    logger.debug("Freshness check completed for %d metrics.", len(registry))


async def freshness_checker_loop(shutdown_event: asyncio.Event | None = None) -> None:
    """Run freshness checks every 15 minutes until shutdown."""
    from api.database import AsyncSessionLocal

    while True:
        if shutdown_event and shutdown_event.is_set():
            break

        try:
            async with AsyncSessionLocal() as session:
                await _check_all_freshness(session)
        except Exception:
            logger.debug("Freshness checker error", exc_info=True)

        # Sleep 15 minutes (interruptible)
        try:
            await asyncio.sleep(15 * 60)
        except asyncio.CancelledError:
            break
