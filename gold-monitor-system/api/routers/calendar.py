"""
Economic Calendar API router.

Endpoints:
- GET /api/calendar — list economic events with filters
- GET /api/calendar/upcoming — next high-impact events (for dashboard widget)
- POST /api/calendar/sync — trigger manual sync (admin only)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_admin
from api.calendar_config import get_gold_impact_note, EVENT_GOLD_NOTES
from api.database import get_db
from api.models import AdminUser, EconomicEvent

logger = logging.getLogger("gold_monitor.calendar")

router = APIRouter(tags=["calendar"])

# Tehran timezone offset: UTC+3:30
_TEHRAN_OFFSET = timedelta(hours=3, minutes=30)


def _to_tehran(dt: datetime) -> str:
    """Convert a UTC datetime to Tehran timezone ISO string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    tehran_dt = dt + _TEHRAN_OFFSET
    # Format with +03:30 offset
    return tehran_dt.strftime("%Y-%m-%dT%H:%M:%S+03:30")


def _time_until(dt: datetime) -> str:
    """Return a human-readable Persian string for time until an event."""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = dt - now

    if diff.total_seconds() < 0:
        return "گذشته"

    days = diff.days
    hours = diff.seconds // 3600
    minutes = (diff.seconds % 3600) // 60

    parts = []
    if days > 0:
        parts.append(f"{days} روز")
    if hours > 0:
        parts.append(f"{hours} ساعت")
    if minutes > 0 and days == 0:
        parts.append(f"{minutes} دقیقه")

    return " و ".join(parts) if parts else "کمتر از یک دقیقه"


def _is_upcoming(dt: datetime) -> bool:
    """Check if an event is in the future."""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt > now


def _format_event(event: EconomicEvent) -> dict[str, Any]:
    """Format an EconomicEvent ORM object to API response dict."""
    dt = event.datetime_utc
    upcoming = _is_upcoming(dt)

    result: dict[str, Any] = {
        "id": str(event.id),
        "event_name": event.event_name,
        "event_name_fa": event.event_name_fa,
        "country": event.country,
        "currency": event.currency,
        "category": event.category,
        "datetime_utc": dt.isoformat() if dt else None,
        "datetime_tehran": _to_tehran(dt) if dt else None,
        "impact": event.impact,
        "actual": event.actual,
        "forecast": event.forecast,
        "previous": event.previous,
        "source": event.source,
        "affected_assets": event.affected_assets or [],
        "is_upcoming": upcoming,
        "time_until": _time_until(dt) if upcoming else None,
    }

    # Gold impact note: prefer stored value, fall back to dynamic lookup
    if event.gold_impact_note:
        result["gold_impact_note"] = event.gold_impact_note
    else:
        gold_note = get_gold_impact_note(event.event_name)
        if gold_note:
            result["gold_impact_note"] = gold_note
        else:
            for note_name, notes in EVENT_GOLD_NOTES.items():
                if note_name.lower() in event.event_name.lower():
                    first_asset = next(iter(notes), None)
                    if first_asset:
                        result["gold_impact_note"] = notes[first_asset]
                    break

    return result


