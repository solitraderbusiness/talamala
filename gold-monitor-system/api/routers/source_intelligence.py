"""Source Intelligence admin endpoints.

Provides source inventory stats, coverage analysis, dedupe health,
and automated recommendations for improving news diversity.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_admin
from api.database import get_db

router = APIRouter(
    tags=["source-intelligence"],
    dependencies=[Depends(get_current_admin)],
)

# ── Coverage buckets ──────────────────────────────────────────────────

COVERAGE_BUCKETS = {
    "central_banks": "بانک‌های مرکزی",
    "inflation": "تورم و CPI",
    "yields_rates": "نرخ بهره و بازده",
    "geopolitics": "ژئوپلیتیک",
    "mining_supply": "معدن و عرضه",
    "china_demand": "تقاضای چین",
    "etf_flows": "جریان ETF",
    "usd_dollar": "دلار آمریکا",
    "oil_energy": "نفت و انرژی",
    "crypto_narrative": "روایت رمزارز",
    "iran_economy": "اقتصاد ایران",
    "iran_politics": "سیاست ایران",
    "price_movement": "حرکت قیمت",
    "gold_funds": "صندوق‌های طلا",
}


# ── Schemas ───────────────────────────────────────────────────────────

class TagAction(BaseModel):
    source_id: str
    tag: str
    action: str = "add"  # "add" or "remove"


# ── Overview ──────────────────────────────────────────────────────────

@router.get("/overview")
async def source_overview(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Source inventory with production stats."""
    q = text("""
        WITH alert_stats AS (
            SELECT source_name, COUNT(*) as alerts,
                   AVG(confidence) as avg_conf,
                   COUNT(CASE WHEN severity='critical' THEN 1 END) as critical,
                   COUNT(CASE WHEN severity='high' THEN 1 END) as high,
                   COUNT(CASE WHEN severity='medium' THEN 1 END) as medium,
                   COUNT(CASE WHEN severity='low' THEN 1 END) as low
            FROM alerts WHERE created_at >= NOW() - MAKE_INTERVAL(days => :days)
            GROUP BY source_name
        ),
        raw_stats AS (
            SELECT s.name as source_name, COUNT(ri.id) as raw_count
            FROM sources s LEFT JOIN raw_items ri
                ON ri.source_id = s.id
                AND ri.fetched_at >= NOW() - MAKE_INTERVAL(days => :days)
            GROUP BY s.name
        ),
        error_stats AS (
            SELECT s.name as source_name,
                   COUNT(fl.id) FILTER (WHERE fl.error_message IS NOT NULL) as errors
            FROM sources s LEFT JOIN fetch_logs fl
                ON fl.source_id = s.id
                AND fl.started_at >= NOW() - MAKE_INTERVAL(days => :days)
            GROUP BY s.name
        ),
        tags_agg AS (
            SELECT st.source_id, array_agg(st.tag ORDER BY st.tag) as tags
            FROM source_tags st GROUP BY st.source_id
        )
        SELECT
            s.id, s.name, s.type, s.base_url, s.enabled,
            s.poll_interval_seconds,
            s.categories,
            s.last_fetched_at, s.last_success_at, s.last_error,
            COALESCE(rs.raw_count, 0) as raw_count,
            COALESCE(als.alerts, 0) as alert_count,
            CASE WHEN COALESCE(rs.raw_count, 0) > 0
                 THEN ROUND((COALESCE(als.alerts, 0)::numeric / rs.raw_count * 100), 2)
                 ELSE 0 END as match_rate_pct,
            ROUND(COALESCE(als.avg_conf, 0)::numeric, 4) as avg_confidence,
            als.critical, als.high, als.medium, als.low,
            COALESCE(es.errors, 0) as error_count,
            COALESCE(ta.tags, '{}') as tags
        FROM sources s
        LEFT JOIN alert_stats als ON als.source_name = s.name
        LEFT JOIN raw_stats rs ON rs.source_name = s.name
        LEFT JOIN error_stats es ON es.source_name = s.name
        LEFT JOIN tags_agg ta ON ta.source_id = s.id
        ORDER BY s.enabled DESC, COALESCE(als.alerts, 0) DESC, s.name
    """)
    rows = (await db.execute(q, {"days": days})).mappings().all()

    sources = []
    total_alerts = 0
    total_raw = 0
    for r in rows:
        total_alerts += r["alert_count"]
        total_raw += r["raw_count"]
        sources.append({
            "id": str(r["id"]),
            "name": r["name"],
            "type": r["type"],
            "base_url": r["base_url"],
            "enabled": r["enabled"],
            "poll_interval_seconds": r["poll_interval_seconds"],
            "categories": r["categories"],
            "last_fetched_at": r["last_fetched_at"].isoformat() if r["last_fetched_at"] else None,
            "last_success_at": r["last_success_at"].isoformat() if r["last_success_at"] else None,
            "last_error": r["last_error"],
            "raw_count": r["raw_count"],
            "alert_count": r["alert_count"],
            "match_rate_pct": float(r["match_rate_pct"]),
            "avg_confidence": float(r["avg_confidence"]),
            "severity": {
                "critical": r["critical"] or 0,
                "high": r["high"] or 0,
                "medium": r["medium"] or 0,
                "low": r["low"] or 0,
            },
            "error_count": r["error_count"],
            "tags": list(r["tags"]) if r["tags"] != "{}" else [],
        })

    return {
        "days": days,
        "total_sources": len(sources),
        "enabled_sources": sum(1 for s in sources if s["enabled"]),
        "total_alerts": total_alerts,
        "total_raw_items": total_raw,
        "overall_match_rate_pct": round(total_alerts / total_raw * 100, 2) if total_raw > 0 else 0,
        "sources": sources,
        "coverage_buckets": COVERAGE_BUCKETS,
    }


