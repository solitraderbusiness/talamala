"""
OpenRouter chat client for the AI chat widget.

Handles streaming chat completions with tool use support.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

import httpx

from api.config import settings

logger = logging.getLogger(__name__)

# ── Load system prompt template ────────────────────────────────────────

_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "chat-system.txt"


def _load_system_prompt() -> str:
    """Load the system prompt template from file."""
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("System prompt file not found at %s", _PROMPT_PATH)
        return (
            "You are the AI assistant for Talamala (طلاملا), a gold market analysis platform. "
            "Always respond in Persian. Use the available tools to query our database."
        )


def build_system_prompt(custom_prompt: str | None = None) -> str:
    """Build the system prompt with today's date filled in."""
    template = custom_prompt or _load_system_prompt()

    now_utc = datetime.now(timezone.utc)
    # Tehran is UTC+3:30
    from datetime import timedelta
    tehran_offset = timedelta(hours=3, minutes=30)
    now_tehran = now_utc + tehran_offset

    # Format dates
    today_gregorian = now_tehran.strftime("%Y-%m-%d")
    current_time = now_tehran.strftime("%H:%M")

    # Simple Shamsi date approximation (for display purposes)
    # A proper library would be ideal, but we keep deps minimal
    today_shamsi = _gregorian_to_shamsi_approx(now_tehran)

    return template.format(
        today_date_shamsi=today_shamsi,
        today_date_gregorian=today_gregorian,
        current_time_tehran=current_time,
    )


def _gregorian_to_shamsi_approx(dt: datetime) -> str:
    """Approximate Gregorian to Shamsi date conversion."""
    gy = dt.year
    gm = dt.month
    gd = dt.day

    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)

    months = [
        "", "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
        "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
    ]
    month_name = months[jm] if 1 <= jm <= 12 else str(jm)
    return f"{jd} {month_name} {jy}"


class ChatOpenRouterClient:
    """OpenRouter client for streaming chat completions with tool use."""

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self) -> None:
        self.api_key: str = settings.OPENROUTER_API_KEY

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://talamala.com",
            "X-Title": "Talamala AI Chat",
        }

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str | None = None,
    ) -> dict[str, Any]:
        """Non-streaming chat completion (used for tool call round)."""
        payload = {
            "model": model or settings.CHAT_MODEL,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.post(
                self.BASE_URL,
                headers=self._headers(),
                json=payload,
            )

        if response.status_code != 200:
            logger.error(
                "OpenRouter chat API returned HTTP %d: %s",
                response.status_code,
                response.text[:500],
            )
            raise RuntimeError(f"OpenRouter API error: HTTP {response.status_code}")

        data = response.json()
        return data

    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming chat completion (for final response to user)."""
        payload = {
            "model": model or settings.CHAT_MODEL,
            "messages": messages,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            async with client.stream(
                "POST",
                self.BASE_URL,
                headers=self._headers(),
                json=payload,
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    logger.error(
                        "OpenRouter streaming API returned HTTP %d: %s",
                        response.status_code,
                        error_body.decode()[:500],
                    )
                    raise RuntimeError(f"OpenRouter API error: HTTP {response.status_code}")

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue

    def extract_tool_calls(self, response_data: dict[str, Any]) -> list[dict[str, Any]] | None:
        """Extract tool calls from a non-streaming response."""
        try:
            message = response_data["choices"][0]["message"]
            tool_calls = message.get("tool_calls")
            if tool_calls:
                return tool_calls
        except (KeyError, IndexError):
            pass
        return None

    def extract_content(self, response_data: dict[str, Any]) -> str | None:
        """Extract text content from a non-streaming response."""
        try:
            return response_data["choices"][0]["message"].get("content")
        except (KeyError, IndexError):
            return None

    def extract_usage(self, response_data: dict[str, Any]) -> int:
        """Extract total tokens used from response."""
        try:
            usage = response_data.get("usage", {})
            return usage.get("total_tokens", 0)
        except (KeyError, TypeError):
            return 0
