"""
OpenRouter API client for generating Persian text fields on alerts.

Responsibilities (text generation ONLY):
    - summary_fa        Persian summary of the news (2-3 sentences)
    - why_important_fa  Why this matters for the gold market (2-3 bullet points)
    - follow_up_questions  2-3 follow-up questions in Persian

NOT responsible for:
    - severity          Determined by the rule engine
    - time_horizon      Determined by the rule engine
    - confidence        Determined by the rule engine
    - Any classification or scoring decisions
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Setting

logger = logging.getLogger(__name__)

# ── Defaults ────────────────────────────────────────────────────────────

_DEFAULTS: dict[str, Any] = {
    "enable_llm": False,
    "openrouter_model": "anthropic/claude-sonnet-4",
    "temperature": 0.3,
    "max_tokens": 1000,
}

# ── System prompt (English for model clarity; instructs Persian output) ─

_SYSTEM_PROMPT = """\
You are a Persian-language financial news analyst specializing in precious metals, \
particularly gold. Your ONLY job is to generate text in Persian (Farsi). You must \
follow these rules strictly:

1. ALL output MUST be in Persian (فارسی). Do not write any English.
2. You do NOT assign severity, importance level, time horizon, or any scores. \
   Those are handled by a separate deterministic system. Never mention severity \
   or importance levels in your output.
3. Respond ONLY with a valid JSON object — no markdown fences, no commentary.
4. The JSON object must have exactly four keys:
   - "title_fa": A short, descriptive title in Persian (maximum 80 characters). \
     This should capture the main point of the news in a concise Persian headline.
   - "summary_fa": A concise summary of the news in 2-3 Persian sentences.
   - "why_important_fa": Why this news matters for the gold and precious metals \
     market, written as 2-3 Persian bullet points (use "- " prefix for each point). \
     IMPORTANT: Only list impacts that represent NEW information or CHANGES from \
     the current status quo. Do NOT list existing, ongoing conditions (like \
     "sanctions continue to exist" or "tensions remain" or "economic instability \
     persists") as reasons — the market has already priced those in. If the news \
     contains no genuinely new market-moving information, write: \
     "این خبر حاوی اطلاعات جدید تاثیرگذار بر بازار نیست"
   - "follow_up_questions": A JSON array of 2-3 follow-up questions in Persian \
     that a gold market analyst should investigate next.

Example output format (content is illustrative):
{"title_fa": "افزایش نرخ بهره بانک مرکزی آمریکا", "summary_fa": "بانک مرکزی نرخ بهره را ۰.۲۵ درصد افزایش داد. این تصمیم پس از افزایش تورم در ماه گذشته اتخاذ شد.", "why_important_fa": "- افزایش نرخ بهره معمولاً فشار نزولی بر قیمت طلا وارد می‌کند\\n- سرمایه‌گذاران ممکن است به سمت اوراق قرضه حرکت کنند\\n- تأثیر بر تقاضای طلا به عنوان پناهگاه امن", "follow_up_questions": ["آیا بانک‌های مرکزی دیگر نیز مسیر مشابهی را دنبال خواهند کرد؟", "تأثیر این تصمیم بر تقاضای فیزیکی طلا چگونه خواهد بود؟"]}
"""

# ── User prompt template ────────────────────────────────────────────────

_USER_PROMPT_TEMPLATE = """\
Below is a news item that matched one or more monitoring rules for the gold market. \
Generate the three Persian text fields as instructed.

=== NEWS TITLE ===
{title}

=== NEWS CONTENT ===
{content}

=== MATCHED RULES (for context only — do NOT assign severity) ===
{rules_context}

