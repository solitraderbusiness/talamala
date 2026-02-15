"""
Tool definitions for the AI chat widget.

These define the functions the LLM can call to query our database.
"""

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_news",
            "description": "Search and filter news articles/alerts from our database. Use this for any question about news, events, or developments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keywords in Persian or English (e.g., 'جنگ', 'فدرال رزرو', 'تحریم', 'China gold')",
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Start date filter in YYYY-MM-DD format. Use for queries like 'امروز' (today), 'دیروز' (yesterday), 'این هفته' (this week)",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "End date filter in YYYY-MM-DD format",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Severity level filter. Use 'high' for important/critical news.",
                    },
                    "asset": {
                        "type": "string",
                        "enum": ["global_gold", "iran_gold", "coin", "gold_funds", "all"],
                        "description": "Filter by which asset section the news affects. Default 'all'",
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["date", "severity", "confidence"],
                        "description": "How to sort results. Default 'date'",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of results to return. Default 10, max 20",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_calendar_events",
            "description": "Get economic calendar events (e.g., NFP, CPI, Fed meetings, FOMC). Use for questions about upcoming or past economic data releases.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "End date in YYYY-MM-DD format",
                    },
                    "impact": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Filter by impact level. For 'important' queries, use 'high'",
                    },
                    "country": {
                        "type": "string",
                        "description": "Filter by country (e.g., 'US', 'EU', 'CN', 'IR')",
                    },
                    "search": {
                        "type": "string",
                        "description": "Search event name (e.g., 'NFP', 'CPI', 'نرخ بهره')",
                    },
                    "upcoming_only": {
                        "type": "boolean",
                        "description": "If true, only return future events. Default false",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results. Default 10",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_price_data",
            "description": "Get current price data for assets. Use for price checks and current market data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "asset": {
                        "type": "string",
                        "enum": ["gold_global", "gold_18k", "usd", "emami_coin", "all"],
                        "description": "Which asset's price to fetch. Use 'all' for all prices.",
                    },
                },
                "required": ["asset"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_news_summary",
            "description": "Get a summary/overview of news for a specific time period. Use when user asks for a general overview or 'what happened today/this week'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["today", "yesterday", "this_week", "last_week", "this_month"],
                        "description": "Time period for the summary",
                    },
                    "asset": {
                        "type": "string",
                        "enum": ["global_gold", "iran_gold", "coin", "gold_funds", "all"],
                        "description": "Focus on specific asset section. Default 'all'",
                    },
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sentiment",
            "description": "Get current market sentiment score and analysis for gold. Use when user asks about market mood, sentiment, or overall feeling.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timeframe": {
                        "type": "string",
                        "enum": ["1h", "4h", "24h"],
                        "description": "Timeframe for sentiment. Default '24h'",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_videos",
            "description": "Search curated gold-related YouTube videos. Use when user asks about videos, wants video recommendations, or asks to find a video on a topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keywords in Persian or English (e.g., 'gold price', 'تحلیل تکنیکال', 'Fed policy')",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["analysis", "news", "education", "interview", "documentary", "podcast"],
                        "description": "Filter by video category",
                    },
                    "topic": {
                        "type": "string",
                        "description": "Filter by topic slug (e.g., 'gold_price', 'fed_policy', 'technical_analysis')",
                    },
                    "outlook": {
                        "type": "string",
                        "enum": ["bullish", "bearish", "neutral", "mixed"],
                        "description": "Filter by gold outlook",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of results. Default 5, max 10",
                    },
                },
            },
        },
    },
    # ── Data Copilot tools ──────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "list_metrics",
            "description": (
                "Search available metrics by name or keyword. Use when the user asks "
                "'what metrics/data do you have?', 'چه داده‌هایی داری؟', or wants to "
                "discover what they can ask about."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Optional search keyword in Persian or English (e.g., 'ETF', 'بهره', 'dollar')",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_metric_latest",
            "description": (
                "Get the latest value of a specific metric with source, date, and freshness info. "
                "Use when user asks 'what is X now?', 'الان چنده؟', 'مقدار فعلی'. "
                "Available keys include: gold_price, dxy, vix, sp500, silver_price, btc_price, "
                "dfii10, dgs10, t10yie, fedfunds, cpi, gld_holdings, gld_change, "
                "cot_net, cot_oi, corr_gold_dxy, corr_gold_vix, corr_gold_sp500, "
                "sentiment_composite, risk_radar, "
                "gld_zscore_90d, gld_percentile_2yr, cot_wow_pct_oi, money_flow_signal."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_key": {
                        "type": "string",
                        "description": "The metric key (e.g., 'gold_price', 'dfii10', 'gld_holdings', 'cot_net')",
                    },
                },
                "required": ["metric_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_metric_range",
            "description": (
                "Get historical time series for a metric over a date range. "
                "Use when user asks about trends, history, or 'N روز اخیر', 'روند', 'تاریخچه'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_key": {
                        "type": "string",
                        "description": "The metric key (e.g., 'gold_price', 'dfii10')",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days of history. Default 30, max 365",
                    },
                },
                "required": ["metric_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_live_snapshot",
            "description": (
                "Get a complete market snapshot with all metrics, sentiment, and staleness info. "
                "Use when user asks 'وضعیت کلی بازار', 'خلاصه بازار', 'market overview', "
                "or any broad market question that needs multiple data points."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_calc_run",
            "description": (
                "Explain how a computed score (sentiment, risk, money_flow) was calculated, "
                "showing all component breakdowns. Use when user asks 'چرا', 'توضیح بده', "
                "'why is sentiment X?', 'how was this calculated?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_key": {
                        "type": "string",
                        "description": "The computed metric key: 'sentiment_composite', 'risk_radar', or 'money_flow'",
                    },
                },
                "required": ["metric_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_changes",
            "description": (
                "Get 1-day and 5-day changes (deltas) for key metrics. "
                "Use when user asks 'چه تغییر کرده؟', 'نسبت به دیروز', "
                "'what changed today?', 'deltas'."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_freshness_report",
            "description": (
                "Check which data sources are fresh or stale. "
                "Use when user asks 'کدوم داده‌ها stale هستند؟', 'کیفیت داده', "
                "'is data stale?', 'data quality'."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_analysis_snapshot",
            "description": (
                "Get a snapshot of all 6 canonical analysis indicators with scores. "
                "Use when user asks 'خلاصه تحلیل', 'شاخص‌ها چطورن؟', "
                "'analysis snapshot', 'how are indicators?', 'وضعیت شاخص‌ها'."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_indicator_detail",
            "description": (
                "Get detailed info about a specific canonical indicator. "
                "Use when user asks about one indicator in detail, e.g. "
                "'جزئیات ETF', 'COT چطوره؟', 'detail of VIX', 'شاخص دلار'. "
                "Available indicator_ids: ETF_FLOW_GLD, COT_POSITION, REAL_RATES, "
                "DOLLAR_STRENGTH, VIX_LEVEL, GOLD_PRICE_MOMENTUM."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "indicator_id": {
                        "type": "string",
                        "description": (
                            "The canonical indicator ID. One of: "
                            "ETF_FLOW_GLD, COT_POSITION, REAL_RATES, "
                            "DOLLAR_STRENGTH, VIX_LEVEL, GOLD_PRICE_MOMENTUM"
                        ),
                    },
                },
                "required": ["indicator_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_indicator",
            "description": (
                "Explain how a specific indicator score is calculated — full provenance. "
                "Use when user asks 'این امتیاز چطوری حساب شده؟', "
                "'explain calculation', 'چرا این عدده؟', 'محاسبه شاخص'. "
                "Available indicator_ids: ETF_FLOW_GLD, COT_POSITION, REAL_RATES, "
                "DOLLAR_STRENGTH, VIX_LEVEL, GOLD_PRICE_MOMENTUM."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "indicator_id": {
                        "type": "string",
                        "description": (
                            "The canonical indicator ID. One of: "
                            "ETF_FLOW_GLD, COT_POSITION, REAL_RATES, "
                            "DOLLAR_STRENGTH, VIX_LEVEL, GOLD_PRICE_MOMENTUM"
                        ),
                    },
                },
                "required": ["indicator_id"],
            },
        },
    },
]
