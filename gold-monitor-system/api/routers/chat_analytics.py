"""
Chat analytics router — admin endpoints for monitoring the chat feature.

All endpoints require authentication (admin JWT).
Includes: overview, insights (intents, topics, assets, feature-gaps,
usage-hours, session-depth), conversations, settings, and CSV export.
"""

from __future__ import annotations

import csv
import io
import logging
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import case, cast, desc, extract, func, select, update, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_admin
from api.database import get_db
from api.models import ChatAnalytics, ChatMessage, ChatSession, ChatSetting

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat-analytics"])


# ── Response models ────────────────────────────────────────────────────

class ChatDashboard(BaseModel):
    messages_today: int
    messages_this_week: int
    messages_this_month: int
    sessions_today: int
    avg_messages_per_session: float
    total_tokens_today: int
    total_sessions: int


class ChatOverview(BaseModel):
    total_messages: int
    prev_total_messages: int
    unique_sessions: int
    prev_unique_sessions: int
    avg_messages_per_session: float
    api_cost_estimate: float
    unanswered_count: int


class ChatSessionSummary(BaseModel):
    id: str
    messages_count: int
    first_message: str | None
    ip_address: str
    primary_intent: str | None
    had_answer_rate: float | None
    created_at: str
    last_active_at: str


class ChatConversation(BaseModel):
    session: ChatSessionSummary
    messages: list[dict[str, Any]]


class ChatSettingsResponse(BaseModel):
    enabled: str
    model: str
    rate_limit_ip: str
    rate_limit_global: str
    welcome_message: str
    system_prompt: str


class ChatSettingsUpdate(BaseModel):
    enabled: str | None = None
    model: str | None = None
    rate_limit_ip: str | None = None
    rate_limit_global: str | None = None
    welcome_message: str | None = None
    system_prompt: str | None = None


# ── Helpers ────────────────────────────────────────────────────────────

