"""Sentiment QA admin endpoints.

Three-layer quality assurance for the sentiment pipeline:
1. Human labeling — gold set for ground truth
2. LLM cross-check — reference model disagreement detection
3. Market calibration — sentiment vs forward price returns
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_admin
from api.database import get_db

router = APIRouter(
    tags=["sentiment-qa"],
    dependencies=[Depends(get_current_admin)],
)


# ── Schemas ───────────────────────────────────────────────────────────

class LabelSubmission(BaseModel):
    alert_id: str
    direction_label: str = Field(..., pattern="^(positive|negative|neutral)$")
    intensity: int = Field(..., ge=1, le=5)
    relevance: int = Field(..., ge=1, le=5)
    notes: str | None = None


# ── Label Queue ───────────────────────────────────────────────────────

@router.get("/label-queue")
async def label_queue(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Stratified sample of alerts needing human labels.

    Selection strategy: prioritise unlabeled alerts, stratify by
    severity & direction to ensure diverse coverage. Also skip alerts
    that already have a sentiment_labels row.
    """
    q = text("""
        WITH unlabeled AS (
            SELECT a.id, a.title, a.source_name, a.severity,
                   a.confidence,
                   a.created_at,
                   a.event_category,
                   COALESCE((a.match_evidence->>'direction')::text, 'unknown') as direction,
                   COALESCE((a.match_evidence->>'alert_score')::text, '0') as alert_score,
                   a.summary_fa
            FROM alerts a
            LEFT JOIN sentiment_labels sl ON sl.alert_id = a.id
            WHERE sl.id IS NULL
        ),
        ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY severity, direction
                       ORDER BY RANDOM()
                   ) as rn
            FROM unlabeled
        )
        SELECT id, title, source_name, severity, confidence,
               created_at, event_category, direction, alert_score, summary_fa
        FROM ranked
        WHERE rn <= GREATEST(:lim / 8, 2)
        ORDER BY severity DESC, created_at DESC
        LIMIT :lim
    """)
    rows = (await db.execute(q, {"lim": limit})).mappings().all()

    # Total unlabeled count
    total_unlabeled = (await db.execute(text("""
        SELECT COUNT(*) FROM alerts a
        LEFT JOIN sentiment_labels sl ON sl.alert_id = a.id
        WHERE sl.id IS NULL
    """))).scalar() or 0

    total_labeled = (await db.execute(text(
        "SELECT COUNT(*) FROM sentiment_labels"
    ))).scalar() or 0

    return {
        "queue": [
            {
                "id": str(r["id"]),
                "title": r["title"],
                "source_name": r["source_name"],
                "severity": r["severity"],
                "confidence": float(r["confidence"]) if r["confidence"] else 0,
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "event_category": r["event_category"],
                "direction": r["direction"],
                "alert_score": r["alert_score"],
                "summary_fa": r["summary_fa"],
            }
            for r in rows
        ],
        "total_unlabeled": total_unlabeled,
        "total_labeled": total_labeled,
    }


# ── Submit Label ──────────────────────────────────────────────────────

