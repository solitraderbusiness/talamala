"""Metric definitions (Data Cards) and QA threshold configuration.

Seed data for the ``metric_definitions`` table, plus per-metric QA
thresholds used by the validation runner.
"""

from __future__ import annotations

import os

# Toggle verbose payload logging (default off for production)
DATA_RELIABILITY_VERBOSE = os.environ.get("DATA_RELIABILITY_VERBOSE", "false").lower() == "true"

# ── Metric Data Cards ─────────────────────────────────────────────────
# Each entry seeds one row in metric_definitions on startup.

METRIC_DEFINITIONS = [
    # Yahoo Finance prices
    {
        "metric_id": "price_gc_f",
        "display_name": "قیمت طلا (اونس)",
        "unit": "USD/oz",
        "update_frequency_minutes": 360,
        "raw_sources": [{"provider": "yahoo_finance", "endpoint": "GC=F", "params": {"interval": "1d"}}],
        "formula_steps": [
            {"step": "fetch", "description": "Fetch daily OHLCV from Yahoo Finance"},
            {"step": "store", "description": "Insert new rows, skip existing dates"},
        ],
        "dependencies": [],
    },
    {
        "metric_id": "price_dxy",
        "display_name": "شاخص دلار",
        "unit": "index",
        "update_frequency_minutes": 360,
        "raw_sources": [{"provider": "yahoo_finance", "endpoint": "DX-Y.NYB", "params": {"interval": "1d"}}],
        "formula_steps": [
            {"step": "fetch", "description": "Fetch daily OHLCV from Yahoo Finance"},
            {"step": "store", "description": "Insert new rows, skip existing dates"},
        ],
        "dependencies": [],
    },
    {
        "metric_id": "price_vix",
        "display_name": "شاخص ترس (VIX)",
        "unit": "index",
        "update_frequency_minutes": 360,
        "raw_sources": [{"provider": "yahoo_finance", "endpoint": "^VIX", "params": {"interval": "1d"}}],
        "formula_steps": [
            {"step": "fetch", "description": "Fetch daily OHLCV from Yahoo Finance"},
            {"step": "store", "description": "Insert new rows, skip existing dates"},
        ],
        "dependencies": [],
    },
    {
        "metric_id": "price_sp500",
        "display_name": "شاخص S&P 500",
        "unit": "index",
        "update_frequency_minutes": 360,
        "raw_sources": [{"provider": "yahoo_finance", "endpoint": "^GSPC", "params": {"interval": "1d"}}],
        "formula_steps": [
            {"step": "fetch", "description": "Fetch daily OHLCV from Yahoo Finance"},
            {"step": "store", "description": "Insert new rows, skip existing dates"},
        ],
        "dependencies": [],
    },
    {
        "metric_id": "price_tnx",
        "display_name": "بازده ۱۰ ساله",
        "unit": "%",
        "update_frequency_minutes": 360,
        "raw_sources": [{"provider": "yahoo_finance", "endpoint": "^TNX", "params": {"interval": "1d"}}],
        "formula_steps": [
            {"step": "fetch", "description": "Fetch daily OHLCV from Yahoo Finance"},
            {"step": "store", "description": "Insert new rows, skip existing dates"},
        ],
        "dependencies": [],
    },
    {
        "metric_id": "price_btc",
        "display_name": "بیت‌کوین",
        "unit": "USD",
        "update_frequency_minutes": 360,
        "raw_sources": [{"provider": "yahoo_finance", "endpoint": "BTC-USD", "params": {"interval": "1d"}}],
        "formula_steps": [
            {"step": "fetch", "description": "Fetch daily OHLCV from Yahoo Finance"},
            {"step": "store", "description": "Insert new rows, skip existing dates"},
        ],
        "dependencies": [],
    },
    {
        "metric_id": "price_silver",
        "display_name": "نقره",
        "unit": "USD/oz",
        "update_frequency_minutes": 360,
        "raw_sources": [{"provider": "yahoo_finance", "endpoint": "SI=F", "params": {"interval": "1d"}}],
        "formula_steps": [
            {"step": "fetch", "description": "Fetch daily OHLCV from Yahoo Finance"},
            {"step": "store", "description": "Insert new rows, skip existing dates"},
        ],
        "dependencies": [],
    },
    {
        "metric_id": "price_hyg",
        "display_name": "اوراق پربازده (HYG)",
        "unit": "USD",
        "update_frequency_minutes": 360,
        "raw_sources": [{"provider": "yahoo_finance", "endpoint": "HYG", "params": {"interval": "1d"}}],
        "formula_steps": [
            {"step": "fetch", "description": "Fetch daily OHLCV from Yahoo Finance"},
            {"step": "store", "description": "Insert new rows, skip existing dates"},
        ],
        "dependencies": [],
    },
    {
        "metric_id": "price_ief",
        "display_name": "اوراق خزانه (IEF)",
        "unit": "USD",
        "update_frequency_minutes": 360,
        "raw_sources": [{"provider": "yahoo_finance", "endpoint": "IEF", "params": {"interval": "1d"}}],
        "formula_steps": [
            {"step": "fetch", "description": "Fetch daily OHLCV from Yahoo Finance"},
            {"step": "store", "description": "Insert new rows, skip existing dates"},
        ],
        "dependencies": [],
    },
    # FRED macro indicators
    {
        "metric_id": "fred_fedfunds",
        "display_name": "نرخ بهره فدرال",
        "unit": "%",
        "update_frequency_minutes": 360,
        "raw_sources": [{"provider": "fred_api", "endpoint": "FEDFUNDS", "params": {"limit": 100}}],
        "formula_steps": [
            {"step": "fetch", "description": "Fetch observations from FRED API"},
            {"step": "parse", "description": "Filter missing values (marked as '.')"},
            {"step": "store", "description": "Insert new observations, skip existing"},
        ],
        "dependencies": [],
    },
    {
        "metric_id": "fred_cpi",
        "display_name": "شاخص قیمت مصرف‌کننده",
        "unit": "index",
        "update_frequency_minutes": 360,
        "raw_sources": [{"provider": "fred_api", "endpoint": "CPIAUCSL", "params": {"limit": 100}}],
        "formula_steps": [
            {"step": "fetch", "description": "Fetch observations from FRED API"},
            {"step": "parse", "description": "Filter missing values"},
            {"step": "store", "description": "Insert new observations"},
        ],
        "dependencies": [],
    },
    {
        "metric_id": "fred_dfii10",
        "display_name": "نرخ بهره واقعی ۱۰ ساله",
        "unit": "%",
        "update_frequency_minutes": 360,
        "raw_sources": [{"provider": "fred_api", "endpoint": "DFII10", "params": {"limit": 100}}],
        "formula_steps": [
            {"step": "fetch", "description": "Fetch TIPS-implied real rate"},
            {"step": "store", "description": "Insert new observations"},
        ],
        "dependencies": [],
    },
    {
        "metric_id": "fred_dgs10",
        "display_name": "بازده اسمی ۱۰ ساله",
        "unit": "%",
        "update_frequency_minutes": 360,
        "raw_sources": [{"provider": "fred_api", "endpoint": "DGS10", "params": {"limit": 100}}],
        "formula_steps": [
            {"step": "fetch", "description": "Fetch 10Y Treasury yield"},
            {"step": "store", "description": "Insert new observations"},
        ],
        "dependencies": [],
    },
    {
        "metric_id": "fred_t10yie",
        "display_name": "انتظارات تورمی ۱۰ ساله",
        "unit": "%",
        "update_frequency_minutes": 360,
        "raw_sources": [{"provider": "fred_api", "endpoint": "T10YIE", "params": {"limit": 100}}],
        "formula_steps": [
            {"step": "fetch", "description": "Fetch breakeven inflation"},
            {"step": "store", "description": "Insert new observations"},
        ],
        "dependencies": [],
    },
    # ETF holdings
    {
        "metric_id": "etf_gld",
        "display_name": "دارایی صندوق GLD",
        "unit": "tonnes",
        "update_frequency_minutes": 360,
        "raw_sources": [{"provider": "spdr_csv", "endpoint": "https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive.csv", "params": {}}],
        "formula_steps": [
            {"step": "fetch", "description": "Download SPDR daily holdings CSV"},
            {"step": "parse", "description": "Parse date + GLD Holdings (tonnes) column"},
            {"step": "delta", "description": "Calculate day-over-day change in tonnes"},
            {"step": "store", "description": "Insert daily holding record"},
        ],
        "dependencies": [],
    },
    {
        "metric_id": "etf_iau",
        "display_name": "دارایی صندوق IAU (غیرفعال)",
        "unit": "tonnes",
        "update_frequency_minutes": 360,
        "raw_sources": [],
        "formula_steps": [
            {"step": "disabled", "description": "IAU data source unreliable (yfinance sharesOutstanding). No alternative source configured."},
        ],
        "disabled": True,
        "dependencies": [],
    },
    # COT data
    {
        "metric_id": "cot_gold",
        "display_name": "موقعیت سفته‌بازان طلا",
        "unit": "contracts",
        "update_frequency_minutes": 10080,
        "raw_sources": [{"provider": "cftc", "endpoint": "deafut.txt", "params": {"contract": "088691"}}],
        "formula_steps": [
            {"step": "fetch", "description": "Download CFTC disaggregated CSV"},
            {"step": "filter", "description": "Filter for gold futures (contract 088691)"},
            {"step": "parse", "description": "Extract commercial/non-commercial positions"},
            {"step": "net", "description": "Compute net = longs - shorts"},
            {"step": "delta", "description": "Calculate week-over-week change"},
            {"step": "store", "description": "Insert weekly COT record"},
        ],
        "dependencies": [],
    },
    # Correlations
    {
        "metric_id": "corr_gold_dxy",
        "display_name": "همبستگی طلا-دلار",
        "unit": "coefficient",
        "update_frequency_minutes": 360,
        "raw_sources": [],
        "formula_steps": [
            {"step": "load", "description": "Load gold and DXY daily closes"},
            {"step": "align", "description": "Align by common trading dates"},
            {"step": "returns", "description": "Compute log-returns ln(p[t]/p[t-1])"},
            {"step": "pearson", "description": "Compute Pearson correlation on returns"},
        ],
        "dependencies": ["price_gc_f", "price_dxy"],
    },
    {
        "metric_id": "corr_gold_vix",
        "display_name": "همبستگی طلا-VIX",
        "unit": "coefficient",
        "update_frequency_minutes": 360,
        "raw_sources": [],
        "formula_steps": [
            {"step": "load", "description": "Load gold and VIX daily closes"},
            {"step": "align", "description": "Align by common trading dates"},
            {"step": "returns", "description": "Compute log-returns"},
            {"step": "pearson", "description": "Compute Pearson correlation"},
        ],
        "dependencies": ["price_gc_f", "price_vix"],
    },
    {
        "metric_id": "corr_gold_sp500",
        "display_name": "همبستگی طلا-S&P500",
        "unit": "coefficient",
        "update_frequency_minutes": 360,
        "raw_sources": [],
        "formula_steps": [
            {"step": "load", "description": "Load gold and S&P 500 daily closes"},
            {"step": "align", "description": "Align by common trading dates"},
            {"step": "returns", "description": "Compute log-returns"},
            {"step": "pearson", "description": "Compute Pearson correlation"},
        ],
        "dependencies": ["price_gc_f", "price_sp500"],
    },
    {
        "metric_id": "corr_gold_tnx",
        "display_name": "همبستگی طلا-بازده ۱۰ ساله",
        "unit": "coefficient",
        "update_frequency_minutes": 360,
        "raw_sources": [],
        "formula_steps": [
            {"step": "load", "description": "Load gold and 10Y yield daily closes"},
            {"step": "align", "description": "Align by common trading dates"},
            {"step": "returns", "description": "Compute log-returns"},
            {"step": "pearson", "description": "Compute Pearson correlation"},
        ],
        "dependencies": ["price_gc_f", "price_tnx"],
    },
    {
        "metric_id": "corr_gold_btc",
        "display_name": "همبستگی طلا-بیتکوین",
        "unit": "coefficient",
        "update_frequency_minutes": 360,
        "raw_sources": [],
        "formula_steps": [
            {"step": "load", "description": "Load gold and BTC daily closes"},
            {"step": "align", "description": "Align by common trading dates"},
            {"step": "returns", "description": "Compute log-returns"},
            {"step": "pearson", "description": "Compute Pearson correlation"},
        ],
        "dependencies": ["price_gc_f", "price_btc"],
    },
    {
        "metric_id": "corr_gold_silver",
        "display_name": "همبستگی طلا-نقره",
        "unit": "coefficient",
        "update_frequency_minutes": 360,
        "raw_sources": [],
        "formula_steps": [
            {"step": "load", "description": "Load gold and silver daily closes"},
            {"step": "align", "description": "Align by common trading dates"},
            {"step": "returns", "description": "Compute log-returns"},
            {"step": "pearson", "description": "Compute Pearson correlation"},
        ],
        "dependencies": ["price_gc_f", "price_silver"],
    },
    # Composite metrics
    {
        "metric_id": "sentiment_composite",
        "display_name": "شاخص احساسات ترکیبی",
        "unit": "score_0_100",
        "update_frequency_minutes": 5,
        "raw_sources": [],
        "formula_steps": [
            {"step": "etf_flows", "description": "5-day avg GLD change → 0-100"},
            {"step": "cot_positioning", "description": "Net speculative → 0-100"},
            {"step": "real_rates", "description": "DFII10 → 0-100 (inverse)"},
            {"step": "dollar_strength", "description": "DXY 5d change → 0-100 (inverse)"},
            {"step": "risk_sentiment", "description": "VIX → 0-100"},
            {"step": "price_momentum", "description": "Gold 10d % change → 0-100"},
            {"step": "composite", "description": "Weighted average of available components"},
        ],
        "dependencies": ["etf_gld", "cot_gold", "fred_dfii10", "price_dxy", "price_vix", "price_gc_f"],
    },
    # Regime engine
    {
        "metric_id": "regime_lsi",
        "display_name": "شاخص فشار نقدینگی",
        "unit": "zscore",
        "update_frequency_minutes": 360,
        "raw_sources": [],
        "formula_steps": [
            {"step": "fetch", "description": "Load VIX, HYG, IEF, S&P 500 prices"},
            {"step": "credit_proxy", "description": "Compute -ln(HYG/IEF)"},
            {"step": "spx_drawdown", "description": "Compute S&P 500 drawdown from rolling high"},
            {"step": "zscore", "description": "Rolling z-scores (252d window)"},
            {"step": "composite", "description": "LSI = 0.5*z_vix + 0.3*z_credit + 0.2*z_spx_dd"},
        ],
        "dependencies": ["price_vix", "price_hyg", "price_ief", "price_sp500"],
    },
    {
        "metric_id": "regime_usdx",
        "display_name": "شاخص فشار دلار",
        "unit": "zscore",
        "update_frequency_minutes": 360,
        "raw_sources": [],
        "formula_steps": [
            {"step": "fetch", "description": "Load DXY prices"},
            {"step": "return_20d", "description": "Compute 20-day log return"},
            {"step": "zscore", "description": "Rolling z-score (252d window)"},
        ],
        "dependencies": ["price_dxy"],
    },
    {
        "metric_id": "regime_rypi",
        "display_name": "شاخص فشار بهره واقعی",
        "unit": "zscore",
        "update_frequency_minutes": 360,
        "raw_sources": [],
        "formula_steps": [
            {"step": "fetch", "description": "Load DFII10 (fallback: DGS10)"},
            {"step": "zscore", "description": "Rolling z-score (252d window)"},
        ],
        "dependencies": ["fred_dfii10", "fred_dgs10"],
    },
    {
        "metric_id": "regime_composite",
        "display_name": "رژیم کلان غالب",
        "unit": "probability",
        "update_frequency_minutes": 360,
        "raw_sources": [],
        "formula_steps": [
            {"step": "score", "description": "Compute 4 regime scores from LSI, USDX, RYPI"},
            {"step": "softmax", "description": "Convert scores to probabilities"},
            {"step": "ewma", "description": "Smooth probabilities (alpha=0.2)"},
            {"step": "argmax", "description": "Select dominant regime"},
        ],
        "dependencies": ["regime_lsi", "regime_usdx", "regime_rypi"],
    },
    # Events
    {
        "metric_id": "event_etf_flow",
        "display_name": "رویداد جریان ETF",
        "unit": "event",
        "update_frequency_minutes": 30,
        "raw_sources": [],
        "formula_steps": [
            {"step": "scan", "description": "Check if ETF daily change > 3 tonnes"},
            {"step": "dedup", "description": "Skip if similar event in last 12h"},
            {"step": "generate", "description": "Create market event with impact/magnitude"},
        ],
        "dependencies": ["etf_gld", "etf_iau"],
    },
    {
        "metric_id": "event_price_move",
        "display_name": "رویداد حرکت قیمت",
        "unit": "event",
        "update_frequency_minutes": 30,
        "raw_sources": [],
        "formula_steps": [
            {"step": "scan", "description": "Check if gold daily change > 1.5%"},
            {"step": "dedup", "description": "Skip if similar event in last 12h"},
            {"step": "generate", "description": "Create market event with impact/magnitude"},
        ],
        "dependencies": ["price_gc_f"],
    },
    {
        "metric_id": "event_cot",
        "display_name": "رویداد تغییر COT",
        "unit": "event",
        "update_frequency_minutes": 30,
        "raw_sources": [],
        "formula_steps": [
            {"step": "scan", "description": "Check if COT net change > 10k contracts"},
            {"step": "dedup", "description": "Skip if similar event in last 5 days"},
            {"step": "generate", "description": "Create market event with impact/magnitude"},
        ],
        "dependencies": ["cot_gold"],
    },
]

