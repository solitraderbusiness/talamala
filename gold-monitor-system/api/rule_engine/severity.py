"""
Deterministic severity assessment using event-type classification.

**Priority order:**

1. **Event classification** — regex patterns classify the EVENT TYPE
   (war, rate decision, price record, etc.) into severity levels.
2. **YAML condition matching** — ``importance_criteria`` substring check.
3. **Match-score fallback** — score thresholds when nothing else matches.

**No LLM is involved.**
"""

from __future__ import annotations

import re

from api.rule_engine.load_rules import Rule
from api.rule_engine.matcher import MatchResult, normalize_text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

_VALID_SEVERITIES = frozenset(
    {SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW}
)

# Confidence clamp bounds
_MIN_CONFIDENCE = 0.3
_MAX_CONFIDENCE = 0.95

# Match-score thresholds (last-resort fallback only)
_HIGH_SCORE_THRESHOLD = 0.35
_HIGH_IMMEDIATE_THRESHOLD = 0.25
_LOW_SCORE_THRESHOLD = 0.15

# ---------------------------------------------------------------------------
# Event-type severity patterns
# ---------------------------------------------------------------------------
# Checked in order: critical → high → medium → low.
# First match wins.

EVENT_SEVERITY_MAP: dict[str, list[str]] = {
    "critical": [
        r"(جنگ|حمله\s*نظامی|war\b|military\s*strike|بمباران)",
        r"(فدرال\s*رزرو.*نرخ\s*بهره|fed.*rate\s*(cut|hike|decision))",
        r"(تحریم\s*جدید|new\s*sanction|snapback)",
        r"(مذاکرات?\s*هسته.?ای|nuclear\s*negoti|JCPOA|برجام)",
        r"(رکورد\s*(تاریخی|جدید)|all.time\s*high|ATH)",
        r"(سقوط\s*(شدید|بازار)|crash|black\s*swan)",
    ],
    "high": [
        r"(CPI|تورم\s*آمریکا|inflation\s*data)",
        r"(NFP|non.?farm|اشتغال\s*آمریکا)",
        r"(بانک\s*مرکزی.*خرید\s*طلا|central\s*bank.*gold\s*buy)",
        r"(ETF.*(inflow|outflow|ورود|خروج))",
        r"(نرخ\s*بهره.*(افزایش|کاهش)|rate\s*(hike|cut))",
        r"(قیمت\s*طلا.*(بالای|زیر)\s*\d{3,}|gold.*(above|below)\s*\d{3,})",
        r"(دلار.*(سقوط|جهش)|dollar.*(crash|surge))",
        r"(تنش.*ایران|iran.*tension)",
    ],
    "medium": [
        r"(تحلیل|analysis|پیش.?بینی|forecast)",
        r"(گزارش\s*فصلی|quarterly\s*report)",
        r"(PMI|GDP|بازار\s*سهام|stock\s*market)",
        r"(تقاضای?\s*(فیزیکی|طلا)|physical\s*demand)",
    ],
    "low": [
        r"(نظرسنجی|survey|poll)",
        r"(آموزش|tutorial|معرفی)",
        r"(تاریخچه|history|گذشته)",
    ],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_severity(title: str, content: str = "") -> str | None:
    """Classify severity based on EVENT TYPE using regex patterns.

    Returns the severity level if a pattern matches, or ``None`` if
    no event pattern was recognized.
    """
    text = f"{title} {content}"
    for severity in ("critical", "high", "medium", "low"):
        for pattern in EVENT_SEVERITY_MAP[severity]:
            if re.search(pattern, text, re.IGNORECASE):
                return severity
    return None


def determine_severity(
    content: str,
    rule: Rule,
    match_score: float = 0.0,
    title: str = "",
) -> str:
    """Determine the severity level using a 3-tier approach.

    **Priority order:**

    1. **Event classification** — regex patterns on title + content.
    2. **YAML condition matching** — ``importance_criteria`` substrings.
    3. **Match-score fallback** — thresholds based on keyword match quality.

    Parameters
    ----------
    content:
        The raw (un-normalised) news body text.
    rule:
        The matched :class:`Rule` whose criteria to evaluate.
    match_score:
        The match score from the matcher (0.0 – 1.0).
    title:
        The news title (used for event classification).

    Returns
    -------
    str
        One of ``"critical"``, ``"high"``, ``"medium"``, or ``"low"``.
    """
    # 1. Event classification (regex on title + content)
    event_sev = classify_severity(title, content)
    if event_sev is not None:
        return event_sev

    # 2. YAML condition matching (original logic)
    norm_content = normalize_text(content)
    criteria = rule.importance_criteria

    if _any_condition_matches(norm_content, criteria.get("high_if", [])):
        return SEVERITY_HIGH
    if _any_condition_matches(norm_content, criteria.get("medium_if", [])):
        return SEVERITY_MEDIUM
    if _any_condition_matches(norm_content, criteria.get("low_if", [])):
        return SEVERITY_LOW

    # 3. Score-based fallback
    high_threshold = (
        _HIGH_IMMEDIATE_THRESHOLD
        if rule.horizon == "immediate"
        else _HIGH_SCORE_THRESHOLD
    )
    if match_score >= high_threshold:
        return SEVERITY_HIGH
    if match_score < _LOW_SCORE_THRESHOLD:
        return SEVERITY_LOW

    return SEVERITY_MEDIUM


def calculate_confidence(match_result: MatchResult) -> float:
    """Derive a confidence score from the ``match_score`` of a match result.

    Linear mapping: score 0 → 0.3, score 1 → 0.95.
    Clamped to [0.3, 0.95].
    """
    raw = _MIN_CONFIDENCE + match_result.match_score * (_MAX_CONFIDENCE - _MIN_CONFIDENCE)
    return _clamp(raw, _MIN_CONFIDENCE, _MAX_CONFIDENCE)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _any_condition_matches(
    norm_content: str, conditions: list[str]
) -> bool:
    """Return ``True`` if any normalised condition string is found in *norm_content*."""
    for condition in conditions:
        norm_cond = normalize_text(condition)
        if norm_cond and norm_cond in norm_content:
            return True
    return False


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp *value* to [*lo*, *hi*]."""
    return max(lo, min(hi, value))
