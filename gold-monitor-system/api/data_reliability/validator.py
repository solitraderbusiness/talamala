"""QA validation runner for metric computations.

Runs standardized checks (range, staleness, spike, schema) and stores
results in the ``validation_results`` table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.data_reliability.config import METRIC_QA_CONFIG
from api.data_reliability.models import MetricAlert, MetricRun, ValidationResult

logger = logging.getLogger("data_reliability.validator")


async def validate_metric(
    session: AsyncSession,
    run_id: UUID,
    metric_id: str,
    value: Any,
    data_timestamp: datetime | None = None,
) -> str:
    """Run all applicable QA checks for a metric.

    Returns ``"pass"``, ``"warning"``, or ``"fail"``.
    Stores individual check results in ``validation_results``.
    """
    config = METRIC_QA_CONFIG.get(metric_id, {})
    results: list[dict] = []
    overall = "pass"

    # 1. Range check
    if "hard_range" in config and _is_numeric(value):
        val = float(value)
        hard_min, hard_max = config["hard_range"]
        soft_min, soft_max = config.get("soft_range", (hard_min, hard_max))

        if val < hard_min or val > hard_max:
            results.append({"check": "range_check", "result": "fail",
                            "reason": f"Value {val} outside hard range [{hard_min}, {hard_max}]"})
            overall = "fail"
        elif val < soft_min or val > soft_max:
            results.append({"check": "range_check", "result": "warning",
                            "reason": f"Value {val} outside soft range [{soft_min}, {soft_max}]"})
            if overall != "fail":
                overall = "warning"
        else:
            results.append({"check": "range_check", "result": "pass", "reason": "Within expected range"})

    # 2. Staleness check
    if "max_staleness_hours" in config and data_timestamp:
        age_hours = (datetime.now(timezone.utc) - data_timestamp).total_seconds() / 3600
        max_h = config["max_staleness_hours"]
        if age_hours > max_h * 4:
            results.append({"check": "staleness_check", "result": "fail",
                            "reason": f"Data is {age_hours:.1f}h old (4x threshold of {max_h}h)"})
            overall = "fail"
        elif age_hours > max_h * 2:
            results.append({"check": "staleness_check", "result": "warning",
                            "reason": f"Data is {age_hours:.1f}h old (2x threshold of {max_h}h)"})
            if overall != "fail":
                overall = "warning"
        else:
            results.append({"check": "staleness_check", "result": "pass",
                            "reason": f"Data is {age_hours:.1f}h old (within {max_h}h threshold)"})

    # 3. Spike check — compare with previous run
    if "spike_threshold_pct" in config and _is_numeric(value):
        prev_run = await session.execute(
            select(MetricRun)
            .where(
                MetricRun.metric_id == metric_id,
                MetricRun.status == "success",
                MetricRun.id != run_id,
            )
            .order_by(desc(MetricRun.started_at))
            .limit(1)
        )
        prev = prev_run.scalar_one_or_none()
        if prev and prev.final_value is not None and _is_numeric(prev.final_value):
            prev_val = float(prev.final_value)
            cur_val = float(value)
            if prev_val != 0:
                pct_change = abs(cur_val - prev_val) / abs(prev_val) * 100
                threshold = config["spike_threshold_pct"]
                if pct_change > threshold * 2:
                    results.append({"check": "spike_check", "result": "fail",
                                    "reason": f"Change {pct_change:.1f}% exceeds 2x spike threshold {threshold}%"})
                    overall = "fail"
                elif pct_change > threshold:
                    results.append({"check": "spike_check", "result": "warning",
                                    "reason": f"Change {pct_change:.1f}% exceeds spike threshold {threshold}%"})
                    if overall != "fail":
                        overall = "warning"
                else:
                    results.append({"check": "spike_check", "result": "pass",
                                    "reason": f"Change {pct_change:.1f}% within threshold"})

    # 4. Missingness check
    if value is None:
        results.append({"check": "missingness_check", "result": "fail",
                        "reason": "Output value is None"})
        overall = "fail"
    else:
        results.append({"check": "missingness_check", "result": "pass", "reason": "Value present"})

    # Persist each result
    for r in results:
        session.add(ValidationResult(
            run_id=run_id,
            check_name=r["check"],
            result=r["result"],
            reason=r["reason"],
        ))

    return overall


async def create_alert_if_needed(
    session: AsyncSession,
    metric_id: str,
    qa_result: str,
    reason: str | None = None,
) -> None:
    """Create a metric alert if QA result is fail, or resolve existing alerts if pass."""
    if qa_result == "fail":
        # Check for existing unresolved alert
        existing = await session.execute(
            select(MetricAlert).where(
                MetricAlert.metric_id == metric_id,
                MetricAlert.resolved_at.is_(None),
            ).limit(1)
        )
        if not existing.scalar_one_or_none():
            session.add(MetricAlert(
                metric_id=metric_id,
                alert_type="qa_fail",
                severity="critical",
                message=reason or f"QA validation failed for {metric_id}",
            ))
    elif qa_result == "pass":
        # Resolve any existing unresolved alerts
        existing_q = await session.execute(
            select(MetricAlert).where(
                MetricAlert.metric_id == metric_id,
                MetricAlert.resolved_at.is_(None),
            )
        )
        for alert in existing_q.scalars().all():
            alert.resolved_at = datetime.now(timezone.utc)


def _is_numeric(value: Any) -> bool:
    """Check if a value can be treated as a number."""
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
            return True
        except ValueError:
            return False
    return False