@router.post("/labels")
async def submit_label(
    body: LabelSubmission,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Submit a human label for an alert."""
    # Fetch alert's system prediction for comparison
    alert = (await db.execute(text("""
        SELECT id, confidence,
               COALESCE((match_evidence->>'direction')::text, 'unknown') as direction,
               COALESCE((match_evidence->>'alert_score')::text, '0') as alert_score
        FROM alerts WHERE id = :aid
    """), {"aid": body.alert_id})).mappings().first()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    label_id = str(uuid.uuid4())
    await db.execute(text("""
        INSERT INTO sentiment_labels
            (id, alert_id, direction_label, intensity, relevance,
             system_direction, system_alert_score, system_confidence,
             labeler, notes)
        VALUES (:id, :aid, :dir, :intensity, :relevance,
                :sys_dir, :sys_score, :sys_conf,
                'admin', :notes)
        ON CONFLICT (alert_id) DO UPDATE SET
            direction_label = EXCLUDED.direction_label,
            intensity = EXCLUDED.intensity,
            relevance = EXCLUDED.relevance,
            system_direction = EXCLUDED.system_direction,
            system_alert_score = EXCLUDED.system_alert_score,
            system_confidence = EXCLUDED.system_confidence,
            notes = EXCLUDED.notes,
            labeled_at = NOW()
    """), {
        "id": label_id,
        "aid": body.alert_id,
        "dir": body.direction_label,
        "intensity": body.intensity,
        "relevance": body.relevance,
        "sys_dir": alert["direction"],
        "sys_score": int(alert["alert_score"]) if alert["alert_score"] else 0,
        "sys_conf": float(alert["confidence"]) if alert["confidence"] else 0,
        "notes": body.notes,
    })
    await db.commit()

    return {"ok": True, "label_id": label_id, "alert_id": body.alert_id}


# ── Label Stats (Confusion Matrix + Accuracy) ────────────────────────

@router.get("/label-stats")
async def label_stats(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Confusion matrix and accuracy metrics for labeled alerts."""
    labels = (await db.execute(text("""
        SELECT direction_label, system_direction, intensity, relevance,
               system_alert_score, system_confidence
        FROM sentiment_labels
        WHERE labeled_at >= NOW() - MAKE_INTERVAL(days => :days)
    """), {"days": days})).mappings().all()

    if not labels:
        return {
            "days": days,
            "total_labels": 0,
            "confusion_matrix": {},
            "accuracy": None,
            "macro_f1": None,
            "direction_breakdown": {},
            "avg_intensity": None,
            "avg_relevance": None,
        }

    # Build confusion matrix: system_direction → direction_label → count
    directions = ["positive", "negative", "neutral"]
    matrix: dict[str, dict[str, int]] = {d: {d2: 0 for d2 in directions} for d in directions + ["unknown"]}
    correct = 0
    total = len(labels)

    for l in labels:
        sys_dir = _normalize_direction(l["system_direction"])
        human_dir = l["direction_label"]
        if sys_dir not in matrix:
            matrix[sys_dir] = {d: 0 for d in directions}
        if human_dir in matrix[sys_dir]:
            matrix[sys_dir][human_dir] += 1
        if sys_dir == human_dir:
            correct += 1

    accuracy = round(correct / max(total, 1) * 100, 1)

    # Macro F1
    f1_scores = []
    for d in directions:
        tp = matrix.get(d, {}).get(d, 0)
        fp = sum(matrix.get(other, {}).get(d, 0) for other in matrix if other != d)
        fn = sum(matrix.get(d, {}).get(other, 0) for other in directions if other != d)
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-9)
        f1_scores.append(f1)

    macro_f1 = round(sum(f1_scores) / max(len(f1_scores), 1) * 100, 1)

    # Direction breakdown
    dir_counts: dict[str, int] = {}
    for l in labels:
        d = l["direction_label"]
        dir_counts[d] = dir_counts.get(d, 0) + 1

    return {
        "days": days,
        "total_labels": total,
        "confusion_matrix": matrix,
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "direction_breakdown": dir_counts,
        "avg_intensity": round(sum(l["intensity"] for l in labels) / total, 2),
        "avg_relevance": round(sum(l["relevance"] for l in labels) / total, 2),
    }


# ── Disagreements (System vs Reference Model) ────────────────────────

