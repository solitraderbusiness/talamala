"""Workbench router — admin-only analysis chat with extended tools and SQL access.

Endpoints:
- POST /chat          — SSE streaming chat (admin auth)
- GET  /history       — conversation history for a session
- GET  /sessions      — list past sessions
- DELETE /sessions/{id} — delete a session
- GET  /schema        — DB schema metadata for LLM context
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_admin
from api.config import settings
from api.database import AsyncSessionLocal, get_db
from api.models import AdminUser, ChatMessage, ChatSession
from api.services.chat.openrouter import ChatOpenRouterClient
from api.services.workbench.panel_context import build_panel_context
from api.services.workbench.tool_executor import execute_tool
from api.services.workbench.tools import WORKBENCH_TOOL_DEFINITIONS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workbench"])

# ── Constants ────────────────────────────────────────────────────────────
SESSION_TTL_MINUTES = 120
MAX_MESSAGES_PER_SESSION = 200
MAX_HISTORY_MESSAGES = 30
MAX_INPUT_LENGTH = 2000
MAX_RESPONSE_TOKENS = 2000

# ── Schema metadata (static, built once) ─────────────────────────────────
_SCHEMA_TABLES = [
    {"name": "alerts", "description": "News alerts with severity, confidence, matched rules",
     "columns": "id, title, summary_fa, why_important_fa, severity, confidence, timestamp_utc, source_name, matched_rule_ids, direction, alert_score"},
    {"name": "economic_events", "description": "Economic calendar events (NFP, CPI, FOMC, etc.)",
     "columns": "id, event_name, event_name_fa, country, currency, impact, datetime_utc, actual, forecast, previous, category"},
    {"name": "asset_prices_daily", "description": "Daily OHLCV for 7 symbols from Yahoo Finance",
     "columns": "id, symbol, trade_date, open, high, low, close, volume"},
    {"name": "macro_indicators", "description": "FRED economic indicators (5 series)",
     "columns": "id, series_id, observation_date, value"},
    {"name": "etf_holdings", "description": "Gold ETF holdings (GLD, IAU) in tonnes",
     "columns": "id, fund, holding_date, total_tonnes, change_tonnes"},
    {"name": "cot_data", "description": "CFTC Commitment of Traders reports",
     "columns": "id, asset, report_date, non_commercial_long, non_commercial_short, non_commercial_net, open_interest, change_non_commercial_net"},
    {"name": "correlation_cache", "description": "30-day Pearson correlations between gold and other assets",
     "columns": "id, pair_a, pair_b, correlation, window_days, computed_date"},
    {"name": "regime_scores", "description": "Macro liquidity regime scores (4 regimes)",
     "columns": "id, ts, chosen_regime, p_expansion, p_tightening, p_stress, p_recovery, liquidity_stress_index, usd_pressure_index, real_yield_pressure_index"},
    {"name": "market_events_analysis", "description": "Auto-generated market events from data changes",
     "columns": "id, event_type, title, title_fa, description_fa, impact, magnitude, data_json, created_at"},
    {"name": "sentiment_timeline", "description": "5-minute sentiment snapshots with gold price",
     "columns": "id, recorded_at, composite_score, direction, gold_price, gold_change_1h_pct, alerts_active_24h"},
    {"name": "price_history", "description": "5-minute OHLCV candles for XAUUSD",
     "columns": "id, symbol, timeframe, datetime_utc, open, high, low, close, volume"},
    {"name": "gold_articles", "description": "Curated gold analysis articles",
     "columns": "id, title_fa, title_original, source_name, published_at, gold_outlook, importance_score, topics, summary_fa"},
    {"name": "curated_videos", "description": "Curated gold-related YouTube videos",
     "columns": "id, youtube_id, title_fa, channel_name, category, gold_outlook, published_at, summary_fa"},
    {"name": "parsed_signals", "description": "Parsed trading signals from Telegram/TradingView",
     "columns": "id, source_id, direction, entry_price, stop_loss, take_profit_1, timeframe, confidence_raw, status, outcome_pips, parsed_at"},
    {"name": "consensus_snapshots", "description": "Weighted consensus from multiple signal sources",
     "columns": "id, consensus_view, consensus_direction, consensus_strength, signals_count, buy_count, sell_count, generated_at"},
    {"name": "sources", "description": "News data sources (RSS, HTML, etc.)",
     "columns": "id, name, type, base_url, enabled, poll_interval_seconds, categories, rule_bindings, reliability_score"},
]


# ── Request/Response models ───────────────────────────────────────────────

class WorkbenchMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=MAX_INPUT_LENGTH)


class WorkbenchChatRequest(BaseModel):
    messages: list[WorkbenchMessage] = Field(..., min_length=1, max_length=1)
    session_id: str | None = None
    active_panels: list[str] = []


# ── Helpers ───────────────────────────────────────────────────────────────

def _sanitize_input(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", "", text)
    return cleaned.strip()[:MAX_INPUT_LENGTH]


def _build_system_prompt(
    panel_context: str = "",
    schema_context: str = "",
) -> str:
    """Build the workbench system prompt with dynamic context."""
    from pathlib import Path
    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "workbench-system.txt"

    try:
        template = prompt_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        template = (
            "You are a quantitative analyst for Talamala (طلاملا). "
            "Respond in Persian. Use tools and SQL to explore gold market data."
        )

    from api.services.chat.openrouter import (
        _gregorian_to_shamsi_approx,
    )
    now_utc = datetime.now(timezone.utc)
    tehran_offset = timedelta(hours=3, minutes=30)
    now_tehran = now_utc + tehran_offset
    today_gregorian = now_tehran.strftime("%Y-%m-%d")
    current_time = now_tehran.strftime("%H:%M")
    today_shamsi = _gregorian_to_shamsi_approx(now_tehran)

    return template.format(
        today_date_shamsi=today_shamsi,
        today_date_gregorian=today_gregorian,
        current_time_tehran=current_time,
        schema_context=schema_context,
        active_panels_context=panel_context,
    )


def _format_schema_context() -> str:
    """Format schema metadata as text for the system prompt."""
    lines = ["## Database Schema Reference"]
    for t in _SCHEMA_TABLES:
        lines.append(f"**{t['name']}**: {t['description']}")
        lines.append(f"  Columns: {t['columns']}")
    return "\n".join(lines)


async def _get_or_create_session(
    db: AsyncSession,
    session_id: str | None,
) -> tuple[ChatSession, bool]:
    """Get existing workbench session or create new one."""
    if session_id:
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            sid = None
        if sid:
            result = await db.execute(
                select(ChatSession).where(
                    ChatSession.id == sid,
                    ChatSession.session_type == "workbench",
                )
            )
            session = result.scalar_one_or_none()
            if session:
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=SESSION_TTL_MINUTES)
                if session.last_active_at and session.last_active_at < cutoff:
                    pass  # Expired, create new
                else:
                    session.last_active_at = datetime.now(timezone.utc)
                    return session, False

    new_session = ChatSession(
        ip_address="admin",
        session_type="workbench",
        messages_count=0,
    )
    db.add(new_session)
    await db.flush()
    return new_session, True


async def _get_history(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> list[dict[str, str]]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(desc(ChatMessage.created_at))
        .limit(MAX_HISTORY_MESSAGES)
    )
    messages = list(reversed(result.scalars().all()))
    return [{"role": m.role, "content": m.content} for m in messages]


async def _save_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    role: str,
    content: str,
    tool_calls: Any = None,
    tokens_used: int | None = None,
) -> ChatMessage:
    msg = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        tool_calls=tool_calls,
        tokens_used=tokens_used,
    )
    db.add(msg)
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


# ── SSE streaming ─────────────────────────────────────────────────────────

async def _generate_sse(
    user_content: str,
    session_id: uuid.UUID,
    active_panels: list[str],
):
    """Generator for SSE streaming workbench chat.

    Supports multi-round tool calls: the model can request tools up to
    MAX_TOOL_ROUNDS times before a final streaming response is generated.
    """
    MAX_TOOL_ROUNDS = 3
    client = ChatOpenRouterClient()
    total_tokens = 0

    async with AsyncSessionLocal() as db:
        try:
            history = await _get_history(db, session_id)

            # Build panel context
            panel_context = await build_panel_context(active_panels, db)
            schema_context = _format_schema_context()
            system_prompt = _build_system_prompt(panel_context, schema_context)

            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
            ]
            messages.extend(history)
            messages.append({"role": "user", "content": user_content})

            # Save user message
            await _save_message(db, session_id, "user", user_content)
            await db.commit()

            # ── Multi-round tool loop ────────────────────────────────
            all_tool_results_for_save: list[dict] = []
            all_tool_names: list[str] = []
            chart_events: list[dict] = []

            yield f"data: {json.dumps({'type': 'status', 'content': 'thinking'}, ensure_ascii=False)}\n\n"

            for round_num in range(MAX_TOOL_ROUNDS):
                response_data = await client.chat_completion(
                    messages=messages,
                    tools=WORKBENCH_TOOL_DEFINITIONS,
                )
                total_tokens += client.extract_usage(response_data)

                tool_calls = client.extract_tool_calls(response_data)

                if not tool_calls:
                    # No (more) tool calls — model is done thinking.
                    # Extract any direct content from this final non-streaming call.
                    raw_content = client.extract_content(response_data)
                    if raw_content:
                        chunk_size = 20
                        for i in range(0, len(raw_content), chunk_size):
                            chunk = raw_content[i:i + chunk_size]
                            yield f"data: {json.dumps({'type': 'content', 'content': chunk}, ensure_ascii=False)}\n\n"

                        await _save_message(
                            db, session_id, "assistant", raw_content,
                            tool_calls=all_tool_results_for_save or None,
                            tokens_used=total_tokens,
                        )
                        await db.commit()
                    elif not all_tool_results_for_save:
                        # No tools were ever called and no content — fallback
                        yield f"data: {json.dumps({'type': 'content', 'content': 'متأسفانه نتوانستم پاسخی تولید کنم.'}, ensure_ascii=False)}\n\n"
                    else:
                        # Tools were called in previous rounds but this round
                        # returned no content. Fall through to streaming below.
                        break
                    # Emit any chart events before done
                    for chart_spec in chart_events:
                        yield f"data: {json.dumps({'type': 'chart', 'content': chart_spec}, ensure_ascii=False, default=str)}\n\n"
                    # We got a complete non-streaming answer, emit done.
                    yield f"data: {json.dumps({'type': 'done', 'session_id': str(session_id)}, ensure_ascii=False)}\n\n"
                    return

                # ── Execute tool calls for this round ────────────────
                assistant_tc_msg = response_data["choices"][0]["message"]
                messages.append(assistant_tc_msg)

                tool_names = [tc["function"]["name"] for tc in tool_calls]
                all_tool_names.extend(tool_names)
                yield f"data: {json.dumps({'type': 'tools', 'content': all_tool_names}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'status', 'content': 'searching'}, ensure_ascii=False)}\n\n"

                for tc in tool_calls:
                    tool_name = tc["function"]["name"]
                    try:
                        tool_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        tool_args = {}

                    logger.info("Workbench tool (round %d): %s args: %s", round_num + 1, tool_name, tool_args)

                    prices_fetcher = None
                    if tool_name == "get_price_data":
                        from api.routers.prices import get_prices
                        prices_fetcher = get_prices

                    tool_result = await execute_tool(
                        tool_name, tool_args, db,
                        prices_fetcher=prices_fetcher,
                        chart_events=chart_events,
                    )

                    all_tool_results_for_save.append({
                        "name": tool_name,
                        "arguments": tool_args,
                        "result_preview": tool_result[:300],
                    })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_result,
                    })

            # ── Final streaming response after tool rounds ───────────
            # Either we exhausted MAX_TOOL_ROUNDS or the loop broke
            # because the model returned no content. Generate a streaming
            # response so the model can produce a full answer.
            yield f"data: {json.dumps({'type': 'status', 'content': 'generating'}, ensure_ascii=False)}\n\n"
            full_response = ""

            async for chunk in client.chat_completion_stream(
                messages=messages,
                max_tokens=MAX_RESPONSE_TOKENS,
            ):
                full_response += chunk
                yield f"data: {json.dumps({'type': 'content', 'content': chunk}, ensure_ascii=False)}\n\n"

            if not full_response:
                full_response = "متأسفانه نتوانستم پاسخی تولید کنم."
                yield f"data: {json.dumps({'type': 'content', 'content': full_response}, ensure_ascii=False)}\n\n"

            await _save_message(
                db, session_id, "assistant", full_response,
                tool_calls=all_tool_results_for_save or None,
                tokens_used=total_tokens,
            )
            await db.commit()

            # Emit any chart events before done
            for chart_spec in chart_events:
                yield f"data: {json.dumps({'type': 'chart', 'content': chart_spec}, ensure_ascii=False, default=str)}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'session_id': str(session_id)}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.exception("Workbench SSE error: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'content': 'خطایی رخ داد. لطفاً دوباره تلاش کنید.'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'session_id': str(session_id)}, ensure_ascii=False)}\n\n"


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/chat")
async def workbench_chat(
    req: WorkbenchChatRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """SSE streaming chat for the admin workbench."""
    if not settings.OPENROUTER_API_KEY:
        return JSONResponse(
            content={"error": "not_configured", "message": "OpenRouter API key not set"},
            status_code=500,
        )

    session, is_new = await _get_or_create_session(db, req.session_id)

    if (session.messages_count or 0) >= MAX_MESSAGES_PER_SESSION:
        return JSONResponse(
            content={"error": "session_limit", "message": "Session message limit reached"},
            status_code=400,
        )

    user_content = _sanitize_input(req.messages[0].content)
    if not user_content:
        return JSONResponse(
            content={"error": "empty_message", "message": "Empty message"},
            status_code=400,
        )

    # Set first message for session analytics
    if is_new or not session.first_message:
        session.first_message = user_content[:500]

    await db.commit()

    return StreamingResponse(
        _generate_sse(user_content, session.id, req.active_panels),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Chat-Session-Id": str(session.id),
        },
    )


@router.get("/history")
async def workbench_history(
    session_id: str,
    admin: AdminUser = Depends(get_current_admin),
):
    """Return message history for a workbench session."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        return JSONResponse(content={"messages": []})

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == sid)
            .order_by(ChatMessage.created_at.asc())
            .limit(MAX_MESSAGES_PER_SESSION)
        )
        msgs = result.scalars().all()

    return {
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in msgs
            if m.role in ("user", "assistant")
        ]
    }


