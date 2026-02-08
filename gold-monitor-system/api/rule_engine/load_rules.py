"""
Rule loader — reads the gold-monitor YAML rule file and converts it to typed
dataclass objects.

The YAML is loaded once and cached at module level.  Call ``reload_rules()``
to force a re-read (e.g. after a hot-reload of the YAML file on disk).

All public helpers are pure functions that accept already-parsed YAML dicts,
so they are trivially testable without touching the filesystem.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Rule:
    """A single monitoring rule extracted from the YAML specification."""

    id: str
    section: str  # global_gold | iran_gold | coin | gold_funds
    title: str
    what_it_is: str
    watch_for_keywords: list[str]
    watch_for_signals: list[str]
    why_important: str
    importance_criteria: dict[str, list[str]]  # {high_if, medium_if, low_if}
    impact_hypothesis: dict[str, Any]
    horizon: str  # immediate | short | medium | long


@dataclass(frozen=True, slots=True)
class TechnicalSignal:
    """A technical / market signal definition from the YAML."""

    id: str
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()
_cached_yaml: dict[str, Any] | None = None
_cached_path: str | None = None
_cached_rules: list[Rule] | None = None
_cached_signals: list[TechnicalSignal] | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_rules(yaml_path: str) -> dict[str, Any]:
    """Load the full YAML file from *yaml_path* and return the parsed dict.

    Results are cached at module level.  Subsequent calls with the same path
    return the cached copy.  Use :func:`reload_rules` to invalidate the cache.

    Parameters
    ----------
    yaml_path:
        Absolute or relative path to the YAML rule file.

    Returns
    -------
    dict
        The raw parsed YAML data.

    Raises
    ------
    FileNotFoundError
        If *yaml_path* does not exist.
    yaml.YAMLError
        If the file contains invalid YAML.
    """
    global _cached_yaml, _cached_path  # noqa: PLW0603

    with _cache_lock:
        if _cached_yaml is not None and _cached_path == yaml_path:
            return _cached_yaml

    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Rule YAML not found: {yaml_path}")

    with open(path, encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)

    if not isinstance(data, dict):
        raise ValueError(f"Expected top-level YAML dict, got {type(data).__name__}")

    with _cache_lock:
        _cached_yaml = data
        _cached_path = yaml_path

    logger.info("Loaded rule YAML from %s", yaml_path)
    return data


def reload_rules(yaml_path: str) -> dict[str, Any]:
    """Force-reload the YAML file, bypassing the cache.

    This invalidates the cached rules and technical signals too.
    """
    global _cached_yaml, _cached_path, _cached_rules, _cached_signals  # noqa: PLW0603

    with _cache_lock:
        _cached_yaml = None
        _cached_path = None
        _cached_rules = None
        _cached_signals = None

    return load_rules(yaml_path)


def get_rules(yaml_data: dict[str, Any]) -> list[Rule]:
    """Extract all rules from every section of the parsed YAML.

    Parameters
    ----------
    yaml_data:
        The dict returned by :func:`load_rules`.

    Returns
    -------
    list[Rule]
        Ordered list of :class:`Rule` objects.
    """
    global _cached_rules  # noqa: PLW0603

    with _cache_lock:
        if _cached_rules is not None:
            return list(_cached_rules)

    rules: list[Rule] = []

    # The YAML may contain ``rules`` as either:
    #   A) A flat list of rule dicts (each with its own ``section`` key), or
    #   B) A dict of section dicts, each containing a ``rules`` list.
    # We support both layouts.
    sections_container = yaml_data.get("rules", yaml_data)

    if isinstance(sections_container, list):
        # Layout A: flat list of rule dicts
        for item in sections_container:
            if not isinstance(item, dict):
                continue
            section = str(item.get("section", "unknown"))
            rule = _dict_to_rule(item, section=section)
            if rule is not None:
                rules.append(rule)
    elif isinstance(sections_container, dict):
        # Layout B: dict of section dicts
        for section_key, section_body in sections_container.items():
            if section_key in ("alert_template", "technical_signals", "meta", "version"):
                continue

            if not isinstance(section_body, dict):
                continue

            # Each section may have a ``rules`` list or the items directly.
            rule_list = section_body.get("rules", [])
            if isinstance(section_body, dict) and not rule_list:
                rule_list = _extract_rule_dicts(section_body)

            for item in rule_list:
                if not isinstance(item, dict):
                    continue
                rule = _dict_to_rule(item, section=section_key)
                if rule is not None:
                    rules.append(rule)

    with _cache_lock:
        _cached_rules = list(rules)

    logger.info("Parsed %d rules from YAML data", len(rules))
    return rules


def get_technical_signals(yaml_data: dict[str, Any]) -> list[TechnicalSignal]:
    """Extract technical signal definitions from the parsed YAML.

    Parameters
    ----------
    yaml_data:
        The dict returned by :func:`load_rules`.

    Returns
    -------
    list[TechnicalSignal]
    """
    global _cached_signals  # noqa: PLW0603

    with _cache_lock:
        if _cached_signals is not None:
            return list(_cached_signals)

    signals: list[TechnicalSignal] = []
    raw_signals = yaml_data.get("technical_signals", [])

    if isinstance(raw_signals, list):
        for idx, item in enumerate(raw_signals):
            if not isinstance(item, dict):
                continue
            sig = TechnicalSignal(
                id=str(item.get("id", f"signal_{idx}")),
                name=str(item.get("name", "")),
                description=str(item.get("description", "")),
                parameters=item.get("parameters", {}),
            )
            signals.append(sig)
    elif isinstance(raw_signals, dict):
        for key, val in raw_signals.items():
            if not isinstance(val, dict):
                continue
            sig = TechnicalSignal(
                id=str(val.get("id", key)),
                name=str(val.get("name", key)),
                description=str(val.get("description", "")),
                parameters=val.get("parameters", {}),
            )
            signals.append(sig)

    with _cache_lock:
        _cached_signals = list(signals)

    logger.info("Parsed %d technical signals from YAML data", len(signals))
    return signals


def get_alert_template(yaml_data: dict[str, Any]) -> dict[str, Any]:
    """Return the ``alert_template`` section of the YAML as a plain dict.

    If the section is missing an empty dict is returned.

    Parameters
    ----------
    yaml_data:
        The dict returned by :func:`load_rules`.
    """
    template = yaml_data.get("alert_template", {})
    if not isinstance(template, dict):
        return {}
    return dict(template)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_rule_dicts(section_body: dict[str, Any]) -> list[dict[str, Any]]:
    """Attempt to pull rule dicts from a section when there is no ``rules`` key.

    Handles the case where the YAML section directly contains numbered /
    keyed rule entries.
    """
    results: list[dict[str, Any]] = []
    for _key, val in section_body.items():
        if isinstance(val, dict) and ("title" in val or "watch_for_keywords" in val):
            results.append(val)
    return results


def _safe_list(value: Any) -> list[str]:
    """Coerce *value* to a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _safe_dict(value: Any) -> dict[str, Any]:
    """Coerce *value* to a dict."""
    if isinstance(value, dict):
        return dict(value)
    return {}


