"""Alert Accuracy Dashboard — admin endpoints for evaluating alert
prediction quality across time intervals, categories, severities,
and news sources.

Endpoints
---------
- ``GET /overview``       — overall accuracy at each time interval
- ``GET /by-category``    — accuracy grouped by YAML rule section
- ``GET /by-severity``    — accuracy heatmap: severity x time_horizon
- ``GET /impact-curve``   — avg price change after alert by severity
- ``GET /by-source``      — per news source accuracy
"""

from __future__ import annotations

import logging
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select

from api.auth import get_current_admin
from api.database import AsyncSessionLocal
from api.data_collection.models import AlertOutcome
from api.models import Alert

logger = logging.getLogger("gold_monitor.alert_accuracy")

router = APIRouter(tags=["alert-accuracy"])

# All 6 tracked intervals
INTERVALS = ["30min", "1h", "4h", "24h", "48h", "7d"]


def _direction_correct_col(interval: str):
    """Return the direction_correct column for a given interval."""
    return getattr(AlertOutcome, f"direction_correct_{interval}")


def _change_pct_col(interval: str):
    """Return the change_pct column for a given interval."""
    return getattr(AlertOutcome, f"change_pct_{interval}")


def _extract_category(rule_id: str) -> str:
    """Extract the section prefix from a rule ID like GLOB_RATE_DECISION.

    Convention: split by '_' and take all parts except the last one.
    For single-segment IDs, return the ID itself.
    """
    parts = rule_id.split("_")
    if len(parts) <= 1:
        return rule_id
    return "_".join(parts[:-1])


# ══════════════════════════════════════════════════════════════════════════
#  1. GET /overview — overall accuracy at each time interval
# ══════════════════════════════════════════════════════════════════════════

@router.get(
    "/overview",
    dependencies=[Depends(get_current_admin)],
)
async def accuracy_overview():
    """Overall accuracy at each time interval (30min, 1h, 4h, 24h, 48h, 7d)."""
    async with AsyncSessionLocal() as session:
        # Total outcomes count
        total_q = await session.execute(
            select(func.count(AlertOutcome.id))
        )
        total_outcomes = total_q.scalar() or 0

        intervals_data = []
        for interval in INTERVALS:
            col = _direction_correct_col(interval)
            # Count rows where direction_correct_{interval} IS NOT NULL
            # and count how many are True using case()
            count_q = await session.execute(
                select(
                    func.count(AlertOutcome.id).label("total"),
                    func.sum(
                        case((col == True, 1), else_=0)  # noqa: E712
                    ).label("correct"),
                ).where(col.isnot(None))
            )
            row = count_q.one()
            total = row.total or 0
            correct = int(row.correct or 0)
            accuracy_pct = round((correct / total) * 100, 1) if total > 0 else None

            intervals_data.append({
                "interval": interval,
                "total": total,
                "correct": correct,
                "accuracy_pct": accuracy_pct,
            })

        return {
            "intervals": intervals_data,
            "total_outcomes": total_outcomes,
        }


# ══════════════════════════════════════════════════════════════════════════
#  2. GET /by-category — accuracy grouped by YAML rule section
# ══════════════════════════════════════════════════════════════════════════

@router.get(
    "/by-category",
    dependencies=[Depends(get_current_admin)],
)
async def accuracy_by_category():
    """Accuracy grouped by the YAML rule section prefix (e.g. GLOB, IR, FX)."""
    async with AsyncSessionLocal() as session:
        # Fetch all outcomes joined with their alert to get matched_rule_ids
        q = await session.execute(
            select(
                AlertOutcome.direction_correct_24h,
                Alert.matched_rule_ids,
            )
            .join(Alert, AlertOutcome.alert_id == Alert.id)
            .where(AlertOutcome.direction_correct_24h.isnot(None))
        )
        rows = q.all()

        # Group in Python by category
        cat_stats: dict[str, dict] = defaultdict(
            lambda: {"total": 0, "correct_24h": 0}
        )
        for direction_correct_24h, matched_rule_ids in rows:
            # matched_rule_ids is JSONB — comes back as a Python list
            rules = matched_rule_ids if isinstance(matched_rule_ids, list) else []
            if not rules:
                category = "UNKNOWN"
            else:
                category = _extract_category(rules[0])

            cat_stats[category]["total"] += 1
            if direction_correct_24h:
                cat_stats[category]["correct_24h"] += 1

        categories = []
        for cat, stats in sorted(cat_stats.items()):
            total = stats["total"]
            correct = stats["correct_24h"]
            categories.append({
                "category": cat,
                "total": total,
                "correct_24h": correct,
                "accuracy_24h_pct": round((correct / total) * 100, 1) if total > 0 else None,
            })

        return {"categories": categories}