@router.get("/disagreements")
async def disagreements(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Alerts where system and reference model disagree on direction."""
    rows = (await db.execute(text("""
        SELECT rs.id, rs.alert_id, rs.system_direction, rs.system_score,
               rs.ref_direction, rs.ref_intensity, rs.ref_confidence,
               rs.ref_model, rs.ref_reasoning, rs.trace_id, rs.scored_at,
               a.title, a.source_name, a.severity, a.created_at
        FROM sentiment_reference_scores rs
        JOIN alerts a ON a.id = rs.alert_id
        WHERE rs.direction_agrees = false
          AND rs.scored_at >= NOW() - MAKE_INTERVAL(days => :days)
        ORDER BY rs.scored_at DESC
        LIMIT 100
    """), {"days": days})).mappings().all()

    total_scored = (await db.execute(text("""
        SELECT COUNT(*) FROM sentiment_reference_scores
        WHERE scored_at >= NOW() - MAKE_INTERVAL(days => :days)
    """), {"days": days})).scalar() or 0

    total_disagree = (await db.execute(text("""
        SELECT COUNT(*) FROM sentiment_reference_scores
        WHERE direction_agrees = false
          AND scored_at >= NOW() - MAKE_INTERVAL(days => :days)
    """), {"days": days})).scalar() or 0

    return {
        "days": days,
        "total_scored": total_scored,
        "total_disagreements": total_disagree,
        "disagreement_rate_pct": round(total_disagree / max(total_scored, 1) * 100, 1),
        "items": [
            {
                "id": str(r["id"]),
                "alert_id": str(r["alert_id"]),
                "title": r["title"],
                "source_name": r["source_name"],
                "severity": r["severity"],
                "alert_created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "system_direction": r["system_direction"],
                "system_score": r["system_score"],
                "ref_direction": r["ref_direction"],
                "ref_intensity": r["ref_intensity"],
                "ref_confidence": float(r["ref_confidence"]) if r["ref_confidence"] else None,
                "ref_model": r["ref_model"],
                "ref_reasoning": r["ref_reasoning"],
                "trace_id": r["trace_id"],
                "scored_at": r["scored_at"].isoformat() if r["scored_at"] else None,
            }
            for r in rows
        ],
    }


# ── Calibration (Sentiment vs Forward Returns) ───────────────────────

@router.get("/calibration")
async def calibration(
    days: int = Query(90, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Binned sentiment score vs actual forward price returns.

    Groups alerts by system direction + severity, then shows average
    forward returns at multiple horizons (30min, 1h, 4h, 24h).
    """
    rows = (await db.execute(text("""
        SELECT
            a.severity,
            COALESCE((a.match_evidence->>'direction')::text, 'unknown') as direction,
            COALESCE((a.match_evidence->>'alert_score')::text, '0')::int as alert_score,
            ao.change_pct_30min,
            ao.change_pct_1h,
            ao.change_pct_4h,
            ao.change_pct_24h,
            ao.direction_correct_24h
        FROM alerts a
        JOIN alert_outcomes ao ON ao.alert_id = a.id
        WHERE a.created_at >= NOW() - MAKE_INTERVAL(days => :days)
          AND ao.change_pct_24h IS NOT NULL
    """), {"days": days})).mappings().all()

    if not rows:
        return {
            "days": days,
            "total_with_outcomes": 0,
            "bins": [],
            "overall_accuracy_24h": None,
        }

    # Group by (direction, severity) bins
    bins: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = f"{r['direction']}_{r['severity']}"
        if key not in bins:
            bins[key] = {
                "direction": r["direction"],
                "severity": r["severity"],
                "count": 0,
                "returns_30min": [],
                "returns_1h": [],
                "returns_4h": [],
                "returns_24h": [],
                "correct_24h": 0,
            }
        b = bins[key]
        b["count"] += 1
        if r["change_pct_30min"] is not None:
            b["returns_30min"].append(float(r["change_pct_30min"]))
        if r["change_pct_1h"] is not None:
            b["returns_1h"].append(float(r["change_pct_1h"]))
        if r["change_pct_4h"] is not None:
            b["returns_4h"].append(float(r["change_pct_4h"]))
        if r["change_pct_24h"] is not None:
            b["returns_24h"].append(float(r["change_pct_24h"]))
        if r["direction_correct_24h"]:
            b["correct_24h"] += 1

    result_bins = []
    total_correct = 0
    total_with_24h = 0
    for b in bins.values():
        n = b["count"]
        result_bins.append({
            "direction": b["direction"],
            "severity": b["severity"],
            "count": n,
            "avg_return_30min": round(sum(b["returns_30min"]) / max(len(b["returns_30min"]), 1), 4),
            "avg_return_1h": round(sum(b["returns_1h"]) / max(len(b["returns_1h"]), 1), 4),
            "avg_return_4h": round(sum(b["returns_4h"]) / max(len(b["returns_4h"]), 1), 4),
            "avg_return_24h": round(sum(b["returns_24h"]) / max(len(b["returns_24h"]), 1), 4),
            "accuracy_24h": round(b["correct_24h"] / max(n, 1) * 100, 1),
        })
        total_correct += b["correct_24h"]
        total_with_24h += n

    result_bins.sort(key=lambda x: x["count"], reverse=True)

    return {
        "days": days,
        "total_with_outcomes": len(rows),
        "bins": result_bins,
        "overall_accuracy_24h": round(total_correct / max(total_with_24h, 1) * 100, 1),
    }


# ── Outliers (Biggest Prediction Mismatches) ──────────────────────────

@router.get("/outliers")
async def outliers(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Alerts with biggest mismatch between predicted direction and outcome."""
    rows = (await db.execute(text("""
        SELECT a.id, a.title, a.source_name, a.severity,
               a.created_at, a.confidence,
               COALESCE((a.match_evidence->>'direction')::text, 'unknown') as direction,
               COALESCE((a.match_evidence->>'alert_score')::text, '0') as alert_score,
               ao.change_pct_24h,
               ao.change_pct_4h,
               ao.direction_correct_24h,
               ao.price_at_alert,
               ao.price_24h
        FROM alerts a
        JOIN alert_outcomes ao ON ao.alert_id = a.id
        WHERE ao.change_pct_24h IS NOT NULL
          AND ao.direction_correct_24h = false
        ORDER BY ABS(ao.change_pct_24h) DESC
        LIMIT :lim
    """), {"lim": limit})).mappings().all()

    return {
        "total": len(rows),
        "items": [
            {
                "id": str(r["id"]),
                "title": r["title"],
                "source_name": r["source_name"],
                "severity": r["severity"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "direction": r["direction"],
                "alert_score": r["alert_score"],
                "confidence": float(r["confidence"]) if r["confidence"] else 0,
                "change_pct_24h": float(r["change_pct_24h"]),
                "change_pct_4h": float(r["change_pct_4h"]) if r["change_pct_4h"] else None,
                "price_at_alert": float(r["price_at_alert"]) if r["price_at_alert"] else None,
                "price_24h": float(r["price_24h"]) if r["price_24h"] else None,
            }
            for r in rows
        ],
    }


# ── Provenance (Full Explain Chain) ───────────────────────────────────

@router.get("/provenance/{alert_id}")
async def provenance(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Full explain chain for a single alert: rule match → enrichment → outcome."""
    # Alert details
    alert = (await db.execute(text("""
        SELECT id, title, source_name, source_url, severity, confidence,
               time_horizon, created_at, match_evidence, matched_rule_ids,
               summary_fa, why_important_fa, event_category, news_type,
               price_xauusd_at_alert, price_usdirr_at_alert,
               price_coin_at_alert, price_18k_at_alert
        FROM alerts WHERE id = :aid
    """), {"aid": alert_id})).mappings().first()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    # Raw item
    raw_item = (await db.execute(text("""
        SELECT ri.id, ri.title, ri.url, ri.content_hash, ri.fetched_at
        FROM raw_items ri
        JOIN alerts a ON a.raw_item_id = ri.id
        WHERE a.id = :aid
    """), {"aid": alert_id})).mappings().first()

    # Human label
    label = (await db.execute(text("""
        SELECT direction_label, intensity, relevance, labeler, labeled_at, notes
        FROM sentiment_labels WHERE alert_id = :aid
    """), {"aid": alert_id})).mappings().first()

    # Reference score
    ref = (await db.execute(text("""
        SELECT system_direction, system_score, system_method,
               ref_direction, ref_intensity, ref_confidence,
               ref_model, ref_reasoning, direction_agrees,
               trace_id, scored_at
        FROM sentiment_reference_scores WHERE alert_id = :aid
    """), {"aid": alert_id})).mappings().first()

    # Outcome
    outcome = (await db.execute(text("""
        SELECT price_at_alert, alert_direction,
               change_pct_30min, direction_correct_30min,
               change_pct_1h, direction_correct_1h,
               change_pct_4h, direction_correct_4h,
               change_pct_24h, direction_correct_24h,
               change_pct_48h, direction_correct_48h
        FROM alert_outcomes WHERE alert_id = :aid
    """), {"aid": alert_id})).mappings().first()

    # Market snapshot
    snapshot = (await db.execute(text("""
        SELECT xauusd, usdirr, coin, gold_18k,
               wti, btcusd, dxy,
               created_at
        FROM alert_market_snapshots WHERE alert_id = :aid
    """), {"aid": alert_id})).mappings().first()

    return {
        "alert": {
            "id": str(alert["id"]),
            "title": alert["title"],
            "source_name": alert["source_name"],
            "source_url": alert["source_url"],
            "severity": alert["severity"],
            "confidence": float(alert["confidence"]),
            "time_horizon": alert["time_horizon"],
            "created_at": alert["created_at"].isoformat() if alert["created_at"] else None,
            "match_evidence": alert["match_evidence"],
            "matched_rule_ids": alert["matched_rule_ids"],
            "summary_fa": alert["summary_fa"],
            "why_important_fa": alert["why_important_fa"],
            "event_category": alert["event_category"],
            "news_type": alert["news_type"],
            "prices_at_alert": {
                "xauusd": float(alert["price_xauusd_at_alert"]) if alert["price_xauusd_at_alert"] else None,
                "usdirr": float(alert["price_usdirr_at_alert"]) if alert["price_usdirr_at_alert"] else None,
                "coin": float(alert["price_coin_at_alert"]) if alert["price_coin_at_alert"] else None,
                "gold_18k": float(alert["price_18k_at_alert"]) if alert["price_18k_at_alert"] else None,
            },
        },
        "raw_item": {
            "id": str(raw_item["id"]),
            "title": raw_item["title"],
            "url": raw_item["url"],
            "content_hash": raw_item["content_hash"],
            "fetched_at": raw_item["fetched_at"].isoformat() if raw_item["fetched_at"] else None,
        } if raw_item else None,
        "human_label": {
            "direction_label": label["direction_label"],
            "intensity": label["intensity"],
            "relevance": label["relevance"],
            "labeler": label["labeler"],
            "labeled_at": label["labeled_at"].isoformat() if label["labeled_at"] else None,
            "notes": label["notes"],
        } if label else None,
        "reference_score": {
            "system_direction": ref["system_direction"],
            "system_score": ref["system_score"],
            "system_method": ref["system_method"],
            "ref_direction": ref["ref_direction"],
            "ref_intensity": ref["ref_intensity"],
            "ref_confidence": float(ref["ref_confidence"]) if ref["ref_confidence"] else None,
            "ref_model": ref["ref_model"],
            "ref_reasoning": ref["ref_reasoning"],
            "direction_agrees": ref["direction_agrees"],
            "trace_id": ref["trace_id"],
            "scored_at": ref["scored_at"].isoformat() if ref["scored_at"] else None,
        } if ref else None,
        "outcome": {
            "price_at_alert": float(outcome["price_at_alert"]) if outcome["price_at_alert"] else None,
            "alert_direction": outcome["alert_direction"],
            "windows": {
                "30min": {
                    "change_pct": float(outcome["change_pct_30min"]) if outcome["change_pct_30min"] is not None else None,
                    "direction_correct": outcome["direction_correct_30min"],
                },
                "1h": {
                    "change_pct": float(outcome["change_pct_1h"]) if outcome["change_pct_1h"] is not None else None,
                    "direction_correct": outcome["direction_correct_1h"],
                },
                "4h": {
                    "change_pct": float(outcome["change_pct_4h"]) if outcome["change_pct_4h"] is not None else None,
                    "direction_correct": outcome["direction_correct_4h"],
                },
                "24h": {
                    "change_pct": float(outcome["change_pct_24h"]) if outcome["change_pct_24h"] is not None else None,
                    "direction_correct": outcome["direction_correct_24h"],
                },
                "48h": {
                    "change_pct": float(outcome["change_pct_48h"]) if outcome["change_pct_48h"] is not None else None,
                    "direction_correct": outcome["direction_correct_48h"],
                },
            },
        } if outcome else None,
        "market_snapshot": {
            "xauusd": float(snapshot["xauusd"]) if snapshot and snapshot["xauusd"] else None,
            "usdirr": float(snapshot["usdirr"]) if snapshot and snapshot["usdirr"] else None,
            "coin": float(snapshot["coin"]) if snapshot and snapshot["coin"] else None,
            "gold_18k": float(snapshot["gold_18k"]) if snapshot and snapshot["gold_18k"] else None,
            "wti": float(snapshot["wti"]) if snapshot and snapshot["wti"] else None,
            "btcusd": float(snapshot["btcusd"]) if snapshot and snapshot["btcusd"] else None,
            "dxy": float(snapshot["dxy"]) if snapshot and snapshot["dxy"] else None,
            "captured_at": snapshot["created_at"].isoformat() if snapshot and snapshot["created_at"] else None,
        } if snapshot else None,
    }


# ── Helpers ───────────────────────────────────────────────────────────

def _normalize_direction(d: str | None) -> str:
    """Map system direction values to standard positive/negative/neutral."""
    if not d:
        return "unknown"
    d = d.lower().strip()
    if d in ("positive", "bullish", "up"):
        return "positive"
    if d in ("negative", "bearish", "down"):
        return "negative"
    if d in ("neutral", "mixed"):
        return "neutral"
    return "unknown"
