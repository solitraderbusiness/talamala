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
]
