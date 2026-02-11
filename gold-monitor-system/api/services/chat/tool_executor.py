"""
Tool executor — maps LLM tool calls to actual database queries.

Each function takes sanitized parameters and returns clean JSON-serializable data.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, func, or_, select, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Alert, EconomicEvent, SentimentScore

logger = logging.getLogger(__name__)

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

    # Try to fetch from Redis cache or live API
    try:
        if prices_fetcher:
            prices = await prices_fetcher()
            if prices and isinstance(prices, dict):
                price_data = prices.get("prices", {})
                if asset == "all":
                    return {
                        "prices": price_data,
                        "source": prices.get("source", "unknown"),
                        "updated_at": prices.get("updated_at"),
                    }
                elif asset in price_data:
                    return {
                        "prices": {asset: price_data[asset]},
                        "source": prices.get("source", "unknown"),
                        "updated_at": prices.get("updated_at"),
                    }
                else:
                    return {"error": f"Asset '{asset}' not found in price data"}
    except Exception as e:
        logger.warning("Price fetch failed: %s", e)

    return {"error": "Price data is currently unavailable"}


# ── get_news_summary ──────────────────────────────────────────────────

async def _get_news_summary(args: dict[str, Any], db: AsyncSession) -> dict:
    period = args.get("period", "today")
    asset = args.get("asset", "all")

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

    return {
        "period": period,
        "total_news": total,
        "by_severity": severity_counts,
        "top_news": top_items,
    }


# ── get_sentiment ──────────────────────────────────────────────────────

async def _get_sentiment(args: dict[str, Any], db: AsyncSession) -> dict:
    timeframe = args.get("timeframe", "24h")
    if timeframe not in ("1h", "4h", "24h"):
        timeframe = "24h"

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

    return {
        "timeframe": timeframe,
        "available": True,
        "score": score.score,
        "sentiment": score.sentiment,
        "sentiment_label": score.sentiment_label,
        "alert_count": score.alert_count,
        "updated_at": score.created_at.isoformat() if score.created_at else None,
    }
