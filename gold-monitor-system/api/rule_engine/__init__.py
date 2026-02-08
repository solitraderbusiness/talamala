"""
rule_engine — Deterministic rule matching for the Gold Monitor System.

This package matches incoming news items against rules defined in a YAML
file.  Severity and importance are decided entirely by substring matching
against rule criteria — **no LLM is involved** in the classification step.

Submodules
----------
load_rules
    Load and parse the YAML rule file into typed dataclass objects.
matcher
    Normalise text and match news items against rules by keyword / signal.
severity
    Deterministic severity assessment and confidence scoring.
alert_builder
    Assemble structured alert dicts from match results.

Quick-start
-----------
>>> from rule_engine import load_rules, get_rules, match_rules, build_alert
>>> yaml_data = load_rules("/path/to/rules.yaml")
>>> rules = get_rules(yaml_data)
>>> matches = match_rules(title, content, rules)
>>> alert = build_alert(raw_item, matches)
"""

from __future__ import annotations

# -- load_rules ------------------------------------------------------------
from api.rule_engine.load_rules import (
    Rule,
    TechnicalSignal,
    get_alert_template,
    get_rules,
    get_technical_signals,
    load_rules,
    reload_rules,
)

# -- matcher ---------------------------------------------------------------
from api.rule_engine.matcher import (
    MatchResult,
    keyword_match,
    match_rules,
    normalize_text,
    signal_match,
)

# -- severity --------------------------------------------------------------
from api.rule_engine.severity import (
    calculate_confidence,
    determine_severity,
)

# -- alert_builder ---------------------------------------------------------
from api.rule_engine.alert_builder import (
    build_alert,
    generate_dedupe_key,
)

__all__ = [
    # Dataclasses
    "Rule",
    "TechnicalSignal",
    "MatchResult",
    # load_rules
    "load_rules",
    "reload_rules",
    "get_rules",
    "get_technical_signals",
    "get_alert_template",
    # matcher
    "normalize_text",
    "keyword_match",
    "signal_match",
    "match_rules",
    # severity
    "determine_severity",
    "calculate_confidence",
    # alert_builder
    "build_alert",
    "generate_dedupe_key",
]
