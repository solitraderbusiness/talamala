"""
Tests for api.rule_engine.alert_builder — build_alert and generate_dedupe_key.
"""

import sys
from pathlib import Path

# Ensure the project root is on sys.path so that ``api.rule_engine`` is importable.
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pytest

from api.rule_engine.alert_builder import build_alert, generate_dedupe_key
from api.rule_engine.matcher import MatchResult
from api.rule_engine.load_rules import Rule


# ---------------------------------------------------------------------------
# Helpers
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
    why_important: str = "test importance",
) -> Rule:
    """Create a Rule with sensible defaults."""
    return Rule(
        id=rule_id,
        section=section,
        title=title,
        what_it_is="test description",
        watch_for_keywords=keywords or [],
        watch_for_signals=signals or [],
        why_important=why_important,
        importance_criteria=importance_criteria
        or {"high_if": [], "medium_if": [], "low_if": []},
        impact_hypothesis=impact_hypothesis or {},
        horizon=horizon,
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
# generate_dedupe_key
# =========================================================================


class TestGenerateDedupeKey:
    """Tests for deterministic dedupe key generation."""

    def test_returns_64_char_hex_string(self):
        key = generate_dedupe_key(["rule1"], "title", "source")
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_deterministic_same_inputs_same_key(self):
        key1 = generate_dedupe_key(["rule1", "rule2"], "title", "source")
        key2 = generate_dedupe_key(["rule1", "rule2"], "title", "source")
        assert key1 == key2

    def test_different_rules_different_key(self):
        key1 = generate_dedupe_key(["rule1"], "title", "source")
        key2 = generate_dedupe_key(["rule2"], "title", "source")
        assert key1 != key2

    def test_different_title_different_key(self):
        key1 = generate_dedupe_key(["rule1"], "title_a", "source")
        key2 = generate_dedupe_key(["rule1"], "title_b", "source")
        assert key1 != key2

    def test_same_title_different_source_same_key(self):
        # Cross-source dedup: same title + same rules = same key regardless of source
        key1 = generate_dedupe_key(["rule1"], "title", "source_a")
        key2 = generate_dedupe_key(["rule1"], "title", "source_b")
        assert key1 == key2

    def test_rule_order_does_not_matter(self):
        # Rules are sorted internally, so order should not affect the key
        key1 = generate_dedupe_key(["rule_b", "rule_a"], "title", "source")
        key2 = generate_dedupe_key(["rule_a", "rule_b"], "title", "source")
        assert key1 == key2

    def test_title_normalisation_applied(self):
        # Titles with different whitespace / case should produce the same key
        key1 = generate_dedupe_key(["r1"], "  Hello  World  ", "src")
        key2 = generate_dedupe_key(["r1"], "hello world", "src")
        assert key1 == key2

    def test_persian_normalisation_in_title(self):
        # Arabic yaa vs Persian yaa should normalise to the same key
        key1 = generate_dedupe_key(["r1"], "خبر\u064a", "src")  # Arabic yaa
        key2 = generate_dedupe_key(["r1"], "خبر\u06cc", "src")  # Persian yaa
        assert key1 == key2

    def test_source_normalisation_applied(self):
        key1 = generate_dedupe_key(["r1"], "title", "  BBC  News  ")
        key2 = generate_dedupe_key(["r1"], "title", "bbc news")
        assert key1 == key2

    def test_empty_rule_ids(self):
        # Should still produce a valid hash
        key = generate_dedupe_key([], "title", "source")
        assert len(key) == 64


# =========================================================================
# build_alert
# =========================================================================


class TestBuildAlert:
    """Tests for building complete alert dicts."""

    def test_raises_on_empty_match_results(self):
        with pytest.raises(ValueError, match="must not be empty"):
            build_alert({"title": "x", "content": "y"}, [])

    def test_basic_alert_structure(self):
        rule = _make_rule(rule_id="rule_1", horizon="short")
        mr = _make_match_result(
            rule=rule,
            match_score=0.8,
            matched_keywords=["kw1"],
        )
        raw_item = {
            "title": "Test Title",
            "content": "Test content body",
            "source": "Test Source",
            "url": "https://example.com/article",
        }
        alert = build_alert(raw_item, [mr])

        # Verify all required keys are present
        required_keys = {
            "title",
            "timestamp_utc",
            "source_name",
            "source_url",
            "matched_rule_ids",
            "summary_fa",
            "why_important_fa",
            "expected_impact",
            "severity",
            "time_horizon",
            "confidence",
            "follow_up_questions",
            "dedupe_key",
            "match_evidence",
        }
        assert required_keys.issubset(set(alert.keys()))

    def test_title_from_raw_item(self):
        rule = _make_rule()
        mr = _make_match_result(rule=rule)
        alert = build_alert({"title": "My Title", "content": ""}, [mr])
        assert alert["title"] == "My Title"

    def test_source_name_from_source_key(self):
        rule = _make_rule()
        mr = _make_match_result(rule=rule)
        alert = build_alert(
            {"title": "", "content": "", "source": "Reuters"},
            [mr],
        )
        assert alert["source_name"] == "Reuters"

    def test_source_name_from_source_name_key(self):
        rule = _make_rule()
        mr = _make_match_result(rule=rule)
        alert = build_alert(
            {"title": "", "content": "", "source_name": "Bloomberg"},
            [mr],
        )
        assert alert["source_name"] == "Bloomberg"

    def test_source_url_from_url_key(self):
        rule = _make_rule()
        mr = _make_match_result(rule=rule)
        alert = build_alert(
            {"title": "", "content": "", "url": "https://example.com"},
            [mr],
        )
        assert alert["source_url"] == "https://example.com"

    def test_source_url_from_source_url_key(self):
        rule = _make_rule()
        mr = _make_match_result(rule=rule)
        alert = build_alert(
            {"title": "", "content": "", "source_url": "https://test.com"},
            [mr],
        )
        assert alert["source_url"] == "https://test.com"

    def test_matched_rule_ids(self):
        rule1 = _make_rule(rule_id="r1")
        rule2 = _make_rule(rule_id="r2")
        mr1 = _make_match_result(rule=rule1)
        mr2 = _make_match_result(rule=rule2)
        alert = build_alert({"title": "", "content": ""}, [mr1, mr2])
        assert alert["matched_rule_ids"] == ["r1", "r2"]

    def test_timestamp_utc_is_iso_format(self):
        rule = _make_rule()
        mr = _make_match_result(rule=rule)
        alert = build_alert({"title": "", "content": ""}, [mr])
        ts = alert["timestamp_utc"]
        # Should be a valid ISO-8601 string containing 'T' and timezone info
        assert "T" in ts

    def test_severity_defaults_to_medium_when_no_criteria(self):
        rule = _make_rule()
        mr = _make_match_result(rule=rule)
        alert = build_alert({"title": "", "content": ""}, [mr])
        assert alert["severity"] == "medium"

    def test_severity_high_when_content_matches_high_criteria(self):
        rule = _make_rule(
            importance_criteria={
                "high_if": ["critical event"],
                "medium_if": [],
                "low_if": [],
            }
        )
        mr = _make_match_result(rule=rule)
        alert = build_alert(
            {"title": "", "content": "This is a critical event in the market"},
            [mr],
        )
        assert alert["severity"] == "high"

    def test_highest_severity_wins_across_rules(self):
        rule_high = _make_rule(
            rule_id="high_rule",
            importance_criteria={
                "high_if": ["critical"],
                "medium_if": [],
                "low_if": [],
            },
        )
        rule_low = _make_rule(
            rule_id="low_rule",
            importance_criteria={
                "high_if": [],
                "medium_if": [],
                "low_if": ["minor"],
            },
        )
        mr_high = _make_match_result(rule=rule_high)
        mr_low = _make_match_result(rule=rule_low)
        alert = build_alert(
            {"title": "", "content": "This is critical and also minor news"},
            [mr_high, mr_low],
        )
        assert alert["severity"] == "high"

    def test_time_horizon_from_highest_severity_rule(self):
        rule_high = _make_rule(
            rule_id="high_rule",
            horizon="immediate",
            importance_criteria={
                "high_if": ["critical"],
                "medium_if": [],
                "low_if": [],
            },
        )
        rule_low = _make_rule(
            rule_id="low_rule",
            horizon="long",
            importance_criteria={
                "high_if": [],
                "medium_if": [],
                "low_if": ["minor"],
            },
        )
        mr_high = _make_match_result(rule=rule_high, match_score=0.9)
        mr_low = _make_match_result(rule=rule_low, match_score=0.3)
        alert = build_alert(
            {"title": "", "content": "critical and minor event"},
            [mr_high, mr_low],
        )
        assert alert["time_horizon"] == "immediate"

    def test_confidence_in_valid_range(self):
        rule = _make_rule()
        mr = _make_match_result(rule=rule, match_score=0.6)
        alert = build_alert({"title": "", "content": ""}, [mr])
        assert 0.3 <= alert["confidence"] <= 0.95

    def test_confidence_average_of_multiple_results(self):
        rule1 = _make_rule(rule_id="r1")
        rule2 = _make_rule(rule_id="r2")
        mr1 = _make_match_result(rule=rule1, match_score=0.0)  # confidence = 0.3
        mr2 = _make_match_result(rule=rule2, match_score=1.0)  # confidence = 0.95
        alert = build_alert({"title": "", "content": ""}, [mr1, mr2])
        # Average of 0.3 and 0.95 = 0.625
        assert alert["confidence"] == pytest.approx(0.625)

    def test_summary_fa_from_llm_output(self):
        rule = _make_rule()
        mr = _make_match_result(rule=rule)
        llm = {"summary_fa": "خلاصه توسط هوش مصنوعی"}
        alert = build_alert({"title": "", "content": ""}, [mr], llm_output=llm)
        assert alert["summary_fa"] == "خلاصه توسط هوش مصنوعی"

    def test_summary_fa_fallback_to_truncated_content(self):
        rule = _make_rule()
        mr = _make_match_result(rule=rule)
        content = "A" * 300
        alert = build_alert({"title": "", "content": content}, [mr])
        # Should be truncated to 200 chars (197 + "...")
        assert len(alert["summary_fa"]) == 200
        assert alert["summary_fa"].endswith("...")

    def test_summary_fa_short_content_not_truncated(self):
        rule = _make_rule()
        mr = _make_match_result(rule=rule)
        content = "Short content"
        alert = build_alert({"title": "", "content": content}, [mr])
        assert alert["summary_fa"] == content

    def test_why_important_fa_from_llm(self):
        rule = _make_rule(why_important="rule explanation")
        mr = _make_match_result(rule=rule)
        llm = {"why_important_fa": "LLM explanation"}
        alert = build_alert({"title": "", "content": ""}, [mr], llm_output=llm)
        assert alert["why_important_fa"] == "LLM explanation"

    def test_why_important_fa_fallback_to_rule(self):
        rule = _make_rule(why_important="rule explanation")
        mr = _make_match_result(rule=rule)
        alert = build_alert({"title": "", "content": ""}, [mr])
        assert alert["why_important_fa"] == "rule explanation"

    def test_follow_up_questions_from_llm(self):
        rule = _make_rule()
        mr = _make_match_result(rule=rule)
        llm = {"follow_up_questions": ["Question 1?", "Question 2?"]}
        alert = build_alert({"title": "", "content": ""}, [mr], llm_output=llm)
        assert alert["follow_up_questions"] == ["Question 1?", "Question 2?"]

    def test_follow_up_questions_default_empty(self):
        rule = _make_rule()
        mr = _make_match_result(rule=rule)
        alert = build_alert({"title": "", "content": ""}, [mr])
        assert alert["follow_up_questions"] == []

    def test_dedupe_key_present_and_deterministic(self):
        rule = _make_rule(rule_id="r1")
        mr = _make_match_result(rule=rule)
        raw = {"title": "Test", "content": "", "source": "Src"}
        alert1 = build_alert(raw, [mr])
        alert2 = build_alert(raw, [mr])
        assert len(alert1["dedupe_key"]) == 64
        assert alert1["dedupe_key"] == alert2["dedupe_key"]

    def test_match_evidence_structure(self):
        rule = _make_rule(rule_id="r1")
        mr = _make_match_result(
            rule=rule,
            matched_keywords=["kw1", "kw2"],
            matched_signals=["sig1"],
        )
        alert = build_alert({"title": "", "content": ""}, [mr])
        evidence = alert["match_evidence"]
        assert "r1" in evidence
        assert evidence["r1"]["keywords"] == ["kw1", "kw2"]
        assert evidence["r1"]["signals"] == ["sig1"]

    def test_match_evidence_multiple_rules(self):
        rule1 = _make_rule(rule_id="r1")
        rule2 = _make_rule(rule_id="r2")
        mr1 = _make_match_result(rule=rule1, matched_keywords=["a"])
        mr2 = _make_match_result(rule=rule2, matched_signals=["b"])
        alert = build_alert({"title": "", "content": ""}, [mr1, mr2])
        assert "r1" in alert["match_evidence"]
        assert "r2" in alert["match_evidence"]

    def test_expected_impact_with_asset_key(self):
        rule = _make_rule(
            impact_hypothesis={
                "asset": "global_gold",
                "direction": "bullish",
                "mechanism": "safe haven",
            }
        )
        mr = _make_match_result(rule=rule)
        alert = build_alert({"title": "", "content": ""}, [mr])
        impacts = alert["expected_impact"]
        assert len(impacts) >= 1
        assert impacts[0]["asset"] == "global_gold"
        assert impacts[0]["direction"] == "bullish"
        assert impacts[0]["mechanism"] == "safe haven"

    def test_expected_impact_with_impacts_list(self):
        rule = _make_rule(
            impact_hypothesis={
                "impacts": [
                    {"asset": "gold", "direction": "up", "mechanism": "reason1"},
                    {"asset": "coin", "direction": "down", "mechanism": "reason2"},
                ]
            }
        )
        mr = _make_match_result(rule=rule)
        alert = build_alert({"title": "", "content": ""}, [mr])
        assert len(alert["expected_impact"]) == 2

    def test_expected_impact_deduplication(self):
        rule1 = _make_rule(
            rule_id="r1",
            impact_hypothesis={
                "asset": "gold",
                "direction": "up",
                "mechanism": "reason",
            },
        )
        rule2 = _make_rule(
            rule_id="r2",
            impact_hypothesis={
                "asset": "gold",
                "direction": "up",
                "mechanism": "reason",
            },
        )
        mr1 = _make_match_result(rule=rule1)
        mr2 = _make_match_result(rule=rule2)
        alert = build_alert({"title": "", "content": ""}, [mr1, mr2])
        # Same impact from two rules should be deduplicated
        assert len(alert["expected_impact"]) == 1

    def test_expected_impact_empty_hypothesis(self):
        rule = _make_rule(impact_hypothesis={})
        mr = _make_match_result(rule=rule)
        alert = build_alert({"title": "", "content": ""}, [mr])
        assert alert["expected_impact"] == []

    def test_no_llm_output(self):
        rule = _make_rule(why_important="fallback text")
        mr = _make_match_result(rule=rule)
        alert = build_alert({"title": "", "content": "some content"}, [mr])
        assert alert["why_important_fa"] == "fallback text"
        assert alert["follow_up_questions"] == []

    def test_missing_raw_item_keys_default_to_empty(self):
        rule = _make_rule()
        mr = _make_match_result(rule=rule)
        alert = build_alert({}, [mr])
        assert alert["title"] == ""
        assert alert["source_name"] == ""
        assert alert["source_url"] == ""