# ── Coverage ──────────────────────────────────────────────────────────

@router.get("/coverage")
async def source_coverage(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Alerts breakdown by category, direction, severity, and source."""
    by_category = (await db.execute(text("""
        SELECT COALESCE(NULLIF(event_category, ''), 'uncategorized') as cat, COUNT(*) as cnt
        FROM alerts WHERE created_at >= NOW() - MAKE_INTERVAL(days => :days)
        GROUP BY cat ORDER BY cnt DESC
    """), {"days": days})).mappings().all()

    by_direction = (await db.execute(text("""
        SELECT COALESCE(NULLIF((match_evidence->>'direction')::text, ''), 'unknown') as dir,
               COUNT(*) as cnt
        FROM alerts WHERE created_at >= NOW() - MAKE_INTERVAL(days => :days)
        GROUP BY dir ORDER BY cnt DESC
    """), {"days": days})).mappings().all()

    by_severity = (await db.execute(text("""
        SELECT severity, COUNT(*) as cnt
        FROM alerts WHERE created_at >= NOW() - MAKE_INTERVAL(days => :days)
        GROUP BY severity ORDER BY cnt DESC
    """), {"days": days})).mappings().all()

    by_source = (await db.execute(text("""
        SELECT source_name, COUNT(*) as cnt
        FROM alerts WHERE created_at >= NOW() - MAKE_INTERVAL(days => :days)
        GROUP BY source_name ORDER BY cnt DESC
    """), {"days": days})).mappings().all()

    by_news_type = (await db.execute(text("""
        SELECT COALESCE(NULLIF(news_type, ''), 'uncategorized') as nt, COUNT(*) as cnt
        FROM alerts WHERE created_at >= NOW() - MAKE_INTERVAL(days => :days)
        GROUP BY nt ORDER BY cnt DESC
    """), {"days": days})).mappings().all()

    # Identify missing buckets by checking which COVERAGE_BUCKETS have <3 alerts
    cat_counts = {r["cat"]: r["cnt"] for r in by_category}
    missing_buckets = []
    for key, label in COVERAGE_BUCKETS.items():
        cnt = cat_counts.get(key, 0)
        if cnt < 3:
            missing_buckets.append({"key": key, "label": label, "count": cnt})

    total = sum(r["cnt"] for r in by_category)

    return {
        "days": days,
        "total_alerts": total,
        "by_category": [{"name": r["cat"], "count": r["cnt"]} for r in by_category],
        "by_direction": [{"name": r["dir"], "count": r["cnt"]} for r in by_direction],
        "by_severity": [{"name": r["severity"], "count": r["cnt"]} for r in by_severity],
        "by_source": [{"name": r["source_name"], "count": r["cnt"]} for r in by_source],
        "by_news_type": [{"name": r["nt"], "count": r["cnt"]} for r in by_news_type],
        "missing_buckets": sorted(missing_buckets, key=lambda x: x["count"]),
        "uncategorized_pct": round(cat_counts.get("uncategorized", 0) / max(total, 1) * 100, 1),
    }


# ── Dedupe Health ─────────────────────────────────────────────────────

@router.get("/dedupe")
async def dedupe_health(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cross-source collision analysis and dedupe system health."""
    # Cross-source title collisions
    collisions = (await db.execute(text("""
        SELECT title,
               COUNT(DISTINCT source_name) as src_count,
               COUNT(*) as alert_count,
               array_agg(DISTINCT source_name) as sources,
               MIN(created_at) as first_seen,
               MAX(created_at) as last_seen
        FROM alerts
        WHERE created_at >= NOW() - MAKE_INTERVAL(days => :days)
        GROUP BY title
        HAVING COUNT(DISTINCT source_name) > 1
        ORDER BY alert_count DESC
        LIMIT 20
    """), {"days": days})).mappings().all()

    # Raw-to-alert ratio per source (high raw + low alerts = waste)
    waste = (await db.execute(text("""
        SELECT s.name, COUNT(ri.id) as raw_count,
               (SELECT COUNT(*) FROM alerts a
                WHERE a.source_name = s.name
                  AND a.created_at >= NOW() - MAKE_INTERVAL(days => :days)) as alert_count
        FROM sources s
        JOIN raw_items ri ON ri.source_id = s.id
            AND ri.fetched_at >= NOW() - MAKE_INTERVAL(days => :days)
        WHERE s.enabled = true
        GROUP BY s.name, s.id
        HAVING COUNT(ri.id) > 100
        ORDER BY COUNT(ri.id) DESC
    """), {"days": days})).mappings().all()

    # Total stats
    total_raw = (await db.execute(text("""
        SELECT COUNT(*) as cnt FROM raw_items
        WHERE fetched_at >= NOW() - MAKE_INTERVAL(days => :days)
    """), {"days": days})).scalar() or 0

    total_alerts = (await db.execute(text("""
        SELECT COUNT(*) as cnt FROM alerts
        WHERE created_at >= NOW() - MAKE_INTERVAL(days => :days)
    """), {"days": days})).scalar() or 0

    return {
        "days": days,
        "total_raw_items": total_raw,
        "total_alerts": total_alerts,
        "overall_dedup_rate_pct": round((1 - total_alerts / max(total_raw, 1)) * 100, 1),
        "cross_source_collisions": [
            {
                "title": c["title"][:120],
                "source_count": c["src_count"],
                "alert_count": c["alert_count"],
                "sources": list(c["sources"]),
                "first_seen": c["first_seen"].isoformat() if c["first_seen"] else None,
                "last_seen": c["last_seen"].isoformat() if c["last_seen"] else None,
            }
            for c in collisions
        ],
        "high_waste_sources": [
            {
                "name": w["name"],
                "raw_count": w["raw_count"],
                "alert_count": w["alert_count"],
                "waste_pct": round((1 - w["alert_count"] / max(w["raw_count"], 1)) * 100, 1),
            }
            for w in waste
        ],
        "dedupe_layers": [
            {"layer": "raw_item_hash", "storage": "Redis + DB", "ttl": "24h", "risk": "none"},
            {"layer": "alert_dedupe_key", "storage": "Redis + DB", "ttl": "6h (configurable)", "risk": "none"},
            {"layer": "event_fingerprint", "storage": "Redis only", "ttl": "4h", "risk": "lost on Redis restart"},
        ],
    }


# ── Recommendations ───────────────────────────────────────────────────

@router.get("/recommendations")
async def source_recommendations(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Auto-generated recommendations for improving source diversity."""
    recommendations: list[dict[str, Any]] = []

    # 1. Over-concentration: any single source > 25% of alerts
    conc = (await db.execute(text("""
        SELECT source_name, COUNT(*) as cnt,
               ROUND(COUNT(*)::numeric / GREATEST(
                   (SELECT COUNT(*) FROM alerts WHERE created_at >= NOW() - MAKE_INTERVAL(days => :days)),
                   1) * 100, 1) as pct
        FROM alerts WHERE created_at >= NOW() - MAKE_INTERVAL(days => :days)
        GROUP BY source_name
        HAVING COUNT(*)::numeric / GREATEST(
            (SELECT COUNT(*) FROM alerts WHERE created_at >= NOW() - MAKE_INTERVAL(days => :days)),
            1) > 0.25
        ORDER BY cnt DESC
    """), {"days": days})).mappings().all()

    for c in conc:
        recommendations.append({
            "type": "over_concentration",
            "severity": "warning",
            "title_fa": f"تمرکز بیش از حد بر {c['source_name']}",
            "detail": f"{c['source_name']} produces {c['pct']}% of all alerts ({c['cnt']} alerts in {days}d). Consider adding more diverse sources.",
            "action": "add_sources",
            "source_name": c["source_name"],
        })

    # 2. Low match rate (raw > 500, match rate < 1%)
    low_match = (await db.execute(text("""
        SELECT s.name, COUNT(ri.id) as raw_count,
               (SELECT COUNT(*) FROM alerts a WHERE a.source_name = s.name
                AND a.created_at >= NOW() - MAKE_INTERVAL(days => :days)) as alert_count
        FROM sources s
        JOIN raw_items ri ON ri.source_id = s.id
            AND ri.fetched_at >= NOW() - MAKE_INTERVAL(days => :days)
        WHERE s.enabled = true
        GROUP BY s.name, s.id
        HAVING COUNT(ri.id) > 500
           AND (SELECT COUNT(*) FROM alerts a WHERE a.source_name = s.name
                AND a.created_at >= NOW() - MAKE_INTERVAL(days => :days))::numeric / COUNT(ri.id) < 0.01
        ORDER BY COUNT(ri.id) DESC
    """), {"days": days})).mappings().all()

    for lm in low_match:
        rate = round(lm["alert_count"] / max(lm["raw_count"], 1) * 100, 2)
        recommendations.append({
            "type": "low_match_rate",
            "severity": "info",
            "title_fa": f"نرخ تطبیق پایین: {lm['name']}",
            "detail": f"{lm['name']}: {lm['raw_count']} raw items but only {lm['alert_count']} alerts ({rate}%). Consider adding relevant keywords or adjusting poll interval.",
            "action": "adjust_rules",
            "source_name": lm["name"],
        })

    # 3. Missing coverage buckets (< 3 alerts)
    cat_counts = (await db.execute(text("""
        SELECT COALESCE(NULLIF(event_category, ''), 'uncategorized') as cat, COUNT(*) as cnt
        FROM alerts WHERE created_at >= NOW() - MAKE_INTERVAL(days => :days)
        GROUP BY cat
    """), {"days": days})).mappings().all()
    cat_map = {r["cat"]: r["cnt"] for r in cat_counts}

    for key, label in COVERAGE_BUCKETS.items():
        cnt = cat_map.get(key, 0)
        if cnt < 3:
            recommendations.append({
                "type": "missing_bucket",
                "severity": "warning" if cnt == 0 else "info",
                "title_fa": f"پوشش ناکافی: {label}",
                "detail": f"Only {cnt} alerts in '{key}' bucket in {days}d. Add specialized sources or rules for this category.",
                "action": "enable_source",
                "bucket": key,
            })

    # 4. Uncategorized alerts > 30%
    total_alerts = sum(r["cnt"] for r in cat_counts)
    uncat = cat_map.get("uncategorized", 0)
    if total_alerts > 0 and uncat / total_alerts > 0.3:
        recommendations.append({
            "type": "high_uncategorized",
            "severity": "warning",
            "title_fa": "درصد بالای هشدارهای بدون دسته‌بندی",
            "detail": f"{round(uncat / total_alerts * 100, 1)}% of alerts have no event_category. Improve classification rules.",
            "action": "improve_classification",
        })

    # 5. Disabled sources that could help
    disabled = (await db.execute(text("""
        SELECT id, name, base_url, categories FROM sources WHERE enabled = false ORDER BY name
    """))).mappings().all()

    if disabled:
        recommendations.append({
            "type": "disabled_sources",
            "severity": "info",
            "title_fa": f"{len(disabled)} منبع غیرفعال وجود دارد",
            "detail": f"Consider re-enabling: {', '.join(d['name'] for d in disabled[:5])}{'...' if len(disabled) > 5 else ''}",
            "action": "enable_source",
            "disabled_sources": [
                {"id": str(d["id"]), "name": d["name"], "base_url": d["base_url"]}
                for d in disabled
            ],
        })

    return {
        "days": days,
        "recommendations": recommendations,
        "total_recommendations": len(recommendations),
    }


# ── Source Tags ───────────────────────────────────────────────────────

@router.post("/source-tags")
async def manage_source_tag(
    body: TagAction,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Add or remove a tag from a source."""
    if body.tag not in COVERAGE_BUCKETS:
        return {"ok": False, "error": f"Invalid tag '{body.tag}'. Must be one of: {list(COVERAGE_BUCKETS.keys())}"}

    if body.action == "add":
        await db.execute(text("""
            INSERT INTO source_tags (id, source_id, tag)
            VALUES (:id, :sid, :tag)
            ON CONFLICT (source_id, tag) DO NOTHING
        """), {"id": str(uuid.uuid4()), "sid": body.source_id, "tag": body.tag})
        await db.commit()
        return {"ok": True, "action": "added", "source_id": body.source_id, "tag": body.tag}
    elif body.action == "remove":
        await db.execute(text("""
            DELETE FROM source_tags WHERE source_id = :sid AND tag = :tag
        """), {"sid": body.source_id, "tag": body.tag})
        await db.commit()
        return {"ok": True, "action": "removed", "source_id": body.source_id, "tag": body.tag}
    else:
        return {"ok": False, "error": f"Invalid action '{body.action}'. Must be 'add' or 'remove'."}
