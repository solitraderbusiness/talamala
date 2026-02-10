"""
Sentiment analysis router — deterministic 3-layer weighted scoring +
optional LLM text generation.

Scoring uses a deterministic formula based on:
  Layer 1: Per-alert RSS = Polarity × Confidence
  Layer 2: Importance weighting by severity
  Layer 3: Exponential time decay

The LLM (when available) is used ONLY for generating Persian text
(summary, key_drivers, outlook).  The numeric score is ALWAYS
computed by the deterministic formula.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import math
from typing import Any

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.database import get_db
from api.models import Alert, SentimentScore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sentiment"])

# Max alerts to send to LLM per timeframe (prevents token overflows)
_MAX_LLM_ALERTS = 20

# Redis cache TTL for LLM text output (seconds)
_LLM_CACHE_TTL = 300  # 5 minutes

# ── Timeframes ──────────────────────────────────────────────────────────

_TIMEFRAMES = [
    {"key": "1h", "hours": 1, "label": "۱ ساعت اخیر"},
    {"key": "4h", "hours": 4, "label": "۴ ساعت اخیر"},
    {"key": "24h", "hours": 24, "label": "۲۴ ساعت اخیر"},
]

# ── 3-Layer Sentiment Formula Parameters ─────────────────────────────

# Importance weights mapping severity → weight
_IMPORTANCE_WEIGHT: dict[str, float] = {
    "critical": 4.0,
    "high": 2.0,
    "medium": 1.0,
    "low": 0.5,
}

# Exponential decay rate (lambda) per timeframe.
# Higher λ = faster decay = more emphasis on very recent alerts.
_DECAY_LAMBDA: dict[str, float] = {
    "1h": 2.0,
    "4h": 0.5,
    "24h": 0.1,
}

# Volume thresholds per timeframe for dampening.
# Below threshold, the signal is dampened proportionally.
_VOLUME_THRESHOLD: dict[str, int] = {
    "1h": 10,
    "4h": 20,
    "24h": 30,
}


# ── Polarity Detection ───────────────────────────────────────────────


def _detect_polarity(alert: dict) -> tuple[float, float]:
    """Detect polarity from alert's direction data.

    Returns (polarity, confidence) where polarity is:
    -1.0 (bearish for gold), +1.0 (bullish for gold), or 0.0 (neutral).

    Uses stored direction data from the pipeline if available,
    otherwise computes on-the-fly using detect_direction.
    Neutral alerts contribute 0 polarity (not a small positive).
    """
    from api.rule_engine.direction import detect_direction

    # Check for stored direction (new pipeline alerts)
    evidence = alert.get("match_evidence", {})
    stored_direction = evidence.get("direction")
    stored_confidence = evidence.get("direction_confidence")

    if stored_direction:
        direction = stored_direction
        confidence = stored_confidence or 0.3
    else:
        # Compute on-the-fly for legacy alerts
        title = alert.get("title", "")
        summary = alert.get("summary_fa", "")
        dir_result = detect_direction(title, summary)
        direction = dir_result["direction"]
        confidence = dir_result["confidence"]

    if direction == "bullish":
        return (1.0, confidence)
    elif direction == "bearish":
        return (-1.0, confidence)
    else:
        return (0.0, 0.0)  # neutral contributes nothing


# ── Deterministic Score Computation ──────────────────────────────────


def _compute_sentiment_score(
    alerts: list[dict],
    timeframe_key: str,
    window_hours: int,
) -> tuple[int, str, str]:
    """Compute deterministic sentiment score using 3-layer weighted formula.

    Layer 1 (per alert):  RSS_i = Polarity_i × Direction_Confidence_i
    Layer 2 (importance):  WS_i  = RSS_i × W_imp_i
    Layer 3 (time decay):  contribution_i = WS_i × e^(-λ × t_i)

    Key change: neutral polarity = 0 (not a small positive). Neutral alerts
    do not push the score in either direction.

    Aggregation:
        raw = Σ(WS_i × W_time_i) / Σ(|W_imp_i × W_time_i|) × 100
    Volume dampening:
        dampened = raw × min(1.0, n / threshold)
    Directional ratio dampening:
        If most alerts are neutral, dampens score toward 50.
    Final score:
        50 + dampened / 2, clamped to [0, 100]

    Returns (score, sentiment_key, sentiment_label_fa).
    """
    if not alerts:
        return 50, "neutral", "خنثی"

    now = datetime.datetime.now(datetime.timezone.utc)
    decay_lambda = _DECAY_LAMBDA.get(timeframe_key, 0.5)
    volume_threshold = _VOLUME_THRESHOLD.get(timeframe_key, 20)

    numerator = 0.0
    denominator = 0.0
    directional_count = 0  # alerts with non-neutral direction

    for alert in alerts:
        # Skip price reports — they are informational only and should
        # NOT influence the sentiment gauge (circular logic prevention).
        alert_news_type = alert.get("match_evidence", {}).get("news_type", "")
        if alert_news_type == "price_report":
            continue

        # Layer 1: RSS = Polarity × Direction_Confidence
        polarity, dir_confidence = _detect_polarity(alert)
        if polarity != 0.0:
            directional_count += 1
            rss = polarity * max(dir_confidence, 0.3)
        else:
            rss = 0.0  # neutral contributes nothing to direction

        # Layer 2: Importance weight
        severity = alert.get("severity", "medium")
        w_imp = _IMPORTANCE_WEIGHT.get(severity, 1.0)
        ws = rss * w_imp

        # Layer 3: Time decay
        ts_str = alert.get("timestamp_utc", "")
        try:
            ts = datetime.datetime.fromisoformat(ts_str)
            hours_ago = max((now - ts).total_seconds() / 3600.0, 0.0)
        except (ValueError, TypeError):
            hours_ago = window_hours / 2  # Default to middle of window

        w_time = math.exp(-decay_lambda * hours_ago)

        numerator += ws * w_time
        denominator += abs(w_imp * w_time)

    # Aggregation
    if denominator < 1e-9:
        sentiment_raw = 0.0
    else:
        sentiment_raw = (numerator / denominator) * 100  # -100 to +100

    # Volume dampening
    n = len(alerts)
    dampening = min(1.0, n / volume_threshold)
    dampened = sentiment_raw * dampening

    # Directional ratio dampening: if most alerts are neutral,
    # the overall score should stay closer to 50
    if n > 0:
        directional_ratio = directional_count / n
        # Minimum ratio: even with 1 directional alert, keep some signal
        dir_dampening = max(0.3, directional_ratio)
        dampened = dampened * dir_dampening

    # Final score: 50 + dampened/2, clamped to [0, 100]
    score = int(round(max(0, min(100, 50 + dampened / 2))))

    # Map score to sentiment category
    sentiment_key, sentiment_label = _score_to_sentiment(score)
    return score, sentiment_key, sentiment_label


def _score_to_sentiment(score: int) -> tuple[str, str]:
    """Map a 0-100 score to a (sentiment_key, persian_label) pair."""
    if score >= 80:
        return "very_bullish", "بسیار صعودی"
    if score >= 65:
        return "bullish", "صعودی"
    if score >= 55:
        return "slightly_bullish", "نسبتاً صعودی"
    if score >= 45:
        return "neutral", "خنثی"
    if score >= 35:
        return "slightly_bearish", "نسبتاً نزولی"
    if score >= 20:
        return "bearish", "نزولی"
    return "very_bearish", "بسیار نزولی"


# ── LLM Text Generation ─────────────────────────────────────────────

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
   - "summary": 2-3 sentence Persian summary of the overall market mood
   - "key_drivers": array of 1-3 objects, each with:
     * "title": short Persian title of the driver
     * "impact": "bullish" or "bearish" or "neutral"
     * "weight": "high" or "medium" or "low" (how much this driver matters)
   - "outlook": 1 sentence Persian outlook/prediction
"""