# ══════════════════════════════════════════════════════════════════════════
#  3. GET /by-severity — accuracy heatmap: severity × time_horizon
# ══════════════════════════════════════════════════════════════════════════

@router.get(
    "/by-severity",
    dependencies=[Depends(get_current_admin)],
)
async def accuracy_by_severity():
    """Accuracy heatmap: severity x time interval."""
    async with AsyncSessionLocal() as session:
        # Fetch all outcomes with their severity
        q = await session.execute(
            select(AlertOutcome)
            .where(AlertOutcome.alert_severity.isnot(None))
        )
        rows = q.scalars().all()

        # Group by severity, then compute accuracy at each interval
        sev_groups: dict[str, list] = defaultdict(list)
        for row in rows:
            sev_groups[row.alert_severity].append(row)

        heatmap = []
        for severity in ["high", "medium", "low"]:
            outcomes = sev_groups.get(severity, [])
            interval_stats = []
            for interval in INTERVALS:
                col_name = f"direction_correct_{interval}"
                evaluated = [
                    o for o in outcomes if getattr(o, col_name) is not None
                ]
                total = len(evaluated)
                correct = sum(1 for o in evaluated if getattr(o, col_name))
                accuracy_pct = round((correct / total) * 100, 1) if total > 0 else None
                interval_stats.append({
                    "interval": interval,
                    "total": total,
                    "correct": correct,
                    "accuracy_pct": accuracy_pct,
                })
            heatmap.append({
                "severity": severity,
                "intervals": interval_stats,
            })

        return {"heatmap": heatmap}


# ══════════════════════════════════════════════════════════════════════════
#  4. GET /impact-curve — avg price change after alert by severity
# ══════════════════════════════════════════════════════════════════════════

@router.get(
    "/impact-curve",
    dependencies=[Depends(get_current_admin)],
)
async def impact_curve():
    """Average price change after alert, grouped by severity at each interval."""
    async with AsyncSessionLocal() as session:
        # Fetch all outcomes with severity
        q = await session.execute(
            select(AlertOutcome)
            .where(AlertOutcome.alert_severity.isnot(None))
        )
        rows = q.scalars().all()

        sev_groups: dict[str, list] = defaultdict(list)
        for row in rows:
            sev_groups[row.alert_severity].append(row)

        curves = []
        for severity in ["high", "medium", "low"]:
            outcomes = sev_groups.get(severity, [])
            avg_changes = []
            for interval in INTERVALS:
                col_name = f"change_pct_{interval}"
                values = [
                    getattr(o, col_name)
                    for o in outcomes
                    if getattr(o, col_name) is not None
                ]
                avg_val = round(sum(values) / len(values), 4) if values else None
                avg_changes.append({
                    "interval": interval,
                    "avg_change_pct": avg_val,
                    "sample_size": len(values),
                })
            curves.append({
                "severity": severity,
                "avg_changes": avg_changes,
            })

        return {"curves": curves}


# ══════════════════════════════════════════════════════════════════════════
#  5. GET /by-source — per news source accuracy
# ══════════════════════════════════════════════════════════════════════════

@router.get(
    "/by-source",
    dependencies=[Depends(get_current_admin)],
)
async def accuracy_by_source():
    """Per news source accuracy (direction_correct_24h) and average impact."""
    async with AsyncSessionLocal() as session:
        # Join AlertOutcome -> Alert to get source_name
        q = await session.execute(
            select(
                AlertOutcome.direction_correct_24h,
                AlertOutcome.change_pct_24h,
                Alert.source_name,
            )
            .join(Alert, AlertOutcome.alert_id == Alert.id)
        )
        rows = q.all()

        # Group in Python by source_name
        src_stats: dict[str, dict] = defaultdict(
            lambda: {
                "total": 0,
                "correct_24h": 0,
                "evaluated": 0,
                "impact_values": [],
            }
        )
        for direction_correct_24h, change_pct_24h, source_name in rows:
            name = source_name or "UNKNOWN"
            src_stats[name]["total"] += 1
            if direction_correct_24h is not None:
                src_stats[name]["evaluated"] += 1
                if direction_correct_24h:
                    src_stats[name]["correct_24h"] += 1
            if change_pct_24h is not None:
                src_stats[name]["impact_values"].append(change_pct_24h)

        sources = []
        for name, stats in sorted(src_stats.items()):
            evaluated = stats["evaluated"]
            correct = stats["correct_24h"]
            impact_vals = stats["impact_values"]
            avg_impact = (
                round(sum(impact_vals) / len(impact_vals), 4)
                if impact_vals
                else None
            )
            sources.append({
                "source_name": name,
                "total": stats["total"],
                "correct_24h": correct,
                "accuracy_pct": round((correct / evaluated) * 100, 1) if evaluated > 0 else None,
                "avg_impact_24h": avg_impact,
            })

        return {"sources": sources}
