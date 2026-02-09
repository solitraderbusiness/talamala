"""
Deterministic severity assessment — checks news content against the
``importance_criteria`` conditions defined in each rule, with a
match-score-based fallback for meaningful severity distribution.

**No LLM is involved.**  Severity is decided by condition matching first,
then by match_score thresholds when conditions don't match.
"""

from __future__ import annotations

from api.rule_engine.load_rules import Rule
from api.rule_engine.matcher import MatchResult, normalize_text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

_VALID_SEVERITIES = frozenset({SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW})

# Confidence clamp bounds
_MIN_CONFIDENCE = 0.3
_MAX_CONFIDENCE = 0.95

# Match-score thresholds for severity fallback.
# These kick in when the YAML importance_criteria conditions don't match.
_HIGH_SCORE_THRESHOLD = 0.35       # 3+ keywords or 2 kw + signals → high
_HIGH_IMMEDIATE_THRESHOLD = 0.25   # immediate-horizon rules: lower bar for high
_LOW_SCORE_THRESHOLD = 0.15        # borderline single-keyword match → low


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def determine_severity(
    content: str,
    rule: Rule,
    match_score: float = 0.0,
) -> str:
    """Determine the severity level for *content* using the rule's criteria.

    The function first tries condition-based matching from the YAML
    ``importance_criteria``, then falls back to match-score thresholds
    for a meaningful severity distribution.

    **Priority order:**

    1. **Condition matching** — if any ``high_if`` / ``medium_if`` /
       ``low_if`` condition string is found in the normalised content,
       return that severity immediately.
    2. **Score-based fallback** — when no condition matches:
       - ``"high"`` if score >= 0.35 (or >= 0.25 for immediate-horizon rules)
       - ``"low"`` if score < 0.15
       - ``"medium"`` otherwise

    Parameters
    ----------
    content:
        The raw (un-normalised) news body text.
    rule:
        The matched :class:`Rule` whose criteria to evaluate.
    match_score:
        The match score from the matcher (0.0 – 1.0).  Higher scores mean
        more keywords/signals matched.

    Returns
    -------
    str
        One of ``"high"``, ``"medium"``, or ``"low"``.
    """
    norm_content = normalize_text(content)
    criteria = rule.importance_criteria

    # 1. Condition-based matching (original YAML logic)
    if _any_condition_matches(norm_content, criteria.get("high_if", [])):
        return SEVERITY_HIGH

    if _any_condition_matches(norm_content, criteria.get("medium_if", [])):
        return SEVERITY_MEDIUM

    if _any_condition_matches(norm_content, criteria.get("low_if", [])):
        return SEVERITY_LOW

    # 2. Score-based fallback for meaningful severity distribution
    # Immediate-horizon rules (breaking events) have a lower threshold for high
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

    Higher ``match_score`` (more keywords/signals matched) yields higher
    confidence.  The value is clamped to [0.3, 0.95] — we never claim 100 %
    confidence from substring matching alone, and even a single-keyword match
    gives at least 0.3.

    Parameters
    ----------
    match_result:
        The :class:`MatchResult` produced by the matcher.

    Returns
    -------
    float
        Confidence in [0.3, 0.95].
    """
    # Linear mapping:  score 0 -> 0.3,  score 1 -> 0.95
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
