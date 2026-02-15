"""Admin API endpoints for data reliability & provenance.

All endpoints require admin authentication.
Mounted at ``/api/admin/data-reliability``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select

from api.database import AsyncSessionLocal
from api.routers.admin import get_current_admin
from api.data_reliability.models import (
    MetricAlert,
    MetricDefinition,
    MetricRun,
    RawIngest,
    TransformStep,
    ValidationResult,
)

router = APIRouter(tags=["data-reliability"], dependencies=[Depends(get_current_admin)])
logger = logging.getLogger("data_reliability.routes")


# ── Overview dashboard ────────────────────────────────────────────────

@router.get("/overview")
async def overview():
    """Dashboard summary: metric counts, pass/warn/fail, staleness, 24h stats."""
    async with AsyncSessionLocal() as session:
        # Get all metric definitions
        defs_q = await session.execute(select(func.count()).select_from(MetricDefinition))
        total_metrics = defs_q.scalar() or 0

        # Get latest run per metric with QA status
        since_24h = datetime.now(timezone.utc) - timedelta(hours=24)

        # Latest QA results per metric (using subquery)
        latest_runs_q = await session.execute(
            select(MetricRun.metric_id, MetricRun.qa_result, MetricRun.status)
            .distinct(MetricRun.metric_id)
            .order_by(MetricRun.metric_id, desc(MetricRun.started_at))
        )
        latest_runs = latest_runs_q.all()

        pass_count = sum(1 for _, qa, st in latest_runs if qa == "pass" and st == "success")
        warning_count = sum(1 for _, qa, st in latest_runs if qa == "warning" and st == "success")
        fail_count = sum(1 for _, qa, st in latest_runs if qa == "fail" or st == "failed")
        no_data_count = total_metrics - len(latest_runs)

        # 24h run stats
        runs_24h_q = await session.execute(
            select(func.count(), func.avg(MetricRun.duration_ms))
            .select_from(MetricRun)
            .where(MetricRun.started_at >= since_24h)
        )
        runs_24h_row = runs_24h_q.one()
        total_runs_24h = runs_24h_row[0] or 0
        avg_duration_24h = round(runs_24h_row[1] or 0)

        success_24h_q = await session.execute(
            select(func.count())
            .select_from(MetricRun)
            .where(MetricRun.started_at >= since_24h, MetricRun.status == "success")
        )
        success_24h = success_24h_q.scalar() or 0
        success_rate = round(success_24h / total_runs_24h * 100, 1) if total_runs_24h > 0 else 0

        # Unresolved alerts
        alerts_q = await session.execute(
            select(func.count())
            .select_from(MetricAlert)
            .where(MetricAlert.resolved_at.is_(None))
        )
        unresolved_alerts = alerts_q.scalar() or 0

        return {
            "total_metrics": total_metrics,
            "qa_summary": {
                "pass": pass_count,
                "warning": warning_count,
                "fail": fail_count,
                "no_data": no_data_count,
            },
            "runs_24h": {
                "total": total_runs_24h,
                "success_rate_pct": success_rate,
                "avg_duration_ms": avg_duration_24h,
            },
            "unresolved_alerts": unresolved_alerts,
        }


# ── Metric definitions list ──────────────────────────────────────────

@router.get("/metrics")
async def list_metrics():
    """List all metric definitions with their latest run status."""
    async with AsyncSessionLocal() as session:
        defs_q = await session.execute(
            select(MetricDefinition).order_by(MetricDefinition.metric_id)
        )
        definitions = defs_q.scalars().all()

        metrics = []
        for d in definitions:
            # Get latest run
            latest_q = await session.execute(
                select(MetricRun)
                .where(MetricRun.metric_id == d.metric_id)
                .order_by(desc(MetricRun.started_at))
                .limit(1)
            )
            latest = latest_q.scalar_one_or_none()

            metrics.append({
                "metric_id": d.metric_id,
                "display_name": d.display_name,
                "unit": d.unit,
                "update_frequency_minutes": d.update_frequency_minutes,
                "formula_version": d.formula_version,
                "latest_run": {
                    "run_id": str(latest.id) if latest else None,
                    "status": latest.status if latest else None,
                    "qa_result": latest.qa_result if latest else None,
                    "final_value": latest.final_value if latest else None,
                    "started_at": latest.started_at.isoformat() if latest and latest.started_at else None,
                    "duration_ms": latest.duration_ms if latest else None,
                    "data_timestamp": latest.data_timestamp.isoformat() if latest and latest.data_timestamp else None,
                } if latest else None,
            })

        return {"metrics": metrics}


# ── Single metric detail ─────────────────────────────────────────────

@router.get("/metrics/{metric_id}")
async def get_metric(metric_id: str):
    """Full Data Card + latest value + QA status for a specific metric."""
    async with AsyncSessionLocal() as session:
        defn_q = await session.execute(
            select(MetricDefinition).where(MetricDefinition.metric_id == metric_id)
        )
        defn = defn_q.scalar_one_or_none()
        if not defn:
            return {"error": "Metric not found", "metric_id": metric_id}

        # Latest run
        latest_q = await session.execute(
            select(MetricRun)
            .where(MetricRun.metric_id == metric_id)
            .order_by(desc(MetricRun.started_at))
            .limit(1)
        )
        latest = latest_q.scalar_one_or_none()

        return {
            "metric_id": defn.metric_id,
            "display_name": defn.display_name,
            "description": defn.description,
            "unit": defn.unit,
            "timezone": defn.timezone,
            "update_frequency_minutes": defn.update_frequency_minutes,
            "formula_version": defn.formula_version,
            "raw_sources": defn.raw_sources,
            "formula_steps": defn.formula_steps,
            "dependencies": defn.dependencies,
            "expected_range": defn.expected_range,
            "sanity_rules": defn.sanity_rules,
            "latest_run": {
                "run_id": str(latest.id),
                "status": latest.status,
                "qa_result": latest.qa_result,
                "qa_reasons": latest.qa_reasons,
                "final_value": latest.final_value,
                "started_at": latest.started_at.isoformat() if latest.started_at else None,
                "finished_at": latest.finished_at.isoformat() if latest.finished_at else None,
                "duration_ms": latest.duration_ms,
                "data_timestamp": latest.data_timestamp.isoformat() if latest.data_timestamp else None,
                "formula_version": latest.formula_version,
                "fallback_used": latest.fallback_used,
                "error_message": latest.error_message,
            } if latest else None,
        }


# ── Run history for a metric ─────────────────────────────────────────

@router.get("/metrics/{metric_id}/runs")
async def list_runs(
    metric_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Paginated run history for a specific metric."""
    async with AsyncSessionLocal() as session:
        total_q = await session.execute(
            select(func.count()).select_from(MetricRun).where(MetricRun.metric_id == metric_id)
        )
        total = total_q.scalar() or 0

        runs_q = await session.execute(
            select(MetricRun)
            .where(MetricRun.metric_id == metric_id)
            .order_by(desc(MetricRun.started_at))
            .offset(offset)
            .limit(limit)
        )
        runs = runs_q.scalars().all()

        return {
            "metric_id": metric_id,
            "total": total,
            "offset": offset,
            "limit": limit,
            "runs": [
                {
                    "run_id": str(r.id),
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                    "duration_ms": r.duration_ms,
                    "status": r.status,
                    "qa_result": r.qa_result,
                    "final_value": r.final_value,
                    "data_timestamp": r.data_timestamp.isoformat() if r.data_timestamp else None,
                    "formula_version": r.formula_version,
                    "error_message": r.error_message,
                }
                for r in runs
            ],
        }


