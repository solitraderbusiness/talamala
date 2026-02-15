"""Unified audit logging for the Gold Monitor system.

Provides a single ``log_audit`` function that all subsystems call to
record provenance — job runs, data ingestions, metric computations,
alert generation, and admin actions — into the ``audit_logs`` table.

Usage::

    from api.audit import log_audit, new_trace_id

    trace = new_trace_id()
    await log_audit(
        event_type="job_run",
        action="yahoo_fetcher.run",
        entity_type="asset_prices_daily",
        details={"symbols": 7, "rows_inserted": 42},
        trace_id=trace,
        duration_ms=1234,
    )
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from api.database import AsyncSessionLocal

logger = logging.getLogger("audit")


def new_trace_id() -> str:
    """Generate a new trace ID (UUID4 hex, 32 chars)."""
    return uuid.uuid4().hex


async def log_audit(
    *,
    event_type: str,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: dict[str, Any] | None = None,
    trace_id: str | None = None,
    parent_trace_id: str | None = None,
    actor: str = "system",
    status: str = "success",
    error_message: str | None = None,
    duration_ms: int | None = None,
    code_version: str | None = None,
) -> None:
    """Insert a single audit log entry.

    Silently catches exceptions so callers don't fail due to logging.
    """
    if trace_id is None:
        trace_id = new_trace_id()

    import json

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text(
                    "INSERT INTO audit_logs "
                    "  (id, trace_id, parent_trace_id, event_type, actor, "
                    "   entity_type, entity_id, action, details, "
                    "   duration_ms, status, error_message, code_version, created_at) "
                    "VALUES "
                    "  (gen_random_uuid(), :trace, :parent, :etype, :actor, "
                    "   :entity_type, :entity_id, :action, CAST(:details AS jsonb), "
                    "   :dur, :status, :err, :ver, NOW())"
                ),
                {
                    "trace": trace_id,
                    "parent": parent_trace_id,
                    "etype": event_type,
                    "actor": actor,
                    "entity_type": entity_type,
                    "entity_id": str(entity_id) if entity_id else None,
                    "action": action,
                    "details": json.dumps(details or {}, default=str),
                    "dur": duration_ms,
                    "status": status,
                    "err": error_message[:2000] if error_message else None,
                    "ver": code_version,
                },
            )
            await session.commit()
    except Exception:
        logger.debug("Failed to write audit log", exc_info=True)
