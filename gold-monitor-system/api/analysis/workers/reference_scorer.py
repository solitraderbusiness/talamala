"""Reference scorer — LLM cross-check for sentiment QA.

Picks a batch of unscored alerts every 6 hours, sends them in groups
of 10 to OpenRouter (Haiku for cost efficiency) with a structured prompt,
and stores the reference prediction in `sentiment_reference_scores`.

The system prediction (from rule engine) is compared with the LLM's
independent assessment.  Disagreements surface in the admin QA page.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import text

from api.config import settings
from api.database import AsyncSessionLocal

logger = logging.getLogger("analysis.reference_scorer")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
BATCH_SIZE = 50
BATCH_CHUNK = 10  # alerts per LLM call (batched)
MODEL = "anthropic/claude-haiku-4.5"

SYSTEM_PROMPT = """\
You are a gold market sentiment analyst.  You will be given a numbered list
of news headlines with summaries.  For EACH item, classify the sentiment
with respect to the gold price (XAUUSD).

Return a JSON array (one object per item, in the same order) where each
object has:
- index: the item number (1-based)
- direction: "positive" | "negative" | "neutral"
  (positive = bullish for gold, negative = bearish for gold)
- intensity: integer 1-5  (1=barely relevant, 5=major driver)
- confidence: float 0.0-1.0
- reasoning: one sentence explaining your classification

Return ONLY the JSON array, nothing else."""


async def run() -> dict:
    """Score a batch of unscored alerts via OpenRouter LLM."""
    api_key = settings.OPENROUTER_API_KEY
    if not api_key:
        logger.warning("OPENROUTER_API_KEY not set; skipping reference scoring.")
        return {"status": "skipped", "reason": "no_api_key"}

    async with AsyncSessionLocal() as db:
        # Pick alerts that have no reference score yet
        rows = (await db.execute(text("""
            SELECT a.id, a.title, a.summary_fa, a.severity,
                   a.confidence,
                   COALESCE((a.match_evidence->>'direction')::text, 'unknown') as sys_direction,
                   COALESCE((a.match_evidence->>'alert_score')::text, '0') as sys_score
            FROM alerts a
            LEFT JOIN sentiment_reference_scores rs ON rs.alert_id = a.id
            WHERE rs.id IS NULL
              AND a.created_at >= NOW() - INTERVAL '7 days'
            ORDER BY a.created_at DESC
            LIMIT :batch
        """), {"batch": BATCH_SIZE})).mappings().all()

        if not rows:
            logger.info("No unscored alerts found.")
            return {"status": "ok", "scored": 0}

        scored = 0
        errors = 0
        trace_id = f"ref_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        # Process in chunks of BATCH_CHUNK
        for chunk_start in range(0, len(rows), BATCH_CHUNK):
            chunk = rows[chunk_start:chunk_start + BATCH_CHUNK]
            try:
                results = await _score_batch(api_key, chunk)
                if not results:
                    errors += len(chunk)
                    continue

                for alert, result in zip(chunk, results):
                    if not result or "direction" not in result:
                        errors += 1
                        continue

                    sys_dir = alert["sys_direction"]
                    ref_dir = result.get("direction", "neutral")

                    sys_norm = _norm(sys_dir)
                    ref_norm = _norm(ref_dir)
                    agrees = sys_norm == ref_norm

                    await db.execute(text("""
                        INSERT INTO sentiment_reference_scores
                            (id, alert_id, system_direction, system_score, system_method,
                             ref_direction, ref_intensity, ref_confidence,
                             ref_model, ref_reasoning, direction_agrees, trace_id)
                        VALUES (:id, :aid, :sys_dir, :sys_score, 'rule_engine',
                                :ref_dir, :ref_int, :ref_conf,
                                :model, :reasoning, :agrees, :trace)
                        ON CONFLICT (alert_id) DO NOTHING
                    """), {
                        "id": str(uuid.uuid4()),
                        "aid": str(alert["id"]),
                        "sys_dir": sys_dir,
                        "sys_score": int(alert["sys_score"]) if alert["sys_score"] else 0,
                        "ref_dir": ref_dir,
                        "ref_int": int(result.get("intensity", 3)),
                        "ref_conf": float(result.get("confidence", 0.5)),
                        "model": MODEL,
                        "reasoning": str(result.get("reasoning", ""))[:500],
                        "agrees": agrees,
                        "trace": trace_id,
                    })
                    scored += 1
            except Exception:
                logger.exception("Error scoring batch starting at %d", chunk_start)
                errors += len(chunk)

        await db.commit()
        logger.info("Reference scorer: scored=%d, errors=%d, trace=%s", scored, errors, trace_id)
        return {"status": "ok", "scored": scored, "errors": errors, "trace_id": trace_id}


async def _score_batch(api_key: str, alerts: list) -> list[dict | None]:
    """Score multiple alerts in a single LLM call.

    Returns a list of result dicts (one per alert), or None on failure.
    """
    # Build numbered list of alerts
    lines = []
    for i, alert in enumerate(alerts, 1):
        title = alert["title"] or "(no title)"
        summary = (alert["summary_fa"] or "")[:300]
        lines.append(f"{i}. Headline: {title}\n   Summary: {summary}")

    user_msg = "\n\n".join(lines)

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": 200 * len(alerts),
        "temperature": 0.1,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://talamala.com",
        "X-Title": "Talamala Reference Scorer",
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)

    if resp.status_code != 200:
        logger.error("OpenRouter %d: %s", resp.status_code, resp.text[:300])
        return [None] * len(alerts)

    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

    # Parse JSON from response — strip markdown code fences if present
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1]
    if content.endswith("```"):
        content = content.rsplit("```", 1)[0]
    content = content.strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("Could not parse LLM JSON for batch: %s", content[:200])
        return [None] * len(alerts)

    if not isinstance(parsed, list):
        # LLM returned a single object — wrap it
        if isinstance(parsed, dict):
            parsed = [parsed]
        else:
            return [None] * len(alerts)

    # Map results by index (1-based) to align with alerts
    result_map: dict[int, dict] = {}
    for item in parsed:
        if isinstance(item, dict):
            idx = item.get("index")
            if isinstance(idx, int) and 1 <= idx <= len(alerts):
                result_map[idx] = item

    # Build ordered result list
    results = []
    for i in range(1, len(alerts) + 1):
        results.append(result_map.get(i))

    # Fall back: if no index field, assume sequential order
    if not result_map and len(parsed) == len(alerts):
        results = parsed

    return results


def _norm(d: str) -> str:
    """Normalise direction string for comparison."""
    d = (d or "").lower().strip()
    if d in ("positive", "bullish", "up"):
        return "positive"
    if d in ("negative", "bearish", "down"):
        return "negative"
    if d in ("neutral", "mixed"):
        return "neutral"
    return "unknown"
