"""
Session manager for chat widget.

Stores chat sessions in PostgreSQL with in-memory caching via Redis.
Sessions expire after 30 minutes of inactivity.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import ChatMessage, ChatSession

logger = logging.getLogger(__name__)

SESSION_TTL_MINUTES = 30
MAX_MESSAGES_PER_SESSION = 50
MAX_HISTORY_MESSAGES = 10


async def get_or_create_session(
    db: AsyncSession,
    session_id: str | None,
    ip_address: str = "",
) -> tuple[ChatSession, bool]:
    """Get existing session or create a new one.

    Returns (session, is_new) tuple.
    """
    if session_id:
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            sid = None

        if sid:
            result = await db.execute(
                select(ChatSession).where(ChatSession.id == sid)
            )
            session = result.scalar_one_or_none()

            if session:
                # Check if session is expired
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=SESSION_TTL_MINUTES)
                if session.last_active_at and session.last_active_at < cutoff:
                    # Session expired, create new
                    logger.debug("Session %s expired, creating new", session_id)
                else:
                    # Update last_active
                    session.last_active_at = datetime.now(timezone.utc)
                    return session, False

    # Create new session
    new_session = ChatSession(
        ip_address=ip_address[:45],
        messages_count=0,
    )
    db.add(new_session)
    await db.flush()
    return new_session, True


async def get_conversation_history(
    db: AsyncSession,
    session_id: uuid.UUID,
    limit: int = MAX_HISTORY_MESSAGES,
) -> list[dict[str, str]]:
    """Get recent conversation messages for context."""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(desc(ChatMessage.created_at))
        .limit(limit)
    )
    messages = result.scalars().all()

    # Reverse to get chronological order
    messages = list(reversed(messages))

    return [
        {"role": msg.role, "content": msg.content}
        for msg in messages
    ]


async def save_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    role: str,
    content: str,
    tool_calls: Any = None,
    tokens_used: int | None = None,
) -> ChatMessage:
    """Save a message to the conversation history."""
    msg = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        tool_calls=tool_calls,
        tokens_used=tokens_used,
    )
    db.add(msg)

    # Update session counters
    await db.execute(
        update(ChatSession)
        .where(ChatSession.id == session_id)
        .values(
            messages_count=ChatSession.messages_count + 1,
            last_active_at=datetime.now(timezone.utc),
        )
    )

    await db.flush()
    return msg


async def set_first_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    message: str,
) -> None:
    """Set the first message for a session (for analytics)."""
    await db.execute(
        update(ChatSession)
        .where(
            ChatSession.id == session_id,
            ChatSession.first_message.is_(None),
        )
        .values(first_message=message[:500])
    )


def is_session_message_limit_reached(session: ChatSession) -> bool:
    """Check if session has reached the message limit."""
    return (session.messages_count or 0) >= MAX_MESSAGES_PER_SESSION
