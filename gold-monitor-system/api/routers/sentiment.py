"""
Sentiment analysis router — LLM-powered aggregate market sentiment.

Provides multi-timeframe sentiment analysis (1h, 4h, 24h) using the
OpenRouter API.  The analysis weights recent high-severity events more
heavily, so a war 8 hours ago still affects the 1-hour outlook even if
no new war-related news appeared in the last hour.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.database import get_db
from api.models import Alert

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sentiment"])

# ── Timeframes ──────────────────────────────────────────────────────────

_TIMEFRAMES = [
    {"key": "1h", "hours": 1, "label": "۱ ساعت اخیر"},
    {"key": "4h", "hours": 4, "label": "۴ ساعت اخیر"},
    {"key": "24h", "hours": 24, "label": "۲۴ ساعت اخیر"},
]

# ── System prompt ───────────────────────────────────────────────────────

_SENTIMENT_SYSTEM = """\
You are a senior gold market analyst. You analyze batches of news alerts \
and provide aggregate market sentiment analysis in Persian (Farsi).

CRITICAL RULES:
1. ALL output MUST be in Persian.
2. Consider IMPORTANCE WEIGHTING: A high-severity event (war, sanctions, \
   rate decision) from hours ago is MORE important than 10 minor news items \
   from minutes ago. Do NOT just average the recent headlines — weigh by impact.
3. Respond ONLY with a valid JSON object (no markdown fences).
4. The JSON must have these keys:
   - "sentiment": one of "very_bullish", "bullish", "neutral", "bearish", "very_bearish"
   - "sentiment_label": Persian label (e.g. "بسیار صعودی", "صعودی", "خنثی", "نزولی", "بسیار نزولی")
   - "summary": 2-3 sentence Persian summary of the overall market mood
   - "key_drivers": array of 1-3 objects, each with:
     * "title": short Persian title of the driver
     * "impact": "bullish" or "bearish" or "neutral"
     * "weight": "high" or "medium" or "low" (how much this driver matters)
   - "outlook": 1 sentence Persian outlook/prediction
"""

_SENTIMENT_USER = """\
Analyze the following {count} gold market alerts from the past {timeframe}. \
Provide your aggregate sentiment analysis.

IMPORTANT: If there are HIGH severity alerts from earlier (even outside this \
exact window), they may still be listed here with a [STILL RELEVANT] tag. \
These should be weighted heavily in your analysis.

=== ALERTS ===
{alerts_text}

Respond with ONLY the JSON object.
"""


def _format_alerts_for_llm(alerts: list[dict], window_hours: int) -> str:
    """Format alerts into text for the LLM prompt."""
    now = datetime.datetime.now(datetime.timezone.utc)
    lines = []
    for i, a in enumerate(alerts, 1):
        ts = a.get("timestamp_utc", "")
        severity = a.get("severity", "medium")
        title = a.get("title", "")
        summary = a.get("summary_fa", "")
        source = a.get("source_name", "")

        # Calculate hours ago
        try:
            dt = datetime.datetime.fromisoformat(ts)
            hours_ago = (now - dt).total_seconds() / 3600
        except (ValueError, TypeError):
            hours_ago = 0

        still_relevant = ""
        if hours_ago > window_hours and severity == "high":
            still_relevant = " [STILL RELEVANT — high impact event]"

        sev_label = {"high": "🔴 HIGH", "medium": "🟡 MED", "low": "⚪ LOW"}.get(severity, severity)

        line = f"{i}. [{sev_label}] {title}{still_relevant}"
        if summary:
            line += f"\n   {summary[:200]}"
        line += f"\n   Source: {source} | {hours_ago:.1f}h ago"
        lines.append(line)

    return "\n\n".join(lines) if lines else "(No alerts in this period)"


# ── Endpoint ────────────────────────────────────────────────────────────


@router.get("", response_model=None)
async def get_sentiment(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return multi-timeframe sentiment analysis.

    For each timeframe (1h, 4h, 24h):
    - Gathers alerts in that window
    - Includes still-relevant high-severity alerts from up to 24h
    - Sends to LLM for aggregate analysis
    - Returns structured sentiment data

    If LLM is unavailable, returns a rule-based fallback.
    """
    now = datetime.datetime.now(datetime.timezone.utc)

    # Fetch all alerts from last 24h (superset for all timeframes)
    cutoff_24h = now - datetime.timedelta(hours=24)
    result = await db.execute(
        select(Alert)
        .where(Alert.created_at >= cutoff_24h)
        .order_by(desc(Alert.created_at))
    )
    all_alerts_orm = list(result.scalars().all())

    all_alerts = []
    for a in all_alerts_orm:
        all_alerts.append({
            "title": a.title,
            "severity": a.severity,
            "timestamp_utc": a.timestamp_utc.isoformat() if a.timestamp_utc else "",
            "summary_fa": a.summary_fa or "",
            "source_name": a.source_name or "",
            "confidence": a.confidence or 0.5,
            "matched_rule_ids": a.matched_rule_ids or [],
        })

    # High-severity alerts from last 24h (always considered)
    high_severity = [a for a in all_alerts if a["severity"] == "high"]

    results: dict[str, Any] = {
        "timeframes": {},
        "updated_at": now.isoformat(),
        "alert_count_24h": len(all_alerts),
    }

    api_key = settings.OPENROUTER_API_KEY
    use_llm = bool(api_key)

    for tf in _TIMEFRAMES:
        key = tf["key"]
        hours = tf["hours"]
        cutoff = now - datetime.timedelta(hours=hours)

        # Alerts in this window
        window_alerts = [
            a for a in all_alerts
            if _parse_ts(a["timestamp_utc"]) and _parse_ts(a["timestamp_utc"]) >= cutoff
        ]

        # Add high-severity alerts from outside window (still relevant)
        if hours < 24:
            for ha in high_severity:
                ts = _parse_ts(ha["timestamp_utc"])
                if ts and ts < cutoff:
                    window_alerts.append(ha)

        # Remove duplicates by title
        seen_titles: set[str] = set()
        unique_alerts: list[dict] = []
        for a in window_alerts:
            if a["title"] not in seen_titles:
                seen_titles.add(a["title"])
                unique_alerts.append(a)

        if use_llm and unique_alerts:
            sentiment_data = await _call_sentiment_llm(
                unique_alerts, hours, tf["label"], api_key,
            )
        else:
            sentiment_data = _fallback_sentiment(unique_alerts)

        sentiment_data["alert_count"] = len(unique_alerts)
        sentiment_data["label"] = tf["label"]
        results["timeframes"][key] = sentiment_data

    return results


