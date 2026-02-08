"""
Tests for api.rule_engine.matcher — normalize_text, keyword_match, signal_match,
match_rules, and MatchResult.
"""

import sys
from pathlib import Path

# Ensure the project root is on sys.path so that ``api.rule_engine`` is importable.
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pytest

from api.rule_engine.matcher import (
    MatchResult,
    keyword_match,
    match_rules,
    normalize_text,
    signal_match,
)
from api.rule_engine.load_rules import Rule


# ---------------------------------------------------------------------------
# Helpers — factory for Rule dataclass instances
# ---------------------------------------------------------------------------


def _make_rule(
    rule_id: str = "test_rule",
    section: str = "global_gold",
    title: str = "Test Rule",
    keywords: list[str] | None = None,
    signals: list[str] | None = None,
    importance_criteria: dict | None = None,
    impact_hypothesis: dict | None = None,
    horizon: str = "immediate",
) -> Rule:
    """Create a Rule with sensible defaults for testing."""
    return Rule(
        id=rule_id,
        section=section,
        title=title,
        what_it_is="test description",
        watch_for_keywords=keywords or [],
        watch_for_signals=signals or [],
        why_important="test importance",
        importance_criteria=importance_criteria
        or {"high_if": [], "medium_if": [], "low_if": []},
        impact_hypothesis=impact_hypothesis or {},
        horizon=horizon,
    )


# =========================================================================
# normalize_text
# =========================================================================


class TestNormalizeText:
    """Tests for Persian/Arabic text normalisation."""

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_plain_english_lowercased(self):
        assert normalize_text("Hello World") == "hello world"

    def test_arabic_yaa_converted_to_persian(self):
        # Arabic yaa U+064A should become Persian yaa U+06CC
        arabic_yaa = "\u064a"
        persian_yaa = "\u06cc"
        result = normalize_text(arabic_yaa)
        assert persian_yaa in result
        assert arabic_yaa not in result

    def test_arabic_kaf_converted_to_persian(self):
        # Arabic kaf U+0643 should become Persian kaf U+06A9
        arabic_kaf = "\u0643"
        persian_kaf = "\u06a9"
        result = normalize_text(arabic_kaf)
        assert persian_kaf in result
        assert arabic_kaf not in result

    def test_diacritics_stripped(self):
        # Arabic fatha (U+064E) on alef should be removed
        text_with_diacritics = "\u0627\u064e"  # alef + fatha
        result = normalize_text(text_with_diacritics)
        assert "\u064e" not in result
        assert "\u0627" in result

    def test_zwnj_replaced_with_space(self):
        # ZWNJ (U+200C) is commonly used in Persian; it should become a space
        text = "می\u200cشود"
        result = normalize_text(text)
        assert "\u200c" not in result
        # The ZWNJ should be replaced (collapsed into whitespace)
        assert "می شود" == result

    def test_invisible_characters_removed(self):
        # Zero-width joiner (U+200D), LRM (U+200E), RLM (U+200F), BOM (U+FEFF)
        text = "hello\u200d\u200e\u200f\ufeffworld"
        result = normalize_text(text)
        assert result == "helloworld"

    def test_whitespace_collapsed(self):
        text = "  foo   bar   baz  "
        result = normalize_text(text)
        assert result == "foo bar baz"

    def test_mixed_persian_arabic_normalisation(self):
        # A word with Arabic yaa and kaf should normalise identically to
        # the same word with Persian yaa and kaf.
        word_arabic = "\u0643\u062a\u0627\u0628\u064a"  # Arabic kaf + taa + alef + baa + Arabic yaa
        word_persian = "\u06a9\u062a\u0627\u0628\u06cc"  # Persian kaf + taa + alef + baa + Persian yaa
        assert normalize_text(word_arabic) == normalize_text(word_persian)

    def test_nfc_normalisation(self):
        # Precomposed vs decomposed forms should normalise to the same string
        # Example: e-acute as single char vs e + combining acute
        precomposed = "\u00e9"  # e-acute
        decomposed = "e\u0301"  # e + combining acute accent
        assert normalize_text(precomposed) == normalize_text(decomposed)

    def test_persian_sentence(self):
        text = "  افزایش  نرخ  بهره  "
        result = normalize_text(text)
        assert result == "افزایش نرخ بهره"


# =========================================================================
# keyword_match
# =========================================================================