@router.get("")
async def get_calendar_events(
    db: AsyncSession = Depends(get_db),
    from_date: str | None = Query(None, alias="from", description="Start date YYYY-MM-DD"),
    to_date: str | None = Query(None, alias="to", description="End date YYYY-MM-DD"),
    asset: str = Query("all", description="Filter by asset: xauusd, iran_gold, usd_irr, coin, gold_fund, all"),
    impact: str = Query("all", description="Filter by impact: high, medium, low, all"),
) -> dict[str, Any]:
    """List economic events with filters."""
    now = datetime.now(timezone.utc)

    # Parse dates
    if from_date:
        try:
            start = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if to_date:
        try:
            end = datetime.strptime(to_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
        except ValueError:
            end = start + timedelta(days=7)
    else:
        end = start + timedelta(days=7)

    # Build query
    conditions = [
        EconomicEvent.datetime_utc >= start,
        EconomicEvent.datetime_utc <= end,
    ]

    if impact and impact != "all":
        conditions.append(EconomicEvent.impact == impact)

    query = (
        select(EconomicEvent)
        .where(and_(*conditions))
        .order_by(EconomicEvent.datetime_utc.asc())
    )

    result = await db.execute(query)
    events = result.scalars().all()

    # Filter by asset (done in Python since affected_assets is JSONB array)
    if asset and asset != "all":
        events = [
            e for e in events
            if asset in (e.affected_assets or [])
        ]

    # Format response
    formatted = [_format_event(e) for e in events]

    # Compute counts
    counts = {"total": len(formatted), "high": 0, "medium": 0, "low": 0}
    for e in formatted:
        impact_val = e.get("impact", "low")
        if impact_val in counts:
            counts[impact_val] += 1

    return {
        "events": formatted,
        "counts": counts,
        "from": start.strftime("%Y-%m-%d"),
        "to": end.strftime("%Y-%m-%d"),
    }


@router.get("/upcoming")
async def get_upcoming_events(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(5, ge=1, le=20, description="Number of events to return"),
    impact: str = Query("high", description="Minimum impact level: high, medium, low"),
) -> dict[str, Any]:
    """Get next upcoming high-impact events (for dashboard widget).

    Auto-widens to medium impact if no high-impact events are found,
    so the dashboard widget always shows something when data exists.
    """
    now = datetime.now(timezone.utc)

    # Impact filter
    impact_levels = []
    if impact == "low":
        impact_levels = ["high", "medium", "low"]
    elif impact == "medium":
        impact_levels = ["high", "medium"]
    else:
        impact_levels = ["high"]

    query = (
        select(EconomicEvent)
        .where(
            and_(
                EconomicEvent.datetime_utc > now,
                EconomicEvent.impact.in_(impact_levels),
            )
        )
        .order_by(EconomicEvent.datetime_utc.asc())
        .limit(limit)
    )

    result = await db.execute(query)
    events = result.scalars().all()

    # Auto-widen: if caller asked for "high" but got nothing, retry with medium
    widened = False
    if not events and impact == "high":
        query2 = (
            select(EconomicEvent)
            .where(
                and_(
                    EconomicEvent.datetime_utc > now,
                    EconomicEvent.impact.in_(["high", "medium"]),
                )
            )
            .order_by(EconomicEvent.datetime_utc.asc())
            .limit(limit)
        )
        result2 = await db.execute(query2)
        events = result2.scalars().all()
        if events:
            widened = True

    formatted = [_format_event(e) for e in events]

    # Countdown for nearest event
    countdown = None
    if formatted:
        nearest = formatted[0]
        countdown = {
            "event_name": nearest["event_name"],
            "event_name_fa": nearest["event_name_fa"],
            "time_until": nearest["time_until"],
            "datetime_utc": nearest["datetime_utc"],
            "datetime_tehran": nearest["datetime_tehran"],
            "impact": nearest["impact"],
        }

    resp: dict[str, Any] = {
        "events": formatted,
        "countdown": countdown,
        "last_synced": now.isoformat(),
    }
    if widened:
        resp["widened_to_medium"] = True
    return resp


@router.get("/sync-status")
async def get_sync_status(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get the last sync status for the calendar."""
    # Get the most recently updated event to estimate last sync time
    query = (
        select(EconomicEvent.updated_at)
        .order_by(EconomicEvent.updated_at.desc())
        .limit(1)
    )
    result = await db.execute(query)
    last_updated = result.scalar_one_or_none()

    # Count total events
    count_query = select(func.count(EconomicEvent.id))
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return {
        "last_synced": last_updated.isoformat() if last_updated else None,
        "total_events": total,
    }


@router.post("/sync")
async def trigger_sync(
    _admin: AdminUser = Depends(get_current_admin),
) -> dict[str, Any]:
    """Manually trigger a calendar sync (admin only, requires JWT)."""
    from api.worker.calendar_sync import sync_calendar
    result = await sync_calendar(force=True)
    return {"status": "ok", "result": result}
