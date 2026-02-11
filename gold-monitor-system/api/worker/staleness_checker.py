"""
Staleness Checker — background task that runs every 60 seconds.

Evaluates each registered system_job and updates its status based on:
- If job is disabled → skip (leave as-is)
- If last run failed → status = "error"
- If hasn't run in 5× expected_interval → status = "error"
- If hasn't run in 2× expected_interval → status = "warning"
- If last run succeeded and within expected_interval → status = "healthy"
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import text

from api.database import AsyncSessionLocal

logger = logging.getLogger("staleness_checker")

CHECK_INTERVAL = 60  # seconds


async def run_staleness_checker(shutdown_event: asyncio.Event | None = None) -> None:
    """Run the staleness checker loop indefinitely (or until shutdown_event is set)."""
    logger.info("Staleness checker started (interval=%ds)", CHECK_INTERVAL)

    while True:
        try:
            await _check_all_jobs()
        except Exception:
            logger.exception("Staleness checker encountered an error")

        # Sleep until next check, or exit if shutdown is requested
        if shutdown_event is not None:
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=CHECK_INTERVAL)
                logger.info("Staleness checker shutting down")
                return
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(CHECK_INTERVAL)


async def _check_all_jobs() -> None:
    """Evaluate staleness for all enabled jobs and update their status."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT id, job_name, last_run_at, last_success_at, "
                "       last_failure_at, expected_interval_minutes, enabled, status "
                "FROM system_jobs "
                "WHERE enabled = true"
            )
        )
        rows = result.mappings().all()

        now = datetime.now(timezone.utc)
        updates: list[dict] = []

        for row in rows:
            new_status = _evaluate_status(row, now)
            if new_status != row["status"]:
                updates.append({"id": row["id"], "status": new_status})

        for update in updates:
            await session.execute(
                text(
                    "UPDATE system_jobs "
                    "SET status = :status, updated_at = NOW() "
                    "WHERE id = :id"
                ),
                update,
            )

        if updates:
            await session.commit()
            logger.info(
                "Staleness check updated %d job(s): %s",
                len(updates),
                ", ".join(f"{u['id']}→{u['status']}" for u in updates),
            )


def _evaluate_status(row: dict, now: datetime) -> str:
    """Determine the correct status for a job based on timing rules."""
    last_run = row.get("last_run_at")
    last_success = row.get("last_success_at")
    last_failure = row.get("last_failure_at")
    expected_minutes = row.get("expected_interval_minutes", 5)

    # Never ran → stale/error
    if last_run is None:
        return "warning"

    # Last run was a failure (failure is more recent than success)
    if last_failure and (last_success is None or last_failure > last_success):
        return "error"

    # Check staleness based on expected interval
    age_minutes = (now - last_run).total_seconds() / 60.0

    if age_minutes > expected_minutes * 5:
        return "error"

    if age_minutes > expected_minutes * 2:
        return "warning"

    return "healthy"