class TestKeywordMatch:
    """Tests for keyword substring matching."""

    def test_empty_text_returns_empty(self):
        assert keyword_match("", ["foo"]) == []

    def test_empty_keywords_returns_empty(self):
        assert keyword_match("some text", []) == []

    def test_single_keyword_present(self):
        result = keyword_match("The Fed rate decision was announced", ["Fed rate"])
        assert result == ["Fed rate"]

    def test_single_keyword_absent(self):
        result = keyword_match("The weather is nice", ["Fed rate"])
        assert result == []

    def test_multiple_keywords_partial_match(self):
        text = "The FOMC decision included a rate cut today"
        keywords = ["rate cut", "FOMC decision", "rate hike", "ECB rate"]
        result = keyword_match(text, keywords)
        assert "rate cut" in result
        assert "FOMC decision" in result
        assert "rate hike" not in result
        assert "ECB rate" not in result

    def test_case_insensitive_matching(self):
        result = keyword_match("RATE HIKE announced", ["rate hike"])
        assert result == ["rate hike"]

    def test_duplicate_keywords_deduplicated(self):
        result = keyword_match("rate hike is coming", ["rate hike", "rate hike"])
        assert result == ["rate hike"]

    def test_persian_keyword_matching(self):
        text = "خبر افزایش نرخ بهره توسط بانک مرکزی"
        keywords = ["افزایش نرخ بهره", "کاهش نرخ بهره"]
        result = keyword_match(text, keywords)
        assert "افزایش نرخ بهره" in result
        assert "کاهش نرخ بهره" not in result

    def test_arabic_persian_cross_matching(self):
        # Text with Arabic yaa should match keyword with Persian yaa
        text_arabic_yaa = "بازار\u064a"  # Arabic yaa
        keyword_persian_yaa = "بازار\u06cc"  # Persian yaa
        result = keyword_match(text_arabic_yaa, [keyword_persian_yaa])
        assert len(result) == 1

    def test_empty_keyword_string_skipped(self):
        result = keyword_match("some text", ["", "some"])
        assert result == ["some"]

    def test_original_keyword_returned(self):
        # The original un-normalised keyword should be returned, not the normalised form
        keyword = "  Rate   Hike  "
        result = keyword_match("rate hike announced", [keyword])
        assert result == [keyword]


# =========================================================================
# signal_match
# =========================================================================


class TestSignalMatch:
    """Tests for signal substring matching."""

    def test_empty_text_returns_empty(self):
        assert signal_match("", ["some signal"]) == []

    def test_empty_signals_returns_empty(self):
        assert signal_match("some text", []) == []

    def test_signal_present_in_text(self):
        text = "گزارش افزایش نرخ بهره یا اشاره به افزایش‌های بیشتر در آینده"
        signals = ["افزایش نرخ بهره یا اشاره به افزایش‌های بیشتر"]
        result = signal_match(text, signals)
        assert len(result) == 1

    def test_signal_absent_from_text(self):
        text = "The weather is sunny"
        signals = ["افزایش نرخ بهره"]
        result = signal_match(text, signals)
        assert result == []

    def test_multiple_signals_partial_match(self):
        text = "تغییر لحن از سختگیرانه به نرم در بیانیه"
        signals = [
            "تغییر لحن از سختگیرانه به نرم یا برعکس",
            "اشاره به نگرانی رکود",
        ]
        # The first signal should NOT match because it has extra text ("یا برعکس")
        # that is not in the source. But "تغییر لحن از سختگیرانه به نرم" IS a
        # substring of the normalised text — let's verify behaviour.
        # Actually the signal is the haystack element; the normalised signal must
        # be a substring of the normalised text. The full signal "تغییر لحن از
        # سختگیرانه به نرم یا برعکس" is longer so it won't match the shorter text.
        result = signal_match(text, signals)
        assert "اشاره به نگرانی رکود" not in result

    def test_duplicate_signals_deduplicated(self):
        text = "جهش شدید DXY"
        signals = ["جهش", "جهش"]
        result = signal_match(text, signals)
        assert result == ["جهش"]

    def test_empty_signal_string_skipped(self):
        result = signal_match("some text here", ["", "some"])
        assert result == ["some"]


# =========================================================================
# MatchResult
# =========================================================================


class TestMatchResult:
    """Tests for the MatchResult dataclass."""

    def test_default_score_zero(self):
        rule = _make_rule()
        mr = MatchResult(rule=rule)
        assert mr.match_score == 0.0
        assert mr.matched_keywords == []
        assert mr.matched_signals == []

    def test_score_clamped_below_zero(self):
        rule = _make_rule()
        mr = MatchResult(rule=rule, match_score=-0.5)
        assert mr.match_score == 0.0

    def test_score_clamped_above_one(self):
        rule = _make_rule()
        mr = MatchResult(rule=rule, match_score=1.5)
        assert mr.match_score == 1.0

    def test_score_within_range_unchanged(self):
        rule = _make_rule()
        mr = MatchResult(rule=rule, match_score=0.75)
        assert mr.match_score == 0.75


# =========================================================================
# match_rules
# =========================================================================


