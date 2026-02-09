"""
Alerts router -- list, detail, and today's stats for gold-monitor alerts.
"""

from __future__ import annotations

import datetime
import math
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import Select, cast, desc, func, or_, select, String
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import Alert

router = APIRouter(tags=["alerts"])

# -- Rule-section mapping (derived from rule ID prefix) ----------------------
_RULE_SECTION_MAP: dict[str, str] = {
    "GLOB": "global_gold",
    "IR": "iran_gold",
    "COIN": "coin",
    "FUNDS": "gold_funds",
}

_SECTION_META: dict[str, dict[str, str]] = {
    "global_gold": {"label": "طلای جهانی", "icon": "🌍"},
    "iran_gold": {"label": "طلا و ارز ایران", "icon": "🇮🇷"},
    "coin": {"label": "سکه", "icon": "🪙"},
    "gold_funds": {"label": "صندوق‌های طلا", "icon": "📈"},
    "geopolitics": {"label": "ژئوپلیتیک", "icon": "⚡"},
}

# Geopolitics rule IDs
_GEOPOLITICS_RULES = {
    "GLOB_GEOPOL_RISK", "GLOB_EQUITY_RISK_OFF", "IR_RESERVES_SANCTIONS",
    "IR_FOREIGN_POLICY", "IR_INTERNAL_POL_SOCIAL",
}


def _alert_section(alert: Alert) -> str:
    """Determine the display section for an alert based on its matched rules."""
    rule_ids = alert.matched_rule_ids or []
    if not rule_ids:
        return "global_gold"

    # Check geopolitics first (takes priority)
    for rid in rule_ids:
        if rid in _GEOPOLITICS_RULES:
            return "geopolitics"

    # Derive from first rule ID prefix
    first_rule = rule_ids[0] if rule_ids else ""
    prefix = first_rule.split("_")[0] if "_" in first_rule else ""
    return _RULE_SECTION_MAP.get(prefix, "global_gold")


def _alert_to_dict(alert: Alert) -> dict[str, Any]:
    """Convert a SQLAlchemy Alert object to a plain dict."""
    section = _alert_section(alert)
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
        "section": section,
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


def _compute_activity_score(alerts: list[Alert]) -> int:
    """Compute a decay-weighted market activity score (0-100).

    Measures how much gold-relevant activity is happening — NOT risk direction.
    Sentiment analysis handles bullish/bearish direction separately.

    Each alert contributes based on:
    - severity weight: high=8, medium=2, low=0.5
    - recency decay: exponential decay with 4h half-life
    - confidence: the match confidence (0-1)

    The raw sum is mapped to 0-100 via a logarithmic scale so that:
    - 1-2 high alerts in last hour   ≈ 30-40
    - 5+ high alerts in last 4h      ≈ 60-75
    - Only extreme, sustained volume  → 80+
    - Medium-only noise stays below 50
    """
    if not alerts:
        return 0

    now = datetime.datetime.now(datetime.timezone.utc)
    severity_w = {"high": 8.0, "medium": 2.0, "low": 0.5}
    half_life_hours = 4.0
    decay_constant = math.log(2) / half_life_hours

    raw = 0.0
    for a in alerts:
        ts = a.timestamp_utc or a.created_at or now
        hours_ago = max((now - ts).total_seconds() / 3600.0, 0.0)
        recency = math.exp(-decay_constant * hours_ago)
        sw = severity_w.get(a.severity, 1.0)
        conf = max(a.confidence or 0.3, 0.3)
        raw += sw * recency * conf

    # Logarithmic scaling: score = 20 * ln(1 + raw)
    score = 20.0 * math.log(1.0 + raw)
    return min(100, max(0, round(score)))


@router.get("/stats/today", response_model=None)
async def alerts_stats_today(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)

    # Fetch all alerts from last 24h for risk scoring and categorization
    all_stmt = (
        select(Alert)
        .where(Alert.created_at >= cutoff)
        .order_by(desc(Alert.created_at))
    )
    all_alerts = list((await db.execute(all_stmt)).scalars().all())

    # Severity counts
    counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for a in all_alerts:
        counts[a.severity] = counts.get(a.severity, 0) + 1

    # Activity score (decay-weighted)
    risk_score = _compute_activity_score(all_alerts)

    # Top alerts: prioritize by severity, then recency (most recent first)
    severity_order = {"high": 0, "medium": 1, "low": 2}
    now = datetime.datetime.now(datetime.timezone.utc)
    sorted_by_importance = sorted(
        all_alerts,
        key=lambda a: (
            severity_order.get(a.severity, 9),
            -(a.timestamp_utc or a.created_at or now).timestamp(),
        ),
    )
    top_alerts = sorted_by_importance[:3]

    # Categorized sections
    sections: dict[str, list[dict]] = {}
    for a in all_alerts:
        sec = _alert_section(a)
        if sec not in sections:
            sections[sec] = []
        if len(sections[sec]) < 5:  # max 5 per section
            sections[sec].append(_alert_to_dict(a))

    # Section summaries (ordered by high-severity count, then total)
    section_summaries = []
    for sec_id in sorted(
        sections.keys(),
        key=lambda s: (
            -sum(1 for a in sections[s] if a.get("severity") == "high"),
            -len(sections[s]),
        ),
    ):
        meta = _SECTION_META.get(sec_id, {"label": sec_id, "icon": "📰"})
        sec_alerts = sections[sec_id]
        high_count = sum(1 for a in sec_alerts if a["severity"] == "high")
        med_count = sum(1 for a in sec_alerts if a["severity"] == "medium")
        section_summaries.append({
            "id": sec_id,
            "label": meta["label"],
            "icon": meta["icon"],
            "total": len([a for a in all_alerts if _alert_section(a) == sec_id]),
            "high": high_count,
            "medium": med_count,
            "alerts": sec_alerts,
        })

    return {
        "top_alerts": [_alert_to_dict(a) for a in top_alerts],
        "risk_score": risk_score,
        "counts": counts,
        "sections": section_summaries,
    }


def _alert_section_from_dict(alert) -> str:
    """Get section from an Alert ORM object (used internally)."""
    if isinstance(alert, dict):
        rule_ids = alert.get("matched_rule_ids", [])
    else:
        rule_ids = alert.matched_rule_ids or []
    if not rule_ids:
        return "global_gold"
    for rid in rule_ids:
        if rid in _GEOPOLITICS_RULES:
            return "geopolitics"
    first_rule = rule_ids[0] if rule_ids else ""
    prefix = first_rule.split("_")[0] if "_" in first_rule else ""
    return _RULE_SECTION_MAP.get(prefix, "global_gold")


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