# ── Run detail (drill-down) ──────────────────────────────────────────

@router.get("/metrics/{metric_id}/runs/{run_id}")
async def get_run_detail(metric_id: str, run_id: str):
    """Full run detail: raw ingests + transform steps + validations."""
    async with AsyncSessionLocal() as session:
        run_uuid = UUID(run_id)

        run_q = await session.execute(
            select(MetricRun).where(MetricRun.id == run_uuid, MetricRun.metric_id == metric_id)
        )
        run = run_q.scalar_one_or_none()
        if not run:
            return {"error": "Run not found"}

        # Raw ingests
        ingests_q = await session.execute(
            select(RawIngest).where(RawIngest.run_id == run_uuid).order_by(RawIngest.retrieved_at)
        )
        ingests = ingests_q.scalars().all()

        # Transform steps
        steps_q = await session.execute(
            select(TransformStep).where(TransformStep.run_id == run_uuid).order_by(TransformStep.step_order)
        )
        steps = steps_q.scalars().all()

        # Validations
        validations_q = await session.execute(
            select(ValidationResult).where(ValidationResult.run_id == run_uuid)
        )
        validations = validations_q.scalars().all()

        return {
            "run": {
                "run_id": str(run.id),
                "metric_id": run.metric_id,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "duration_ms": run.duration_ms,
                "status": run.status,
                "qa_result": run.qa_result,
                "qa_reasons": run.qa_reasons,
                "final_value": run.final_value,
                "data_timestamp": run.data_timestamp.isoformat() if run.data_timestamp else None,
                "formula_version": run.formula_version,
                "fallback_used": run.fallback_used,
                "error_message": run.error_message,
            },
            "raw_ingests": [
                {
                    "id": str(i.id),
                    "source_id": i.source_id,
                    "request_url": i.request_url,
                    "request_params": i.request_params,
                    "response_status": i.response_status,
                    "response_size_bytes": i.response_size_bytes,
                    "payload_hash": i.payload_hash,
                    "payload_sample": i.payload_sample,
                    "data_timestamp": i.data_timestamp_in_payload.isoformat() if i.data_timestamp_in_payload else None,
                    "retrieved_at": i.retrieved_at.isoformat() if i.retrieved_at else None,
                    "latency_ms": i.latency_ms,
                }
                for i in ingests
            ],
            "transform_steps": [
                {
                    "step_order": s.step_order,
                    "step_name": s.step_name,
                    "input_refs": s.input_refs,
                    "output_value": s.output_value,
                    "normalization_method": s.normalization_method,
                    "normalization_params": s.normalization_params,
                    "notes": s.notes,
                }
                for s in steps
            ],
            "validations": [
                {
                    "check_name": v.check_name,
                    "result": v.result,
                    "reason": v.reason,
                    "details": v.details,
                }
                for v in validations
            ],
        }


