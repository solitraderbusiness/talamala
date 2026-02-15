"""Publish/fallback logic for metric values.

If QA passes or warns, the new value is published.
If QA fails, the last-known-good value is returned instead,
marked as stale.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.data_reliability.models import MetricRun

logger = logging.getLogger("data_reliability.publisher")


async def publish_or_fallback(
    session: AsyncSession,
    metric_id: str,
    run_id: UUID,
    qa_result: str,
    value: Any,
    data_timestamp: datetime | None = None,
) -> dict:
    """Return the value to publish, with QA metadata.

    Returns::

        {
            "value": ...,
            "qa_status": "pass" | "warning" | "fail",
            "stale": bool,
            "data_timestamp": str | None,
            "last_good_at": str | None,   # only if stale
        }
    """
    if qa_result in ("pass", "warning"):
        return {
            "value": value,
            "qa_status": qa_result,
            "stale": False,
            "data_timestamp": data_timestamp.isoformat() if data_timestamp else None,
        }

    # QA failed — find last-known-good
    last_good_q = await session.execute(
        select(MetricRun)
        .where(
            MetricRun.metric_id == metric_id,
            MetricRun.qa_result.in_(["pass", "warning"]),
            MetricRun.status == "success",
        )
        .order_by(desc(MetricRun.started_at))
        .limit(1)
    )
    last_good = last_good_q.scalar_one_or_none()

    if last_good:
        logger.warning(
            "Metric %s QA failed — falling back to value from %s",
            metric_id, last_good.started_at,
        )
        return {
            "value": last_good.final_value,
            "qa_status": "fail",
            "stale": True,
            "data_timestamp": last_good.data_timestamp.isoformat() if last_good.data_timestamp else None,
            "last_good_at": last_good.started_at.isoformat() if last_good.started_at else None,
        }

    # No good value ever — return the bad value with clear marking
    logger.warning("Metric %s QA failed and no previous good value exists", metric_id)
    return {
        "value": value,
        "qa_status": "fail",
        "stale": True,
        "data_timestamp": data_timestamp.isoformat() if data_timestamp else None,
    }
