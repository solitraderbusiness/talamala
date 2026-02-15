"""Live market snapshot builder.

Aggregates all registered metrics + computed scores into a single JSON
payload for the chatbot and REST API.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from api.copilot.models import CalcRun
from api.copilot.queries import (
    compute_metric_freshness,
    get_all_registry,
    query_metric_latest,
)

logger = logging.getLogger("gold_monitor.copilot.snapshot")


async def build_live_snapshot(
    session: AsyncSession,
    asset: str = "XAUUSD",
) -> dict:
    """Build a complete market snapshot from all registered metrics.

    Returns a dict with:
    - metrics: latest values for all raw metrics
    - computed: sentiment + risk_radar with component breakdown
    - staleness_summary: how many metrics are fresh vs stale
    """
    now = datetime.now(timezone.utc)
    registry = await get_all_registry(session)

    metrics: dict = {}
    stale_keys: list[str] = []

    for reg in registry:
        if reg.source_table == "calc_runs":
            # Computed metrics handled separately below
            continue

        try:
            latest = await query_metric_latest(session, reg)
        except Exception:
            logger.debug("Failed to query metric %s", reg.key, exc_info=True)
            latest = None

        if latest:
            metrics[reg.key] = latest
            if latest.get("is_stale"):
                stale_keys.append(reg.key)
        else:
            metrics[reg.key] = {
                "key": reg.key,
                "label_fa": reg.label_fa,
                "value": None,
                "unit": reg.unit,
                "ts": None,
                "source_name": reg.source_name,
                "is_stale": True,
                "error": "no data",
            }
            stale_keys.append(reg.key)

    # ── Computed metrics ─────────────────────────────────────────────
    computed: dict = {}

    # Sentiment composite
    try:
        from api.data_collection.sentiment_calculator import compute_sentiment

        sentiment_result = await compute_sentiment(session)
        run_id = str(uuid4())

        # Save CalcRun for audit trail
        calc_run = CalcRun(
            run_id=run_id,
            run_type="sentiment_score",
            asset=asset,
            ts=now,
            inputs={
                "components": [
                    {
                        "name": c["name"],
                        "score": c["score"],
                        "weight": c["weight"],
                        "raw_value": c.get("raw_value"),
                        "explanation": c.get("explanation"),
                    }
                    for c in sentiment_result.get("components", [])
                ]
            },
            outputs={
                "composite_score": sentiment_result.get("composite_score"),
                "label": sentiment_result.get("label"),
                "label_fa": sentiment_result.get("label_fa"),
            },
            warnings=None,
        )
        session.add(calc_run)
        try:
            await session.commit()
        except Exception:
            await session.rollback()

        computed["sentiment_composite"] = {
            "value": sentiment_result.get("composite_score"),
            "label": sentiment_result.get("label"),
            "label_fa": sentiment_result.get("label_fa"),
            "components": [
                {
                    "name": c["name"],
                    "label_fa": c.get("label_fa"),
                    "score": c["score"],
                    "weight": c["weight"],
                    "raw_value": c.get("raw_value"),
                    "explanation": c.get("explanation"),
                    "stale": c.get("stale", False),
                }
                for c in sentiment_result.get("components", [])
            ],
            "run_id": run_id,
            "warnings": [],
        }
    except Exception:
        logger.warning("Sentiment computation failed for snapshot", exc_info=True)
        computed["sentiment_composite"] = {
            "value": None,
            "error": "computation failed",
        }

    # Money flow derived stats
    try:
        from api.analysis.money_flow_service import get_money_flow_derived

        mf_derived = await get_money_flow_derived(session)
        computed["money_flow_derived"] = mf_derived
    except Exception:
        logger.debug("Money flow derived stats failed for snapshot", exc_info=True)
        computed["money_flow_derived"] = {"error": "computation failed"}

    # Canonical indicators
    try:
        from api.analysis.indicator_registry import (
            INDICATORS,
            compute_all_indicators,
            indicator_to_dict,
        )
        canonical_results = await compute_all_indicators(session)
        computed["canonical_indicators"] = {
            ind_id: {
                "label_fa": INDICATORS[ind_id].label_fa if ind_id in INDICATORS else ind_id,
                "score": r.score,
                "percentile": r.percentile,
                "zscore": r.zscore,
                "stale": r.stale,
                "crowded": r.crowded,
                "source_name": r.source_name,
            }
            for ind_id, r in canonical_results.items()
        }
    except Exception:
        logger.debug("Canonical indicators failed for snapshot", exc_info=True)
        computed["canonical_indicators"] = {"error": "computation failed"}

    # Risk radar
    try:
        from api.services.analysis.risk_radar_engine import compute_risk_radar

        risk_result = await compute_risk_radar(session)
        computed["risk_radar"] = {
            "value": risk_result.get("composite_score"),
            "label": risk_result.get("label"),
            "components": [
                {
                    "name": c["name"],
                    "name_fa": c.get("name_fa"),
                    "score": c["score"],
                    "weight": c["weight"],
                    "confidence": c.get("confidence"),
                    "raw_value": c.get("raw_value"),
                    "explanation_fa": c.get("explanation_fa"),
                }
                for c in risk_result.get("components_detailed", risk_result.get("components", []))
            ],
            "weights": risk_result.get("weights"),
            "confidences": risk_result.get("confidences"),
            "warnings": risk_result.get("warnings", []),
            "run_id": risk_result.get("meta", {}).get("run_id"),
        }
    except Exception:
        logger.debug("Risk radar computation failed for snapshot", exc_info=True)
        computed["risk_radar"] = {"value": None, "error": "computation failed"}

    # Staleness summary
    total_metrics = len([r for r in registry if r.source_table != "calc_runs"])
    fresh_count = total_metrics - len(stale_keys)

    return {
        "snapshot_at": now.isoformat(),
        "asset": asset,
        "metrics": metrics,
        "computed": computed,
        "staleness_summary": {
            "total": total_metrics,
            "fresh": fresh_count,
            "stale": len(stale_keys),
            "stale_keys": stale_keys,
        },
    }
