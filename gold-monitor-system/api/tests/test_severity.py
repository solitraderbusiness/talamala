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
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    calculate_confidence,
    classify_severity,
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


# =========================================================================
# classify_severity (event-type regex classification)
# =========================================================================


class TestClassifySeverity:
    """Tests for regex-based event-type classification."""

    def test_war_is_critical(self):
        assert classify_severity("جنگ در منطقه") == "critical"

    def test_fed_rate_decision_is_critical(self):
        assert classify_severity("Fed rate decision today") == "critical"

    def test_nuclear_negotiations_is_critical(self):
        assert classify_severity("مذاکرات هسته ای برجام") == "critical"

    def test_all_time_high_is_critical(self):
        assert classify_severity("Gold hits all-time high") == "critical"

    def test_crash_is_critical(self):
        assert classify_severity("Market crash continues") == "critical"

    def test_cpi_is_high(self):
        assert classify_severity("CPI inflation data released") == "high"

    def test_gold_above_price_is_high(self):
        assert classify_severity("Gold above 3000 mark") == "high"

    def test_iran_tension_is_high(self):
        assert classify_severity("تنش ایران و آمریکا") == "high"

    def test_analysis_is_medium(self):
        assert classify_severity("تحلیل بازار طلا") == "medium"

    def test_survey_is_low(self):
        assert classify_severity("نظرسنجی بازار") == "low"

    def test_no_match_returns_none(self):
        assert classify_severity("random unrelated text") is None

    def test_event_classification_priority_over_score(self):
        # War in title → critical, even with low match score
        rule = _make_rule(horizon="short")
        result = determine_severity(
            "some content", rule, match_score=0.12, title="جنگ در منطقه"
        )
        assert result == "critical"


# =========================================================================
# Direction detection tests
# =========================================================================


class TestDirectionDetection:
    """Tests for the 3-stage direction detection module."""

    def test_bullish_regex_detection(self):
        from api.rule_engine.direction import detect_direction
        result = detect_direction("قیمت طلا افزایش یافت", "")
        assert result["direction"] == "bullish"
        assert result["confidence"] >= 0.5

    def test_bearish_regex_detection(self):
        from api.rule_engine.direction import detect_direction
        result = detect_direction("Gold price drops sharply", "gold falls below 2000")
        assert result["direction"] == "bearish"

    def test_neutral_fallback(self):
        from api.rule_engine.direction import detect_direction
        result = detect_direction("random unrelated text", "")
        assert result["direction"] == "neutral"

    def test_alert_score_neutral_is_50(self):
        from api.rule_engine.direction import calculate_alert_score
        assert calculate_alert_score("neutral", 0.0, "high") == 50

    def test_alert_score_bullish_above_50(self):
        from api.rule_engine.direction import calculate_alert_score
        score = calculate_alert_score("bullish", 0.7, "high")
        assert score > 50

    def test_alert_score_bearish_below_50(self):
        from api.rule_engine.direction import calculate_alert_score
        score = calculate_alert_score("bearish", 0.7, "high")
        assert score < 50

    def test_alert_score_clamped_0_100(self):
        from api.rule_engine.direction import calculate_alert_score
        score = calculate_alert_score("bullish", 1.0, "critical")
        assert 0 <= score <= 100
        score = calculate_alert_score("bearish", 1.0, "critical")
        assert 0 <= score <= 100


# =========================================================================
# Enriched alert score tests
# =========================================================================


