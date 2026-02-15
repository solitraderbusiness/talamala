"""Admin API endpoints for the unified audit log.

Mounted at ``/api/admin/audit-logs``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select, text

from api.database import AsyncSessionLocal
from api.routers.admin import get_current_admin

router = APIRouter(tags=["audit-logs"], dependencies=[Depends(get_current_admin)])
logger = logging.getLogger("audit.routes")


@router.get("/overview")
async def audit_overview():
    """Summary stats for the audit log dashboard."""
    async with AsyncSessionLocal() as session:
        since_24h = datetime.now(timezone.utc) - timedelta(hours=24)
        since_7d = datetime.now(timezone.utc) - timedelta(days=7)

        # Total entries 24h
        total_24h_q = await session.execute(
            text("SELECT COUNT(*) FROM audit_logs WHERE created_at >= :since"),
            {"since": since_24h},
        )
        total_24h = total_24h_q.scalar() or 0

        # By event type (24h)
        by_type_q = await session.execute(
            text(
                "SELECT event_type, COUNT(*), "
                "  SUM(CASE WHEN status = 'failure' THEN 1 ELSE 0 END) as failures "
                "FROM audit_logs WHERE created_at >= :since "
                "GROUP BY event_type ORDER BY COUNT(*) DESC"
            ),
            {"since": since_24h},
        )
        by_type = [
            {"event_type": row[0], "count": row[1], "failures": row[2]}
            for row in by_type_q.all()
        ]

        # Failure rate 24h
        failures_24h = sum(t["failures"] for t in by_type)
        failure_rate = round(failures_24h / total_24h * 100, 1) if total_24h > 0 else 0

        # Total 7d
        total_7d_q = await session.execute(
            text("SELECT COUNT(*) FROM audit_logs WHERE created_at >= :since"),
            {"since": since_7d},
        )
        total_7d = total_7d_q.scalar() or 0

        # Top actors 24h
        actors_q = await session.execute(
            text(
                "SELECT actor, COUNT(*) FROM audit_logs "
                "WHERE created_at >= :since GROUP BY actor ORDER BY COUNT(*) DESC LIMIT 10"
            ),
            {"since": since_24h},
        )
        top_actors = [{"actor": row[0], "count": row[1]} for row in actors_q.all()]

        return {
            "total_24h": total_24h,
            "total_7d": total_7d,
            "failure_rate_24h": failure_rate,
            "failures_24h": failures_24h,
            "by_event_type": by_type,
            "top_actors": top_actors,
        }


@router.get("")
async def list_audit_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    event_type: str | None = Query(None),
    entity_type: str | None = Query(None),
    trace_id: str | None = Query(None),
    actor: str | None = Query(None),
    status: str | None = Query(None),
    action: str | None = Query(None),
    hours: int | None = Query(None, ge=1, le=720),
):
    """Paginated, filterable audit log listing."""
    async with AsyncSessionLocal() as session:
        conditions = []
        params: dict = {}

        if event_type:
            conditions.append("event_type = :etype")
            params["etype"] = event_type
        if entity_type:
            conditions.append("entity_type = :entity_type")
            params["entity_type"] = entity_type
        if trace_id:
            conditions.append("trace_id = :trace_id")
            params["trace_id"] = trace_id
        if actor:
            conditions.append("actor = :actor")
            params["actor"] = actor
        if status:
            conditions.append("status = :status")
            params["status"] = status
        if action:
            conditions.append("action ILIKE :action")
            params["action"] = f"%{action}%"
        if hours:
            conditions.append("created_at >= :since")
            params["since"] = datetime.now(timezone.utc) - timedelta(hours=hours)

        where = " AND ".join(conditions) if conditions else "1=1"

        # Count
        count_q = await session.execute(
            text(f"SELECT COUNT(*) FROM audit_logs WHERE {where}"), params
        )
        total = count_q.scalar() or 0

        # Data
        offset = (page - 1) * per_page
        data_q = await session.execute(
            text(
                f"SELECT id, trace_id, parent_trace_id, event_type, actor, "
                f"  entity_type, entity_id, action, details, duration_ms, "
                f"  status, error_message, code_version, created_at "
                f"FROM audit_logs WHERE {where} "
                f"ORDER BY created_at DESC "
                f"LIMIT :limit OFFSET :offset"
            ),
            {**params, "limit": per_page, "offset": offset},
        )

        logs = []
        for row in data_q.all():
            logs.append({
                "id": str(row[0]),
                "trace_id": row[1],
                "parent_trace_id": row[2],
                "event_type": row[3],
                "actor": row[4],
                "entity_type": row[5],
                "entity_id": row[6],
                "action": row[7],
                "details": row[8],
                "duration_ms": row[9],
                "status": row[10],
                "error_message": row[11],
                "code_version": row[12],
                "created_at": row[13].isoformat() if row[13] else None,
            })

        return {
            "items": logs,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page if per_page > 0 else 0,
        }


@router.get("/trace/{trace_id}")
async def get_trace(trace_id: str):
    """Get all audit log entries for a specific trace ID."""
    async with AsyncSessionLocal() as session:
        q = await session.execute(
            text(
                "SELECT id, trace_id, parent_trace_id, event_type, actor, "
                "  entity_type, entity_id, action, details, duration_ms, "
                "  status, error_message, code_version, created_at "
                "FROM audit_logs "
                "WHERE trace_id = :tid OR parent_trace_id = :tid "
                "ORDER BY created_at ASC"
            ),
            {"tid": trace_id},
        )

        logs = []
        for row in q.all():
            logs.append({
                "id": str(row[0]),
                "trace_id": row[1],
                "parent_trace_id": row[2],
                "event_type": row[3],
                "actor": row[4],
                "entity_type": row[5],
                "entity_id": row[6],
                "action": row[7],
                "details": row[8],
                "duration_ms": row[9],
                "status": row[10],
                "error_message": row[11],
                "code_version": row[12],
                "created_at": row[13].isoformat() if row[13] else None,
            })

        return {"trace_id": trace_id, "entries": logs, "total": len(logs)}


@router.get("/event-types")
async def list_event_types():
    """List distinct event types for filter dropdowns."""
    async with AsyncSessionLocal() as session:
        q = await session.execute(
            text("SELECT DISTINCT event_type FROM audit_logs ORDER BY event_type")
        )
        return {"event_types": [row[0] for row in q.all()]}


@router.get("/entity-types")
async def list_entity_types():
    """List distinct entity types for filter dropdowns."""
    async with AsyncSessionLocal() as session:
        q = await session.execute(
            text(
                "SELECT DISTINCT entity_type FROM audit_logs "
                "WHERE entity_type IS NOT NULL ORDER BY entity_type"
            )
        )
        return {"entity_types": [row[0] for row in q.all()]}
