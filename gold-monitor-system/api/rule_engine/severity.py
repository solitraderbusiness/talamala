"""
Deterministic severity assessment — checks news content against the
``importance_criteria`` conditions defined in each rule.

**No LLM is involved.**  Severity is decided by simple substring matching of
the condition phrases from the YAML against the normalised content.
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def determine_severity(content: str, rule: Rule) -> str:
    """Determine the severity level for *content* using the rule's criteria.

    The function walks the rule's ``importance_criteria`` dict in priority
    order:

    1. **high_if** — if *any* condition string is a substring of the
       normalised content, return ``"high"``.
    2. **medium_if** — likewise, return ``"medium"``.
    3. **low_if** — likewise, return ``"low"``.
    4. If none of the above match but the rule *did* match (i.e. we are
       calling this function at all), default to ``"medium"``.

    Parameters
    ----------
    content:
        The raw (un-normalised) news body text.
    rule:
        The matched :class:`Rule` whose criteria to evaluate.

    Returns
    -------
    str
        One of ``"high"``, ``"medium"``, or ``"low"``.
    """
    norm_content = normalize_text(content)
    criteria = rule.importance_criteria

    # Check in priority order
    if _any_condition_matches(norm_content, criteria.get("high_if", [])):
        return SEVERITY_HIGH

    if _any_condition_matches(norm_content, criteria.get("medium_if", [])):
        return SEVERITY_MEDIUM

    if _any_condition_matches(norm_content, criteria.get("low_if", [])):
        return SEVERITY_LOW

    # Default when the rule matched but no specific criterion was triggered
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
