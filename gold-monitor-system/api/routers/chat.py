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
from fastapi.responses import StreamingResponse
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

    async with AsyncSessionLocal() as db:
        try:
            # 1. Get conversation history
            history = await get_conversation_history(db, session_id)

            # 2. Build system prompt
            # Try to load custom prompt from chat_settings
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

            # 5. First LLM call (may return tool_calls)
            response_data = await client.chat_completion(
                messages=messages,
                tools=TOOL_DEFINITIONS,
            )
            total_tokens += client.extract_usage(response_data)

            # 6. Check for tool calls
            tool_calls = client.extract_tool_calls(response_data)

            if tool_calls:
                # Execute tool calls
                tool_results_for_save = []

                # Add assistant's tool_calls message
                assistant_tc_msg = response_data["choices"][0]["message"]
                messages.append(assistant_tc_msg)

                for tc in tool_calls:
                    tool_name = tc["function"]["name"]
                    try:
                        tool_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        tool_args = {}

                    logger.info("Executing tool: %s with args: %s", tool_name, tool_args)

                    # Create a prices fetcher for price tool
                    prices_fetcher = _fetch_prices_for_tool if tool_name == "get_price_data" else None

                    tool_result = await execute_tool(
                        tool_name, tool_args, db, prices_fetcher=prices_fetcher
                    )

                    tool_results_for_save.append({
                        "name": tool_name,
                        "arguments": tool_args,
                        "result_preview": tool_result[:200],
                    })

                    # Add tool result message
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_result,
                    })

                # 7. Second LLM call — stream the final response
                full_response = ""
                async for chunk in client.chat_completion_stream(messages=messages):
                    full_response += chunk
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk}, ensure_ascii=False)}\n\n"

                # Save assistant response with tool call info
                await save_message(
                    db, session_id, "assistant", full_response,
                    tool_calls=tool_results_for_save,
                    tokens_used=total_tokens,
                )
                await db.commit()

            else:
                # No tool calls — check if there's direct content
                content = client.extract_content(response_data)
                if content:
                    # Stream the content character by character for typing effect
                    # (In practice, we got it all at once from non-streaming call)
                    # Split into reasonable chunks
                    chunk_size = 10
                    for i in range(0, len(content), chunk_size):
                        chunk = content[i:i + chunk_size]
                        yield f"data: {json.dumps({'type': 'content', 'content': chunk}, ensure_ascii=False)}\n\n"

                    await save_message(
                        db, session_id, "assistant", content,
                        tokens_used=total_tokens,
                    )
                    await db.commit()
                else:
                    error_msg = "متأسفانه نتوانستم پاسخ مناسبی تولید کنم. لطفاً دوباره تلاش کنید."
                    yield f"data: {json.dumps({'type': 'content', 'content': error_msg}, ensure_ascii=False)}\n\n"

            # Send done event
            yield f"data: {json.dumps({'type': 'done', 'session_id': str(session_id)}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.exception("Chat SSE error")
            error_msg = "متأسفانه خطایی رخ داد. لطفاً دوباره تلاش کنید."
            yield f"data: {json.dumps({'type': 'error', 'content': error_msg}, ensure_ascii=False)}\n\n"


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
        return {"error": "disabled", "message": "سرویس چت غیرفعال است."}

    # Check API key
    if not settings.OPENROUTER_API_KEY:
        return {"error": "not_configured", "message": "سرویس چت پیکربندی نشده است."}

    ip_address = _get_client_ip(request)

    # Rate limiting
    allowed, error_msg = await rate_limiter.check_rate_limit(ip_address)
    if not allowed:
        return {"error": "rate_limited", "message": error_msg}

    # Get or create session
    session, is_new = await get_or_create_session(
        db, chat_request.session_id, ip_address
    )

    # Check session message limit
    if is_session_message_limit_reached(session):
        return {
            "error": "session_limit",
            "message": "تعداد پیام‌های این مکالمه به حد مجاز رسیده. لطفاً مکالمه جدیدی شروع کنید.",
        }

    # Sanitize input
    user_message = chat_request.messages[0]
    sanitized_content = _sanitize_input(user_message.content)

    if not sanitized_content:
        return {"error": "empty_message", "message": "پیام خالی است."}

    # Increment rate limit
    await rate_limiter.increment(ip_address)

    # Commit the session creation
    await db.commit()

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


@router.get("/status")
async def chat_status():
    """Check if chat is enabled and return welcome message."""
    enabled = settings.CHAT_ENABLED and bool(settings.OPENROUTER_API_KEY)

    welcome = "سلام! من دستیار هوشمند طلامالا هستم. هر سوالی درباره اخبار، قیمت‌ها، تقویم اقتصادی و تحلیل بازار طلا دارید، بپرسید!"

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
