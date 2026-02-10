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


# =========================================================================
# News type classification tests
# =========================================================================


class TestNewsTypeClassification:
    """Tests for news type classifier (price_report / causal_event / mixed)."""

    def test_persian_daily_price_listing(self):
        from api.rule_engine.news_type import classify_news_type
        assert classify_news_type("قیمت طلا و سکه امروز ۲۱ بهمن ۱۴۰۴") == "price_report"

    def test_persian_price_reached(self):
        from api.rule_engine.news_type import classify_news_type
        assert classify_news_type("قیمت طلا به بالای ۵۰۰۰ دلار رسید") == "price_report"

    def test_english_gold_price_today(self):
        from api.rule_engine.news_type import classify_news_type
        assert classify_news_type("Gold price today update") == "price_report"

    def test_xau_usd_trading(self):
        from api.rule_engine.news_type import classify_news_type
        assert classify_news_type("XAU/USD at $2450 after steady trading") == "price_report"

    def test_persian_coin_price_listing(self):
        from api.rule_engine.news_type import classify_news_type
        assert classify_news_type("قیمت سکه امروز ۲۱ بهمن") == "price_report"

    def test_fed_rate_decision_is_causal(self):
        from api.rule_engine.news_type import classify_news_type
        assert classify_news_type("Fed cuts interest rates by 25 basis points") == "causal_event"

    def test_sanctions_is_causal(self):
        from api.rule_engine.news_type import classify_news_type
        assert classify_news_type("تحریم‌های جدید آمریکا علیه ایران") == "causal_event"

    def test_war_is_causal(self):
        from api.rule_engine.news_type import classify_news_type
        assert classify_news_type("جنگ در خاورمیانه تشدید شد") == "causal_event"

    def test_cpi_data_is_causal(self):
        from api.rule_engine.news_type import classify_news_type
        assert classify_news_type("CPI inflation data shows 3.5% increase") == "causal_event"

    def test_price_with_cause_is_mixed(self):
        from api.rule_engine.news_type import classify_news_type
        result = classify_news_type(
            "قیمت طلا به بالای ۵۰۰۰ دلار رسید",
            "طلا به دلیل تحریم‌های جدید آمریکا افزایش یافت",
        )
        assert result == "mixed"

    def test_gold_rises_due_to_fed_is_mixed(self):
        from api.rule_engine.news_type import classify_news_type
        result = classify_news_type(
            "Gold price today at $2500",
            "Gold climbed because of the Fed rate cut decision",
        )
        assert result == "mixed"

    def test_random_text_is_causal_default(self):
        from api.rule_engine.news_type import classify_news_type
        assert classify_news_type("some random news about markets") == "causal_event"

    def test_geopolitical_analysis_is_causal(self):
        from api.rule_engine.news_type import classify_news_type
        assert classify_news_type("تحلیل تنش ایران و آمریکا و تأثیر بر بازار طلا") == "causal_event"

    def test_price_report_score_override_in_builder(self):
        """Price reports should get score=50, severity=low, neutral direction."""
        from api.rule_engine.alert_builder import build_alert

        raw_item = {
            "title": "قیمت طلا و سکه امروز ۲۱ بهمن ۱۴۰۴",
            "content": "طلای ۱۸ عیار: ۵,۰۰۰,۰۰۰ تومان سکه امامی: ۱۵,۰۰۰,۰۰۰ تومان",
            "source_name": "khabarfarsi",
            "url": "http://example.com",
        }
        mr = _make_match_result(match_score=0.5)
        alert = build_alert(raw_item, [mr])

        assert alert["news_type"] == "price_report"
        assert alert["alert_score"] == 50
        assert alert["severity"] == "low"
        assert alert["direction"] == "neutral"

    def test_causal_event_gets_full_scoring(self):
        """Causal events should get normal direction/severity scoring."""
        from api.rule_engine.alert_builder import build_alert

        raw_item = {
            "title": "Fed cuts interest rates by 50 basis points",
            "content": "The Federal Reserve announced a surprise rate cut today",
            "source_name": "reuters",
            "url": "http://example.com",
        }
        mr = _make_match_result(match_score=0.5)
        alert = build_alert(raw_item, [mr])

        assert alert["news_type"] == "causal_event"
        # Causal events should NOT be forced to score 50
        assert alert["severity"] != "low" or alert["direction"] != "neutral"

    # --- Background context tests (Fix #9) ---

    def test_anniversary_is_background(self):
        from api.rule_engine.news_type import classify_news_type
        result = classify_news_type(
            "چهل و هفتمین سالگرد پیروزی انقلاب اسلامی و تأثیر بر بازار طلا",
            "ایران سالگرد انقلاب را در شرایط تحریم و تنش پشت سر می‌گذارد",
        )
        assert result == "background_context"

    def test_english_anniversary_is_background(self):
        from api.rule_engine.news_type import classify_news_type
        assert classify_news_type("47th anniversary of Islamic Revolution and its impact on gold") == "background_context"

    def test_commemoration_is_background(self):
        from api.rule_engine.news_type import classify_news_type
        assert classify_news_type("یادبود شهدای جنگ تحمیلی و وضعیت اقتصادی") == "background_context"

    def test_ceremony_is_background(self):
        from api.rule_engine.news_type import classify_news_type
        assert classify_news_type("مراسم بزرگداشت هفته دولت") == "background_context"

    def test_historical_review_is_background(self):
        from api.rule_engine.news_type import classify_news_type
        assert classify_news_type("تاریخچه بازار طلا در ایران") == "background_context"

    def test_look_at_review_is_background(self):
        from api.rule_engine.news_type import classify_news_type
        assert classify_news_type("نگاهی به روند تحولات بازار ارز") == "background_context"

    def test_editorial_is_background(self):
        from api.rule_engine.news_type import classify_news_type
        assert classify_news_type("Editorial: Gold market outlook for 2026") == "background_context"

    def test_anniversary_with_new_policy_is_NOT_background(self):
        """Anniversary + new event = causal (new event overrides)."""
        from api.rule_engine.news_type import classify_news_type
        result = classify_news_type(
            "سالگرد انقلاب: دولت سیاست ارزی جدید اعلام کرد",
            "رئیس بانک مرکزی اعلام کرد نرخ بهره کاهش داد",
        )
        assert result != "background_context"

    def test_anniversary_with_new_sanctions_is_NOT_background(self):
        """Anniversary + new sanctions announced = not background."""
        from api.rule_engine.news_type import classify_news_type
        result = classify_news_type(
            "سالگرد انقلاب: تحریم‌های جدید آمریکا اعمال شد",
        )
        assert result != "background_context"

    def test_background_content_heavy_status_quo(self):
        """Content with heavy status-quo language and no new event."""
        from api.rule_engine.news_type import classify_news_type
        result = classify_news_type(
            "وضعیت بازار طلا",
            "تحلیلگران معتقدند شرایط همچنان ادامه دارد و پیش‌بینی می‌شود تغییر چندانی رخ ندهد",
        )
        assert result == "background_context"

    def test_background_override_in_builder(self):
        """Background context should get score=50, severity=low, neutral."""
        from api.rule_engine.alert_builder import build_alert

        raw_item = {
            "title": "چهل و هفتمین سالگرد پیروزی انقلاب اسلامی و تأثیر بر بازار طلا",
            "content": "ایران سالگرد انقلاب را در شرایط تحریم و تنش پشت سر می‌گذارد",
            "source_name": "irna",
            "url": "http://example.com",
        }
        mr = _make_match_result(match_score=0.5)
        alert = build_alert(raw_item, [mr])

        assert alert["news_type"] == "background_context"
        assert alert["alert_score"] == 50
        assert alert["severity"] == "low"
        assert alert["direction"] == "neutral"
        assert alert["direction_method"] == "background_context"
