"""
Alert builder — assembles a structured alert dict from raw news items,
match results, and (optional) LLM enrichment output.

The output schema mirrors the ``alert_template`` section of the YAML rule
file so that downstream consumers always receive a consistent shape.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from api.rule_engine.matcher import MatchResult, normalize_text
from api.rule_engine.direction import (
    calculate_alert_score,
    detect_direction,
)
from api.rule_engine.severity import (
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    calculate_confidence,
    determine_severity,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity ordering (for "pick the highest")
# ---------------------------------------------------------------------------

_SEVERITY_RANK: dict[str, int] = {
    SEVERITY_CRITICAL: 4,
    SEVERITY_HIGH: 3,
    SEVERITY_MEDIUM: 2,
    "low": 1,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_dedupe_key(rule_ids: list[str], title: str, source: str) -> str:
    """Generate a stable deduplication key.

    The key is a SHA-256 hex digest of the sorted rule IDs and the normalised
    title.  Source is intentionally excluded so that the same story reported
    by multiple outlets (IRNA, Mehr, etc.) produces the same key —
    preventing duplicate alerts for the same news.

    Parameters
    ----------
    rule_ids:
        Rule identifiers that matched.
    title:
        News item title (will be normalised).
    source:
        Source / publisher name (kept for API compatibility, not used in hash).

    Returns
    -------
    str
        64-character lower-case hex SHA-256 digest.
    """
    parts = [
        ",".join(sorted(rule_ids)),
        normalize_text(title),
    ]
    payload = "|".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_alert(
    raw_item: dict[str, Any],
    match_results: list[MatchResult],
    llm_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a complete alert dict from a news item and its match results.

    The returned dict matches the ``alert_template`` from the YAML rule file:

    .. code-block:: python

        {
            "title": str,
            "timestamp_utc": str,           # ISO-8601
            "source_name": str,
            "source_url": str,
            "matched_rule_ids": list[str],
            "summary_fa": str,
            "why_important_fa": str,
            "expected_impact": list[dict],   # [{asset, direction, mechanism}]
            "severity": str,                 # high | medium | low
            "time_horizon": str,
            "confidence": float,             # 0.3 – 0.95
            "follow_up_questions": list[str],
            "dedupe_key": str,
            "match_evidence": dict,          # {rule_id: {keywords, signals}}
        }

    Parameters
    ----------
    raw_item:
        The ingested news item.  Expected keys: ``title``, ``content``,
        ``source`` (or ``source_name``), ``url`` (or ``source_url``).
    match_results:
        Non-empty list of :class:`MatchResult` objects (sorted by score).
    llm_output:
        Optional dict with LLM-enriched fields: ``summary_fa``,
        ``why_important_fa``, ``follow_up_questions``.

    Returns
    -------
    dict
        The assembled alert.
    """
    if not match_results:
        raise ValueError("match_results must not be empty")

    llm = llm_output or {}

    # --- basic metadata --------------------------------------------------- #
    item_title: str = str(raw_item.get("title", ""))
    item_content: str = str(raw_item.get("content", ""))
    source_name: str = str(
        raw_item.get("source_name", raw_item.get("source", ""))
    )
    source_url: str = str(
        raw_item.get("source_url", raw_item.get("url", ""))
    )

    # LLM title is no longer used for the alert title — original source title
    # is always preserved to prevent hallucinated/fabricated headlines.

    # --- matched rule ids ------------------------------------------------- #
    matched_rule_ids: list[str] = [mr.rule.id for mr in match_results]

    # --- severity per rule ------------------------------------------------ #
    severity_map: dict[str, str] = {}
    for mr in match_results:
        sev = determine_severity(
            item_content, mr.rule, mr.match_score, title=item_title,
        )
        severity_map[mr.rule.id] = sev

    highest_severity = _pick_highest_severity(list(severity_map.values()))

    # --- time horizon (from the highest-severity rule) -------------------- #
    time_horizon = _pick_horizon(match_results, severity_map)

    # --- direction detection (3-stage: regex → lexicon → fallback) -------- #
    dir_result = detect_direction(item_title, item_content)
    direction = dir_result["direction"]
    direction_confidence = dir_result["confidence"]
    direction_method = dir_result["method"]

    # --- confidence (based on detection method + match quality) ------------ #
    base_confidences = [calculate_confidence(mr) for mr in match_results]
    avg_match_confidence = round(sum(base_confidences) / len(base_confidences), 4)

    # Blend match confidence with direction confidence for final value
    if direction in ("bullish", "bearish"):
        avg_confidence = round(
            0.5 * avg_match_confidence + 0.5 * direction_confidence, 4
        )
    else:
        avg_confidence = avg_match_confidence

    # --- expected impact -------------------------------------------------- #
    expected_impact = _build_expected_impact(match_results)

    # --- summary / why_important ------------------------------------------ #
    summary_fa: str = llm.get("summary_fa") or _truncate(item_content, 200)
    why_important_fa: str = (
        llm.get("why_important_fa") or match_results[0].rule.why_important
    )
    follow_up_questions: list[str] = llm.get("follow_up_questions", [])

    # --- per-alert sentiment score ---------------------------------------- #
    best_match_score = match_results[0].match_score
    total_keywords = sum(len(mr.matched_keywords) for mr in match_results)
    total_signals = sum(len(mr.matched_signals) for mr in match_results)
    content_len = len(item_content)

    alert_score = calculate_alert_score(
        direction, direction_confidence, highest_severity,
        match_score=best_match_score,
        num_rules_matched=len(match_results),
        num_keywords_matched=total_keywords,
        num_signals_matched=total_signals,
        direction_method=direction_method,
        content_length=content_len,
    )

    # --- dedupe key ------------------------------------------------------- #
    dedupe_key = generate_dedupe_key(matched_rule_ids, item_title, source_name)

    # --- match evidence --------------------------------------------------- #
    match_evidence = _build_match_evidence(match_results)

    return {
        "title": item_title,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_name": source_name,
        "source_url": source_url,
        "matched_rule_ids": matched_rule_ids,
        "summary_fa": summary_fa,
        "why_important_fa": why_important_fa,
        "expected_impact": expected_impact,
        "severity": highest_severity,
        "time_horizon": time_horizon,
        "confidence": avg_confidence,
        "direction": direction,
        "direction_confidence": direction_confidence,
        "direction_method": direction_method,
        "alert_score": alert_score,
        "follow_up_questions": follow_up_questions,
        "dedupe_key": dedupe_key,
        "match_evidence": match_evidence,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _pick_highest_severity(severities: list[str]) -> str:
    """Return the most severe level from a list of severity strings."""
    if not severities:
        return SEVERITY_MEDIUM
    return max(severities, key=lambda s: _SEVERITY_RANK.get(s, 0))


def _pick_horizon(
    match_results: list[MatchResult],
    severity_map: dict[str, str],
) -> str:
    """Return the time horizon of the highest-severity matched rule.

    If multiple rules share the highest severity, use the first one
    (highest match score — the list is pre-sorted).
    """
    highest_sev = _pick_highest_severity(list(severity_map.values()))
    for mr in match_results:
        if severity_map.get(mr.rule.id) == highest_sev:
            return mr.rule.horizon
    # Fallback
    return match_results[0].rule.horizon


def _build_expected_impact(
    match_results: list[MatchResult],
) -> list[dict[str, str]]:
    """Aggregate ``impact_hypothesis`` from all matched rules.

    Each rule's impact_hypothesis may contain keys like ``asset``,
    ``direction``, ``mechanism``, or a ``typical_effect`` list with
    ``asset`` and ``effect`` fields.  We normalise everything into a
    flat list of dicts with ``asset``, ``direction``, ``mechanism``.
    """
    impacts: list[dict[str, str]] = []
    seen: set[str] = set()

    for mr in match_results:
        hyp = mr.rule.impact_hypothesis
        if not hyp:
            continue

        # Collect candidate item dicts from various YAML layouts
        items: list[dict[str, Any]]
        if "impacts" in hyp and isinstance(hyp["impacts"], list):
            items = hyp["impacts"]
        elif "typical_effect" in hyp and isinstance(hyp["typical_effect"], list):
            items = hyp["typical_effect"]
        elif "asset" in hyp:
            items = [hyp]
        else:
            # Try treating all values as impact dicts or lists
            items = []
            for v in hyp.values():
                if isinstance(v, dict):
                    items.append(v)
                elif isinstance(v, list):
                    items.extend(d for d in v if isinstance(d, dict))
            if not items:
                items = [hyp]

        for item in items:
            if not isinstance(item, dict):
                continue

            asset = str(item.get("asset", ""))
            direction = str(item.get("direction", ""))
            mechanism = str(item.get("mechanism", "") or item.get("effect", ""))

            # Try to infer direction from effect text when not explicit
            if not direction and mechanism:
                ml = mechanism.lower()
                has_bull = "bullish" in ml or "price_up" in ml
                has_bear = "bearish" in ml or "price_down" in ml
                if has_bull and has_bear:
                    direction = "mixed"
                elif has_bull:
                    direction = "up"
                elif has_bear:
                    direction = "down"

            entry = {
                "asset": asset,
                "direction": direction,
                "mechanism": mechanism,
            }
            fingerprint = f"{entry['asset']}|{entry['direction']}|{entry['mechanism']}"
            if fingerprint not in seen:
                seen.add(fingerprint)
                impacts.append(entry)

    return impacts


def _build_match_evidence(
    match_results: list[MatchResult],
) -> dict[str, dict[str, list[str]]]:
    """Build the ``match_evidence`` audit dict.

    Structure::

        {
            "rule_id_1": {"keywords": [...], "signals": [...]},
            "rule_id_2": {"keywords": [...], "signals": [...]},
        }
    """
    evidence: dict[str, dict[str, list[str]]] = {}
    for mr in match_results:
        evidence[mr.rule.id] = {
            "keywords": list(mr.matched_keywords),
            "signals": list(mr.matched_signals),
        }
    return evidence


def _truncate(text: str, max_len: int) -> str:
    """Truncate *text* to *max_len* characters, appending ``...`` if clipped."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."