def _period_start(period: str) -> datetime:
    now = datetime.now(timezone.utc)
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = now - timedelta(days=now.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # "all" — return a very old date
    return datetime(2020, 1, 1, tzinfo=timezone.utc)


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _date_range(
    period: str | None,
    from_date: str | None,
    to_date: str | None,
) -> tuple[datetime, datetime]:
    """Return (start, end) datetimes from period or explicit dates."""
    now = datetime.now(timezone.utc)
    if from_date or to_date:
        start = _parse_date(from_date) or datetime(2020, 1, 1, tzinfo=timezone.utc)
        end = _parse_date(to_date) or now
        return start, end
    p = period or "all"
    return _period_start(p), now


# ── Legacy endpoints (kept for existing admin panel) ──────────────────

@router.get("/chat/dashboard")
async def chat_dashboard(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> ChatDashboard:
    """Dashboard overview cards for chat analytics."""
    today_start = _period_start("today")
    week_start = _period_start("week")
    month_start = _period_start("month")

    result = await db.execute(
        select(func.count(ChatMessage.id)).where(ChatMessage.created_at >= today_start)
    )
    messages_today = result.scalar() or 0

    result = await db.execute(
        select(func.count(ChatMessage.id)).where(ChatMessage.created_at >= week_start)
    )
    messages_this_week = result.scalar() or 0

    result = await db.execute(
        select(func.count(ChatMessage.id)).where(ChatMessage.created_at >= month_start)
    )
    messages_this_month = result.scalar() or 0

    result = await db.execute(
        select(func.count(ChatSession.id)).where(ChatSession.created_at >= today_start)
    )
    sessions_today = result.scalar() or 0

    result = await db.execute(select(func.count(ChatSession.id)))
    total_sessions = result.scalar() or 0

    result = await db.execute(
        select(func.avg(ChatSession.messages_count)).where(ChatSession.messages_count > 0)
    )
    avg_msgs = result.scalar() or 0.0

    result = await db.execute(
        select(func.coalesce(func.sum(ChatMessage.tokens_used), 0)).where(
            ChatMessage.created_at >= today_start
        )
    )
    total_tokens_today = result.scalar() or 0

    return ChatDashboard(
        messages_today=messages_today,
        messages_this_week=messages_this_week,
        messages_this_month=messages_this_month,
        sessions_today=sessions_today,
        avg_messages_per_session=round(float(avg_msgs), 1),
        total_tokens_today=total_tokens_today,
        total_sessions=total_sessions,
    )


# ── New Insights endpoints ────────────────────────────────────────────

@router.get("/chat/overview")
async def chat_overview(
    period: str = "today",
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> ChatOverview:
    """Enhanced overview with trend comparison to previous period."""
    now = datetime.now(timezone.utc)
    start = _period_start(period)
    duration = now - start
    prev_start = start - duration
    prev_end = start

    # Current period messages
    result = await db.execute(
        select(func.count(ChatMessage.id)).where(ChatMessage.created_at >= start)
    )
    total_messages = result.scalar() or 0

    # Previous period messages
    result = await db.execute(
        select(func.count(ChatMessage.id)).where(
            ChatMessage.created_at >= prev_start,
            ChatMessage.created_at < prev_end,
        )
    )
    prev_total_messages = result.scalar() or 0

    # Unique sessions current
    result = await db.execute(
        select(func.count(ChatSession.id)).where(
            ChatSession.created_at >= start,
            ChatSession.messages_count > 0,
        )
    )
    unique_sessions = result.scalar() or 0

    # Unique sessions previous
    result = await db.execute(
        select(func.count(ChatSession.id)).where(
            ChatSession.created_at >= prev_start,
            ChatSession.created_at < prev_end,
            ChatSession.messages_count > 0,
        )
    )
    prev_unique_sessions = result.scalar() or 0

    # Average messages per session
    result = await db.execute(
        select(func.avg(ChatSession.messages_count)).where(
            ChatSession.created_at >= start,
            ChatSession.messages_count > 0,
        )
    )
    avg_msgs = result.scalar() or 0.0

    # API cost estimate (tokens * $0.003/1K for input + $0.015/1K for output, approximate)
    result = await db.execute(
        select(func.coalesce(func.sum(ChatMessage.tokens_used), 0)).where(
            ChatMessage.created_at >= start
        )
    )
    total_tokens = result.scalar() or 0
    api_cost = (total_tokens / 1000) * 0.01  # rough average

    # Unanswered count
    result = await db.execute(
        select(func.count(ChatAnalytics.id)).where(
            ChatAnalytics.created_at >= start,
            ChatAnalytics.had_answer.is_(False),
        )
    )
    unanswered_count = result.scalar() or 0

    return ChatOverview(
        total_messages=total_messages,
        prev_total_messages=prev_total_messages,
        unique_sessions=unique_sessions,
        prev_unique_sessions=prev_unique_sessions,
        avg_messages_per_session=round(float(avg_msgs), 1),
        api_cost_estimate=round(api_cost, 2),
        unanswered_count=unanswered_count,
    )


@router.get("/chat/insights/intents")
async def insights_intents(
    period: str | None = None,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> list[dict[str, Any]]:
    """Intent distribution for pie/donut chart."""
    start, end = _date_range(period, from_date, to_date)

    result = await db.execute(
        select(
            ChatAnalytics.intent,
            func.count(ChatAnalytics.id).label("count"),
        )
        .where(ChatAnalytics.created_at.between(start, end))
        .group_by(ChatAnalytics.intent)
        .order_by(desc("count"))
    )

    return [{"intent": row.intent, "count": row.count} for row in result]


@router.get("/chat/insights/topics")
async def insights_topics(
    period: str | None = None,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> list[dict[str, Any]]:
    """Trending topics extracted from analytics."""
    start, end = _date_range(period, from_date, to_date)

    result = await db.execute(
        select(ChatAnalytics.topics)
        .where(
            ChatAnalytics.created_at.between(start, end),
            ChatAnalytics.topics.isnot(None),
        )
    )
    rows = result.scalars().all()

    # Flatten and count topics
    topic_counts: dict[str, int] = {}
    for topics_list in rows:
        if isinstance(topics_list, list):
            for t in topics_list:
                if isinstance(t, str) and t.strip():
                    topic_counts[t.strip()] = topic_counts.get(t.strip(), 0) + 1

    sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
    return [{"topic": t, "count": c} for t, c in sorted_topics[:limit]]


@router.get("/chat/insights/assets")
async def insights_assets(
    period: str | None = None,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> list[dict[str, Any]]:
    """Asset interest from analytics."""
    start, end = _date_range(period, from_date, to_date)

    result = await db.execute(
        select(ChatAnalytics.assets_mentioned)
        .where(
            ChatAnalytics.created_at.between(start, end),
            ChatAnalytics.assets_mentioned.isnot(None),
        )
    )
    rows = result.scalars().all()

    asset_counts: dict[str, int] = {}
    for assets_list in rows:
        if isinstance(assets_list, list):
            for a in assets_list:
                if isinstance(a, str) and a.strip():
                    asset_counts[a.strip()] = asset_counts.get(a.strip(), 0) + 1

    sorted_assets = sorted(asset_counts.items(), key=lambda x: x[1], reverse=True)
    asset_labels = {
        "xauusd": "طلای جهانی (XAU/USD)",
        "coin": "سکه بهار آزادی",
        "domestic_gold": "طلای داخلی",
        "gold_fund": "صندوق طلا",
    }
    return [
        {"asset": a, "label": asset_labels.get(a, a), "count": c}
        for a, c in sorted_assets
    ]


@router.get("/chat/insights/feature-gaps")
async def insights_feature_gaps(
    period: str | None = None,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> list[dict[str, Any]]:
    """Feature gap report — unanswered questions grouped by missing_feature."""
    start, end = _date_range(period, from_date, to_date)

    result = await db.execute(
        select(
            ChatAnalytics.missing_feature,
            func.count(ChatAnalytics.id).label("count"),
        )
        .where(
            ChatAnalytics.created_at.between(start, end),
            ChatAnalytics.had_answer.is_(False),
            ChatAnalytics.missing_feature.isnot(None),
        )
        .group_by(ChatAnalytics.missing_feature)
        .order_by(desc("count"))
        .limit(limit)
    )
    gaps = result.all()

    # For each gap, fetch one example question
    items = []
    for gap in gaps:
        example_result = await db.execute(
            select(ChatMessage.content)
            .join(ChatAnalytics, ChatAnalytics.message_id == ChatMessage.id)
            .where(
                ChatAnalytics.missing_feature == gap.missing_feature,
                ChatAnalytics.created_at.between(start, end),
                ChatMessage.role == "user",
            )
            .limit(1)
        )
        # message_id points to the assistant message, so get the user message before it
        example_q = example_result.scalar_one_or_none()

        # Fallback: get user message from same session
        if not example_q:
            example_result = await db.execute(
                select(ChatMessage.content)
                .join(ChatAnalytics, ChatAnalytics.session_id == ChatMessage.session_id)
                .where(
                    ChatAnalytics.missing_feature == gap.missing_feature,
                    ChatAnalytics.created_at.between(start, end),
                    ChatMessage.role == "user",
                )
                .order_by(desc(ChatMessage.created_at))
                .limit(1)
            )
            example_q = example_result.scalar_one_or_none()

        items.append({
            "feature": gap.missing_feature,
            "count": gap.count,
            "example": (example_q or "")[:200],
        })

    return items


@router.get("/chat/insights/usage-hours")
async def insights_usage_hours(
    period: str | None = None,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> list[dict[str, Any]]:
    """Usage heatmap data: hour × day_of_week grid."""
    start, end = _date_range(period, from_date, to_date)

    # Tehran offset: UTC + 3:30
    tehran_hour = extract("hour", ChatMessage.created_at) + 3
    tehran_dow = extract("dow", ChatMessage.created_at)  # 0=Sunday

    result = await db.execute(
        select(
            cast(tehran_dow, Integer).label("dow"),
            cast(tehran_hour, Integer).label("hour"),
            func.count(ChatMessage.id).label("count"),
        )
        .where(
            ChatMessage.created_at.between(start, end),
            ChatMessage.role == "user",
        )
        .group_by("dow", "hour")
        .order_by("dow", "hour")
    )

    return [
        {"dow": row.dow, "hour": row.hour % 24, "count": row.count}
        for row in result
    ]


@router.get("/chat/insights/session-depth")
async def insights_session_depth(
    period: str | None = None,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> list[dict[str, Any]]:
    """Session depth histogram."""
    start, end = _date_range(period, from_date, to_date)

    bucket = case(
        (ChatSession.messages_count == 1, "1"),
        (ChatSession.messages_count <= 3, "2-3"),
        (ChatSession.messages_count <= 5, "4-5"),
        (ChatSession.messages_count <= 10, "6-10"),
        else_="10+",
    )

    result = await db.execute(
        select(
            bucket.label("bucket"),
            func.count(ChatSession.id).label("count"),
        )
        .where(
            ChatSession.created_at.between(start, end),
            ChatSession.messages_count > 0,
        )
        .group_by(bucket)
    )

    # Ensure order
    order = ["1", "2-3", "4-5", "6-10", "10+"]
    counts_map = {row.bucket: row.count for row in result}
    return [{"bucket": b, "count": counts_map.get(b, 0)} for b in order]


# ── Conversations (enhanced) ─────────────────────────────────────────

@router.get("/chat/conversations")
async def chat_conversations(
    page: int = 1,
    limit: int = 20,
    intent: str | None = None,
    had_answer: bool | None = None,
    period: str | None = None,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> dict[str, Any]:
    """List conversations with filtering."""
    limit = min(limit, 100)
    offset = (page - 1) * limit
    start, end = _date_range(period, from_date, to_date)

    query = (
        select(ChatSession)
        .where(
            ChatSession.created_at.between(start, end),
            ChatSession.messages_count > 0,
        )
    )

    if intent:
        query = query.where(ChatSession.primary_intent == intent)
    if had_answer is not None:
        if had_answer:
            query = query.where(ChatSession.had_answer_rate >= 0.5)
        else:
            query = query.where(
                (ChatSession.had_answer_rate < 0.5) | (ChatSession.had_answer_rate.is_(None))
            )

    # Count total
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar() or 0

    # Fetch page
    result = await db.execute(
        query.order_by(desc(ChatSession.last_active_at))
        .limit(limit)
        .offset(offset)
    )
    sessions = result.scalars().all()

    return {
        "items": [
            {
                "id": str(s.id),
                "messages_count": s.messages_count or 0,
                "first_message": s.first_message,
                "ip_address": s.ip_address or "",
                "primary_intent": s.primary_intent,
                "had_answer_rate": s.had_answer_rate,
                "created_at": s.created_at.isoformat() if s.created_at else "",
                "last_active_at": s.last_active_at.isoformat() if s.last_active_at else "",
            }
            for s in sessions
        ],
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit if limit else 1,
    }


@router.get("/chat/conversations/{session_id}")
async def chat_conversation_detail(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> dict[str, Any]:
    """Full conversation with analytics data."""
    try:
        sid = uuid_mod.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    result = await db.execute(
        select(ChatSession).where(ChatSession.id == sid)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == sid)
        .order_by(ChatMessage.created_at)
    )
    messages = result.scalars().all()

    # Load analytics for this session
    result = await db.execute(
        select(ChatAnalytics)
        .where(ChatAnalytics.session_id == sid)
        .order_by(ChatAnalytics.created_at)
    )
    analytics = result.scalars().all()
    analytics_map = {str(a.message_id): a for a in analytics if a.message_id}

    return {
        "session": {
            "id": str(session.id),
            "messages_count": session.messages_count or 0,
            "first_message": session.first_message,
            "ip_address": session.ip_address or "",
            "primary_intent": session.primary_intent,
            "had_answer_rate": session.had_answer_rate,
            "created_at": session.created_at.isoformat() if session.created_at else "",
            "last_active_at": session.last_active_at.isoformat() if session.last_active_at else "",
        },
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
                "tokens_used": m.tokens_used,
                "created_at": m.created_at.isoformat() if m.created_at else "",
                "analytics": (
                    {
                        "intent": analytics_map[str(m.id)].intent,
                        "topics": analytics_map[str(m.id)].topics,
                        "had_answer": analytics_map[str(m.id)].had_answer,
                        "missing_feature": analytics_map[str(m.id)].missing_feature,
                    }
                    if str(m.id) in analytics_map
                    else None
                ),
            }
            for m in messages
        ],
    }


# ── CSV Export ────────────────────────────────────────────────────────

@router.get("/chat/export")
async def chat_export(
    type: str = "analytics",
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    """Export chat data as CSV. type = messages | analytics | sessions."""
    start, end = _date_range(None, from_date, to_date)
    output = io.StringIO()
    # Add UTF-8 BOM for Excel compatibility
    output.write("\ufeff")
    writer = csv.writer(output)

    if type == "messages":
        writer.writerow(["id", "session_id", "role", "content", "tokens_used", "created_at"])
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.created_at.between(start, end))
            .order_by(ChatMessage.created_at)
        )
        for m in result.scalars():
            writer.writerow([
                str(m.id), str(m.session_id), m.role,
                m.content[:500], m.tokens_used,
                m.created_at.isoformat() if m.created_at else "",
            ])

    elif type == "analytics":
        writer.writerow([
            "id", "session_id", "intent", "topics", "assets_mentioned",
            "had_answer", "missing_feature", "created_at",
        ])
        result = await db.execute(
            select(ChatAnalytics)
            .where(ChatAnalytics.created_at.between(start, end))
            .order_by(ChatAnalytics.created_at)
        )
        for a in result.scalars():
            writer.writerow([
                str(a.id), str(a.session_id), a.intent,
                ",".join(a.topics) if a.topics else "",
                ",".join(a.assets_mentioned) if a.assets_mentioned else "",
                a.had_answer, a.missing_feature or "",
                a.created_at.isoformat() if a.created_at else "",
            ])

    elif type == "sessions":
        writer.writerow([
            "id", "messages_count", "first_message", "primary_intent",
            "had_answer_rate", "ip_address", "created_at", "last_active_at",
        ])
        result = await db.execute(
            select(ChatSession)
            .where(
                ChatSession.created_at.between(start, end),
                ChatSession.messages_count > 0,
            )
            .order_by(desc(ChatSession.created_at))
        )
        for s in result.scalars():
            writer.writerow([
                str(s.id), s.messages_count, (s.first_message or "")[:200],
                s.primary_intent or "", s.had_answer_rate or "",
                s.ip_address or "",
                s.created_at.isoformat() if s.created_at else "",
                s.last_active_at.isoformat() if s.last_active_at else "",
            ])
    else:
        raise HTTPException(status_code=400, detail="type must be messages, analytics, or sessions")

    output.seek(0)
    filename = f"chat_{type}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Legacy endpoints (kept for backward compat) ──────────────────────

@router.get("/chat/sessions")
async def chat_sessions(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> list[ChatSessionSummary]:
    """List recent chat sessions."""
    limit = min(limit, 100)

    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.messages_count > 0)
        .order_by(desc(ChatSession.last_active_at))
        .limit(limit)
        .offset(offset)
    )
    sessions = result.scalars().all()

    return [
        ChatSessionSummary(
            id=str(s.id),
            messages_count=s.messages_count or 0,
            first_message=s.first_message,
            ip_address=s.ip_address or "",
            primary_intent=s.primary_intent,
            had_answer_rate=s.had_answer_rate,
            created_at=s.created_at.isoformat() if s.created_at else "",
            last_active_at=s.last_active_at.isoformat() if s.last_active_at else "",
        )
        for s in sessions
    ]


@router.get("/chat/sessions/{session_id}")
async def chat_session_detail(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> ChatConversation:
    """Get full conversation for a specific session."""
    try:
        sid = uuid_mod.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    result = await db.execute(
        select(ChatSession).where(ChatSession.id == sid)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == sid)
        .order_by(ChatMessage.created_at)
    )
    messages = result.scalars().all()

    return ChatConversation(
        session=ChatSessionSummary(
            id=str(session.id),
            messages_count=session.messages_count or 0,
            first_message=session.first_message,
            ip_address=session.ip_address or "",
            primary_intent=session.primary_intent,
            had_answer_rate=session.had_answer_rate,
            created_at=session.created_at.isoformat() if session.created_at else "",
            last_active_at=session.last_active_at.isoformat() if session.last_active_at else "",
        ),
        messages=[
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
                "tokens_used": m.tokens_used,
                "created_at": m.created_at.isoformat() if m.created_at else "",
            }
            for m in messages
        ],
    )


@router.get("/chat/settings")
async def get_chat_settings(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> ChatSettingsResponse:
    """Get current chat settings."""
    defaults = {
        "enabled": "true",
        "model": "anthropic/claude-sonnet-4",
        "rate_limit_ip": "30",
        "rate_limit_global": "1000",
        "welcome_message": "سلام! من دستیار هوشمند طلاملا هستم. هر سوالی درباره اخبار، قیمت‌ها، تقویم اقتصادی و تحلیل بازار طلا دارید، بپرسید!",
        "system_prompt": "",
    }

    result = await db.execute(select(ChatSetting))
    settings_rows = result.scalars().all()

    for row in settings_rows:
        if row.key in defaults:
            defaults[row.key] = row.value

    return ChatSettingsResponse(**defaults)


@router.put("/chat/settings")
async def update_chat_settings(
    data: ChatSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> dict[str, str]:
    """Update chat settings."""
    updates = data.model_dump(exclude_none=True)
    now = datetime.now(timezone.utc)

    for key, value in updates.items():
        result = await db.execute(
            select(ChatSetting).where(ChatSetting.key == key)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.value = str(value)
            existing.updated_at = now
        else:
            db.add(ChatSetting(key=key, value=str(value), updated_at=now))

    await db.commit()
    return {"status": "ok", "updated": str(len(updates))}


@router.get("/chat/popular-questions")
async def popular_questions(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> list[dict[str, Any]]:
    """Get most common first questions from users."""
    limit = min(limit, 50)

    result = await db.execute(
        select(
            ChatSession.first_message,
            func.count(ChatSession.id).label("count"),
        )
        .where(ChatSession.first_message.isnot(None))
        .group_by(ChatSession.first_message)
        .order_by(desc("count"))
        .limit(limit)
    )

    return [
        {"question": row.first_message, "count": row.count}
        for row in result
    ]