def _dict_to_rule(raw: dict[str, Any], *, section: str) -> Rule | None:
    """Convert a raw YAML dict to a :class:`Rule`.

    Returns ``None`` if the dict cannot be interpreted as a valid rule (e.g.
    missing mandatory fields).
    """
    rule_id = raw.get("id")
    if rule_id is None:
        # Try deriving an id from title
        title = raw.get("title", "")
        if not title:
            return None
        rule_id = title.strip().lower().replace(" ", "_")[:64]

    # Normalise importance_criteria keys
    raw_importance = _safe_dict(raw.get("importance_criteria", {}))
    importance_criteria: dict[str, list[str]] = {
        "high_if": _safe_list(raw_importance.get("high_if")),
        "medium_if": _safe_list(raw_importance.get("medium_if")),
        "low_if": _safe_list(raw_importance.get("low_if")),
    }

    # Keywords/signals may be at top level or nested under ``watch_for``
    watch_for = _safe_dict(raw.get("watch_for", {}))
    keywords = raw.get("watch_for_keywords") or watch_for.get("keywords")
    signals = raw.get("watch_for_signals") or watch_for.get("signals")

    return Rule(
        id=str(rule_id),
        section=section,
        title=str(raw.get("title", "")),
        what_it_is=str(raw.get("what_it_is", "")),
        watch_for_keywords=_safe_list(keywords),
        watch_for_signals=_safe_list(signals),
        why_important=str(raw.get("why_important", "")),
        importance_criteria=importance_criteria,
        impact_hypothesis=_safe_dict(raw.get("impact_hypothesis", {})),
        horizon=str(raw.get("horizon", "medium")),
    )