Respond with ONLY the JSON object. No extra text.
"""


class OpenRouterClient:
    """Client for OpenRouter API. Used only for generating Persian text, never for classification."""

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self) -> None:
        self.api_key: str = os.environ.get("OPENROUTER_API_KEY", "")

    # ── Settings helpers ────────────────────────────────────────────────

    async def get_settings(self, db_session: AsyncSession) -> dict[str, Any]:
        """Read LLM settings from the DB ``settings`` table.

        Returns a dict with keys:
            enable_llm (bool), openrouter_model (str),
            temperature (float), max_tokens (int).

        Missing keys fall back to module-level ``_DEFAULTS``.
        """
        result = await db_session.execute(
            select(Setting).where(Setting.key == "llm")
        )
        row = result.scalar_one_or_none()

        if row is None or not isinstance(row.value, dict):
            return dict(_DEFAULTS)

        merged = dict(_DEFAULTS)
        stored = row.value

        if "enable_llm" in stored and isinstance(stored["enable_llm"], bool):
            merged["enable_llm"] = stored["enable_llm"]
        if "openrouter_model" in stored and isinstance(stored["openrouter_model"], str):
            merged["openrouter_model"] = stored["openrouter_model"]
        if "temperature" in stored:
            try:
                merged["temperature"] = float(stored["temperature"])
            except (TypeError, ValueError):
                pass
        if "max_tokens" in stored:
            try:
                merged["max_tokens"] = int(stored["max_tokens"])
            except (TypeError, ValueError):
                pass

        return merged

    async def is_enabled(self, db_session: AsyncSession) -> bool:
        """Check whether LLM text generation is enabled in settings."""
        settings = await self.get_settings(db_session)
        return bool(settings.get("enable_llm", False))

    # ── Public entry point ──────────────────────────────────────────────

    async def generate_alert_text(
        self,
        raw_title: str,
        raw_content: str,
        matched_rules: list[dict[str, Any]],
        db_session: AsyncSession,
    ) -> dict[str, Any] | None:
        """Generate Persian text fields for an alert.

        **IMPORTANT**: This does NOT determine severity or horizon.
        Those are set by the deterministic rule engine.

        Args:
            raw_title: Original title of the news item.
            raw_content: Original content text.
            matched_rules: List of matched-rule dicts, each expected to
                contain keys like ``id``, ``title``, ``why_important``,
                and ``section``.
            db_session: Async DB session for reading settings.

        Returns:
            A dict with keys ``summary_fa``, ``why_important_fa``, and
            ``follow_up_questions``, or ``None`` if the LLM is disabled,
            unconfigured, or the call fails for any reason.
        """
        # --- Pre-flight checks -------------------------------------------
        settings = await self.get_settings(db_session)

        if not settings.get("enable_llm", False):
            logger.debug("LLM is disabled in settings; skipping text generation.")
            return None

        if not self.api_key:
            logger.warning(
                "OPENROUTER_API_KEY is not set; cannot generate LLM text."
            )
            return None

        # --- Build the prompt --------------------------------------------
        rules_context = self._format_rules_context(matched_rules)

        # Truncate content to avoid excessive token usage
        truncated_content = raw_content[:4000] if raw_content else ""

        user_prompt = _USER_PROMPT_TEMPLATE.format(
            title=raw_title or "(no title)",
            content=truncated_content or "(no content)",
            rules_context=rules_context or "(no matched rules provided)",
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        # --- Call the API ------------------------------------------------
        raw_response = await self._call_openrouter(messages, settings)

        if raw_response is None:
            return None

        # --- Parse the response ------------------------------------------
        return self._parse_response(raw_response)

    # ── Internal helpers ────────────────────────────────────────────────

    @staticmethod
    def _format_rules_context(matched_rules: list[dict[str, Any]]) -> str:
        """Build a human-readable summary of matched rules for the prompt."""
        if not matched_rules:
            return ""

        lines: list[str] = []
        for i, rule in enumerate(matched_rules, 1):
            rule_id = rule.get("id", "?")
            title = rule.get("title", "unknown")
            section = rule.get("section", "")
            why = rule.get("why_important", "")
            line = f"{i}. [{rule_id}] {title}"
            if section:
                line += f"  (section: {section})"
            if why:
                line += f"\n   Why important: {why}"
            lines.append(line)

        return "\n".join(lines)

    async def _call_openrouter(
        self,
        messages: list[dict[str, str]],
        settings: dict[str, Any],
    ) -> str | None:
        """Make the actual HTTP call to the OpenRouter API.

        Returns the assistant message content string, or ``None`` on any
        failure (network errors, HTTP errors, malformed responses).
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://gold-monitor.local",
            "X-Title": "Gold Monitor System",
        }

        payload = {
            "model": settings.get("openrouter_model", _DEFAULTS["openrouter_model"]),
            "messages": messages,
            "temperature": settings.get("temperature", _DEFAULTS["temperature"]),
            "max_tokens": settings.get("max_tokens", _DEFAULTS["max_tokens"]),
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                response = await client.post(
                    self.BASE_URL,
                    headers=headers,
                    json=payload,
                )

            if response.status_code != 200:
                logger.error(
                    "OpenRouter API returned HTTP %d: %s",
                    response.status_code,
                    response.text[:500],
                )
                return None

            data = response.json()

        except httpx.TimeoutException:
            logger.error("OpenRouter API call timed out after 30 seconds.")
            return None
        except httpx.RequestError as exc:
            logger.error("OpenRouter API request failed: %s", exc)
            return None
        except json.JSONDecodeError:
            logger.error(
                "OpenRouter API returned invalid JSON: %s",
                response.text[:500],  # type: ignore[possibly-undefined]
            )
            return None
        except Exception:
            logger.exception("Unexpected error calling OpenRouter API.")
            return None

        # Extract the assistant message content
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            logger.error(
                "OpenRouter response has unexpected structure: %s",
                json.dumps(data)[:500],
            )
            return None

        if not isinstance(content, str) or not content.strip():
            logger.error("OpenRouter returned empty content.")
            return None

        return content.strip()

    @staticmethod
    def _parse_response(raw: str) -> dict[str, Any] | None:
        """Parse the raw LLM response into the expected dict.

        Handles common quirks such as markdown fences wrapping the JSON.

        Returns ``None`` if parsing fails or required keys are missing.
        """
        text = raw.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            # Remove opening fence (with optional language tag)
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1:]
            # Remove closing fence
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            logger.error(
                "Failed to parse LLM response as JSON: %.300s", text,
            )
            return None

        if not isinstance(parsed, dict):
            logger.error("LLM response is not a JSON object: %s", type(parsed))
            return None

        # Validate required keys
        title_fa = parsed.get("title_fa")
        summary_fa = parsed.get("summary_fa")
        why_important_fa = parsed.get("why_important_fa")
        follow_up_questions = parsed.get("follow_up_questions")

        if not isinstance(summary_fa, str) or not summary_fa.strip():
            logger.error("LLM response missing or empty 'summary_fa'.")
            return None

        if not isinstance(why_important_fa, str) or not why_important_fa.strip():
            logger.error("LLM response missing or empty 'why_important_fa'.")
            return None

        if not isinstance(follow_up_questions, list):
            logger.warning(
                "LLM response 'follow_up_questions' is not a list; defaulting to empty."
            )
            follow_up_questions = []

        # Ensure all follow-up questions are non-empty strings
        clean_questions = [
            q for q in follow_up_questions
            if isinstance(q, str) and q.strip()
        ]

        result: dict[str, Any] = {
            "summary_fa": summary_fa.strip(),
            "why_important_fa": why_important_fa.strip(),
            "follow_up_questions": clean_questions,
        }

        # title_fa is optional — include if valid
        if isinstance(title_fa, str) and title_fa.strip():
            result["title_fa"] = title_fa.strip()

        return result
