"""
Intent classifier for chat analytics.

Parses <chat_meta> JSON blocks from LLM responses, strips them from
the user-visible text, and persists analytics rows.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import ChatAnalytics, ChatSession

logger = logging.getLogger(__name__)

CHAT_META_PATTERN = re.compile(
    r"<chat_meta>\s*([\s\S]*?)\s*</chat_meta>", re.IGNORECASE
)

VALID_INTENTS = {
    "news_search",
    "calendar_query",
    "price_check",
    "sentiment_query",
    "comparison",
    "prediction",
    "how_to_use",
    "off_topic",
    "feature_not_available",
}


def extract_and_strip_meta(text: str) -> tuple[str, dict[str, Any] | None]:
    """Extract <chat_meta> JSON from text, return (cleaned_text, parsed_meta).

    If no meta block found or parsing fails, returns (original_text, None).
    """
    match = CHAT_META_PATTERN.search(text)
    if not match:
        return text, None

    raw_json = match.group(1).strip()
    cleaned = CHAT_META_PATTERN.sub("", text).rstrip()

    try:
        meta = json.loads(raw_json)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse chat_meta JSON: %s", raw_json[:200])
        return cleaned, None

    # Validate intent
    intent = meta.get("intent", "")
    if intent not in VALID_INTENTS:
        meta["intent"] = "off_topic"

    return cleaned, meta


async def save_analytics(
    db: AsyncSession,
    session_id: uuid.UUID,
    message_id: uuid.UUID | None,
    meta: dict[str, Any],
) -> ChatAnalytics:
    """Save parsed chat_meta to the analytics table."""
    row = ChatAnalytics(
        session_id=session_id,
        message_id=message_id,
        intent=meta.get("intent", "off_topic"),
        topics=meta.get("topics", []),
        assets_mentioned=meta.get("assets_mentioned", []),
        had_answer=meta.get("had_answer", True),
        missing_feature=meta.get("missing_feature"),
        suggested_followups=meta.get("suggested_followups", []),
    )
    db.add(row)
    await db.flush()
    return row


async def update_session_analytics(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> None:
    """Recompute primary_intent and had_answer_rate for the session."""
    # Most frequent intent
    result = await db.execute(
        select(ChatAnalytics.intent, func.count(ChatAnalytics.id).label("cnt"))
        .where(ChatAnalytics.session_id == session_id)
        .group_by(ChatAnalytics.intent)
        .order_by(func.count(ChatAnalytics.id).desc())
        .limit(1)
    )
    top_row = result.first()
    primary_intent = top_row.intent if top_row else None

    # had_answer rate
    result = await db.execute(
        select(func.count(ChatAnalytics.id)).where(
            ChatAnalytics.session_id == session_id
        )
    )
    total = result.scalar() or 0

    result = await db.execute(
        select(func.count(ChatAnalytics.id)).where(
            ChatAnalytics.session_id == session_id,
            ChatAnalytics.had_answer.is_(True),
        )
    )
    answered = result.scalar() or 0

    had_answer_rate = (answered / total) if total > 0 else None

    await db.execute(
        update(ChatSession)
        .where(ChatSession.id == session_id)
        .values(
            primary_intent=primary_intent,
            had_answer_rate=had_answer_rate,
        )
    )
