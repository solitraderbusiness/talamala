"""Admin API for sentiment calculation audit logs.

Provides:
- List recent calculation runs with overall score/label
- Drill-down into per-component details for any run
- Diagnostics: saturation analysis + quality checks
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_admin
from api.database import get_db
from api.data_collection.sentiment_audit import SentimentCalcLog

logger = logging.getLogger("gold_monitor.sentiment_logs")

router = APIRouter(tags=["Sentiment Calc Logs"])


@router.get("/list")
async def list_runs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    """List recent sentiment calculation runs (newest first)."""
    result = await session.execute(
        select(
            SentimentCalcLog.id,
            SentimentCalcLog.run_at,
            SentimentCalcLog.overall_score,
            SentimentCalcLog.overall_label,
            SentimentCalcLog.overall_label_fa,
            SentimentCalcLog.warnings,
        )
        .order_by(desc(SentimentCalcLog.run_at))
        .offset(offset)
        .limit(limit)
    )
    rows = result.all()

    count_result = await session.execute(
        select(func.count()).select_from(SentimentCalcLog)
    )
    total = count_result.scalar() or 0

    items = []
    for row in rows:
        has_stale = False
        has_fallback = False
        if row.warnings:
            has_stale = any("stale" in str(w).lower() for w in row.warnings)
            has_fallback = any("missing" in str(w).lower() for w in row.warnings)

        items.append({
            "id": str(row.id),
            "run_at": row.run_at.isoformat() if row.run_at else None,
            "overall_score": row.overall_score,
            "overall_label": row.overall_label,
            "overall_label_fa": row.overall_label_fa,
            "warning_count": len(row.warnings) if row.warnings else 0,
            "has_stale": has_stale,
            "has_fallback": has_fallback,
        })

    return {"items": items, "total": total}


@router.get("/detail/{run_id}")
async def get_run_detail(
    run_id: str,
    session: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    """Get full details of a specific calculation run."""
    result = await session.execute(
        select(SentimentCalcLog).where(SentimentCalcLog.id == run_id)
    )
    log = result.scalar_one_or_none()

    if log is None:
        return {"error": "Run not found"}

    return {
        "id": str(log.id),
        "run_at": log.run_at.isoformat() if log.run_at else None,
        "overall_score": log.overall_score,
        "overall_label": log.overall_label,
        "overall_label_fa": log.overall_label_fa,
        "app_version": log.app_version,
        "components": log.components or [],
        "warnings": log.warnings or [],
    }


@router.get("/diagnostics")
async def diagnostics(
    days: int = Query(60, ge=7, le=730),
    session: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    """Quality diagnostics: saturation rate, distribution stats, warnings.

    Analyzes the last *days* of audit logs to detect:
    - Saturation: % of runs where a component score is 0 or 100 (target < 5%)
    - Distribution: median/mean/std of component scores (median should be ~50)
    - Staleness: % of runs with stale data
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    result = await session.execute(
        select(SentimentCalcLog.components, SentimentCalcLog.warnings)
        .where(SentimentCalcLog.run_at >= cutoff)
        .order_by(SentimentCalcLog.run_at)
    )
    rows = result.all()

    if not rows:
        return {"message": "No audit logs found in the specified period", "days": days}

    total_runs = len(rows)

    # Collect per-component scores
    comp_scores: dict[str, list[int]] = {}
    comp_stale_count: dict[str, int] = {}
    comp_fallback_count: dict[str, int] = {}
    comp_crowded_count: dict[str, int] = {}

    for row in rows:
        components = row.components or []
        for comp in components:
            name = comp.get("name", "unknown")
            score = comp.get("score")
            if score is None:
                continue

            comp_scores.setdefault(name, []).append(score)

            if comp.get("stale"):
                comp_stale_count[name] = comp_stale_count.get(name, 0) + 1
            if comp.get("fallback_used"):
                comp_fallback_count[name] = comp_fallback_count.get(name, 0) + 1
            if comp.get("crowded"):
                comp_crowded_count[name] = comp_crowded_count.get(name, 0) + 1

    # Compute diagnostics per component
    component_diagnostics = []
    quality_warnings: list[str] = []

    for name, scores in comp_scores.items():
        n = len(scores)
        if n == 0:
            continue

        sorted_scores = sorted(scores)
        mean_score = sum(scores) / n
        median_score = sorted_scores[n // 2]
        min_score = sorted_scores[0]
        max_score = sorted_scores[-1]

        # Saturation: % of runs at 0 or 100
        saturated = sum(1 for s in scores if s == 0 or s == 100)
        saturation_pct = round(saturated / n * 100, 1)

        # Std dev
        variance = sum((s - mean_score) ** 2 for s in scores) / n
        std_dev = round(variance ** 0.5, 1)

        stale_pct = round(comp_stale_count.get(name, 0) / n * 100, 1)
        fallback_pct = round(comp_fallback_count.get(name, 0) / n * 100, 1)
        crowded_pct = round(comp_crowded_count.get(name, 0) / n * 100, 1)

        diag = {
            "component": name,
            "run_count": n,
            "saturation_pct": saturation_pct,
            "saturation_status": "ok" if saturation_pct < 5 else ("warning" if saturation_pct < 10 else "fail"),
            "mean_score": round(mean_score, 1),
            "median_score": median_score,
            "min_score": min_score,
            "max_score": max_score,
            "std_dev": std_dev,
            "stale_pct": stale_pct,
            "fallback_pct": fallback_pct,
            "crowded_pct": crowded_pct,
        }
        component_diagnostics.append(diag)

        # Quality warnings
        if saturation_pct >= 10:
            quality_warnings.append(
                f"{name}: saturation rate {saturation_pct}% exceeds 10% threshold"
            )
        if abs(median_score - 50) > 15:
            quality_warnings.append(
                f"{name}: median score {median_score} deviates significantly from 50"
            )
        if stale_pct > 20:
            quality_warnings.append(
                f"{name}: {stale_pct}% of runs used stale data"
            )

    return {
        "period_days": days,
        "total_runs": total_runs,
        "components": component_diagnostics,
        "quality_warnings": quality_warnings,
    }
