"""
Chat analytics router — admin endpoints for monitoring the chat feature.

All endpoints require authentication (admin JWT).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_admin
from api.database import get_db
from api.models import ChatMessage, ChatSession, ChatSetting

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


class ChatSessionSummary(BaseModel):
    id: str
    messages_count: int
    first_message: str | None
    ip_address: str
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


# ── Helper ─────────────────────────────────────────────────────────────

def _period_start(period: str) -> datetime:
    now = datetime.now(timezone.utc)
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "this_week":
        start = now - timedelta(days=now.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "this_month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


# ── Endpoints ──────────────────────────────────────────────────────────

@router.get("/chat/dashboard")
async def chat_dashboard(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> ChatDashboard:
    """Dashboard overview cards for chat analytics."""
    today_start = _period_start("today")
    week_start = _period_start("this_week")
    month_start = _period_start("this_month")

    # Messages today
    result = await db.execute(
        select(func.count(ChatMessage.id)).where(
            ChatMessage.created_at >= today_start
        )
    )
    messages_today = result.scalar() or 0

    # Messages this week
    result = await db.execute(
        select(func.count(ChatMessage.id)).where(
            ChatMessage.created_at >= week_start
        )
    )
    messages_this_week = result.scalar() or 0

    # Messages this month
    result = await db.execute(
        select(func.count(ChatMessage.id)).where(
            ChatMessage.created_at >= month_start
        )
    )
    messages_this_month = result.scalar() or 0

    # Sessions today
    result = await db.execute(
        select(func.count(ChatSession.id)).where(
            ChatSession.created_at >= today_start
        )
    )
    sessions_today = result.scalar() or 0

    # Total sessions
    result = await db.execute(select(func.count(ChatSession.id)))
    total_sessions = result.scalar() or 0

    # Average messages per session
    result = await db.execute(
        select(func.avg(ChatSession.messages_count)).where(
            ChatSession.messages_count > 0
        )
    )
    avg_msgs = result.scalar() or 0.0

    # Total tokens today
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
    import uuid as uuid_mod

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
        "model": "anthropic/claude-sonnet-4-20250514",
        "rate_limit_ip": "30",
        "rate_limit_global": "1000",
        "welcome_message": "سلام! من دستیار هوشمند طلامالا هستم. هر سوالی درباره اخبار، قیمت‌ها، تقویم اقتصادی و تحلیل بازار طلا دارید، بپرسید!",
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
        # Upsert each setting
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
