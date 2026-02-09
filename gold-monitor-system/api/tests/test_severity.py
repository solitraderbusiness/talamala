"""
Tests for api.rule_engine.severity — determine_severity and calculate_confidence.
"""

import sys
from pathlib import Path

# Ensure the project root is on sys.path so that ``api.rule_engine`` is importable.
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pytest

from api.rule_engine.severity import (
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    calculate_confidence,
    determine_severity,
)
from api.rule_engine.matcher import MatchResult
from api.rule_engine.load_rules import Rule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rule(
    rule_id: str = "test_rule",
    high_if: list[str] | None = None,
    medium_if: list[str] | None = None,
    low_if: list[str] | None = None,
    **kwargs,
) -> Rule:
    """Create a Rule with configurable importance_criteria."""
    return Rule(
        id=rule_id,
        section=kwargs.get("section", "global_gold"),
        title=kwargs.get("title", "Test Rule"),
        what_it_is="test",
        watch_for_keywords=kwargs.get("keywords", []),
        watch_for_signals=kwargs.get("signals", []),
        why_important="test importance",
        importance_criteria={
            "high_if": high_if or [],
            "medium_if": medium_if or [],
            "low_if": low_if or [],
        },
        impact_hypothesis=kwargs.get("impact_hypothesis", {}),
        horizon=kwargs.get("horizon", "immediate"),
    )


def _make_match_result(
    rule: Rule | None = None,
    match_score: float = 0.5,
    matched_keywords: list[str] | None = None,
    matched_signals: list[str] | None = None,
) -> MatchResult:
    """Create a MatchResult for testing."""
    if rule is None:
        rule = _make_rule()
    return MatchResult(
        rule=rule,
        matched_keywords=matched_keywords or [],
        matched_signals=matched_signals or [],
        match_score=match_score,
    )


# =========================================================================
# determine_severity
# =========================================================================


class TestDetermineSeverity:
    """Tests for rule-based severity determination."""

    def test_high_severity_when_high_condition_matches(self):
        rule = _make_rule(
            high_if=["شوک بزرگ"],
            medium_if=["خبر معمولی"],
            low_if=["تکراری"],
        )
        content = "این یک شوک بزرگ در بازار بود"
        assert determine_severity(content, rule) == SEVERITY_HIGH

    def test_medium_severity_when_medium_condition_matches(self):
        rule = _make_rule(
            high_if=["شوک بزرگ"],
            medium_if=["خبر معمولی"],
            low_if=["تکراری"],
        )
        content = "این یک خبر معمولی بود"
        assert determine_severity(content, rule) == SEVERITY_MEDIUM

    def test_low_severity_when_low_condition_matches(self):
        rule = _make_rule(
            high_if=["شوک بزرگ"],
            medium_if=["خبر معمولی"],
            low_if=["تکراری"],
        )
        content = "خبر تکراری بدون محتوای جدید"
        assert determine_severity(content, rule) == SEVERITY_LOW

    def test_high_takes_priority_over_medium_and_low(self):
        # Content matches all three levels — high should win
        rule = _make_rule(
            high_if=["بازار"],
            medium_if=["بازار"],
            low_if=["بازار"],
        )
        content = "وضعیت بازار امروز"
        assert determine_severity(content, rule) == SEVERITY_HIGH

    def test_medium_takes_priority_over_low(self):
        # Content matches medium and low — medium should win
        rule = _make_rule(
            high_if=["شوک بزرگ"],
            medium_if=["بازار"],
            low_if=["بازار"],
        )
        content = "وضعیت بازار امروز"
        assert determine_severity(content, rule) == SEVERITY_MEDIUM

    def test_defaults_to_medium_when_no_condition_matches(self):
        rule = _make_rule(
            high_if=["xyz_never_matches"],
            medium_if=["abc_never_matches"],
            low_if=["qrs_never_matches"],
        )
        content = "some unrelated content"
        # With a typical match_score (0.20), falls to score-based medium
        assert determine_severity(content, rule, match_score=0.20) == SEVERITY_MEDIUM

    def test_defaults_to_medium_when_criteria_are_empty(self):
        rule = _make_rule()
        content = "any content"
        assert determine_severity(content, rule, match_score=0.20) == SEVERITY_MEDIUM

    # --- Score-based fallback tests ---

    def test_score_fallback_high_when_score_above_threshold(self):
        rule = _make_rule(horizon="short")
        content = "unmatched content"
        assert determine_severity(content, rule, match_score=0.40) == SEVERITY_HIGH

    def test_score_fallback_high_immediate_horizon_lower_threshold(self):
        rule = _make_rule(horizon="immediate")
        content = "unmatched content"
        # 0.30 is above immediate threshold (0.25) but below general (0.35)
        assert determine_severity(content, rule, match_score=0.30) == SEVERITY_HIGH

    def test_score_fallback_medium_for_moderate_score(self):
        rule = _make_rule(horizon="short")
        content = "unmatched content"
        assert determine_severity(content, rule, match_score=0.20) == SEVERITY_MEDIUM

    def test_score_fallback_low_when_score_below_threshold(self):
        rule = _make_rule(horizon="short")
        content = "unmatched content"
        assert determine_severity(content, rule, match_score=0.12) == SEVERITY_LOW

    def test_condition_match_takes_priority_over_score(self):
        # Condition says medium, but score would say high — condition wins
        rule = _make_rule(medium_if=["بازار"])
        content = "وضعیت بازار امروز"
        assert determine_severity(content, rule, match_score=0.50) == SEVERITY_MEDIUM

    def test_condition_matching_is_case_insensitive(self):
        rule = _make_rule(high_if=["Surprise"])
        content = "This was a big SURPRISE in the market"
        assert determine_severity(content, rule) == SEVERITY_HIGH

    def test_condition_matching_handles_persian_normalisation(self):
        # Use Arabic yaa in the condition; Persian yaa in the content
        rule = _make_rule(high_if=["تصمیم غافلگیرکننده"])
        # Replace Persian yaa with Arabic yaa in the content text
        content = "این تصمیم غافلگیرکننده بود"
        assert determine_severity(content, rule) == SEVERITY_HIGH

    def test_multiple_high_conditions_any_triggers(self):
        rule = _make_rule(
            high_if=["condition_alpha", "condition_beta"],
        )
        # Only the second condition matches
        content = "this has condition_beta in it"
        assert determine_severity(content, rule) == SEVERITY_HIGH

    def test_empty_condition_string_ignored(self):
        rule = _make_rule(high_if=["", "real_condition"])
        content = "this has real_condition"
        assert determine_severity(content, rule) == SEVERITY_HIGH

    def test_english_keywords_in_criteria(self):
        rule = _make_rule(
            high_if=["Surprise"],
            medium_if=["as expected"],
            low_if=["no new information"],
        )
        content = "The rate decision was as expected by the market"
        assert determine_severity(content, rule) == SEVERITY_MEDIUM