def _parse_ts(ts_str: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None


async def _call_sentiment_llm(
    alerts: list[dict],
    window_hours: int,
    timeframe_label: str,
    api_key: str,
) -> dict[str, Any]:
    """Call OpenRouter for sentiment analysis."""
    alerts_text = _format_alerts_for_llm(alerts, window_hours)

    user_prompt = _SENTIMENT_USER.format(
        count=len(alerts),
        timeframe=timeframe_label,
        alerts_text=alerts_text,
    )

    payload = {
        "model": "anthropic/claude-sonnet-4",
        "messages": [
            {"role": "system", "content": _SENTIMENT_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 800,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://gold-monitor.local",
        "X-Title": "Gold Monitor Sentiment",
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )

        if resp.status_code != 200:
            logger.error("Sentiment LLM returned %d: %s", resp.status_code, resp.text[:300])
            return _fallback_sentiment(alerts)

        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()

        # Strip markdown fences
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        parsed = json.loads(content)
        return {
            "sentiment": parsed.get("sentiment", "neutral"),
            "sentiment_label": parsed.get("sentiment_label", "خنثی"),
            "summary": parsed.get("summary", ""),
            "key_drivers": parsed.get("key_drivers", []),
            "outlook": parsed.get("outlook", ""),
        }

    except Exception:
        logger.exception("Sentiment LLM call failed")
        return _fallback_sentiment(alerts)


def _fallback_sentiment(alerts: list[dict]) -> dict[str, Any]:
    """Rule-based sentiment fallback when LLM is unavailable."""
    if not alerts:
        return {
            "sentiment": "neutral",
            "sentiment_label": "خنثی",
            "summary": "هشداری در این بازه زمانی وجود ندارد.",
            "key_drivers": [],
            "outlook": "داده کافی برای تحلیل وجود ندارد.",
        }

    high = sum(1 for a in alerts if a["severity"] == "high")
    med = sum(1 for a in alerts if a["severity"] == "medium")
    total = len(alerts)

    # Simple heuristic: more high-severity = more volatile/bullish for gold
    if high >= 3:
        sentiment = "very_bullish"
        label = "بسیار صعودی"
    elif high >= 1:
        sentiment = "bullish"
        label = "صعودی"
    elif med >= 5:
        sentiment = "bullish"
        label = "صعودی"
    elif total >= 3:
        sentiment = "neutral"
        label = "خنثی"
    else:
        sentiment = "neutral"
        label = "خنثی"

    return {
        "sentiment": sentiment,
        "sentiment_label": label,
        "summary": f"{total} هشدار در این بازه ({high} بالا، {med} متوسط). تحلیل LLM غیرفعال است.",
        "key_drivers": [],
        "outlook": "برای تحلیل دقیق‌تر، LLM را فعال کنید.",
    }
