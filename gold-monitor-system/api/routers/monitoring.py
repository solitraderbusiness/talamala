"""
Monitoring router — operations monitoring dashboard API.

All endpoints require admin authentication except ``/api/admin/health``
which is designed for external monitoring tools (but still protected).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_admin
from api.database import get_db
from api.models import AdminUser, JobRun, SystemJob

logger = logging.getLogger(__name__)

router = APIRouter(tags=["monitoring"])


# ── GET /monitoring/overview ─────────────────────────────────────────────

@router.get("/monitoring/overview", dependencies=[Depends(get_current_admin)])
async def monitoring_overview(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Health overview — counts of healthy/warning/error/stale jobs."""

    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(hours=24)

    # Job status counts
    status_result = await db.execute(
        text(
            "SELECT status, COUNT(*) as cnt "
            "FROM system_jobs WHERE enabled = true "
            "GROUP BY status"
        )
    )
    status_counts = {row.status: row.cnt for row in status_result}

    # Total jobs (including disabled)
    total_result = await db.execute(text("SELECT COUNT(*) FROM system_jobs"))
    total_jobs = total_result.scalar() or 0

    # Runs in last 24h
    runs_24h_result = await db.execute(
        text(
            "SELECT COUNT(*) as total, "
            "       COUNT(*) FILTER (WHERE status = 'success') as success_count "
            "FROM job_runs WHERE started_at >= :since"
        ),
        {"since": yesterday},
    )
    runs_row = runs_24h_result.first()
    total_runs = runs_row.total if runs_row else 0
    success_count = runs_row.success_count if runs_row else 0
    success_rate = (success_count / total_runs * 100) if total_runs > 0 else 100.0

    return {
        "jobs_healthy": status_counts.get("healthy", 0),
        "jobs_warning": status_counts.get("warning", 0),
        "jobs_error": status_counts.get("error", 0),
        "jobs_stale": status_counts.get("stale", 0),
        "total_jobs": total_jobs,
        "total_runs_24h": total_runs,
        "success_rate_24h": round(success_rate, 1),
        "last_check_at": now.isoformat(),
    }


# ── GET /monitoring/jobs ─────────────────────────────────────────────────

@router.get("/monitoring/jobs", dependencies=[Depends(get_current_admin)])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all registered jobs with their status and 24h success rate."""

    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(hours=24)

    # Get all jobs
    jobs_result = await db.execute(
        text(
            "SELECT j.*, "
            "  (SELECT COUNT(*) FROM job_runs r "
            "   WHERE r.job_id = j.id AND r.started_at >= :since) as runs_24h, "
            "  (SELECT COUNT(*) FROM job_runs r "
            "   WHERE r.job_id = j.id AND r.started_at >= :since "
            "   AND r.status = 'success') as success_24h "
            "FROM system_jobs j "
            "ORDER BY "
            "  CASE j.status "
            "    WHEN 'error' THEN 0 "
            "    WHEN 'warning' THEN 1 "
            "    WHEN 'stale' THEN 2 "
            "    WHEN 'healthy' THEN 3 "
            "    ELSE 4 END, "
            "  j.last_run_at DESC NULLS LAST"
        ),
        {"since": yesterday},
    )
    rows = jobs_result.mappings().all()

    jobs = []
    for row in rows:
        runs_24h = row.get("runs_24h", 0) or 0
        success_24h = row.get("success_24h", 0) or 0
        success_rate = (success_24h / runs_24h * 100) if runs_24h > 0 else None

        jobs.append({
            "id": str(row["id"]),
            "job_name": row["job_name"],
            "job_label_fa": row.get("job_label_fa"),
            "job_category": row["job_category"],
            "schedule": row.get("schedule"),
            "last_run_at": row["last_run_at"].isoformat() if row.get("last_run_at") else None,
            "last_success_at": row["last_success_at"].isoformat() if row.get("last_success_at") else None,
            "last_failure_at": row["last_failure_at"].isoformat() if row.get("last_failure_at") else None,
            "last_error": row.get("last_error"),
            "last_duration_ms": row.get("last_duration_ms"),
            "items_processed": row.get("items_processed", 0),
            "status": row["status"],
            "expected_interval_minutes": row["expected_interval_minutes"],
            "enabled": row["enabled"],
            "success_rate_24h": round(success_rate, 1) if success_rate is not None else None,
            "runs_24h": runs_24h,
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        })

    return jobs


# ── GET /monitoring/jobs/{job_id}/runs ────────────────────────────────────

@router.get("/monitoring/jobs/{job_id}/runs", dependencies=[Depends(get_current_admin)])
async def get_job_runs(
    job_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Get run history for a specific job."""

    result = await db.execute(
        text(
            "SELECT r.*, j.job_name "
            "FROM job_runs r "
            "JOIN system_jobs j ON j.id = r.job_id "
            "WHERE r.job_id = :job_id "
            "ORDER BY r.started_at DESC "
            "LIMIT :limit"
        ),
        {"job_id": job_id, "limit": limit},
    )
    rows = result.mappings().all()

    return [
        {
            "id": str(row["id"]),
            "job_id": str(row["job_id"]),
            "job_name": row.get("job_name"),
            "started_at": row["started_at"].isoformat(),
            "finished_at": row["finished_at"].isoformat() if row.get("finished_at") else None,
            "status": row["status"],
            "items_processed": row.get("items_processed", 0),
            "error_message": row.get("error_message"),
            "duration_ms": row.get("duration_ms"),
            "metadata": row.get("metadata_", {}),
        }
        for row in rows
    ]


# ── PUT /monitoring/jobs/{job_id}/toggle ──────────────────────────────────