_SENTIMENT_USER = """\
Analyze the following {count} gold market alerts from the past {timeframe}. \
The calculated sentiment score is {score}/100 ({sentiment_label}).

Provide a Persian text summary explaining the market mood. Do NOT assign \
your own sentiment score — it has already been calculated deterministically.

IMPORTANT: If there are HIGH severity alerts from earlier (even outside this \
exact window), they may still be listed here with a [STILL RELEVANT] tag. \
These should be weighted heavily in your analysis.

=== ALERTS ===
{alerts_text}

Respond with ONLY the JSON object.
"""


def _select_top_alerts(alerts: list[dict], max_count: int) -> list[dict]:
    """Select the most important alerts for LLM analysis.

    Sorts by severity (high first), then recency (newest first).
    Returns at most *max_count* alerts.
    """
    severity_order = {"critical": -1, "high": 0, "medium": 1, "low": 2}

    def sort_key(a: dict) -> tuple:
        sev = severity_order.get(a.get("severity", "medium"), 1)
        ts = a.get("timestamp_utc", "")
        return (sev, ts)  # lower severity number = higher priority

    sorted_alerts = sorted(alerts, key=sort_key)
    return sorted_alerts[:max_count]


def _format_alerts_for_llm(alerts: list[dict], window_hours: int) -> str:
    """Format alerts into text for the LLM prompt.

    Keeps summaries short (100 chars) to stay within token limits.
    """
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
        if hours_ago > window_hours and severity in ("critical", "high"):
            still_relevant = " [STILL RELEVANT]"

        sev_label = {"critical": "CRIT", "high": "HIGH", "medium": "MED", "low": "LOW"}.get(severity, severity)

        line = f"{i}. [{sev_label}] {title}{still_relevant}"
        if summary:
            line += f" — {summary[:100]}"
        line += f" ({source}, {hours_ago:.1f}h ago)"
        lines.append(line)

    return "\n".join(lines) if lines else "(No alerts in this period)"