@router.get("/sessions")
async def workbench_sessions(
    limit: int = Query(20, ge=1, le=50),
    admin: AdminUser = Depends(get_current_admin),
):
    """List past workbench sessions."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ChatSession)
            .where(ChatSession.session_type == "workbench")
            .order_by(desc(ChatSession.last_active_at))
            .limit(limit)
        )
        sessions = result.scalars().all()

    return {
        "sessions": [
            {
                "id": str(s.id),
                "first_message": s.first_message,
                "messages_count": s.messages_count,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "last_active_at": s.last_active_at.isoformat() if s.last_active_at else None,
            }
            for s in sessions
        ]
    }


@router.delete("/sessions/{session_id}")
async def workbench_delete_session(
    session_id: str,
    admin: AdminUser = Depends(get_current_admin),
):
    """Delete a workbench session and its messages."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        return JSONResponse(
            content={"error": "Invalid session ID"},
            status_code=400,
        )

    async with AsyncSessionLocal() as db:
        await db.execute(delete(ChatMessage).where(ChatMessage.session_id == sid))
        await db.execute(delete(ChatSession).where(ChatSession.id == sid))
        await db.commit()

    return {"status": "deleted"}


@router.get("/schema")
async def workbench_schema(
    admin: AdminUser = Depends(get_current_admin),
):
    """Return DB schema metadata for the frontend schema viewer."""
    return {"tables": _SCHEMA_TABLES}
