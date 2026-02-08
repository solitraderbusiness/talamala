"""
Alerts router -- list, detail, and today's stats for gold-monitor alerts.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import Select, cast, desc, func, or_, select, String
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import Alert

router = APIRouter(tags=["alerts"])

# -- Severity weight mapping for risk-score calculation --------------------
_SEVERITY_WEIGHT: dict[str, int] = {
    "high": 15,
    "medium": 7,
    "low": 2,
}


def _alert_to_dict(alert: Alert) -> dict[str, Any]:
    """Convert a SQLAlchemy Alert object to a plain dict."""
    return {
        "id": str(alert.id),
        "title": alert.title,
        "timestamp_utc": alert.timestamp_utc.isoformat() if alert.timestamp_utc else None,
        "source_name": alert.source_name,
        "source_url": alert.source_url,
        "matched_rule_ids": alert.matched_rule_ids or [],
        "summary_fa": alert.summary_fa or "",
        "why_important_fa": alert.why_important_fa or "",
        "expected_impact": alert.expected_impact or {},
        "severity": alert.severity,
        "time_horizon": alert.time_horizon,
        "confidence": alert.confidence,
        "follow_up_questions": alert.follow_up_questions or [],
        "dedupe_key": alert.dedupe_key,
        "raw_item_id": str(alert.raw_item_id) if alert.raw_item_id else None,
        "match_evidence": alert.match_evidence or {},
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
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


@router.get("", response_model=None)
async def list_alerts(
    db: AsyncSession = Depends(get_db),
    asset: str | None = Query(None),
    severity: str | None = Query(None),
    time_horizon: str | None = Query(None),
    q: str | None = Query(None),
    from_date: datetime.datetime | None = Query(None),
    to_date: datetime.datetime | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    base = select(Alert)
    base = _apply_alert_filters(
        base, asset=asset, severity=severity, time_horizon=time_horizon,
        q=q, from_date=from_date, to_date=to_date,
    )

    count_stmt = select(func.count()).select_from(base.subquery())
    total: int = (await db.execute(count_stmt)).scalar_one()

    items_stmt = base.order_by(desc(Alert.created_at)).limit(limit).offset(offset)
    result = await db.execute(items_stmt)
    alerts = result.scalars().all()

    return {
        "items": [_alert_to_dict(a) for a in alerts],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# -- GET /alerts/stats/today  (registered BEFORE the {alert_id} catch-all) -


@router.get("/stats/today", response_model=None)
async def alerts_stats_today(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)

    count_stmt = (
        select(Alert.severity, func.count().label("cnt"))
        .where(Alert.created_at >= cutoff)
        .group_by(Alert.severity)
    )
    rows = (await db.execute(count_stmt)).all()

    counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for sev, cnt in rows:
        counts[str(sev)] = cnt

    risk_score = sum(
        counts.get(sev, 0) * weight for sev, weight in _SEVERITY_WEIGHT.items()
    )
    risk_score = min(risk_score, 100)

    top_stmt = (
        select(Alert)
        .where(Alert.created_at >= cutoff)
        .order_by(desc(Alert.created_at))
        .limit(3)
    )
    top_alerts = (await db.execute(top_stmt)).scalars().all()

    return {
        "top_alerts": [_alert_to_dict(a) for a in top_alerts],
        "risk_score": risk_score,
        "counts": counts,
    }


# -- GET /alerts/{alert_id} -----------------------------------------------


@router.get("/{alert_id}", response_model=None)
async def get_alert(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )
    return _alert_to_dict(alert)
