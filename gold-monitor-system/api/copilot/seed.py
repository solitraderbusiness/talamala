"""Seed metric_registry with ~20 core metrics.

Called on startup — uses INSERT ... ON CONFLICT UPDATE for idempotency.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("gold_monitor.copilot.seed")

# Each tuple: (key, label_fa, label_en, unit, frequency, source_name, source_id,
#               direction_for_gold, precision, source_table, source_column,
#               source_filter, ts_column, staleness_hours)
_SEED_ROWS = [
    # ── Asset prices ─────────────────────────────────────────────────
    ("gold_price", "قیمت طلا", "Gold Price", "$", "daily",
     "Yahoo Finance", "GC=F", "depends", 2,
     "asset_prices_daily", "close", '{"symbol":"GC=F"}', "trade_date", 48),

    ("dxy", "شاخص دلار", "US Dollar Index", "index", "daily",
     "Yahoo Finance", "DX-Y.NYB", "bearish_when_higher", 2,
     "asset_prices_daily", "close", '{"symbol":"DX-Y.NYB"}', "trade_date", 48),

    ("vix", "شاخص ترس (VIX)", "VIX Fear Index", "index", "daily",
     "Yahoo Finance", "^VIX", "bullish_when_higher", 2,
     "asset_prices_daily", "close", '{"symbol":"^VIX"}', "trade_date", 48),

    ("sp500", "شاخص S&P 500", "S&P 500 Index", "index", "daily",
     "Yahoo Finance", "^GSPC", "depends", 2,
     "asset_prices_daily", "close", '{"symbol":"^GSPC"}', "trade_date", 48),

    ("silver_price", "قیمت نقره", "Silver Price", "$", "daily",
     "Yahoo Finance", "SI=F", "depends", 2,
     "asset_prices_daily", "close", '{"symbol":"SI=F"}', "trade_date", 48),

    ("btc_price", "قیمت بیت\u200cکوین", "Bitcoin Price", "$", "daily",
     "Yahoo Finance", "BTC-USD", "depends", 0,
     "asset_prices_daily", "close", '{"symbol":"BTC-USD"}', "trade_date", 48),

    # ── FRED macro indicators ────────────────────────────────────────
    ("dfii10", "نرخ بهره واقعی ۱۰ ساله", "10Y Real Interest Rate", "%", "daily",
     "FRED", "DFII10", "bearish_when_higher", 2,
     "macro_indicators", "value", '{"series_id":"DFII10"}', "observation_date", 72),

    ("dgs10", "بازده اوراق ۱۰ ساله", "10Y Treasury Yield", "%", "daily",
     "FRED", "DGS10", "bearish_when_higher", 2,
     "macro_indicators", "value", '{"series_id":"DGS10"}', "observation_date", 72),

    ("t10yie", "انتظارات تورمی ۱۰ ساله", "10Y Inflation Expectations", "%", "daily",
     "FRED", "T10YIE", "bullish_when_higher", 2,
     "macro_indicators", "value", '{"series_id":"T10YIE"}', "observation_date", 72),

    ("fedfunds", "نرخ بهره فدرال", "Federal Funds Rate", "%", "monthly",
     "FRED", "FEDFUNDS", "bearish_when_higher", 2,
     "macro_indicators", "value", '{"series_id":"FEDFUNDS"}', "observation_date", 72),

    ("cpi", "شاخص قیمت مصرف\u200cکننده", "Consumer Price Index", "index", "monthly",
     "FRED", "CPIAUCSL", "depends", 1,
     "macro_indicators", "value", '{"series_id":"CPIAUCSL"}', "observation_date", 840),

    # ── ETF holdings ─────────────────────────────────────────────────
    ("gld_holdings", "موجودی صندوق GLD", "GLD Total Holdings", "tonnes", "daily",
     "SPDR", "GLD", "bullish_when_higher", 1,
     "etf_holdings", "total_tonnes", '{"fund":"GLD"}', "holding_date", 96),

    ("gld_change", "تغییر موجودی GLD", "GLD Daily Change", "tonnes", "daily",
     "SPDR", "GLD", "bullish_when_higher", 2,
     "etf_holdings", "change_tonnes", '{"fund":"GLD"}', "holding_date", 96),

    # ── COT data ─────────────────────────────────────────────────────
    ("cot_net", "موقعیت خالص COT", "COT Net Non-Commercial", "contracts", "weekly",
     "CFTC", "gold", "bullish_when_higher", 0,
     "cot_data", "non_commercial_net", '{"asset":"gold"}', "report_date", 240),

    ("cot_oi", "بهره باز COT", "COT Open Interest", "contracts", "weekly",
     "CFTC", "gold", "depends", 0,
     "cot_data", "open_interest", '{"asset":"gold"}', "report_date", 240),

    # ── Correlations ─────────────────────────────────────────────────
    ("corr_gold_dxy", "همبستگی طلا-دلار", "Gold-DXY Correlation", "coefficient", "daily",
     "Internal", None, "depends", 3,
     "correlation_cache", "correlation",
     '{"pair_a":"GC=F","pair_b":"DX-Y.NYB"}', "computed_date", 48),

    ("corr_gold_vix", "همبستگی طلا-VIX", "Gold-VIX Correlation", "coefficient", "daily",
     "Internal", None, "depends", 3,
     "correlation_cache", "correlation",
     '{"pair_a":"GC=F","pair_b":"^VIX"}', "computed_date", 48),

    ("corr_gold_sp500", "همبستگی طلا-S&P500", "Gold-S&P500 Correlation", "coefficient", "daily",
     "Internal", None, "depends", 3,
     "correlation_cache", "correlation",
     '{"pair_a":"GC=F","pair_b":"^GSPC"}', "computed_date", 48),

    # ── Money flow derived metrics ────────────────────────────────────
    ("gld_zscore_90d", "z-score تغییرات GLD", "GLD Change Z-Score (90d)", "sigma", "daily",
     "SPDR", "GLD", "bullish_when_higher", 2,
     "calc_runs", None, None, None, 96),

    ("gld_percentile_2yr", "صدک تغییرات GLD", "GLD Change Percentile (2yr)", "%", "daily",
     "SPDR", "GLD", "bullish_when_higher", 1,
     "calc_runs", None, None, None, 96),

    ("cot_wow_pct_oi", "تغییر هفتگی COT (% بهره باز)", "COT WoW Change % of OI", "%", "weekly",
     "CFTC", "gold", "bullish_when_higher", 2,
     "calc_runs", None, None, None, 240),

    ("money_flow_signal", "سیگنال ترکیبی جریان پول", "Combined Money Flow Signal", "signal", "daily",
     "Internal", None, "depends", 0,
     "calc_runs", None, None, None, 96),

    # ── Computed metrics (source_table=calc_runs, special handling) ──
    ("sentiment_composite", "شاخص احساسات", "Composite Sentiment", "score", "intraday",
     "Internal", None, "depends", 0,
     "calc_runs", None, None, None, 1),

    ("risk_radar", "شاخص ریسک", "Risk Radar", "score", "intraday",
     "Internal", None, "depends", 1,
     "calc_runs", None, None, None, 1),
]

_UPSERT_SQL = """
INSERT INTO metric_registry (
    key, label_fa, label_en, unit, frequency, source_name, source_id,
    direction_for_gold, precision, source_table, source_column,
    source_filter, ts_column, staleness_hours
) VALUES (
    :key, :label_fa, :label_en, :unit, :frequency, :source_name, :source_id,
    :direction_for_gold, :precision, :source_table, :source_column,
    CAST(:source_filter AS jsonb), :ts_column, :staleness_hours
)
ON CONFLICT (key) DO UPDATE SET
    label_fa = EXCLUDED.label_fa,
    label_en = EXCLUDED.label_en,
    unit = EXCLUDED.unit,
    frequency = EXCLUDED.frequency,
    source_name = EXCLUDED.source_name,
    source_id = EXCLUDED.source_id,
    direction_for_gold = EXCLUDED.direction_for_gold,
    precision = EXCLUDED.precision,
    source_table = EXCLUDED.source_table,
    source_column = EXCLUDED.source_column,
    source_filter = CAST(EXCLUDED.source_filter AS jsonb),
    ts_column = EXCLUDED.ts_column,
    staleness_hours = EXCLUDED.staleness_hours,
    updated_at = NOW()
"""


async def seed_metric_registry(session: AsyncSession) -> None:
    """Upsert all seed rows into metric_registry (idempotent)."""
    for row in _SEED_ROWS:
        (key, label_fa, label_en, unit, frequency, source_name, source_id,
         direction_for_gold, precision, source_table, source_column,
         source_filter, ts_column, staleness_hours) = row

        await session.execute(
            text(_UPSERT_SQL),
            {
                "key": key,
                "label_fa": label_fa,
                "label_en": label_en,
                "unit": unit,
                "frequency": frequency,
                "source_name": source_name,
                "source_id": source_id,
                "direction_for_gold": direction_for_gold,
                "precision": precision,
                "source_table": source_table,
                "source_column": source_column,
                "source_filter": source_filter,
                "ts_column": ts_column,
                "staleness_hours": staleness_hours,
            },
        )

    await session.commit()
    logger.info("Metric registry seeded (%d rows).", len(_SEED_ROWS))