async def _get_redis() -> aioredis.Redis | None:
    """Get a Redis connection for caching."""
    try:
        return aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception:
        return None


async def _call_sentiment_llm(
    alerts: list[dict],
    window_hours: int,
    timeframe_key: str,
    timeframe_label: str,
    api_key: str,
    score: int,
    sentiment_label: str,
    alert_count: int,
) -> dict[str, Any]:
    """Call OpenRouter for sentiment TEXT generation only.

    The numeric score is NOT derived from the LLM — it was already computed
    deterministically.  The LLM generates summary, key_drivers, and outlook.

    Results are cached in Redis for 5 minutes keyed by timeframe + score + count.
    """
    # Check Redis cache first
    cache_key = f"sentiment:llm:{timeframe_key}:{score}:{alert_count}"
    redis_conn = await _get_redis()
    if redis_conn:
        try:
            cached = await redis_conn.get(cache_key)
            if cached:
                logger.debug("Sentiment LLM cache hit for %s", timeframe_key)
                await redis_conn.aclose()
                return json.loads(cached)
        except Exception:
            pass

    # Select top alerts and format for LLM
    top_alerts = _select_top_alerts(alerts, _MAX_LLM_ALERTS)
    alerts_text = _format_alerts_for_llm(top_alerts, window_hours)

    user_prompt = _SENTIMENT_USER.format(
        count=len(alerts),
        timeframe=timeframe_label,
        alerts_text=alerts_text,
        score=score,
        sentiment_label=sentiment_label,
    )

    payload = {
        "model": "anthropic/claude-sonnet-4",
        "messages": [
            {"role": "system", "content": _SENTIMENT_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 600,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://gold-monitor.local",
        "X-Title": "Gold Monitor Sentiment",
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )

        if resp.status_code != 200:
            logger.error("Sentiment LLM returned %d: %s", resp.status_code, resp.text[:300])
            return {}

        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()

        # Strip markdown fences
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        parsed = json.loads(content)
        result = {
            "summary": parsed.get("summary", ""),
            "key_drivers": parsed.get("key_drivers", []),
            "outlook": parsed.get("outlook", ""),
        }

        # Cache in Redis
        if redis_conn:
            try:
                await redis_conn.set(cache_key, json.dumps(result, ensure_ascii=False), ex=_LLM_CACHE_TTL)
            except Exception:
                pass

        return result

    except Exception:
        logger.exception("Sentiment LLM call failed for %s", timeframe_key)
        return {}
    finally:
        if redis_conn:
            try:
                await redis_conn.aclose()
            except Exception:
                pass


def _fallback_text(alerts: list[dict], score: int) -> dict[str, Any]:
    """Generate fallback text when LLM is unavailable."""
    if not alerts:
        return {
            "summary": "هشداری در این بازه زمانی وجود ندارد.",
            "key_drivers": [],
            "outlook": "داده کافی برای تحلیل وجود ندارد.",
        }

    crit = sum(1 for a in alerts if a["severity"] == "critical")
    high = sum(1 for a in alerts if a["severity"] == "high")
    med = sum(1 for a in alerts if a["severity"] == "medium")
    low = sum(1 for a in alerts if a["severity"] == "low")
    total = len(alerts)

    parts = []
    if crit:
        parts.append(f"{crit} بحرانی")
    if high:
        parts.append(f"{high} بالا")
    if med:
        parts.append(f"{med} متوسط")
    if low:
        parts.append(f"{low} پایین")
    severity_str = "، ".join(parts) if parts else ""

    return {
        "summary": f"{total} هشدار در این بازه ({severity_str}). امتیاز: {score}",
        "key_drivers": [],
        "outlook": "برای تحلیل متنی دقیق‌تر، LLM را فعال کنید.",
    }


# ── Endpoint ────────────────────────────────────────────────────────────


@router.get("", response_model=None)
async def get_sentiment(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return multi-timeframe sentiment analysis.

    For each timeframe (1h, 4h, 24h):
    - Gathers alerts in that window (+ still-relevant high-severity)
    - Computes deterministic score via 3-layer formula
    - Optionally generates Persian text via LLM
    - Returns structured sentiment data with score
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
        evidence = a.match_evidence or {}
        all_alerts.append({
            "title": a.title,
            "severity": a.severity,
            "timestamp_utc": a.timestamp_utc.isoformat() if a.timestamp_utc else "",
            "summary_fa": a.summary_fa or "",
            "source_name": a.source_name or "",
            "confidence": a.confidence or 0.5,
            "matched_rule_ids": a.matched_rule_ids or [],
            "expected_impact": a.expected_impact or [],
            "match_evidence": evidence,
        })

    # High/critical-severity alerts from last 24h (always considered)
    high_severity = [a for a in all_alerts if a["severity"] in ("critical", "high")]

    results: dict[str, Any] = {
        "timeframes": {},
        "updated_at": now.isoformat(),
        "alert_count_24h": len(all_alerts),
    }

    api_key = settings.OPENROUTER_API_KEY
    use_llm = bool(api_key)

    # Pre-parse timestamps once (avoid re-parsing per timeframe)
    alert_timestamps: dict[str, datetime.datetime | None] = {}
    for a in all_alerts:
        alert_timestamps[a["title"]] = _parse_ts(a["timestamp_utc"])

    # Gather unique alerts per timeframe + compute deterministic scores
    tf_data: list[dict[str, Any]] = []
    for tf in _TIMEFRAMES:
        key = tf["key"]
        hours = tf["hours"]
        cutoff = now - datetime.timedelta(hours=hours)

        # Alerts in this window
        window_alerts = [
            a for a in all_alerts
            if alert_timestamps.get(a["title"]) and alert_timestamps[a["title"]] >= cutoff  # type: ignore[operator]
        ]

        # Add high-severity alerts from outside window (still relevant)
        if hours < 24:
            for ha in high_severity:
                ts = alert_timestamps.get(ha["title"])
                if ts and ts < cutoff:
                    window_alerts.append(ha)

        # Remove duplicates by title
        seen_titles: set[str] = set()
        unique_alerts: list[dict] = []
        for a in window_alerts:
            if a["title"] not in seen_titles:
                seen_titles.add(a["title"])
                unique_alerts.append(a)

        # ── Deterministic score (ALWAYS computed) ──
        score, sentiment_key, sentiment_label = _compute_sentiment_score(
            unique_alerts, key, hours,
        )

        tf_data.append({
            "tf": tf,
            "unique_alerts": unique_alerts,
            "score": score,
            "sentiment_key": sentiment_key,
            "sentiment_label": sentiment_label,
        })

    # ── LLM text generation — run all timeframes IN PARALLEL ──
    async def _get_llm_text(td: dict) -> dict[str, Any]:
        tf = td["tf"]
        if use_llm and td["unique_alerts"]:
            result = await _call_sentiment_llm(
                td["unique_alerts"],
                tf["hours"],
                tf["key"],
                tf["label"],
                api_key,
                td["score"],
                td["sentiment_label"],
                len(td["unique_alerts"]),
            )
            return result if result else _fallback_text(td["unique_alerts"], td["score"])
        return _fallback_text(td["unique_alerts"], td["score"])

    llm_results = await asyncio.gather(
        *[_get_llm_text(td) for td in tf_data],
        return_exceptions=True,
    )

    # Assemble final results
    for td, llm_text in zip(tf_data, llm_results):
        tf = td["tf"]
        key = tf["key"]

        if isinstance(llm_text, Exception):
            logger.error("LLM call failed for %s: %s", key, llm_text)
            llm_text = _fallback_text(td["unique_alerts"], td["score"])

        sentiment_data: dict[str, Any] = {
            "sentiment": td["sentiment_key"],
            "sentiment_label": td["sentiment_label"],
            "summary": llm_text.get("summary", ""),
            "key_drivers": llm_text.get("key_drivers", []),
            "outlook": llm_text.get("outlook", ""),
            "alert_count": len(td["unique_alerts"]),
            "label": tf["label"],
        }

        # Persist score to DB
        await _persist_sentiment_score(
            db, key, td["score"], td["sentiment_key"],
            td["sentiment_label"], len(td["unique_alerts"]),
        )
        sentiment_data["score"] = td["score"]

        results["timeframes"][key] = sentiment_data

    return results


def _parse_ts(ts_str: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None


async def _persist_sentiment_score(
    db: AsyncSession,
    timeframe: str,
    score: int,
    sentiment: str,
    sentiment_label: str,
    alert_count: int,
) -> None:
    """Persist a sentiment score to the DB."""
    record = SentimentScore(
        timeframe=timeframe,
        score=score,
        sentiment=sentiment,
        sentiment_label=sentiment_label,
        alert_count=alert_count,
    )
    db.add(record)
    await db.commit()


# ── History endpoint ───────────────────────────────────────────────────


@router.get("/history", response_model=None)
async def get_sentiment_history(
    db: AsyncSession = Depends(get_db),
    timeframe: str = Query("4h", pattern="^(1h|4h|24h)$"),
    hours: int = Query(48, ge=1, le=720),
) -> dict[str, Any]:
    """Return historical sentiment scores for charting.

    Parameters
    ----------
    timeframe:
        Which timeframe to get history for (1h, 4h, 24h).
    hours:
        How many hours of history to return (default 48, max 720 = 30 days).
    """
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)

    result = await db.execute(
        select(SentimentScore)
        .where(SentimentScore.timeframe == timeframe)
        .where(SentimentScore.created_at >= cutoff)
        .order_by(SentimentScore.created_at)
    )
    scores = result.scalars().all()

    return {
        "timeframe": timeframe,
        "hours": hours,
        "data": [
            {
                "score": s.score,
                "sentiment": s.sentiment,
                "sentiment_label": s.sentiment_label,
                "alert_count": s.alert_count,
                "timestamp": s.created_at.isoformat(),
            }
            for s in scores
        ],
    }
