"""Query helpers for the Data Copilot.

All dynamic queries resolve source_table → ORM model via TABLE_MODEL_MAP.
No raw SQL is generated from user input.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.copilot.models import (
    TABLE_MODEL_MAP,
    CalcRun,
    DataFreshness,
    MetricRegistry,
)

logger = logging.getLogger("gold_monitor.copilot.queries")


async def get_all_registry(session: AsyncSession) -> list[MetricRegistry]:
    """Load all rows from metric_registry."""
    result = await session.execute(select(MetricRegistry))
    return list(result.scalars().all())


async def get_registry_row(session: AsyncSession, key: str) -> MetricRegistry | None:
    """Load a single metric_registry row by key."""
    result = await session.execute(
        select(MetricRegistry).where(MetricRegistry.key == key)
    )
    return result.scalar_one_or_none()


async def query_metric_latest(
    session: AsyncSession,
    reg: MetricRegistry,
) -> dict[str, Any] | None:
    """Query latest value for a metric using its registry source mapping.

    Returns dict with value, ts, source info, staleness — or None if no data.
    """
    if not reg.source_table or reg.source_table not in TABLE_MODEL_MAP:
        return None

    model = TABLE_MODEL_MAP[reg.source_table]
    value_col = getattr(model, reg.source_column, None)
    ts_col = getattr(model, reg.ts_column, None)
    if value_col is None or ts_col is None:
        return None

    stmt = select(value_col, ts_col)

    # Apply source_filter entries as WHERE clauses
    if reg.source_filter and isinstance(reg.source_filter, dict):
        for k, v in reg.source_filter.items():
            filter_col = getattr(model, k, None)
            if filter_col is not None:
                stmt = stmt.where(filter_col == v)

    stmt = stmt.order_by(desc(ts_col)).limit(1)
    result = await session.execute(stmt)
    row = result.first()

    if row is None:
        return None

    raw_value = row[0]
    raw_ts = row[1]

    # Compute age
    now = datetime.now(timezone.utc)
    if hasattr(raw_ts, "tzinfo") and raw_ts.tzinfo:
        age_hours = (now - raw_ts).total_seconds() / 3600
    else:
        # Date or naive datetime
        from datetime import date as date_type
        if isinstance(raw_ts, date_type):
            ts_dt = datetime(raw_ts.year, raw_ts.month, raw_ts.day, tzinfo=timezone.utc)
        else:
            ts_dt = raw_ts.replace(tzinfo=timezone.utc)
        age_hours = (now - ts_dt).total_seconds() / 3600

    is_stale = age_hours > (reg.staleness_hours or 96)

    return {
        "key": reg.key,
        "label_fa": reg.label_fa,
        "label_en": reg.label_en,
        "value": float(raw_value) if raw_value is not None else None,
        "unit": reg.unit,
        "ts": str(raw_ts),
        "source_name": reg.source_name,
        "source_id": reg.source_id,
        "frequency": reg.frequency,
        "age_hours": round(age_hours, 1),
        "is_stale": is_stale,
        "direction_for_gold": reg.direction_for_gold,
        "precision": reg.precision,
    }


async def query_metric_range(
    session: AsyncSession,
    reg: MetricRegistry,
    days: int = 30,
    limit: int = 365,
) -> list[dict[str, Any]]:
    """Query time series for a metric over a date range.

    Returns list of {ts, value} dicts, chronologically ordered.
    """
    if not reg.source_table or reg.source_table not in TABLE_MODEL_MAP:
        return []

    model = TABLE_MODEL_MAP[reg.source_table]
    value_col = getattr(model, reg.source_column, None)
    ts_col = getattr(model, reg.ts_column, None)
    if value_col is None or ts_col is None:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = select(value_col, ts_col)

    if reg.source_filter and isinstance(reg.source_filter, dict):
        for k, v in reg.source_filter.items():
            filter_col = getattr(model, k, None)
            if filter_col is not None:
                stmt = stmt.where(filter_col == v)

    # Filter by date range
    from datetime import date as date_type
    if hasattr(cutoff, "date"):
        cutoff_val = cutoff.date()
    else:
        cutoff_val = cutoff
    stmt = stmt.where(ts_col >= cutoff_val)
    stmt = stmt.order_by(ts_col).limit(limit)

    result = await session.execute(stmt)
    rows = result.all()

    return [
        {"ts": str(row[1]), "value": float(row[0]) if row[0] is not None else None}
        for row in rows
    ]


async def query_calc_run_latest(
    session: AsyncSession,
    run_type: str,
) -> CalcRun | None:
    """Get the latest CalcRun for a given run_type."""
    result = await session.execute(
        select(CalcRun)
        .where(CalcRun.run_type == run_type)
        .order_by(desc(CalcRun.ts))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def compute_metric_freshness(session: AsyncSession) -> list[dict[str, Any]]:
    """Compute freshness for all registered metrics.

    Returns list of dicts with staleness info for each metric.
    """
    registry = await get_all_registry(session)
    now = datetime.now(timezone.utc)
    results = []

    for reg in registry:
        if reg.source_table == "calc_runs" or not reg.source_table:
            # Computed metrics — check calc_runs
            run_type_map = {
                "sentiment_composite": "sentiment_score",
                "risk_radar": "risk_radar",
            }
            run_type = run_type_map.get(reg.key)
            if run_type:
                run = await query_calc_run_latest(session, run_type)
                last_ts = run.ts if run else None
            else:
                last_ts = None
        elif reg.source_table in TABLE_MODEL_MAP:
            latest = await query_metric_latest(session, reg)
            if latest and latest.get("ts"):
                # Parse ts string back
                from datetime import date as date_type
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
            else:
                last_ts = None
        else:
            last_ts = None

        if last_ts is not None:
            if not hasattr(last_ts, "tzinfo") or last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
            age_hours = (now - last_ts).total_seconds() / 3600
        else:
            age_hours = None

        is_stale = (
            age_hours is not None
            and age_hours > (reg.staleness_hours or 96)
        ) or (age_hours is None)

        results.append({
            "key": reg.key,
            "label_fa": reg.label_fa,
            "frequency": reg.frequency,
            "last_data_at": str(last_ts) if last_ts else None,
            "age_hours": round(age_hours, 1) if age_hours is not None else None,
            "is_stale": is_stale,
            "expected_frequency": reg.frequency,
            "staleness_hours": reg.staleness_hours,
        })

    return results