# ── Alerts ────────────────────────────────────────────────────────────

@router.get("/alerts")
async def list_alerts(
    limit: int = Query(50, ge=1, le=200),
    unresolved_only: bool = Query(False),
    metric_id: str | None = Query(None),
):
    """Recent metric alerts with optional filtering."""
    async with AsyncSessionLocal() as session:
        q = select(MetricAlert)
        if unresolved_only:
            q = q.where(MetricAlert.resolved_at.is_(None))
        if metric_id:
            q = q.where(MetricAlert.metric_id == metric_id)
        q = q.order_by(desc(MetricAlert.created_at)).limit(limit)

        result = await session.execute(q)
        alerts = result.scalars().all()

        return {
            "alerts": [
                {
                    "id": str(a.id),
                    "metric_id": a.metric_id,
                    "alert_type": a.alert_type,
                    "severity": a.severity,
                    "message": a.message,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
                }
                for a in alerts
            ],
            "total": len(alerts),
        }


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    """Mark a metric alert as resolved."""
    async with AsyncSessionLocal() as session:
        alert_q = await session.execute(
            select(MetricAlert).where(MetricAlert.id == UUID(alert_id))
        )
        alert = alert_q.scalar_one_or_none()
        if not alert:
            return {"error": "Alert not found"}

        alert.resolved_at = datetime.now(timezone.utc)
        await session.commit()
        return {"status": "resolved", "alert_id": alert_id}
