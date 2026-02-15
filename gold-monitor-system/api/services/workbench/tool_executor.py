"""Tool executor for the workbench — dispatches to shared and new tools."""

from __future__ import annotations

import json
import logging
import uuid as _uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.chat.tool_executor import execute_tool as execute_public_tool
from api.services.workbench.sql_guard import execute_safe_query, SQLGuardError

logger = logging.getLogger(__name__)

# Public tools handled by the existing executor
PUBLIC_TOOL_NAMES = {
    "search_news", "get_calendar_events", "get_price_data",
    "get_news_summary", "get_sentiment", "search_videos",
}

# ── Symbol labels (Persian) ──────────────────────────────────────────────
SYMBOL_LABELS: dict[str, str] = {
    "GC=F": "طلا (XAUUSD)",
    "DX-Y.NYB": "شاخص دلار (DXY)",
    "^GSPC": "S&P 500",
    "^TNX": "بازده ۱۰ ساله",
    "^VIX": "VIX",
    "BTC-USD": "بیت‌کوین",
    "SI=F": "نقره",
}

INDICATOR_LABELS: dict[str, str] = {
    "FEDFUNDS": "نرخ بهره فدرال",
    "CPIAUCSL": "شاخص CPI",
    "DFII10": "بازده واقعی ۱۰ ساله",
    "DGS10": "بازده اسمی ۱۰ ساله",
    "T10YIE": "انتظارات تورمی ۱۰ ساله",
}

PAIR_B_LABELS: dict[str, str] = {
    "DX-Y.NYB": "دلار",
    "^GSPC": "S&P 500",
    "^VIX": "VIX",
    "BTC-USD": "بیت‌کوین",
    "SI=F": "نقره",
}


