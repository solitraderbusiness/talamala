"""Provenance logging helpers for metric computation pipelines.

Workers call these functions to record each step of their computation,
creating an audit trail in the ``metric_runs``, ``raw_ingests``, and
``transform_steps`` tables.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.data_reliability.config import DATA_RELIABILITY_VERBOSE
from api.data_reliability.models import MetricRun, RawIngest, TransformStep

logger = logging.getLogger("data_reliability.logger")


async def start_run(
    session: AsyncSession,
    metric_id: str,
    formula_version: str = "v1",
) -> MetricRun:
    """Create a new metric run record. Call at the start of computation."""
    run = MetricRun(
        metric_id=metric_id,
        started_at=datetime.now(timezone.utc),
        status="running",
        formula_version=formula_version,
    )
    session.add(run)
    await session.flush()  # Get the generated id
    return run


async def log_ingest(
    session: AsyncSession,
    run_id: UUID,
    source_id: str,
    url: str | None = None,
    params: dict | None = None,
    status: int | None = None,
    payload_sample: Any = None,
    latency_ms: int | None = None,
    data_timestamp: datetime | None = None,
    response_size: int | None = None,
) -> RawIngest:
    """Log a raw external API fetch. Call after each HTTP request."""
    # Sanitize params — strip API keys
    safe_params = _strip_secrets(params) if params else None

    # Hash payload for integrity tracking
    payload_str = json.dumps(payload_sample, default=str) if payload_sample else ""
    payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()[:16] if payload_str else None

    # In non-verbose mode, store only metadata summary
    if not DATA_RELIABILITY_VERBOSE and payload_sample:
        if isinstance(payload_sample, list):
            payload_sample = {"_record_count": len(payload_sample), "_type": "list"}
        elif isinstance(payload_sample, dict):
            payload_sample = {"_keys": list(payload_sample.keys())[:20], "_type": "dict"}

    ingest = RawIngest(
        run_id=run_id,
        source_id=source_id,
        request_url=url,
        request_params=safe_params,
        response_status=status,
        response_size_bytes=response_size,
        payload_hash=payload_hash,
        payload_sample=payload_sample,
        data_timestamp_in_payload=data_timestamp,
        retrieved_at=datetime.now(timezone.utc),
        latency_ms=latency_ms,
    )
    session.add(ingest)
    return ingest


async def log_transform(
    session: AsyncSession,
    run_id: UUID,
    step_order: int,
    step_name: str,
    input_refs: list | None = None,
    output_value: Any = None,
    normalization_method: str | None = None,
    normalization_params: dict | None = None,
    notes: str | None = None,
) -> TransformStep:
    """Log a computation/transformation step."""
    # Truncate large output values
    if output_value is not None:
        output_str = json.dumps(output_value, default=str)
        if len(output_str) > 10000:
            output_value = {"_truncated": True, "_size": len(output_str)}

    step = TransformStep(
        run_id=run_id,
        step_order=step_order,
        step_name=step_name,
        input_refs=input_refs,
        output_value=output_value,
        normalization_method=normalization_method,
        normalization_params=normalization_params,
        notes=notes,
    )
    session.add(step)
    return step


async def finish_run(
    session: AsyncSession,
    run: MetricRun,
    final_value: Any = None,
    data_timestamp: datetime | None = None,
    status: str = "success",
    error: str | None = None,
    qa_result: str | None = None,
    qa_reasons: list | None = None,
) -> None:
    """Finalize a metric run record. Call at the end of computation."""
    now = datetime.now(timezone.utc)
    run.finished_at = now
    run.duration_ms = int((now - run.started_at).total_seconds() * 1000)
    run.status = status
    run.final_value = final_value
    run.data_timestamp = data_timestamp
    run.error_message = error
    run.qa_result = qa_result
    run.qa_reasons = qa_reasons

    # Emit audit log for metric computation
    try:
        from api.audit import log_audit
        await log_audit(
            event_type="metric_compute",
            action=f"metric.{run.metric_id}",
            entity_type="metric_runs",
            entity_id=str(run.id),
            status=status,
            duration_ms=run.duration_ms,
            error_message=error,
            details={
                "metric_id": run.metric_id,
                "qa_result": qa_result,
                "formula_version": run.formula_version,
                "fallback_used": run.fallback_used,
            },
        )
    except Exception:
        pass  # Never fail due to audit logging


def _strip_secrets(params: dict) -> dict:
    """Remove sensitive keys from request parameters."""
    secret_keys = {"api_key", "apikey", "key", "token", "secret", "password"}
    return {
        k: "***" if k.lower() in secret_keys else v
        for k, v in params.items()
    }
