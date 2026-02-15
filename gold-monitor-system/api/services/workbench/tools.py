"""Tool definitions for the admin workbench chat.

Includes all 6 public chat tools plus 7 new analysis tools.
"""

from api.services.chat.tools import TOOL_DEFINITIONS as PUBLIC_TOOLS

# New analysis tools for the workbench
ANALYSIS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_macro_overview",
            "description": "Get 4 high-level summary cards: Money Flow, Real Rates, Dollar, Risk. Use for a quick macro snapshot.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_money_flow",
            "description": "Get ETF holdings (GLD, IAU) and COT positions history. Shows institutional money movement.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days of history. Default 90, max 365.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_real_rates",
            "description": "Get FRED macro indicators: Fed Funds Rate, CPI, 10Y Real Rate, Treasury Yield, Breakeven Inflation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days of history. Default 90, max 365.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_correlations",
            "description": "Get latest 30-day Pearson correlations between gold and other assets (DXY, S&P 500, VIX, BTC, Silver).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sentiment_gauge",
            "description": "Get composite 0-100 sentiment score from 6 components: ETF flow, COT, real rates, dollar, risk, momentum.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_regime_status",
            "description": "Get current macro liquidity regime (expansion/tightening/stress/recovery) with probability scores.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_sql_query",
            "description": "Execute a read-only SQL query against the database. Use for custom data exploration. Only SELECT allowed. Max 100 rows. Tables include: alerts, sources, economic_events, asset_prices_daily, macro_indicators, etf_holdings, cot_data, correlation_cache, market_events_analysis, regime_scores, sentiment_timeline, price_history, gold_articles, curated_videos, parsed_signals, consensus_snapshots.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL SELECT query to execute",
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Brief explanation of what this query does (for audit logging)",
                    },
                },
                "required": ["query", "explanation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_chart",
            "description": (
                "Generate an inline chart for the user. Use this when the user asks "
                "for a chart, graph, trend visualization, or time-series plot. "
                "Returns structured chart data that is rendered visually in the chat."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": [
                            "gold_price_history",
                            "dxy_history",
                            "asset_comparison",
                            "etf_holdings",
                            "cot_net_position",
                            "macro_indicator",
                            "sentiment_timeline",
                            "correlation_history",
                        ],
                        "description": (
                            "Type of chart query. "
                            "gold_price_history: Gold (XAUUSD) price chart. "
                            "dxy_history: Dollar Index chart. "
                            "asset_comparison: Compare multiple assets (normalized %). "
                            "etf_holdings: GLD/IAU holdings in tonnes. "
                            "cot_net_position: CFTC non-commercial net position. "
                            "macro_indicator: FRED indicator (specify with 'indicator' param). "
                            "sentiment_timeline: Composite sentiment score over time. "
                            "correlation_history: Correlation between gold and another asset."
                        ),
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days of history. Default 90, max 365.",
                    },
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Asset symbols for asset_comparison (e.g. ['GC=F', 'BTC-USD', 'SI=F']). Max 5.",
                    },
                    "indicator": {
                        "type": "string",
                        "description": "FRED series_id for macro_indicator (FEDFUNDS, CPIAUCSL, DFII10, DGS10, T10YIE).",
                    },
                    "chart_type": {
                        "type": "string",
                        "enum": ["line", "bar", "area"],
                        "description": "Chart type override. Default depends on query_type.",
                    },
                },
                "required": ["query_type"],
            },
        },
    },
]

# Combined tool definitions for workbench
WORKBENCH_TOOL_DEFINITIONS = PUBLIC_TOOLS + ANALYSIS_TOOLS