async def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    db: AsyncSession,
    prices_fetcher: Any = None,
    chart_events: list | None = None,
) -> str:
    """Execute a workbench tool call and return JSON string result."""
    # Delegate public tools
    if tool_name in PUBLIC_TOOL_NAMES:
        return await execute_public_tool(
            tool_name, arguments, db, prices_fetcher=prices_fetcher,
        )

    try:
        if tool_name == "generate_chart":
            result = await _execute_generate_chart(arguments, db, chart_events)
        elif tool_name == "get_macro_overview":
            result = await _get_macro_overview(db)
        elif tool_name == "get_money_flow":
            result = await _get_money_flow(arguments, db)
        elif tool_name == "get_real_rates":
            result = await _get_real_rates(arguments, db)
        elif tool_name == "get_correlations":
            result = await _get_correlations(db)
        elif tool_name == "get_sentiment_gauge":
            result = await _get_sentiment_gauge(db)
        elif tool_name == "get_regime_status":
            result = await _get_regime_status(db)
        elif tool_name == "execute_sql_query":
            result = await _execute_sql(arguments, db)
        else:
            result = {"error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        logger.exception("Workbench tool error for %s", tool_name)
        result = {"error": f"Failed to execute {tool_name}: {str(e)}"}

    return json.dumps(result, ensure_ascii=False, default=str)


async def _get_macro_overview(db: AsyncSession) -> dict:
    from api.routers.analysis import macro_overview
    return await macro_overview()


async def _get_money_flow(args: dict, db: AsyncSession) -> dict:
    from api.routers.analysis import money_flow
    days = min(max(int(args.get("days", 90)), 7), 365)
    return await money_flow(days=days)


async def _get_real_rates(args: dict, db: AsyncSession) -> dict:
    from api.routers.analysis import real_rates
    days = min(max(int(args.get("days", 90)), 7), 365)
    return await real_rates(days=days)


async def _get_correlations(db: AsyncSession) -> dict:
    from api.routers.analysis import correlations
    return await correlations()


async def _get_sentiment_gauge(db: AsyncSession) -> dict:
    from api.data_collection.sentiment_calculator import compute_sentiment
    return await compute_sentiment(db)


async def _get_regime_status(db: AsyncSession) -> dict:
    from sqlalchemy import select, desc
    from api.analysis.models import RegimeScore

    q = await db.execute(
        select(RegimeScore).order_by(desc(RegimeScore.ts)).limit(1)
    )
    row = q.scalar_one_or_none()
    if not row:
        return {"status": "pending", "message": "No regime data available"}

    return {
        "ts": str(row.ts),
        "chosen_regime": row.chosen_regime,
        "probabilities": {
            "expansion": round(row.smoothed_p_expansion or row.p_expansion or 0, 3),
            "tightening": round(row.smoothed_p_tightening or row.p_tightening or 0, 3),
            "stress": round(row.smoothed_p_stress or row.p_stress or 0, 3),
            "recovery": round(row.smoothed_p_recovery or row.p_recovery or 0, 3),
        },
        "indices": {
            "liquidity_stress": round(row.liquidity_stress_index or 0, 3),
            "usd_pressure": round(row.usd_pressure_index or 0, 3),
            "real_yield_pressure": round(row.real_yield_pressure_index or 0, 3),
        },
    }


async def _execute_sql(args: dict, db: AsyncSession) -> dict:
    query = args.get("query", "")
    explanation = args.get("explanation", "")
    logger.info("Workbench SQL: %s | %s", explanation, query[:200])

    try:
        return await execute_safe_query(db, query)
    except SQLGuardError as e:
        return {"error": str(e)}


# ── Chart generation ─────────────────────────────────────────────────────

def _clamp_days(args: dict, default: int = 90, maximum: int = 365) -> int:
    return min(max(int(args.get("days", default)), 7), maximum)


def _chart_spec(
    chart_type: str,
    title_fa: str,
    x_key: str,
    y_keys: list[str],
    y_labels: dict[str, str],
    data: list[dict],
    unit: str = "",
) -> dict:
    return {
        "chart_id": str(_uuid.uuid4()),
        "chart_type": chart_type,
        "title_fa": title_fa,
        "x_key": x_key,
        "y_keys": y_keys,
        "y_labels": y_labels,
        "data": data,
        "unit": unit,
    }


async def _execute_generate_chart(
    args: dict,
    db: AsyncSession,
    chart_events: list | None,
) -> dict:
    """Fetch data, build chart spec, push to chart_events, return text summary."""
    query_type = args.get("query_type", "")
    chart_type_override = args.get("chart_type")

    handler = _CHART_HANDLERS.get(query_type)
    if not handler:
        return {"error": f"Unknown query_type: {query_type}"}

    spec, summary = await handler(args, db)
    if not spec:
        return {"error": summary or "No data available for chart."}

    if chart_type_override and chart_type_override in ("line", "bar", "area"):
        spec["chart_type"] = chart_type_override

    if chart_events is not None:
        chart_events.append(spec)

    return {"chart_generated": True, "summary": summary}


# ── Individual chart query handlers ──────────────────────────────────────

async def _chart_gold_price(args: dict, db: AsyncSession):
    from api.analysis.models import AssetPriceDaily

    days = _clamp_days(args)
    cutoff = date.today() - timedelta(days=days)
    q = await db.execute(
        select(AssetPriceDaily)
        .where(AssetPriceDaily.symbol == "GC=F", AssetPriceDaily.trade_date >= cutoff)
        .order_by(AssetPriceDaily.trade_date)
    )
    rows = q.scalars().all()
    if not rows:
        return None, "داده‌ای برای قیمت طلا موجود نیست."

    data = [{"date": str(r.trade_date), "price": round(r.close, 2)} for r in rows]
    first, last = rows[0].close, rows[-1].close
    change_pct = round((last - first) / first * 100, 2) if first else 0

    spec = _chart_spec(
        "line", f"قیمت طلا — {days} روز اخیر",
        "date", ["price"], {"price": "قیمت (USD)"}, data, "USD",
    )
    summary = (
        f"نمودار قیمت طلا در {days} روز اخیر: "
        f"از {first:,.2f}$ به {last:,.2f}$ (تغییر {change_pct:+.2f}%). "
        f"تعداد نقاط: {len(data)}"
    )
    return spec, summary


async def _chart_dxy(args: dict, db: AsyncSession):
    from api.analysis.models import AssetPriceDaily

    days = _clamp_days(args)
    cutoff = date.today() - timedelta(days=days)
    q = await db.execute(
        select(AssetPriceDaily)
        .where(AssetPriceDaily.symbol == "DX-Y.NYB", AssetPriceDaily.trade_date >= cutoff)
        .order_by(AssetPriceDaily.trade_date)
    )
    rows = q.scalars().all()
    if not rows:
        return None, "داده‌ای برای شاخص دلار موجود نیست."

    data = [{"date": str(r.trade_date), "dxy": round(r.close, 2)} for r in rows]
    first, last = rows[0].close, rows[-1].close
    change_pct = round((last - first) / first * 100, 2) if first else 0

    spec = _chart_spec(
        "line", f"شاخص دلار (DXY) — {days} روز اخیر",
        "date", ["dxy"], {"dxy": "DXY"}, data, "",
    )
    summary = (
        f"نمودار شاخص دلار در {days} روز اخیر: "
        f"از {first:.2f} به {last:.2f} (تغییر {change_pct:+.2f}%). "
        f"تعداد نقاط: {len(data)}"
    )
    return spec, summary


async def _chart_asset_comparison(args: dict, db: AsyncSession):
    from api.analysis.models import AssetPriceDaily

    days = _clamp_days(args)
    symbols = args.get("symbols") or ["GC=F", "DX-Y.NYB", "BTC-USD"]
    symbols = symbols[:5]  # max 5
    cutoff = date.today() - timedelta(days=days)

    q = await db.execute(
        select(AssetPriceDaily)
        .where(AssetPriceDaily.symbol.in_(symbols), AssetPriceDaily.trade_date >= cutoff)
        .order_by(AssetPriceDaily.trade_date)
    )
    rows = q.scalars().all()
    if not rows:
        return None, "داده‌ای برای مقایسه موجود نیست."

    # Group by symbol, compute normalized % change from first value
    by_symbol: dict[str, list] = {}
    for r in rows:
        by_symbol.setdefault(r.symbol, []).append(r)

    # Find all unique dates
    all_dates = sorted({str(r.trade_date) for r in rows})
    base_prices: dict[str, float] = {}
    for sym, sym_rows in by_symbol.items():
        base_prices[sym] = sym_rows[0].close if sym_rows else 1

    data = []
    for d in all_dates:
        point: dict[str, Any] = {"date": d}
        for sym in symbols:
            sym_rows = by_symbol.get(sym, [])
            match = next((r for r in sym_rows if str(r.trade_date) == d), None)
            if match and base_prices.get(sym):
                point[sym] = round((match.close - base_prices[sym]) / base_prices[sym] * 100, 2)
        data.append(point)

    y_labels = {s: SYMBOL_LABELS.get(s, s) for s in symbols}
    spec = _chart_spec(
        "line", f"مقایسه دارایی‌ها — {days} روز (تغییر درصدی)",
        "date", symbols, y_labels, data, "%",
    )
    summary_parts = []
    for sym in symbols:
        sym_rows = by_symbol.get(sym, [])
        if len(sym_rows) >= 2:
            f, l = sym_rows[0].close, sym_rows[-1].close
            pct = round((l - f) / f * 100, 2) if f else 0
            summary_parts.append(f"{SYMBOL_LABELS.get(sym, sym)}: {pct:+.2f}%")
    summary = f"مقایسه {days} روزه: " + "، ".join(summary_parts)
    return spec, summary


async def _chart_etf_holdings(args: dict, db: AsyncSession):
    from api.analysis.models import EtfHolding

    days = _clamp_days(args)
    cutoff = date.today() - timedelta(days=days)
    q = await db.execute(
        select(EtfHolding)
        .where(EtfHolding.holding_date >= cutoff)
        .order_by(EtfHolding.holding_date)
    )
    rows = q.scalars().all()
    if not rows:
        return None, "داده‌ای برای ETF موجود نیست."

    # Pivot by date
    by_date: dict[str, dict] = {}
    for r in rows:
        d = str(r.holding_date)
        if d not in by_date:
            by_date[d] = {"date": d}
        by_date[d][r.fund] = round(r.total_tonnes, 2)

    data = list(by_date.values())
    funds = sorted({r.fund for r in rows})
    y_labels = {f: f"{f} (تن)" for f in funds}

    spec = _chart_spec(
        "bar", f"موجودی ETF طلا — {days} روز اخیر",
        "date", funds, y_labels, data, "تن",
    )
    # Summary
    latest = data[-1] if data else {}
    parts = [f"{f}: {latest.get(f, '?')} تن" for f in funds]
    summary = f"موجودی فعلی ETFها: " + "، ".join(parts) + f" (بازه {days} روز)"
    return spec, summary


async def _chart_cot(args: dict, db: AsyncSession):
    from api.analysis.models import CotData

    days = _clamp_days(args, default=180)
    cutoff = date.today() - timedelta(days=days)
    q = await db.execute(
        select(CotData)
        .where(CotData.report_date >= cutoff)
        .order_by(CotData.report_date)
    )
    rows = q.scalars().all()
    if not rows:
        return None, "داده‌ای برای COT موجود نیست."

    data = [
        {"date": str(r.report_date), "net": round(r.non_commercial_net or 0)}
        for r in rows
    ]
    last_net = data[-1]["net"] if data else 0

    spec = _chart_spec(
        "bar", f"پوزیشن خالص غیرتجاری (COT) — {days} روز",
        "date", ["net"], {"net": "پوزیشن خالص"}, data, "قرارداد",
    )
    summary = (
        f"نمودار COT پوزیشن خالص: آخرین مقدار {last_net:,} قرارداد. "
        f"تعداد گزارش: {len(data)}"
    )
    return spec, summary


async def _chart_macro_indicator(args: dict, db: AsyncSession):
    from api.analysis.models import MacroIndicator

    days = _clamp_days(args)
    indicator = args.get("indicator", "DFII10")
    cutoff = date.today() - timedelta(days=days)
    q = await db.execute(
        select(MacroIndicator)
        .where(MacroIndicator.series_id == indicator, MacroIndicator.observation_date >= cutoff)
        .order_by(MacroIndicator.observation_date)
    )
    rows = q.scalars().all()
    if not rows:
        return None, f"داده‌ای برای {indicator} موجود نیست."

    data = [
        {"date": str(r.observation_date), "value": round(r.value, 4)}
        for r in rows
    ]
    label = INDICATOR_LABELS.get(indicator, indicator)

    spec = _chart_spec(
        "line", f"{label} — {days} روز اخیر",
        "date", ["value"], {"value": label}, data, "%",
    )
    first_val, last_val = rows[0].value, rows[-1].value
    summary = (
        f"نمودار {label}: از {first_val:.4f} به {last_val:.4f}. "
        f"تعداد نقاط: {len(data)}"
    )
    return spec, summary


async def _chart_sentiment(args: dict, db: AsyncSession):
    from api.data_collection.models import SentimentTimeline

    days = _clamp_days(args, default=7, maximum=30)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    q = await db.execute(
        select(SentimentTimeline)
        .where(SentimentTimeline.recorded_at >= cutoff)
        .order_by(SentimentTimeline.recorded_at)
    )
    rows = q.scalars().all()
    if not rows:
        return None, "داده‌ای برای سنتیمنت موجود نیست."

    # Downsample: keep every Nth point if too many
    step = max(1, len(rows) // 200)
    sampled = rows[::step]

    data = [
        {
            "date": r.recorded_at.strftime("%m/%d %H:%M") if r.recorded_at else "",
            "sentiment": r.composite_score,
            "price": round(r.gold_price, 2) if r.gold_price else None,
        }
        for r in sampled
    ]

    spec = _chart_spec(
        "area", f"سنتیمنت و قیمت طلا — {days} روز اخیر",
        "date", ["sentiment", "price"], {"sentiment": "سنتیمنت (0-100)", "price": "قیمت طلا"}, data, "",
    )
    avg_sent = round(sum(r.composite_score or 0 for r in rows) / len(rows), 1) if rows else 0
    summary = (
        f"نمودار سنتیمنت {days} روزه: میانگین {avg_sent}/100. "
        f"تعداد نقاط: {len(sampled)}"
    )
    return spec, summary


async def _chart_correlation(args: dict, db: AsyncSession):
    from api.analysis.models import CorrelationCache

    days = _clamp_days(args)
    cutoff = date.today() - timedelta(days=days)
    q = await db.execute(
        select(CorrelationCache)
        .where(
            CorrelationCache.pair_a == "GC=F",
            CorrelationCache.computed_date >= cutoff,
        )
        .order_by(CorrelationCache.computed_date)
    )
    rows = q.scalars().all()
    if not rows:
        return None, "داده‌ای برای همبستگی موجود نیست."

    # Group by date, pivoting pair_b into columns
    by_date: dict[str, dict] = {}
    pair_bs: set[str] = set()
    for r in rows:
        d = str(r.computed_date)
        if d not in by_date:
            by_date[d] = {"date": d}
        by_date[d][r.pair_b] = round(r.correlation, 3)
        pair_bs.add(r.pair_b)

    data = list(by_date.values())
    pair_bs_sorted = sorted(pair_bs)
    y_labels = {p: PAIR_B_LABELS.get(p, p) for p in pair_bs_sorted}

    spec = _chart_spec(
        "line", f"همبستگی طلا با سایر دارایی‌ها — {days} روز",
        "date", pair_bs_sorted, y_labels, data, "",
    )
    # Latest values
    latest = data[-1] if data else {}
    parts = [f"{PAIR_B_LABELS.get(p, p)}: {latest.get(p, '?')}" for p in pair_bs_sorted]
    summary = f"آخرین همبستگی‌ها: " + "، ".join(parts)
    return spec, summary


_CHART_HANDLERS = {
    "gold_price_history": _chart_gold_price,
    "dxy_history": _chart_dxy,
    "asset_comparison": _chart_asset_comparison,
    "etf_holdings": _chart_etf_holdings,
    "cot_net_position": _chart_cot,
    "macro_indicator": _chart_macro_indicator,
    "sentiment_timeline": _chart_sentiment,
    "correlation_history": _chart_correlation,
}