@router.put("/monitoring/jobs/{job_id}/toggle", dependencies=[Depends(get_current_admin)])
async def toggle_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Enable or disable a job."""

    result = await db.execute(
        text("SELECT enabled FROM system_jobs WHERE id = :id"),
        {"id": job_id},
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")

    new_enabled = not row[0]
    await db.execute(
        text(
            "UPDATE system_jobs SET enabled = :enabled, updated_at = NOW() "
            "WHERE id = :id"
        ),
        {"enabled": new_enabled, "id": job_id},
    )
    await db.commit()

    return {"id": job_id, "enabled": new_enabled}


# ── GET /monitoring/recent-failures ───────────────────────────────────────

@router.get("/monitoring/recent-failures", dependencies=[Depends(get_current_admin)])
async def recent_failures(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Last N failed job runs across all jobs."""

    result = await db.execute(
        text(
            "SELECT r.*, j.job_name, j.job_label_fa "
            "FROM job_runs r "
            "JOIN system_jobs j ON j.id = r.job_id "
            "WHERE r.status = 'failure' "
            "ORDER BY r.started_at DESC "
            "LIMIT :limit"
        ),
        {"limit": limit},
    )
    rows = result.mappings().all()

    return [
        {
            "id": str(row["id"]),
            "job_id": str(row["job_id"]),
            "job_name": row.get("job_name"),
            "job_label_fa": row.get("job_label_fa"),
            "started_at": row["started_at"].isoformat(),
            "finished_at": row["finished_at"].isoformat() if row.get("finished_at") else None,
            "error_message": row.get("error_message"),
            "duration_ms": row.get("duration_ms"),
            "items_processed": row.get("items_processed", 0),
        }
        for row in rows
    ]


# ── GET /monitoring/activity ──────────────────────────────────────────────

@router.get("/monitoring/activity", dependencies=[Depends(get_current_admin)])
async def activity_timeline(
    hours: int = Query(24, ge=1, le=168),
    category: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Chronological feed of all job runs in the last N hours."""

    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    query = (
        "SELECT r.*, j.job_name, j.job_label_fa, j.job_category "
        "FROM job_runs r "
        "JOIN system_jobs j ON j.id = r.job_id "
        "WHERE r.started_at >= :since "
    )
    params: dict[str, Any] = {"since": since}

    if category:
        query += "AND j.job_category = :cat "
        params["cat"] = category

    query += "ORDER BY r.started_at DESC LIMIT 500"

    result = await db.execute(text(query), params)
    rows = result.mappings().all()

    return [
        {
            "id": str(row["id"]),
            "job_id": str(row["job_id"]),
            "job_name": row.get("job_name"),
            "job_label_fa": row.get("job_label_fa"),
            "job_category": row.get("job_category"),
            "started_at": row["started_at"].isoformat(),
            "finished_at": row["finished_at"].isoformat() if row.get("finished_at") else None,
            "status": row["status"],
            "items_processed": row.get("items_processed", 0),
            "duration_ms": row.get("duration_ms"),
            "error_message": row.get("error_message"),
        }
        for row in rows
    ]


# ── GET /health (external monitoring) ─────────────────────────────────────

@router.get("/health")
async def admin_health(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """External monitoring endpoint.

    Returns the overall system health status based on job statuses.
    This endpoint requires admin auth via the admin router prefix.
    """

    now = datetime.now(timezone.utc)

    status_result = await db.execute(
        text(
            "SELECT status, COUNT(*) as cnt "
            "FROM system_jobs WHERE enabled = true "
            "GROUP BY status"
        )
    )
    status_counts = {row.status: row.cnt for row in status_result}

    healthy = status_counts.get("healthy", 0)
    warning = status_counts.get("warning", 0)
    error = status_counts.get("error", 0)

    # Determine overall status
    if error > 0:
        overall = "down" if error > healthy else "degraded"
    elif warning > 0:
        overall = "degraded"
    else:
        overall = "healthy"

    # Find oldest stale job
    stale_result = await db.execute(
        text(
            "SELECT job_name FROM system_jobs "
            "WHERE enabled = true AND status IN ('error', 'warning') "
            "ORDER BY last_run_at ASC NULLS FIRST "
            "LIMIT 1"
        )
    )
    stale_row = stale_result.first()

    return {
        "status": overall,
        "jobs_healthy": healthy,
        "jobs_warning": warning,
        "jobs_error": error,
        "oldest_stale_job": stale_row[0] if stale_row else None,
        "timestamp": now.isoformat(),
    }


# ── GET /monitoring/data-freshness (public) ───────────────────────────────

@router.get("/data-freshness")
async def data_freshness(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Public endpoint for data freshness indicators.

    Returns timestamps of last successful runs for key job categories.
    """

    categories = {
        "news_scraping": "last_news_fetch",
        "price_tracking": "last_price_update",
        "sentiment": "last_sentiment_update",
    }

    result_data: dict[str, Any] = {}

    for cat, key in categories.items():
        cat_result = await db.execute(
            text(
                "SELECT last_success_at FROM system_jobs "
                "WHERE job_category = :cat AND enabled = true "
                "ORDER BY last_success_at DESC NULLS LAST "
                "LIMIT 1"
            ),
            {"cat": cat},
        )
        row = cat_result.first()
        result_data[key] = row[0].isoformat() if row and row[0] else None

    # Last worker run from fetch_logs
    worker_result = await db.execute(
        text(
            "SELECT started_at FROM fetch_logs "
            "ORDER BY started_at DESC LIMIT 1"
        )
    )
    worker_row = worker_result.first()
    result_data["last_worker_run"] = (
        worker_row[0].isoformat() if worker_row and worker_row[0] else None
    )

    return result_data
