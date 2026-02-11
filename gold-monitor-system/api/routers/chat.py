"""
Chat router — POST /api/chat endpoint with SSE streaming.

Handles the AI chat widget communication:
1. Validates request (rate limit, session)
2. Loads conversation history
3. Sends to OpenRouter with tool definitions
4. Executes any tool calls
5. Streams the final response via SSE
6. Saves the conversation turn
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.database import AsyncSessionLocal, get_db
from api.services.chat.openrouter import ChatOpenRouterClient, build_system_prompt
from api.services.chat.rate_limiter import rate_limiter
from api.services.chat.session_manager import (
    get_conversation_history,
    get_or_create_session,
    is_session_message_limit_reached,
    save_message,
    set_first_message,
)
from api.services.chat.intent_classifier import (
    extract_and_strip_meta,
    save_analytics,
    update_session_analytics,
)
from api.services.chat.tool_executor import execute_tool
from api.services.chat.tools import TOOL_DEFINITIONS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


# ── Request/Response models ────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=500)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=1)
    session_id: str | None = None


class ChatStatusResponse(BaseModel):
    enabled: bool
    welcome_message: str


# ── Helpers ────────────────────────────────────────────────────────────

def _sanitize_input(text: str) -> str:
    """Strip HTML tags and limit length."""
    cleaned = re.sub(r"<[^>]+>", "", text)
    return cleaned.strip()[:500]


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _error_json(message: str, error: str = "error", status: int = 200) -> JSONResponse:
    """Return a consistent JSON error response."""
    return JSONResponse(
        content={"error": error, "message": message},
        status_code=status,
    )


async def _fetch_prices_for_tool() -> dict[str, Any] | None:
    """Fetch current prices using the prices router logic."""
    try:
        from api.routers.prices import get_prices
        return await get_prices()
    except Exception as e:
        logger.warning("Failed to fetch prices for chat tool: %s", e)
        return None


# ── SSE streaming helper ──────────────────────────────────────────────

async def _generate_sse(
    user_content: str,
    session_id: uuid.UUID,
    ip_address: str,
):
    """Generator that handles the full chat flow and yields SSE events."""
    client = ChatOpenRouterClient()
    total_tokens = 0

    logger.info("[chat-sse] Generator started for session=%s", session_id)
    async with AsyncSessionLocal() as db:
        try:
            # 1. Get conversation history
            history = await get_conversation_history(db, session_id)
            logger.info("[chat-sse] History loaded: %d messages", len(history))

            # 2. Build system prompt
            custom_prompt = None
            try:
                from api.models import ChatSetting
                from sqlalchemy import select
                result = await db.execute(
                    select(ChatSetting).where(ChatSetting.key == "system_prompt")
                )
                setting = result.scalar_one_or_none()
                if setting and setting.value:
                    custom_prompt = setting.value
            except Exception:
                pass

            system_prompt = build_system_prompt(custom_prompt)

            # 3. Build messages array
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
            ]
            messages.extend(history)
            messages.append({"role": "user", "content": user_content})

            # 4. Save user message
            await save_message(db, session_id, "user", user_content)
            await set_first_message(db, session_id, user_content)
            await db.commit()
            logger.info("[chat-sse] User message saved, calling OpenRouter (model=%s)", settings.CHAT_MODEL)

            # 5. First LLM call (may return tool_calls)
            yield f"data: {json.dumps({'type': 'status', 'content': 'thinking'}, ensure_ascii=False)}\n\n"
            response_data = await client.chat_completion(
                messages=messages,
                tools=TOOL_DEFINITIONS,
            )
            total_tokens += client.extract_usage(response_data)
            logger.info("[chat-sse] OpenRouter responded, tokens=%d", total_tokens)

            # 6. Check for tool calls
            tool_calls = client.extract_tool_calls(response_data)
            logger.info("[chat-sse] Tool calls: %s", [tc["function"]["name"] for tc in tool_calls] if tool_calls else "none")

            META_TAG = "<chat_meta>"
            BUFFER_LEN = len(META_TAG)
            cleaned_response = ""
            chat_meta: dict[str, Any] | None = None
            assistant_msg_id: uuid.UUID | None = None

            if tool_calls:
                # Execute tool calls
                tool_results_for_save = []

                # Add assistant's tool_calls message
                assistant_tc_msg = response_data["choices"][0]["message"]
                messages.append(assistant_tc_msg)

                yield f"data: {json.dumps({'type': 'status', 'content': 'searching'}, ensure_ascii=False)}\n\n"

                for tc in tool_calls:
                    tool_name = tc["function"]["name"]
                    try:
                        tool_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        tool_args = {}

                    logger.info("Executing tool: %s with args: %s", tool_name, tool_args)

                    prices_fetcher = _fetch_prices_for_tool if tool_name == "get_price_data" else None

                    tool_result = await execute_tool(
                        tool_name, tool_args, db, prices_fetcher=prices_fetcher
                    )

                    tool_results_for_save.append({
                        "name": tool_name,
                        "arguments": tool_args,
                        "result_preview": tool_result[:200],
                    })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_result,
                    })

                # 7. Second LLM call — stream with meta buffering
                logger.info("[chat-sse] Tools done, starting streaming response")
                yield f"data: {json.dumps({'type': 'status', 'content': 'generating'}, ensure_ascii=False)}\n\n"
                full_response = ""
                yielded_up_to = 0
                meta_found = False

                async for chunk in client.chat_completion_stream(messages=messages):
                    full_response += chunk
                    meta_pos = full_response.find(META_TAG)
                    if meta_pos >= 0:
                        # Yield remaining clean content before the meta tag
                        if meta_pos > yielded_up_to:
                            safe = full_response[yielded_up_to:meta_pos]
                            yield f"data: {json.dumps({'type': 'content', 'content': safe}, ensure_ascii=False)}\n\n"
                            yielded_up_to = meta_pos
                        meta_found = True
                    elif not meta_found:
                        # Hold back BUFFER_LEN chars to catch partial tag starts
                        safe_end = max(yielded_up_to, len(full_response) - BUFFER_LEN)
                        if safe_end > yielded_up_to:
                            safe = full_response[yielded_up_to:safe_end]
                            yield f"data: {json.dumps({'type': 'content', 'content': safe}, ensure_ascii=False)}\n\n"
                            yielded_up_to = safe_end

                # Stream done — parse meta and yield remaining clean content
                cleaned_response, chat_meta = extract_and_strip_meta(full_response)
                remaining = cleaned_response[yielded_up_to:]
                if remaining:
                    yield f"data: {json.dumps({'type': 'content', 'content': remaining}, ensure_ascii=False)}\n\n"
                logger.info("[chat-sse] Streaming complete, response length=%d, meta=%s", len(cleaned_response), bool(chat_meta))

                # Save cleaned assistant response
                saved_msg = await save_message(
                    db, session_id, "assistant", cleaned_response,
                    tool_calls=tool_results_for_save,
                    tokens_used=total_tokens,
                )
                assistant_msg_id = saved_msg.id
                await db.commit()

            else:
                # No tool calls — strip meta before streaming
                raw_content = client.extract_content(response_data)
                if raw_content:
                    cleaned_response, chat_meta = extract_and_strip_meta(raw_content)
                    chunk_size = 10
                    for i in range(0, len(cleaned_response), chunk_size):
                        chunk = cleaned_response[i:i + chunk_size]
                        yield f"data: {json.dumps({'type': 'content', 'content': chunk}, ensure_ascii=False)}\n\n"

                    saved_msg = await save_message(
                        db, session_id, "assistant", cleaned_response,
                        tokens_used=total_tokens,
                    )
                    assistant_msg_id = saved_msg.id
                    await db.commit()
                else:
                    error_msg = "متأسفانه نتوانستم پاسخ مناسبی تولید کنم. لطفاً دوباره تلاش کنید."
                    yield f"data: {json.dumps({'type': 'content', 'content': error_msg}, ensure_ascii=False)}\n\n"

            # 8. Analytics: save chat_meta and send suggestion chips
            if chat_meta:
                try:
                    await save_analytics(db, session_id, assistant_msg_id, chat_meta)
                    await update_session_analytics(db, session_id)
                    await db.commit()

                    # Send suggestion chips to frontend
                    followups = chat_meta.get("suggested_followups", [])
                    if followups and isinstance(followups, list):
                        yield f"data: {json.dumps({'type': 'suggestions', 'content': followups[:3]}, ensure_ascii=False)}\n\n"
                except Exception as analytics_err:
                    logger.warning("[chat-sse] Analytics save failed (non-fatal): %s", analytics_err)

            # Send done event
            yield f"data: {json.dumps({'type': 'done', 'session_id': str(session_id)}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.exception("[chat-sse] Error: %s", e)
            error_msg = "متأسفانه خطایی رخ داد. لطفاً دوباره تلاش کنید."
            yield f"data: {json.dumps({'type': 'error', 'content': error_msg}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'session_id': str(session_id)}, ensure_ascii=False)}\n\n"


# ── Endpoints ──────────────────────────────────────────────────────────

@router.post("")
async def chat(
    chat_request: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Main chat endpoint — returns SSE stream."""

    # Check if chat is enabled
    if not settings.CHAT_ENABLED:
        return _error_json("سرویس چت غیرفعال است.", "disabled")

    # Check API key
    if not settings.OPENROUTER_API_KEY:
        return _error_json("سرویس چت پیکربندی نشده است.", "not_configured")

    ip_address = _get_client_ip(request)

    # Rate limiting
    allowed, error_msg = await rate_limiter.check_rate_limit(ip_address)
    if not allowed:
        return _error_json(error_msg or "محدودیت ارسال", "rate_limited", 429)

    # Get or create session — wrapped in try/except for DB errors
    try:
        session, is_new = await get_or_create_session(
            db, chat_request.session_id, ip_address
        )
    except Exception as e:
        logger.exception("Failed to create chat session: %s", e)
        return _error_json("خطا در ایجاد نشست. لطفاً دوباره تلاش کنید.", "session_error", 500)

    # Check session message limit
    if is_session_message_limit_reached(session):
        return _error_json(
            "تعداد پیام‌های این مکالمه به حد مجاز رسیده. لطفاً مکالمه جدیدی شروع کنید.",
            "session_limit",
        )

    # Sanitize input
    user_message = chat_request.messages[0]
    sanitized_content = _sanitize_input(user_message.content)

    if not sanitized_content:
        return _error_json("پیام خالی است.", "empty_message")

    # Increment rate limit
    await rate_limiter.increment(ip_address)

    # Commit the session creation
    try:
        await db.commit()
    except Exception as e:
        logger.exception("Failed to commit session: %s", e)
        return _error_json("خطای دیتابیس. لطفاً دوباره تلاش کنید.", "db_error", 500)

    # Return SSE stream
    return StreamingResponse(
        _generate_sse(sanitized_content, session.id, ip_address),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Chat-Session-Id": str(session.id),
        },
    )