# ── QA Thresholds per metric ──────────────────────────────────────────

METRIC_QA_CONFIG: dict[str, dict] = {
    # Prices
    "price_gc_f": {
        "hard_range": (500, 8000),
        "soft_range": (1500, 7000),
        "max_staleness_hours": 24,
        "spike_threshold_pct": 5,
    },
    "price_dxy": {
        "hard_range": (60, 150),
        "soft_range": (80, 130),
        "max_staleness_hours": 24,
        "spike_threshold_pct": 3,
    },
    "price_vix": {
        "hard_range": (5, 100),
        "soft_range": (8, 80),
        "max_staleness_hours": 24,
        "spike_threshold_pct": 30,
    },
    "price_sp500": {
        "hard_range": (1000, 12000),
        "soft_range": (3000, 9000),
        "max_staleness_hours": 24,
        "spike_threshold_pct": 5,
    },
    "price_tnx": {
        "hard_range": (0, 20),
        "soft_range": (0.5, 10),
        "max_staleness_hours": 24,
        "spike_threshold_pct": 15,
    },
    "price_btc": {
        "hard_range": (1000, 500000),
        "soft_range": (20000, 400000),
        "max_staleness_hours": 24,
        "spike_threshold_pct": 10,
    },
    "price_silver": {
        "hard_range": (5, 200),
        "soft_range": (15, 100),
        "max_staleness_hours": 24,
        "spike_threshold_pct": 8,
    },
    "price_hyg": {
        "hard_range": (30, 150),
        "soft_range": (50, 120),
        "max_staleness_hours": 24,
        "spike_threshold_pct": 5,
    },
    "price_ief": {
        "hard_range": (50, 200),
        "soft_range": (70, 150),
        "max_staleness_hours": 24,
        "spike_threshold_pct": 5,
    },
    # FRED
    "fred_fedfunds": {
        "hard_range": (0, 25),
        "soft_range": (0, 15),
        "max_staleness_hours": 48,
        "spike_threshold_pct": 20,
    },
    "fred_cpi": {
        "hard_range": (100, 500),
        "soft_range": (200, 400),
        "max_staleness_hours": 48,
        "spike_threshold_pct": 3,
    },
    "fred_dfii10": {
        "hard_range": (-5.0, 10.0),
        "soft_range": (-3.0, 5.0),
        "max_staleness_hours": 48,
        "spike_threshold_pct": 30,
    },
    "fred_dgs10": {
        "hard_range": (0, 20),
        "soft_range": (0.5, 10),
        "max_staleness_hours": 48,
        "spike_threshold_pct": 15,
    },
    "fred_t10yie": {
        "hard_range": (-2, 10),
        "soft_range": (0, 5),
        "max_staleness_hours": 48,
        "spike_threshold_pct": 20,
    },
    # ETFs
    "etf_gld": {
        "hard_range": (800, 1300),
        "soft_range": (900, 1200),
        "max_staleness_hours": 24,
        "spike_threshold_pct": 5,
    },
    # COT
    "cot_gold": {
        "hard_range": (-200000, 500000),
        "soft_range": (-100000, 400000),
        "max_staleness_hours": 192,  # weekly data
        "spike_threshold_pct": 30,
    },
    # Correlations
    "corr_gold_dxy": {"hard_range": (-1.0, 1.0), "soft_range": (-0.95, 0.95), "max_staleness_hours": 24, "spike_threshold_pct": 50},
    "corr_gold_vix": {"hard_range": (-1.0, 1.0), "soft_range": (-0.95, 0.95), "max_staleness_hours": 24, "spike_threshold_pct": 50},
    "corr_gold_sp500": {"hard_range": (-1.0, 1.0), "soft_range": (-0.95, 0.95), "max_staleness_hours": 24, "spike_threshold_pct": 50},
    "corr_gold_tnx": {"hard_range": (-1.0, 1.0), "soft_range": (-0.95, 0.95), "max_staleness_hours": 24, "spike_threshold_pct": 50},
    "corr_gold_btc": {"hard_range": (-1.0, 1.0), "soft_range": (-0.95, 0.95), "max_staleness_hours": 24, "spike_threshold_pct": 50},
    "corr_gold_silver": {"hard_range": (-1.0, 1.0), "soft_range": (-0.95, 0.95), "max_staleness_hours": 24, "spike_threshold_pct": 50},
    # Composite
    "sentiment_composite": {
        "hard_range": (0, 100),
        "soft_range": (5, 95),
        "max_staleness_hours": 1,
        "spike_threshold_pct": 20,
    },
    # Events (no range checks)
    "event_etf_flow": {"max_staleness_hours": 48},
    "event_price_move": {"max_staleness_hours": 48},
    "event_cot": {"max_staleness_hours": 192},
    # Regime engine
    "regime_lsi": {
        "hard_range": (-3, 3),
        "soft_range": (-2.5, 2.5),
        "max_staleness_hours": 24,
        "spike_threshold_pct": 50,
    },
    "regime_usdx": {
        "hard_range": (-3, 3),
        "soft_range": (-2.5, 2.5),
        "max_staleness_hours": 24,
        "spike_threshold_pct": 50,
    },
    "regime_rypi": {
        "hard_range": (-3, 3),
        "soft_range": (-2.5, 2.5),
        "max_staleness_hours": 24,
        "spike_threshold_pct": 50,
    },
    "regime_composite": {
        "hard_range": (0, 1),
        "soft_range": (0.05, 0.95),
        "max_staleness_hours": 24,
        "spike_threshold_pct": 30,
    },
}