class TestMatchRules:
    """Tests for match_rules — end-to-end matching against rules."""

    def test_no_rules_returns_empty(self):
        results = match_rules("some title", "some content", [])
        assert results == []

    def test_no_match_returns_empty(self):
        rule = _make_rule(keywords=["xyz_no_match"])
        results = match_rules("unrelated title", "unrelated content", [rule])
        assert results == []

    def test_keyword_match_produces_result(self):
        rule = _make_rule(
            rule_id="rate_rule",
            keywords=["rate hike", "FOMC"],
        )
        results = match_rules(
            "FOMC announces rate hike",
            "The FOMC decided to raise rates today.",
            [rule],
        )
        assert len(results) == 1
        assert results[0].rule.id == "rate_rule"
        assert "rate hike" in results[0].matched_keywords
        assert "FOMC" in results[0].matched_keywords

    def test_signal_match_produces_result(self):
        rule = _make_rule(
            rule_id="signal_rule",
            signals=["افزایش نرخ بهره"],
        )
        results = match_rules(
            "عنوان خبر",
            "بانک مرکزی افزایش نرخ بهره را اعلام کرد",
            [rule],
        )
        assert len(results) == 1
        assert "افزایش نرخ بهره" in results[0].matched_signals

    def test_combined_keyword_and_signal_match(self):
        rule = _make_rule(
            rule_id="combined_rule",
            keywords=["Fed rate"],
            signals=["افزایش نرخ بهره"],
        )
        results = match_rules(
            "Fed rate decision",
            "بانک مرکزی آمریکا افزایش نرخ بهره را اعلام کرد",
            [rule],
        )
        assert len(results) == 1
        assert results[0].matched_keywords == ["Fed rate"]
        assert results[0].matched_signals == ["افزایش نرخ بهره"]

    def test_results_sorted_by_score_descending(self):
        rule1 = _make_rule(
            rule_id="rule_a",
            keywords=["alpha", "beta", "gamma"],
        )
        rule2 = _make_rule(
            rule_id="rule_b",
            keywords=["alpha"],
        )
        # rule1 should have a higher score (more keywords match)
        results = match_rules(
            "alpha beta gamma",
            "",
            [rule2, rule1],  # intentionally reversed order
        )
        assert len(results) == 2
        assert results[0].rule.id == "rule_a"
        assert results[1].rule.id == "rule_b"
        assert results[0].match_score >= results[1].match_score

    def test_equal_score_sorted_by_rule_id(self):
        rule_b = _make_rule(rule_id="zzz_rule", keywords=["token"])
        rule_a = _make_rule(rule_id="aaa_rule", keywords=["token"])
        results = match_rules("token", "", [rule_b, rule_a])
        assert len(results) == 2
        # Same score, sorted alphabetically by rule id
        assert results[0].rule.id == "aaa_rule"
        assert results[1].rule.id == "zzz_rule"

    def test_match_score_computation_keyword_only(self):
        rule = _make_rule(
            rule_id="kw_only",
            keywords=["one", "two", "three", "four"],
        )
        results = match_rules("one two", "", [rule])
        assert len(results) == 1
        # 2 out of 4 keywords matched, no signals => score = 2/4 = 0.5
        assert results[0].match_score == pytest.approx(0.5)

    def test_match_score_computation_signal_only(self):
        rule = _make_rule(
            rule_id="sig_only",
            signals=["signal_a", "signal_b"],
        )
        results = match_rules("signal_a", "", [rule])
        assert len(results) == 1
        # 1 out of 2 signals matched, no keywords => score = 1/2 = 0.5
        assert results[0].match_score == pytest.approx(0.5)

    def test_match_score_computation_mixed(self):
        rule = _make_rule(
            rule_id="mixed",
            keywords=["kw_a", "kw_b"],
            signals=["sig_a", "sig_b"],
        )
        # All keywords and signals match
        results = match_rules("kw_a kw_b sig_a sig_b", "", [rule])
        assert len(results) == 1
        # score = 0.6*(2/2) + 0.4*(2/2) = 1.0
        assert results[0].match_score == pytest.approx(1.0)

    def test_multiple_rules_only_matching_returned(self):
        rule_match = _make_rule(rule_id="match_me", keywords=["alpha"])
        rule_no_match = _make_rule(rule_id="skip_me", keywords=["zzz_unique"])
        results = match_rules("alpha is here", "", [rule_match, rule_no_match])
        assert len(results) == 1
        assert results[0].rule.id == "match_me"

    def test_title_and_content_both_searched(self):
        rule = _make_rule(
            rule_id="both_fields",
            keywords=["title_keyword", "content_keyword"],
        )
        results = match_rules("title_keyword here", "content_keyword there", [rule])
        assert len(results) == 1
        assert "title_keyword" in results[0].matched_keywords
        assert "content_keyword" in results[0].matched_keywords
