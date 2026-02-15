"""
Job Tracker — utility wrapper for tracking background job executions.

Every background job/cronjob should use ``track_job`` to automatically:
- Register itself in the ``system_jobs`` table (upsert).
- Record start/end times and duration.
- Catch errors and log them.
- Insert a ``job_runs`` history entry for every execution.
- Update the ``system_jobs`` row with the latest status.

Usage::

    from api.worker.job_tracker import track_job

    async def my_task():
        async with track_job(
            job_name="news_fetcher_reuters",
            category="news_scraping",
            expected_interval_minutes=5,
            label_fa="دریافت اخبار رویترز",
            schedule="*/5 * * * *",
        ) as logger:
            items = await fetch_news()
            logger.set_items_processed(len(items))
            logger.add_metadata({"sources": ["reuters"]})
"""

from __future__ import annotations

import logging
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from sqlalchemy import text

from api.database import AsyncSessionLocal

log = logging.getLogger("job_tracker")


class JobLogger:
    """Provides methods for the job body to report progress."""

    def __init__(self) -> None:
        self._items_processed: int = 0
        self._metadata: dict[str, Any] = {}

    def set_items_processed(self, count: int) -> None:
        self._items_processed = count

    def add_metadata(self, data: dict[str, Any]) -> None:
        self._metadata.update(data)

    @property
    def items_processed(self) -> int:
        return self._items_processed

    @property
    def metadata(self) -> dict[str, Any]:
        return self._metadata


@asynccontextmanager
async def track_job(
    *,
    job_name: str,
    category: str = "general",
    expected_interval_minutes: int = 5,
    label_fa: str | None = None,
    schedule: str | None = None,
) -> AsyncGenerator[JobLogger, None]:
    """Async context manager that wraps a job execution.

    On entry it upserts the ``system_jobs`` row and records ``last_run_at``.
    On exit it creates a ``job_runs`` history row and updates the job's
    success/failure timestamps.
    """
    import json

    logger = JobLogger()
    started_at = datetime.now(timezone.utc)
    start_mono = time.monotonic()
    error_message: str | None = None
    run_status = "success"

    try:
        # Ensure the job is registered (upsert)
        await _upsert_job(
            job_name=job_name,
            category=category,
            expected_interval_minutes=expected_interval_minutes,
            label_fa=label_fa,
            schedule=schedule,
        )
        yield logger
    except Exception as exc:
        run_status = "failure"
        error_message = traceback.format_exc(limit=5)[-2000:]
        log.error("Job %s failed: %s", job_name, exc)
        raise
    finally:
        finished_at = datetime.now(timezone.utc)
        duration_ms = int((time.monotonic() - start_mono) * 1000)

        try:
            await _record_run(
                job_name=job_name,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
                status=run_status,
                items_processed=logger.items_processed,
                error_message=error_message,
                metadata=json.dumps(logger.metadata, default=str),
            )
            await _update_job_status(
                job_name=job_name,
                last_run_at=finished_at,
                duration_ms=duration_ms,
                items_processed=logger.items_processed,
                status=run_status,
                error_message=error_message,
            )
        except Exception:
            log.warning(
                "Failed to record tracking data for job %s",
                job_name,
                exc_info=True,
            )

        # Audit log entry for every job run
        try:
            from api.audit import log_audit
            await log_audit(
                event_type="job_run",
                action=f"job.{job_name}",
                entity_type="system_jobs",
                entity_id=job_name,
                status=run_status,
                duration_ms=duration_ms,
                error_message=error_message,
                details={
                    "category": category,
                    "items_processed": logger.items_processed,
                    **logger.metadata,
                },
            )
        except Exception:
            pass  # Never fail due to audit logging


async def _upsert_job(
    *,
    job_name: str,
    category: str,
    expected_interval_minutes: int,
    label_fa: str | None,
    schedule: str | None,
) -> None:
    """Register or update the job in system_jobs (upsert by job_name)."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "INSERT INTO system_jobs "
                "  (id, job_name, job_label_fa, job_category, schedule, "
                "   expected_interval_minutes, status, enabled) "
                "VALUES "
                "  (:id, :name, :label, :cat, :sched, :interval, 'healthy', true) "
                "ON CONFLICT (job_name) DO UPDATE SET "
                "  job_label_fa = COALESCE(EXCLUDED.job_label_fa, system_jobs.job_label_fa), "
                "  job_category = EXCLUDED.job_category, "
                "  schedule = COALESCE(EXCLUDED.schedule, system_jobs.schedule), "
                "  expected_interval_minutes = EXCLUDED.expected_interval_minutes, "
                "  updated_at = NOW()"
            ),
            {
                "id": str(uuid.uuid4()),
                "name": job_name,
                "label": label_fa,
                "cat": category,
                "sched": schedule,
                "interval": expected_interval_minutes,
            },
        )
        await session.commit()


async def _record_run(
    *,
    job_name: str,
    started_at: datetime,
    finished_at: datetime,
    duration_ms: int,
    status: str,
    items_processed: int,
    error_message: str | None,
    metadata: str,
) -> None:
    """Insert a job_runs history row."""
    async with AsyncSessionLocal() as session:
        # Fetch job_id
        result = await session.execute(
            text("SELECT id FROM system_jobs WHERE job_name = :name"),
            {"name": job_name},
        )
        row = result.first()
        if row is None:
            log.warning("Job %s not found in system_jobs — skipping run log", job_name)
            return

        job_id = str(row[0])
        await session.execute(
            text(
                "INSERT INTO job_runs "
                "  (id, job_id, started_at, finished_at, status, "
                "   items_processed, error_message, duration_ms, metadata_) "
                "VALUES "
                "  (:id, :job_id, :started, :finished, :status, "
                "   :items, :err, :dur, CAST(:meta AS jsonb))"
            ),
            {
                "id": str(uuid.uuid4()),
                "job_id": job_id,
                "started": started_at,
                "finished": finished_at,
                "status": status,
                "items": items_processed,
                "err": error_message,
                "dur": duration_ms,
                "meta": metadata,
            },
        )
        await session.commit()


async def _update_job_status(
    *,
    job_name: str,
    last_run_at: datetime,
    duration_ms: int,
    items_processed: int,
    status: str,
    error_message: str | None,
) -> None:
    """Update the system_jobs row after a run completes."""
    async with AsyncSessionLocal() as session:
        if status == "success":
            await session.execute(
                text(
                    "UPDATE system_jobs SET "
                    "  last_run_at = :run_at, "
                    "  last_success_at = :run_at, "
                    "  last_duration_ms = :dur, "
                    "  items_processed = :items, "
                    "  last_error = NULL, "
                    "  status = 'healthy', "
                    "  updated_at = NOW() "
                    "WHERE job_name = :name"
                ),
                {
                    "run_at": last_run_at,
                    "dur": duration_ms,
                    "items": items_processed,
                    "name": job_name,
                },
            )
        else:
            await session.execute(
                text(
                    "UPDATE system_jobs SET "
                    "  last_run_at = :run_at, "
                    "  last_failure_at = :run_at, "
                    "  last_duration_ms = :dur, "
                    "  items_processed = :items, "
                    "  last_error = :err, "
                    "  status = 'error', "
                    "  updated_at = NOW() "
                    "WHERE job_name = :name"
                ),
                {
                    "run_at": last_run_at,
                    "dur": duration_ms,
                    "items": items_processed,
                    "err": error_message,
                    "name": job_name,
                },
            )
        await session.commit()
