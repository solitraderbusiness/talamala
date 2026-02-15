"""
Tool executor — maps LLM tool calls to actual database queries.

Each function takes sanitized parameters and returns clean JSON-serializable data.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import desc, func, or_, select, cast, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.models import Alert, EconomicEvent, SentimentScore
from api.videos.models import CuratedVideo

logger = logging.getLogger(__name__)

# ── Redis cache helpers ──────────────────────────────────────────────

_redis: aioredis.Redis | None = None
CACHE_TTL = 300  # 5 minutes


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def _cache_get(key: str) -> str | None:
    try:
        r = await _get_redis()
        return await r.get(key)
    except Exception:
        return None


async def _cache_set(key: str, value: str, ttl: int = CACHE_TTL) -> None:
    try:
        r = await _get_redis()
        await r.set(key, value, ex=ttl)
    except Exception:
        pass

# ── Section mapping (mirrors alerts router logic) ──────────────────────

_RULE_SECTION_MAP: dict[str, str] = {
    "GLOB": "global_gold",
    "IR": "iran_gold",
    "COIN": "coin",
    "FUNDS": "gold_funds",
}

_GEOPOLITICS_RULES = {
    "GLOB_GEOPOL_RISK", "GLOB_EQUITY_RISK_OFF", "IR_RESERVES_SANCTIONS",
    "IR_FOREIGN_POLICY", "IR_INTERNAL_POL_SOCIAL",
}


def _alert_section(alert: Alert) -> str:
    rule_ids = alert.matched_rule_ids or []
    if not rule_ids:
        return "global_gold"
    for rid in rule_ids:
        if rid in _GEOPOLITICS_RULES:
            return "geopolitics"
    first_rule = rule_ids[0] if rule_ids else ""
    prefix = first_rule.split("_")[0] if "_" in first_rule else ""
    return _RULE_SECTION_MAP.get(prefix, "global_gold")


def _safe_int(val: Any, default: int, max_val: int) -> int:
    try:
        v = int(val)
        return min(max(v, 1), max_val)
    except (TypeError, ValueError):
        return default


def _safe_date(val: Any) -> datetime | None:
    if not val or not isinstance(val, str):
        return None
    try:
        return datetime.strptime(val.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ── Tool execution dispatcher ──────────────────────────────────────────

async def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    db: AsyncSession,
    prices_fetcher: Any = None,
) -> str:
    """Execute a tool call and return JSON string result."""
    try:
        if tool_name == "search_news":
            result = await _search_news(arguments, db)
        elif tool_name == "get_calendar_events":
            result = await _get_calendar_events(arguments, db)
        elif tool_name == "get_price_data":
            result = await _get_price_data(arguments, prices_fetcher)
        elif tool_name == "get_news_summary":
            result = await _get_news_summary(arguments, db)
        elif tool_name == "get_sentiment":
            result = await _get_sentiment(arguments, db)
        elif tool_name == "search_videos":
            result = await _search_videos(arguments, db)
        elif tool_name == "list_metrics":
            result = await _list_metrics(arguments, db)
        elif tool_name == "get_metric_latest":
            result = await _get_metric_latest(arguments, db)
        elif tool_name == "get_metric_range":
            result = await _get_metric_range(arguments, db)
        elif tool_name == "get_live_snapshot":
            result = await _get_live_snapshot(arguments, db)
        elif tool_name == "explain_calc_run":
            result = await _explain_calc_run(arguments, db)
        elif tool_name == "get_changes":
            result = await _get_changes(arguments, db)
        elif tool_name == "get_freshness_report":
            result = await _get_freshness_report(arguments, db)
        elif tool_name == "get_analysis_snapshot":
            result = await _get_analysis_snapshot(arguments, db)
        elif tool_name == "get_indicator_detail":
            result = await _get_indicator_detail(arguments, db)
        elif tool_name == "explain_indicator":
            result = await _explain_indicator(arguments, db)
        else:
            result = {"error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        logger.exception("Tool execution error for %s", tool_name)
        result = {"error": f"Failed to execute {tool_name}: {str(e)}"}

    return json.dumps(result, ensure_ascii=False, default=str)


# ── search_news ────────────────────────────────────────────────────────

async def _search_news(args: dict[str, Any], db: AsyncSession) -> dict:
    limit = _safe_int(args.get("limit"), 10, 20)
    date_from = _safe_date(args.get("date_from"))
    date_to = _safe_date(args.get("date_to"))
    query = args.get("query", "")
    severity = args.get("severity")
    asset = args.get("asset", "all")
    sort_by = args.get("sort_by", "date")

    stmt = select(Alert)

    # Date filters
    if date_from:
        stmt = stmt.where(Alert.timestamp_utc >= date_from)
    if date_to:
        end = date_to + timedelta(days=1)
        stmt = stmt.where(Alert.timestamp_utc < end)

    # Severity filter
    if severity and severity in ("high", "medium", "low"):
        stmt = stmt.where(Alert.severity == severity)

    # Text search
    if query and isinstance(query, str) and query.strip():
        search_term = f"%{query.strip()[:200]}%"
        stmt = stmt.where(
            or_(
                Alert.title.ilike(search_term),
                Alert.summary_fa.ilike(search_term),
                Alert.why_important_fa.ilike(search_term),
            )
        )

    # Sorting
    if sort_by == "severity":
        stmt = stmt.order_by(desc(Alert.severity), desc(Alert.timestamp_utc))
    elif sort_by == "confidence":
        stmt = stmt.order_by(desc(Alert.confidence), desc(Alert.timestamp_utc))
    else:
        stmt = stmt.order_by(desc(Alert.timestamp_utc))

    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    alerts = result.scalars().all()

    # Filter by asset section in Python (since section is derived from rule IDs)
    if asset and asset != "all":
        alerts = [a for a in alerts if _alert_section(a) == asset]

    items = []
    for a in alerts:
        items.append({
            "title": a.title,
            "summary_fa": a.summary_fa or "",
            "why_important_fa": a.why_important_fa or "",
            "severity": a.severity,
            "confidence": round(a.confidence, 2) if a.confidence else None,
            "source_name": a.source_name,
            "timestamp": a.timestamp_utc.isoformat() if a.timestamp_utc else None,
            "section": _alert_section(a),
        })

    return {
        "count": len(items),
        "news": items,
    }


# ── get_calendar_events ───────────────────────────────────────────────

async def _get_calendar_events(args: dict[str, Any], db: AsyncSession) -> dict:
    limit = _safe_int(args.get("limit"), 10, 20)
    date_from = _safe_date(args.get("date_from"))
    date_to = _safe_date(args.get("date_to"))
    impact = args.get("impact")
    country = args.get("country")
    search = args.get("search", "")
    upcoming_only = args.get("upcoming_only", False)

    stmt = select(EconomicEvent)

    if date_from:
        stmt = stmt.where(EconomicEvent.datetime_utc >= date_from)
    if date_to:
        end = date_to + timedelta(days=1)
        stmt = stmt.where(EconomicEvent.datetime_utc < end)

    if impact and impact in ("high", "medium", "low"):
        stmt = stmt.where(EconomicEvent.impact == impact)

    if country and isinstance(country, str):
        stmt = stmt.where(EconomicEvent.country == country.strip()[:10])

    if search and isinstance(search, str) and search.strip():
        search_term = f"%{search.strip()[:200]}%"
        stmt = stmt.where(
            or_(
                EconomicEvent.event_name.ilike(search_term),
                EconomicEvent.event_name_fa.ilike(search_term),
            )
        )

    if upcoming_only:
        stmt = stmt.where(EconomicEvent.datetime_utc > datetime.now(timezone.utc))

    stmt = stmt.order_by(EconomicEvent.datetime_utc.desc()).limit(limit)
    result = await db.execute(stmt)
    events = result.scalars().all()

    items = []
    for e in events:
        items.append({
            "event_name": e.event_name,
            "event_name_fa": e.event_name_fa or e.event_name,
            "country": e.country,
            "currency": e.currency,
            "impact": e.impact,
            "datetime_utc": e.datetime_utc.isoformat() if e.datetime_utc else None,
            "actual": e.actual,
            "forecast": e.forecast,
            "previous": e.previous,
            "category": e.category,
        })

    return {
        "count": len(items),
        "events": items,
    }


# ── get_price_data ────────────────────────────────────────────────────

async def _get_price_data(args: dict[str, Any], prices_fetcher: Any) -> dict:
    """Fetch current prices using the existing prices router logic."""
    asset = args.get("asset", "all")
    cache_key = f"chat:tool:prices:{asset}"

    # Check cache first
    cached = await _cache_get(cache_key)
    if cached:
        return json.loads(cached)

    # Try to fetch from Redis cache or live API
    try:
        if prices_fetcher:
            prices = await prices_fetcher()
            if prices and isinstance(prices, dict):
                price_data = prices.get("prices", {})
                if asset == "all":
                    result = {
                        "prices": price_data,
                        "source": prices.get("source", "unknown"),
                        "updated_at": prices.get("updated_at"),
                    }
                elif asset in price_data:
                    result = {
                        "prices": {asset: price_data[asset]},
                        "source": prices.get("source", "unknown"),
                        "updated_at": prices.get("updated_at"),
                    }
                else:
                    return {"error": f"Asset '{asset}' not found in price data"}
                await _cache_set(cache_key, json.dumps(result, ensure_ascii=False, default=str))
                return result
    except Exception as e:
        logger.warning("Price fetch failed: %s", e)

    return {"error": "Price data is currently unavailable"}


# ── get_news_summary ──────────────────────────────────────────────────

async def _get_news_summary(args: dict[str, Any], db: AsyncSession) -> dict:
    period = args.get("period", "today")
    asset = args.get("asset", "all")
    cache_key = f"chat:tool:news_summary:{period}:{asset}"

    cached = await _cache_get(cache_key)
    if cached:
        return json.loads(cached)

    now = datetime.now(timezone.utc)

    # Determine date range from period
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif period == "yesterday":
        yesterday = now - timedelta(days=1)
        start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "this_week":
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif period == "last_week":
        this_week_start = now - timedelta(days=now.weekday())
        start = this_week_start - timedelta(days=7)
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = this_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "this_month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now

    # Count by severity
    stmt = select(
        Alert.severity,
        func.count(Alert.id).label("count"),
    ).where(
        Alert.timestamp_utc >= start,
        Alert.timestamp_utc <= end,
    ).group_by(Alert.severity)

    result = await db.execute(stmt)
    severity_counts = {row.severity: row.count for row in result}

    # Get top news items
    top_stmt = select(Alert).where(
        Alert.timestamp_utc >= start,
        Alert.timestamp_utc <= end,
    ).order_by(desc(Alert.confidence), desc(Alert.timestamp_utc)).limit(5)

    result = await db.execute(top_stmt)
    top_alerts = result.scalars().all()

    # Filter by asset in Python if needed
    if asset and asset != "all":
        top_alerts = [a for a in top_alerts if _alert_section(a) == asset]

    total = sum(severity_counts.values())

    top_items = []
    for a in top_alerts:
        top_items.append({
            "title": a.title,
            "summary_fa": a.summary_fa or "",
            "severity": a.severity,
            "timestamp": a.timestamp_utc.isoformat() if a.timestamp_utc else None,
            "section": _alert_section(a),
        })

    result = {
        "period": period,
        "total_news": total,
        "by_severity": severity_counts,
        "top_news": top_items,
    }
    await _cache_set(cache_key, json.dumps(result, ensure_ascii=False, default=str))
    return result


# ── get_sentiment ──────────────────────────────────────────────────────

async def _get_sentiment(args: dict[str, Any], db: AsyncSession) -> dict:
    timeframe = args.get("timeframe", "24h")
    if timeframe not in ("1h", "4h", "24h"):
        timeframe = "24h"
    cache_key = f"chat:tool:sentiment:{timeframe}"

    cached = await _cache_get(cache_key)
    if cached:
        return json.loads(cached)

    stmt = select(SentimentScore).where(
        SentimentScore.timeframe == timeframe,
    ).order_by(desc(SentimentScore.created_at)).limit(1)

    result = await db.execute(stmt)
    score = result.scalar_one_or_none()

    if not score:
        return {
            "timeframe": timeframe,
            "available": False,
            "message": "No sentiment data available for this timeframe",
        }

    result = {
        "timeframe": timeframe,
        "available": True,
        "score": score.score,
        "sentiment": score.sentiment,
        "sentiment_label": score.sentiment_label,
        "alert_count": score.alert_count,
        "updated_at": score.created_at.isoformat() if score.created_at else None,
    }
    await _cache_set(cache_key, json.dumps(result, ensure_ascii=False, default=str))
    return result


# ── search_videos ─────────────────────────────────────────────────────

async def _search_videos(args: dict[str, Any], db: AsyncSession) -> dict:
    limit = _safe_int(args.get("limit"), 5, 10)
    query = args.get("query", "")
    category = args.get("category")
    topic = args.get("topic")
    outlook = args.get("outlook")

    stmt = select(CuratedVideo).where(CuratedVideo.is_published.is_(True))

    # Text search across multiple fields
    if query and isinstance(query, str) and query.strip():
        search_term = f"%{query.strip()[:200]}%"
        stmt = stmt.where(
            or_(
                CuratedVideo.title_original.ilike(search_term),
                CuratedVideo.title_fa.ilike(search_term),
                CuratedVideo.summary_fa.ilike(search_term),
                CuratedVideo.channel_name.ilike(search_term),
            )
        )

    if category and category in ("analysis", "news", "education", "interview", "documentary", "podcast"):
        stmt = stmt.where(CuratedVideo.category == category)

    if topic and isinstance(topic, str) and topic.strip():
        stmt = stmt.where(
            CuratedVideo.topics.op("@>")(cast(f'["{topic.strip()}"]', JSONB))
        )

    if outlook and outlook in ("bullish", "bearish", "neutral", "mixed"):
        stmt = stmt.where(CuratedVideo.gold_outlook == outlook)

    stmt = stmt.order_by(desc(CuratedVideo.published_at)).limit(limit)
    result = await db.execute(stmt)
    videos = result.scalars().all()

    items = []
    for v in videos:
        items.append({
            "id": v.id,
            "title": v.title_fa or v.title_original or v.youtube_id,
            "title_original": v.title_original,
            "channel": v.channel_name,
            "category": v.category,
            "outlook": v.gold_outlook,
            "summary_fa": (v.summary_fa or "")[:200],
            "link": f"/analysis/videos/{v.id}",
            "published_at": v.published_at.isoformat() if v.published_at else None,
        })

    return {
        "count": len(items),
        "videos": items,
    }


# ── Data Copilot tools ────────────────────────────────────────────────

async def _list_metrics(args: dict[str, Any], db: AsyncSession) -> dict:
    """Search available metrics by name or keyword."""
    from api.copilot.models import MetricRegistry

    query = (args.get("query") or "").strip()

    stmt = select(MetricRegistry)
    if query:
        search_term = f"%{query[:100]}%"
        stmt = stmt.where(
            or_(
                MetricRegistry.label_fa.ilike(search_term),
                MetricRegistry.label_en.ilike(search_term),
                MetricRegistry.key.ilike(search_term),
            )
        )
    stmt = stmt.limit(20)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    return {
        "count": len(rows),
        "metrics": [
            {
                "key": r.key,
                "label_fa": r.label_fa,
                "label_en": r.label_en,
                "unit": r.unit,
                "frequency": r.frequency,
                "source_name": r.source_name,
                "direction_for_gold": r.direction_for_gold,
            }
            for r in rows
        ],
    }


async def _get_metric_latest(args: dict[str, Any], db: AsyncSession) -> dict:
    """Get latest value of a specific metric with source and freshness."""
    from api.copilot.queries import (
        get_registry_row,
        query_calc_run_latest,
        query_metric_latest,
    )

    metric_key = (args.get("metric_key") or "").strip()
    if not metric_key:
        return {"error": "metric_key is required"}

    reg = await get_registry_row(db, metric_key)
    if not reg:
        # Try to suggest similar keys
        from api.copilot.models import MetricRegistry
        all_keys = await db.execute(
            select(MetricRegistry.key, MetricRegistry.label_fa).limit(20)
        )
        suggestions = [
            {"key": r.key, "label_fa": r.label_fa}
            for r in all_keys
        ]
        return {
            "error": f"metric '{metric_key}' not found",
            "available_metrics": suggestions,
        }

    # Money flow derived metrics (not in registry, computed on the fly)
    _MONEY_FLOW_KEYS = {"gld_zscore_90d", "gld_percentile_2yr", "cot_wow_pct_oi", "money_flow_signal"}
    if metric_key in _MONEY_FLOW_KEYS:
        try:
            from api.analysis.money_flow_service import get_money_flow_derived
            mf = await get_money_flow_derived(db)
            if metric_key == "gld_zscore_90d":
                return {
                    "key": metric_key,
                    "label_fa": "z-score تغییرات GLD (۹۰ روزه)",
                    "value": mf["etf"]["zscore_90d"],
                    "unit": "sigma",
                    "ts": mf["etf"]["latest_date"],
                    "source_name": "SPDR",
                    "is_stale": False,
                }
            elif metric_key == "gld_percentile_2yr":
                return {
                    "key": metric_key,
                    "label_fa": "صدک تغییرات GLD (۲ ساله)",
                    "value": mf["etf"]["percentile_2yr"],
                    "unit": "%",
                    "ts": mf["etf"]["latest_date"],
                    "source_name": "SPDR",
                    "is_stale": False,
                }
            elif metric_key == "cot_wow_pct_oi":
                return {
                    "key": metric_key,
                    "label_fa": "تغییر هفتگی COT (درصد بهره باز)",
                    "value": mf["cot"]["wow_change_pct_of_oi"],
                    "unit": "%",
                    "ts": mf["cot"]["latest_date"],
                    "source_name": "CFTC",
                    "is_stale": False,
                }
            else:  # money_flow_signal
                sig = mf["combined_signal"]
                return {
                    "key": metric_key,
                    "label_fa": "سیگنال ترکیبی جریان پول",
                    "value": sig["signal"],
                    "label": sig["label_fa"],
                    "confidence": sig["confidence"],
                    "reasons": sig["reasons"],
                    "unit": "signal",
                    "ts": mf["etf"]["latest_date"],
                    "source_name": "Internal",
                    "is_stale": False,
                }
        except Exception as e:
            logger.warning("Money flow derived metric failed: %s", e)
            return {"key": metric_key, "error": "computation failed"}

    # Computed metrics (sentiment, risk_radar)
    if reg.source_table == "calc_runs":
        if metric_key == "sentiment_composite":
            # Compute fresh
            try:
                from api.data_collection.sentiment_calculator import compute_sentiment
                result = await compute_sentiment(db)
                return {
                    "key": metric_key,
                    "label_fa": reg.label_fa,
                    "value": result.get("composite_score"),
                    "label": result.get("label_fa"),
                    "unit": reg.unit,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "source_name": "Internal",
                    "is_stale": False,
                    "components_summary": [
                        {
                            "name": c["name"],
                            "label_fa": c.get("label_fa"),
                            "score": c["score"],
                            "weight": c["weight"],
                        }
                        for c in result.get("components", [])
                    ],
                }
            except Exception as e:
                logger.warning("Sentiment compute failed: %s", e)
                return {"key": metric_key, "error": "computation failed"}

        if metric_key == "risk_radar":
            try:
                from api.services.analysis.risk_radar_engine import compute_risk_radar
                result = await compute_risk_radar(db)
                return {
                    "key": metric_key,
                    "label_fa": reg.label_fa,
                    "value": result.get("composite_score"),
                    "label": result.get("label"),
                    "unit": reg.unit,
                    "ts": result.get("computed_at"),
                    "source_name": "Internal",
                    "is_stale": False,
                    "components_summary": [
                        {
                            "name": c["name"],
                            "label_fa": c.get("name_fa"),
                            "score": c["score"],
                            "weight": c["weight"],
                            "confidence": c.get("confidence"),
                        }
                        for c in result.get("components_detailed", result.get("components", []))
                    ],
                    "engine_version": result.get("meta", {}).get("engine_version"),
                }
            except Exception as e:
                logger.warning("Risk radar compute failed: %s", e)
                return {"key": metric_key, "error": "computation failed"}

        # Fallback for other computed metrics
        run_type_map = {
            "sentiment_composite": "sentiment_score",
            "risk_radar": "risk_radar",
        }
        run_type = run_type_map.get(metric_key)
        if run_type:
            run = await query_calc_run_latest(db, run_type)
            if run:
                return {
                    "key": metric_key,
                    "label_fa": reg.label_fa,
                    "value": run.outputs.get("composite_score") if run.outputs else None,
                    "unit": reg.unit,
                    "ts": run.ts.isoformat() if run.ts else None,
                    "source_name": "Internal",
                    "is_stale": False,
                    "run_id": str(run.run_id),
                }
            return {"key": metric_key, "error": "no computed data available"}

    # Raw metrics from source tables
    latest = await query_metric_latest(db, reg)
    if latest:
        return latest
    return {"key": metric_key, "error": "no data available for this metric"}


async def _get_metric_range(args: dict[str, Any], db: AsyncSession) -> dict:
    """Get historical time series for a metric."""
    from api.copilot.queries import get_registry_row, query_metric_range

    metric_key = (args.get("metric_key") or "").strip()
    days = _safe_int(args.get("days"), 30, 365)

    if not metric_key:
        return {"error": "metric_key is required"}

    reg = await get_registry_row(db, metric_key)
    if not reg:
        return {"error": f"metric '{metric_key}' not found"}

    if reg.source_table == "calc_runs":
        return {"key": metric_key, "error": "history not available for computed metrics"}

    data = await query_metric_range(db, reg, days=days)
    return {
        "key": metric_key,
        "label_fa": reg.label_fa,
        "unit": reg.unit,
        "source_name": reg.source_name,
        "frequency": reg.frequency,
        "data": data,
        "count": len(data),
        "period_days": days,
    }


async def _get_live_snapshot(args: dict[str, Any], db: AsyncSession) -> dict:
    """Get complete market snapshot with all metrics."""
    from api.copilot.snapshot import build_live_snapshot

    return await build_live_snapshot(db)


async def _explain_calc_run(args: dict[str, Any], db: AsyncSession) -> dict:
    """Explain how a computed score was calculated."""
    metric_key = (args.get("metric_key") or "").strip()

    if metric_key == "money_flow":
        try:
            from api.analysis.money_flow_service import get_money_flow_derived
            mf = await get_money_flow_derived(db)
            return {
                "metric_key": metric_key,
                "run_type": "money_flow",
                "asset": "XAUUSD",
                "ts": datetime.now(timezone.utc).isoformat(),
                "outputs": {
                    "signal": mf["combined_signal"]["signal"],
                    "label_fa": mf["combined_signal"]["label_fa"],
                    "confidence": mf["combined_signal"]["confidence"],
                },
                "inputs": [
                    {
                        "name": "etf_zscore_90d",
                        "label_fa": "z-score تغییرات GLD (۹۰ روزه)",
                        "value": mf["etf"]["zscore_90d"],
                        "unit": "sigma",
                        "explanation": "انحراف تغییرات روزانه موجودی GLD از میانگین ۹۰ روزه",
                    },
                    {
                        "name": "etf_percentile_2yr",
                        "label_fa": "صدک تغییرات GLD (۲ ساله)",
                        "value": mf["etf"]["percentile_2yr"],
                        "unit": "%",
                        "explanation": "جایگاه تغییرات امروز در توزیع ۲ ساله",
                    },
                    {
                        "name": "cot_wow_pct_oi",
                        "label_fa": "تغییر هفتگی COT (% بهره باز)",
                        "value": mf["cot"]["wow_change_pct_of_oi"],
                        "unit": "%",
                        "explanation": "تغییر موقعیت خالص سفته‌بازان نسبت به بهره باز کل",
                    },
                    {
                        "name": "cot_percentile_3yr",
                        "label_fa": "صدک COT (۳ ساله)",
                        "value": mf["cot"]["percentile_3yr"],
                        "unit": "%",
                        "explanation": "جایگاه موقعیت خالص فعلی در توزیع ۳ ساله",
                    },
                ],
                "reasons": mf["combined_signal"]["reasons"],
                "scoring_method": "rule_based",
                "warnings": [],
            }
        except Exception as e:
            logger.warning("Money flow explain failed: %s", e)
            return {"metric_key": metric_key, "error": "computation failed"}

    if metric_key == "sentiment_composite":
        try:
            from api.data_collection.sentiment_calculator import compute_sentiment
            result = await compute_sentiment(db)
            return {
                "metric_key": metric_key,
                "run_type": "sentiment_score",
                "asset": "XAUUSD",
                "ts": datetime.now(timezone.utc).isoformat(),
                "outputs": {
                    "composite_score": result.get("composite_score"),
                    "label": result.get("label"),
                    "label_fa": result.get("label_fa"),
                },
                "inputs": [
                    {
                        "name": c["name"],
                        "label_fa": c.get("label_fa"),
                        "score": c["score"],
                        "weight": c["weight"],
                        "raw_value": c.get("raw_value"),
                        "raw_units": c.get("raw_units"),
                        "explanation": c.get("explanation"),
                        "percentile": c.get("percentile"),
                        "stale": c.get("stale", False),
                    }
                    for c in result.get("components", [])
                ],
                "scoring_method": result.get("scoring_method", "percentile"),
                "warnings": [],
            }
        except Exception as e:
            logger.warning("Sentiment explain failed: %s", e)
            return {"metric_key": metric_key, "error": "computation failed"}

    if metric_key == "risk_radar":
        try:
            from api.services.analysis.risk_radar_engine import compute_risk_radar
            result = await compute_risk_radar(db)
            return {
                "metric_key": metric_key,
                "run_type": "risk_radar",
                "asset": "XAUUSD",
                "ts": result.get("computed_at"),
                "outputs": {
                    "composite_score": result.get("composite_score"),
                    "label": result.get("label"),
                },
                "inputs": [
                    {
                        "name": c["name"],
                        "label_fa": c.get("name_fa"),
                        "score": c["score"],
                        "weight": c["weight"],
                        "raw_value": c.get("raw_value"),
                        "raw_units": c.get("raw_units"),
                        "explanation": c.get("explanation_fa"),
                        "percentile": c.get("percentile"),
                        "confidence": c.get("confidence"),
                        "fallback_used": c.get("fallback_used", False),
                    }
                    for c in result.get("components_detailed", result.get("components", []))
                ],
                "weights": result.get("weights"),
                "confidences": result.get("confidences"),
                "scoring_method": "percentile_zscore",
                "engine_version": result.get("meta", {}).get("engine_version"),
                "warnings": result.get("warnings", []),
                "run_id": result.get("meta", {}).get("run_id"),
            }
        except Exception as e:
            logger.warning("Risk radar explain failed: %s", e)
            return {"metric_key": metric_key, "error": "computation failed"}

    if metric_key == "momentum":
        try:
            from api.services.analysis.momentum_engine import compute_momentum
            result = await compute_momentum(db)
            return {
                "metric_key": metric_key,
                "run_type": "momentum",
                "asset": "XAUUSD",
                "ts": result.get("meta", {}).get("computed_at"),
                "outputs": {
                    "composite_score": result.get("composite_score"),
                    "direction": result.get("composite_direction"),
                    "direction_fa": result.get("composite_direction_fa"),
                },
                "inputs": [
                    {
                        "name": d["id"],
                        "label_fa": d.get("label_fa"),
                        "score": d["score"],
                        "weight": d["weight"],
                        "raw_value": d.get("raw_value"),
                        "raw_unit": d.get("raw_unit"),
                        "explanation": d.get("explanation_fa"),
                    }
                    for d in result.get("drivers", [])
                ],
                "scoring_method": "percentile_zscore",
                "engine_version": result.get("meta", {}).get("engine_version"),
                "warnings": result.get("warnings", []),
            }
        except Exception as e:
            logger.warning("Momentum explain failed: %s", e)
            return {"metric_key": metric_key, "error": "computation failed"}

    return {"error": f"explain not available for '{metric_key}'. Use 'sentiment_composite', 'risk_radar', 'momentum', or 'money_flow'."}


async def _get_changes(args: dict[str, Any], db: AsyncSession) -> dict:
    """Get 1d and 5d deltas for key metrics — reuses deltas endpoint logic."""
    try:
        from api.routers.analysis import deltas
        return await deltas()
    except Exception as e:
        logger.warning("get_changes failed: %s", e)
        return {"error": "failed to compute deltas", "deltas": []}


async def _get_freshness_report(args: dict[str, Any], db: AsyncSession) -> dict:
    """Check which data sources are fresh or stale."""
    from api.copilot.queries import compute_metric_freshness

    metrics = await compute_metric_freshness(db)

    fresh = [m for m in metrics if not m.get("is_stale")]
    stale = [m for m in metrics if m.get("is_stale")]

    return {
        "total": len(metrics),
        "fresh_count": len(fresh),
        "stale_count": len(stale),
        "metrics": metrics,
    }


# ── Canonical indicator tools ──────────────────────────────────────────

async def _get_analysis_snapshot(args: dict[str, Any], db: AsyncSession) -> dict:
    """Get a snapshot of all 6 canonical analysis indicators."""
    try:
        from api.analysis.indicator_registry import (
            INDICATORS,
            compute_all_indicators,
            indicator_to_dict,
        )

        results = await compute_all_indicators(db)
        indicators = {}
        for ind_id, result in results.items():
            defn = INDICATORS.get(ind_id)
            d = indicator_to_dict(result, defn)
            # Compact version for chat
            indicators[ind_id] = {
                "label_fa": d.get("label_fa", ind_id),
                "score": d["score"],
                "percentile": d["percentile"],
                "direction": d["direction"],
                "stale": d["stale"],
                "crowded": d["crowded"],
                "source_name": d["source_name"],
                "zscore": d["zscore"],
                "raw_value": d["raw_value"],
                "raw_units": d.get("raw_units"),
            }

        return {
            "count": len(indicators),
            "indicators": indicators,
        }
    except Exception as e:
        logger.warning("get_analysis_snapshot failed: %s", e)
        return {"error": "failed to compute analysis snapshot"}


async def _get_indicator_detail(args: dict[str, Any], db: AsyncSession) -> dict:
    """Get detailed info about a specific canonical indicator."""
    try:
        from api.analysis.indicator_registry import (
            INDICATORS,
            compute_indicator,
            indicator_to_dict,
        )

        indicator_id = (args.get("indicator_id") or "").strip().upper()

        # Try to match partial names
        _ALIASES = {
            "ETF": "ETF_FLOW_GLD",
            "GLD": "ETF_FLOW_GLD",
            "COT": "COT_POSITION",
            "RATES": "REAL_RATES",
            "REAL_RATES": "REAL_RATES",
            "DOLLAR": "DOLLAR_STRENGTH",
            "DXY": "DOLLAR_STRENGTH",
            "VIX": "VIX_LEVEL",
            "MOMENTUM": "GOLD_PRICE_MOMENTUM",
            "GOLD": "GOLD_PRICE_MOMENTUM",
        }
        indicator_id = _ALIASES.get(indicator_id, indicator_id)

        if indicator_id not in INDICATORS:
            return {
                "error": f"Unknown indicator: {indicator_id}",
                "available": list(INDICATORS.keys()),
            }

        result = await compute_indicator(db, indicator_id)
        defn = INDICATORS[indicator_id]
        return indicator_to_dict(result, defn)
    except Exception as e:
        logger.warning("get_indicator_detail failed: %s", e)
        return {"error": "failed to compute indicator detail"}


async def _explain_indicator(args: dict[str, Any], db: AsyncSession) -> dict:
    """Explain how a specific indicator score is calculated — full provenance."""
    try:
        from api.analysis.indicator_registry import (
            INDICATORS,
            compute_indicator,
            indicator_to_dict,
        )

        indicator_id = (args.get("indicator_id") or "").strip().upper()

        # Alias matching
        _ALIASES = {
            "ETF": "ETF_FLOW_GLD",
            "GLD": "ETF_FLOW_GLD",
            "COT": "COT_POSITION",
            "RATES": "REAL_RATES",
            "REAL_RATES": "REAL_RATES",
            "DOLLAR": "DOLLAR_STRENGTH",
            "DXY": "DOLLAR_STRENGTH",
            "VIX": "VIX_LEVEL",
            "MOMENTUM": "GOLD_PRICE_MOMENTUM",
            "GOLD": "GOLD_PRICE_MOMENTUM",
        }
        indicator_id = _ALIASES.get(indicator_id, indicator_id)

        if indicator_id not in INDICATORS:
            return {
                "error": f"Unknown indicator: {indicator_id}",
                "available": list(INDICATORS.keys()),
            }

        result = await compute_indicator(db, indicator_id)
        defn = INDICATORS[indicator_id]
        detail = indicator_to_dict(result, defn)

        # Build Persian explanation
        pipeline_steps = [
            f"۱. داده خام از {defn.source_name} دریافت شد",
            f"۲. تبدیل: {defn.raw_transform}",
        ]
        if detail.get("smoothing_applied"):
            pipeline_steps.append("۳. صاف‌سازی EMA اعمال شد")
        if detail.get("winsorize_bounds"):
            bounds = detail["winsorize_bounds"]
            pipeline_steps.append(f"۴. Winsorize: محدوده [{bounds[0]:.3f}, {bounds[1]:.3f}]")
        pipeline_steps.append(f"{'۵' if detail.get('winsorize_bounds') else '۴'}. صدک‌بندی: {(detail['percentile'] * 100):.0f}%")
        if defn.direction == "inverse":
            pipeline_steps.append("← جهت معکوس: مقدار بالاتر = امتیاز پایین‌تر")
        pipeline_steps.append(f"← فشرده‌سازی باند خنثی → امتیاز نهایی: {detail['score']}")

        return {
            "indicator_id": indicator_id,
            "label_fa": defn.label_fa,
            "score": detail["score"],
            "explanation_fa": "\n".join(pipeline_steps),
            "score_semantics": defn.score_semantics,
            "detail": detail,
        }
    except Exception as e:
        logger.warning("explain_indicator failed: %s", e)
        return {"error": "failed to explain indicator"}
