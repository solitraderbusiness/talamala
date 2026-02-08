"""
Alerts router -- list, detail, and today's stats for gold-monitor alerts.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, cast, desc, func, or_, select, String
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import Alert, Severity

router = APIRouter(tags=["alerts"])

# -- Severity weight mapping for risk-score calculation --------------------
_SEVERITY_WEIGHT: dict[str, int] = {
    "high": 15,
    "medium": 7,
    "low": 2,
}


# -- Helpers ---------------------------------------------------------------


def _apply_alert_filters(
    stmt: Select,
    *,
    asset: str | None,
    severity: str | None,
    time_horizon: str | None,
    q: str | None,
    from_date: datetime.datetime | None,
    to_date: datetime.datetime | None,
) -> Select:
    """Apply optional query-parameter filters to an alert SELECT."""

    if severity is not None:
        stmt = stmt.where(Alert.severity == severity)

    if time_horizon is not None:
        stmt = stmt.where(Alert.time_horizon == time_horizon)

    if asset is not None:
        # Asset may appear inside the JSONB matched_rule_ids array or the
        # expected_impact JSONB object.  Cast to text and use ILIKE for a
        # pragmatic, case-insensitive search.
        asset_pattern = f"%{asset.lower()}%"
        stmt = stmt.where(
            or_(
                cast(Alert.matched_rule_ids, String).ilike(asset_pattern),
                cast(Alert.expected_impact, String).ilike(asset_pattern),
            )
        )

    if q is not None:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Alert.title.ilike(pattern),
                Alert.summary_fa.ilike(pattern),
            )
        )

    if from_date is not None:
        stmt = stmt.where(Alert.created_at >= from_date)

    if to_date is not None:
        stmt = stmt.where(Alert.created_at <= to_date)

    return stmt


# -- GET /alerts -----------------------------------------------------------


@router.get("")
async def list_alerts(
    db: AsyncSession = Depends(get_db),
    asset: str | None = Query(
        None,
        description="Filter by asset keyword in matched_rule_ids / expected_impact",
    ),
    severity: str | None = Query(
        None,
        description="Exact severity filter: low, medium, high",
    ),
    time_horizon: str | None = Query(
        None,
        description="Exact time-horizon filter: immediate, short, medium, long",
    ),
    q: str | None = Query(
        None,
        description="Free-text search in title and summary_fa",
    ),
    from_date: datetime.datetime | None = Query(
        None,
        description="Start of date range (created_at >=)",
    ),
    to_date: datetime.datetime | None = Query(
        None,
        description="End of date range (created_at <=)",
    ),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> dict[str, Any]:
    """Return a paginated, filterable list of alerts ordered by created_at desc."""

    base = select(Alert)
    base = _apply_alert_filters(
        base,
        asset=asset,
        severity=severity,
        time_horizon=time_horizon,
        q=q,
        from_date=from_date,
        to_date=to_date,
    )

    # Total count (without limit / offset)
    count_stmt = select(func.count()).select_from(base.subquery())
    total: int = (await db.execute(count_stmt)).scalar_one()

    # Fetch the requested page
    items_stmt = base.order_by(desc(Alert.created_at)).limit(limit).offset(offset)
    result = await db.execute(items_stmt)
    alerts = result.scalars().all()

    return {
        "items": alerts,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# -- GET /alerts/stats/today  (registered BEFORE the {alert_id} catch-all) -


@router.get("/stats/today")
async def alerts_stats_today(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Risk score, severity counts, and top alerts from the last 24 hours."""

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)

    # -- severity counts ---------------------------------------------------
    count_stmt = (
        select(Alert.severity, func.count().label("cnt"))
        .where(Alert.created_at >= cutoff)
        .group_by(Alert.severity)
    )
    rows = (await db.execute(count_stmt)).all()

    counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for sev, cnt in rows:
        key = sev.value if isinstance(sev, Severity) else str(sev)
        counts[key] = cnt

    # -- risk score --------------------------------------------------------
    risk_score = sum(
        counts.get(sev, 0) * weight for sev, weight in _SEVERITY_WEIGHT.items()
    )
    risk_score = min(risk_score, 100)

    # -- top 3 alerts (highest severity first, then most recent) -----------
    severity_order = func.array_position(
        func.cast("{high,medium,low}", String),
        cast(Alert.severity, String),
    )
    top_stmt = (
        select(Alert)
        .where(Alert.created_at >= cutoff)
        .order_by(severity_order, desc(Alert.created_at))
        .limit(3)
    )
    top_alerts = (await db.execute(top_stmt)).scalars().all()

    return {
        "top_alerts": top_alerts,
        "risk_score": risk_score,
        "counts": counts,
    }


# -- GET /alerts/{alert_id} -----------------------------------------------


@router.get("/{alert_id}")
async def get_alert(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Alert:
    """Return a single alert by its UUID, or 404."""

    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )
    return alert