@router.get("/history")
async def chat_history(session_id: str | None = None):
    """Return messages for an existing chat session (no auth — session_id is the secret)."""
    if not session_id:
        return JSONResponse(content={"messages": []})

    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        return JSONResponse(content={"messages": []})

    async with AsyncSessionLocal() as db:
        from api.models import ChatMessage as ChatMessageModel
        from sqlalchemy import select

        result = await db.execute(
            select(ChatMessageModel)
            .where(ChatMessageModel.session_id == sid)
            .order_by(ChatMessageModel.created_at.asc())
            .limit(50)
        )
        msgs = result.scalars().all()

    return JSONResponse(content={
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
            }
            for m in msgs
            if m.role in ("user", "assistant")
        ]
    })


@router.get("/status")
async def chat_status():
    """Check if chat is enabled and return welcome message."""
    enabled = settings.CHAT_ENABLED and bool(settings.OPENROUTER_API_KEY)

    welcome = "سلام! من دستیار هوشمند طلاملا هستم. هر سوالی درباره اخبار، قیمت‌ها، تقویم اقتصادی و تحلیل بازار طلا دارید، بپرسید!"

    # Try to load custom welcome from DB
    try:
        async with AsyncSessionLocal() as db:
            from api.models import ChatSetting
            from sqlalchemy import select
            result = await db.execute(
                select(ChatSetting).where(ChatSetting.key == "welcome_message")
            )
            setting = result.scalar_one_or_none()
            if setting and setting.value:
                welcome = setting.value
    except Exception:
        pass

    return ChatStatusResponse(enabled=enabled, welcome_message=welcome)
