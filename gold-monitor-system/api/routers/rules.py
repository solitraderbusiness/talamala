"""
Rules router -- browse the YAML rule library and fetch individual rules.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, status

from api.config import settings as app_settings
from api.rule_engine.load_rules import get_rules, load_rules

router = APIRouter(tags=["rules"])


# -- GET /rules/library ----------------------------------------------------


@router.get("/library")
async def rules_library() -> dict[str, Any]:
    """Return all rules from the YAML file, grouped by section.

    Each section contains its rules with full metadata (id, title,
    what_it_is, why_important, keywords, signals, horizon,
    importance_criteria).
    """

    try:
        yaml_data = load_rules(app_settings.YAML_PATH)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rules YAML file not found on server",
        )

    all_rules = get_rules(yaml_data)

    # Group rules by section
    sections_map: dict[str, dict[str, Any]] = {}
    for rule in all_rules:
        if rule.section not in sections_map:
            sections_map[rule.section] = {
                "id": rule.section,
                "title": _section_display_title(rule.section),
                "rules": [],
            }
        sections_map[rule.section]["rules"].append({
            "id": rule.id,
            "title": rule.title,
            "what_it_is": rule.what_it_is,
            "why_important": rule.why_important,
            "keywords": rule.watch_for_keywords,
            "signals": rule.watch_for_signals,
            "horizon": rule.horizon,
            "importance_criteria": rule.importance_criteria,
        })

    return {"sections": list(sections_map.values())}


# -- GET /rules/{rule_id} --------------------------------------------------


@router.get("/{rule_id}")
async def get_rule(rule_id: str) -> dict[str, Any]:
    """Return a single rule by its ID with all available detail fields."""

    try:
        yaml_data = load_rules(app_settings.YAML_PATH)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rules YAML file not found on server",
        )

    all_rules = get_rules(yaml_data)
    for rule in all_rules:
        if rule.id == rule_id:
            return asdict(rule)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Rule '{rule_id}' not found",
    )


# -- Helpers ---------------------------------------------------------------

_SECTION_TITLES: dict[str, str] = {
    "global_gold": "Global Gold Market",
    "iran_gold": "Iran Gold Market",
    "coin": "Gold Coins",
    "gold_funds": "Gold Funds",
}


def _section_display_title(section_key: str) -> str:
    """Map a section key to a human-readable title."""
    return _SECTION_TITLES.get(section_key, section_key.replace("_", " ").title())