class TestAlertScoreEnriched:
    """Tests for calculate_alert_score with enrichment parameters."""

    def test_default_params_match_old_formula(self):
        """With all defaults (zeros), output is identical to the old formula."""
        from api.rule_engine.direction import calculate_alert_score

        # Bullish, high confidence, critical severity
        old = 50 + 1 * (15 + (0.85 - 0.3) * (30 / 0.7)) * 1.0
        new = calculate_alert_score("bullish", 0.85, "critical")
        assert new == round(old)

        # Bearish, medium confidence, high severity
        old_b = 50 + (-1) * (15 + (0.7 - 0.3) * (30 / 0.7)) * 0.8
        new_b = calculate_alert_score("bearish", 0.7, "high")
        assert new_b == round(old_b)

    def test_higher_match_score_increases_score(self):
        from api.rule_engine.direction import calculate_alert_score
        low = calculate_alert_score("bullish", 0.7, "high", match_score=0.2)
        high = calculate_alert_score("bullish", 0.7, "high", match_score=0.9)
        assert high > low

    def test_more_rules_increases_score(self):
        from api.rule_engine.direction import calculate_alert_score
        one = calculate_alert_score("bullish", 0.7, "high", num_rules_matched=1)
        three = calculate_alert_score("bullish", 0.7, "high", num_rules_matched=3)
        assert three > one

    def test_more_keywords_signals_increases_score(self):
        from api.rule_engine.direction import calculate_alert_score
        few = calculate_alert_score("bullish", 0.7, "high", num_keywords_matched=1)
        many = calculate_alert_score("bullish", 0.7, "high", num_keywords_matched=6, num_signals_matched=2)
        assert many > few

    def test_regex_method_better_than_fallback(self):
        from api.rule_engine.direction import calculate_alert_score
        regex = calculate_alert_score("bullish", 0.7, "high", direction_method="regex")
        fallback = calculate_alert_score("bullish", 0.7, "high", direction_method="fallback")
        assert regex > fallback

    def test_longer_content_increases_score(self):
        from api.rule_engine.direction import calculate_alert_score
        short = calculate_alert_score("bullish", 0.7, "high", content_length=50)
        long = calculate_alert_score("bullish", 0.7, "high", content_length=600)
        assert long > short

    def test_rule_cap_at_4(self):
        """Multi-rule bonus caps at 3 extra rules (4 total)."""
        from api.rule_engine.direction import calculate_alert_score
        at_cap = calculate_alert_score("bullish", 0.7, "high", num_rules_matched=4)
        over_cap = calculate_alert_score("bullish", 0.7, "high", num_rules_matched=10)
        assert at_cap == over_cap

    def test_evidence_cap_at_8(self):
        """Evidence depth bonus caps at 8 total keywords+signals."""
        from api.rule_engine.direction import calculate_alert_score
        at_cap = calculate_alert_score("bullish", 0.7, "high", num_keywords_matched=5, num_signals_matched=3)
        over_cap = calculate_alert_score("bullish", 0.7, "high", num_keywords_matched=10, num_signals_matched=5)
        assert at_cap == over_cap

    def test_content_bonus_caps_at_500(self):
        """Content bonus caps at 500 chars."""
        from api.rule_engine.direction import calculate_alert_score
        at_cap = calculate_alert_score("bullish", 0.7, "high", content_length=500)
        over_cap = calculate_alert_score("bullish", 0.7, "high", content_length=2000)
        assert at_cap == over_cap

    def test_bearish_enrichment_lowers_score_further(self):
        """Enrichment on bearish alerts pushes score further below 50."""
        from api.rule_engine.direction import calculate_alert_score
        base = calculate_alert_score("bearish", 0.7, "high")
        enriched = calculate_alert_score(
            "bearish", 0.7, "high",
            match_score=0.8, num_rules_matched=3, num_keywords_matched=5,
            direction_method="regex", content_length=600,
        )
        assert enriched < base

    def test_neutral_ignores_enrichment(self):
        """Neutral direction always returns 50 regardless of enrichment."""
        from api.rule_engine.direction import calculate_alert_score
        score = calculate_alert_score(
            "neutral", 0.9, "critical",
            match_score=1.0, num_rules_matched=5, num_keywords_matched=10,
            direction_method="regex", content_length=1000,
        )
        assert score == 50

    def test_meaningful_spread_between_weak_and_strong(self):
        """Weak vs strong evidence should differ by at least 10 points."""
        from api.rule_engine.direction import calculate_alert_score
        weak = calculate_alert_score(
            "bullish", 0.7, "high",
            match_score=0.2, num_rules_matched=1, num_keywords_matched=1,
            direction_method="fallback", content_length=50,
        )
        strong = calculate_alert_score(
            "bullish", 0.7, "high",
            match_score=0.9, num_rules_matched=4, num_keywords_matched=6,
            num_signals_matched=2, direction_method="regex", content_length=600,
        )
        assert strong - weak >= 10

    def test_enriched_scores_clamped_0_100(self):
        """Even with maximum enrichment, scores stay in 0-100."""
        from api.rule_engine.direction import calculate_alert_score
        bull = calculate_alert_score(
            "bullish", 1.0, "critical",
            match_score=1.0, num_rules_matched=10, num_keywords_matched=20,
            num_signals_matched=10, direction_method="regex", content_length=5000,
        )
        assert 0 <= bull <= 100
        bear = calculate_alert_score(
            "bearish", 1.0, "critical",
            match_score=1.0, num_rules_matched=10, num_keywords_matched=20,
            num_signals_matched=10, direction_method="regex", content_length=5000,
        )
        assert 0 <= bear <= 100


# =========================================================================
# Event fingerprint tests
# =========================================================================


class TestEventFingerprint:
    """Tests for semantic event fingerprinting."""

    def test_same_event_different_titles(self):
        from api.worker.dedup import extract_event_fingerprint
        fp1 = extract_event_fingerprint("قیمت طلا به بالای ۵۰۰۰ دلار رسید")
        fp2 = extract_event_fingerprint("طلا بالای ۵۰۰۰ دلار بازگشت")
        # Both should extract gold + dollar + 5000
        assert fp1 == fp2

    def test_different_events_different_fingerprints(self):
        from api.worker.dedup import extract_event_fingerprint
        fp1 = extract_event_fingerprint("Gold above 5000 dollars")
        fp2 = extract_event_fingerprint("Fed rate cut decision")
        assert fp1 != fp2

    def test_empty_text_returns_empty(self):
        from api.worker.dedup import extract_event_fingerprint
        assert extract_event_fingerprint("") == ""

    def test_fingerprint_is_sorted(self):
        from api.worker.dedup import extract_event_fingerprint
        fp = extract_event_fingerprint("Gold and silver prices")
        # Should be alphabetically sorted
        parts = fp.split("|")
        assert parts == sorted(parts)