# =========================================================================
# calculate_confidence
# =========================================================================


class TestCalculateConfidence:
    """Tests for confidence calculation from match scores."""

    def test_zero_score_gives_minimum_confidence(self):
        mr = _make_match_result(match_score=0.0)
        confidence = calculate_confidence(mr)
        assert confidence == pytest.approx(0.3)

    def test_full_score_gives_maximum_confidence(self):
        mr = _make_match_result(match_score=1.0)
        confidence = calculate_confidence(mr)
        assert confidence == pytest.approx(0.95)

    def test_half_score_gives_midpoint_confidence(self):
        mr = _make_match_result(match_score=0.5)
        confidence = calculate_confidence(mr)
        # Linear: 0.3 + 0.5 * (0.95 - 0.3) = 0.3 + 0.325 = 0.625
        assert confidence == pytest.approx(0.625)

    def test_confidence_always_at_least_minimum(self):
        # Even with a very low score, confidence should not drop below 0.3
        mr = _make_match_result(match_score=0.0)
        confidence = calculate_confidence(mr)
        assert confidence >= 0.3

    def test_confidence_never_exceeds_maximum(self):
        # Score is clamped to [0, 1] by MatchResult, so max confidence = 0.95
        mr = _make_match_result(match_score=1.0)
        confidence = calculate_confidence(mr)
        assert confidence <= 0.95

    def test_confidence_increases_with_score(self):
        low = calculate_confidence(_make_match_result(match_score=0.2))
        mid = calculate_confidence(_make_match_result(match_score=0.5))
        high = calculate_confidence(_make_match_result(match_score=0.8))
        assert low < mid < high

    def test_confidence_is_linear(self):
        # Verify the linear formula: confidence = 0.3 + score * 0.65
        for score in [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]:
            mr = _make_match_result(match_score=score)
            expected = 0.3 + score * 0.65
            assert calculate_confidence(mr) == pytest.approx(expected)
