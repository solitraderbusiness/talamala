"""Configuration for the gold articles module.

Contains article source definitions, topic labels (Persian), quality rules,
and scoring thresholds.
"""

from __future__ import annotations

import os

# ── OpenRouter config (reuses existing project config) ───────────────────

OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
ARTICLE_LLM_MODEL: str = os.environ.get(
    "ARTICLE_LLM_MODEL", "anthropic/claude-haiku-4-5-20251001"
)
ARTICLE_LLM_TEMPERATURE: float = 0.2
ARTICLE_LLM_MAX_TOKENS: int = 1500

# ── Budget limits ────────────────────────────────────────────────────────

DAILY_LLM_BUDGET_USD: float = float(os.environ.get("ARTICLE_DAILY_BUDGET", "1.0"))

# ── Scoring thresholds ──────────────────────────────────────────────────

PUBLISH_THRESHOLD: float = 55.0       # importance_score >= this → is_published
MIN_WORD_COUNT: int = 300             # articles shorter than this are rejected
MAX_ARTICLE_AGE_DAYS: int = 7         # articles older than this are rejected
ARTICLE_CONTENT_MAX_CHARS: int = 3000 # max chars sent to LLM

# ── Fetch intervals ─────────────────────────────────────────────────────

FETCH_INTERVAL_SECONDS: int = 4 * 60 * 60  # 4 hours

# ── Article sources ──────────────────────────────────────────────────────

ARTICLE_SOURCES: list[dict] = [
    # === TIER 1: Top quality, always check ===
    {
        "name": "World Gold Council",
        "name_fa": "\u0634\u0648\u0631\u0627\u06cc \u062c\u0647\u0627\u0646\u06cc \u0637\u0644\u0627",
        "url": "https://www.gold.org/goldhub/gold-focus",
        "type": "rss_or_scrape",
        "rss_url": "https://www.gold.org/rss.xml",
        "check_interval_hours": 6,
        "default_importance_boost": 15,
        "topics": ["supply_demand", "central_banks", "etf_flows", "market_outlook"],
    },
    {
        "name": "Kitco News Analysis",
        "name_fa": "\u06a9\u06cc\u062a\u06a9\u0648",
        "url": "https://www.kitco.com/news/gold/",
        "type": "rss",
        "rss_url": "https://www.kitco.com/feed/rss/news/gold",
        "check_interval_hours": 4,
        "default_importance_boost": 0,
        "topics": ["price_analysis", "market_outlook", "technical_analysis"],
    },
    {
        "name": "Reuters Commodities",
        "name_fa": "\u0631\u0648\u06cc\u062a\u0631\u0632",
        "url": "https://www.reuters.com/markets/commodities/",
        "type": "rss",
        "rss_url": "https://news.google.com/rss/search?q=site%3Areuters.com+gold+OR+%22precious+metals%22+when%3A3d&hl=en-US&gl=US&ceid=US:en",
        "check_interval_hours": 4,
        "default_importance_boost": 10,
        "topics": ["market_outlook", "central_banks", "geopolitics"],
    },
    {
        "name": "Bloomberg Commodities",
        "name_fa": "\u0628\u0644\u0648\u0645\u0628\u0631\u06af",
        "url": "https://www.bloomberg.com/commodities",
        "type": "rss_or_scrape",
        "rss_url": "https://news.google.com/rss/search?q=site%3Abloomberg.com+gold+forecast+OR+%22gold+outlook%22+when%3A3d&hl=en-US&gl=US&ceid=US:en",
        "check_interval_hours": 6,
        "default_importance_boost": 10,
        "topics": ["market_outlook", "macro", "central_banks"],
    },
    {
        "name": "Seeking Alpha - Gold",
        "name_fa": "\u0633\u06cc\u06a9\u06cc\u0646\u06af \u0622\u0644\u0641\u0627",
        "url": "https://seekingalpha.com/market-outlook/gold-and-precious-metals",
        "type": "rss_or_scrape",
        "rss_url": "https://news.google.com/rss/search?q=site%3Aseekingalpha.com+gold+analysis+when%3A3d&hl=en-US&gl=US&ceid=US:en",
        "check_interval_hours": 6,
        "default_importance_boost": 0,
        "topics": ["price_analysis", "investment_strategy", "etf_flows"],
    },
    {
        "name": "GoldSeek",
        "name_fa": "\u06af\u0644\u062f\u0633\u06cc\u06a9",
        "url": "https://www.goldseek.com/",
        "type": "rss",
        "rss_url": "https://goldseek.com/rss/news",
        "check_interval_hours": 6,
        "default_importance_boost": 0,
        "topics": ["price_analysis", "technical_analysis", "market_outlook"],
    },
    {
        "name": "Metals Focus",
        "name_fa": "\u0645\u062a\u0627\u0644\u0632 \u0641\u0648\u06a9\u0648\u0633",
        "url": "https://www.metalsfocus.com/",
        "type": "rss_or_scrape",
        "rss_url": None,
        "check_interval_hours": 12,
        "default_importance_boost": 15,
        "topics": ["supply_demand", "market_outlook"],
    },
    {
        "name": "CME Group - Gold",
        "name_fa": "\u06af\u0631\u0648\u0647 CME",
        "url": "https://www.cmegroup.com/articles.html",
        "type": "scrape",
        "rss_url": None,
        "check_interval_hours": 12,
        "default_importance_boost": 10,
        "topics": ["futures", "technical_analysis", "market_structure"],
    },
    {
        "name": "Sprott",
        "name_fa": "\u0627\u0633\u067e\u0631\u0627\u062a",
        "url": "https://sprott.com/insights/",
        "type": "rss_or_scrape",
        "rss_url": "https://sprott.com/insights/feed/",
        "check_interval_hours": 12,
        "default_importance_boost": 5,
        "topics": ["investment_strategy", "market_outlook", "mine_supply"],
    },
    {
        "name": "Zero Hedge - Commodities",
        "name_fa": "\u0632\u06cc\u0631\u0648 \u0647\u062c",
        "url": "https://www.zerohedge.com/commodities",
        "type": "rss",
        "rss_url": "https://feeds.feedburner.com/zerohedge/feed",
        "check_interval_hours": 6,
        "default_importance_boost": -5,
        "topics": ["macro", "geopolitics", "price_analysis"],
    },
    {
        "name": "Investing.com - Gold Analysis",
        "name_fa": "\u0627\u06cc\u0646\u0648\u0633\u062a\u06cc\u0646\u06af",
        "url": "https://www.investing.com/analysis/commodities",
        "type": "rss_or_scrape",
        "rss_url": "https://www.investing.com/rss/news_14.rss",
        "check_interval_hours": 6,
        "default_importance_boost": 0,
        "topics": ["technical_analysis", "price_analysis"],
    },
    {
        "name": "FXStreet - Gold",
        "name_fa": "\u0627\u0641\u200c\u0627\u06cc\u06a9\u0633 \u0627\u0633\u062a\u0631\u06cc\u062a",
        "url": "https://www.fxstreet.com/analysis/gold",
        "type": "rss",
        "rss_url": "https://www.fxstreet.com/rss/news",
        "check_interval_hours": 6,
        "default_importance_boost": 0,
        "topics": ["technical_analysis", "price_analysis"],
    },
    # === TIER 2: Bank research ===
    {
        "name": "State Street - Gold Monitor",
        "name_fa": "\u0627\u0633\u062a\u06cc\u062a \u0627\u0633\u062a\u0631\u06cc\u062a",
        "url": "https://www.ssga.com/us/en/intermediary/insights/gold",
        "type": "scrape",
        "rss_url": None,
        "check_interval_hours": 24,
        "default_importance_boost": 15,
        "topics": ["investment_strategy", "market_outlook", "etf_flows"],
    },
    {
        "name": "UBS Gold Outlook",
        "name_fa": "UBS",
        "url": "https://www.ubs.com/global/en/wealth-management/insights.html",
        "type": "scrape",
        "rss_url": None,
        "check_interval_hours": 24,
        "default_importance_boost": 15,
        "topics": ["market_outlook", "price_forecast"],
    },
]

# ── Topic labels in Persian ──────────────────────────────────────────────

TOPIC_LABELS_FA: dict[str, str] = {
    "fed_policy": "\u0633\u06cc\u0627\u0633\u062a \u0641\u062f\u0631\u0627\u0644 \u0631\u0632\u0631\u0648",
    "ecb_policy": "\u0633\u06cc\u0627\u0633\u062a \u0628\u0627\u0646\u06a9 \u0645\u0631\u06a9\u0632\u06cc \u0627\u0631\u0648\u067e\u0627",
    "china_demand": "\u062a\u0642\u0627\u0636\u0627\u06cc \u0686\u06cc\u0646",
    "india_demand": "\u062a\u0642\u0627\u0636\u0627\u06cc \u0647\u0646\u062f",
    "central_banks": "\u0628\u0627\u0646\u06a9\u200c\u0647\u0627\u06cc \u0645\u0631\u06a9\u0632\u06cc",
    "etf_flows": "\u062c\u0631\u06cc\u0627\u0646 ETF",
    "mine_supply": "\u0639\u0631\u0636\u0647 \u0645\u0639\u062f\u0646\u06cc",
    "geopolitics": "\u0698\u0626\u0648\u067e\u0644\u06cc\u062a\u06cc\u06a9",
    "sanctions": "\u062a\u062d\u0631\u06cc\u0645\u200c\u0647\u0627",
    "inflation": "\u062a\u0648\u0631\u0645",
    "dollar": "\u062f\u0644\u0627\u0631",
    "technical_analysis": "\u062a\u062d\u0644\u06cc\u0644 \u062a\u06a9\u0646\u06cc\u06a9\u0627\u0644",
    "price_forecast": "\u067e\u06cc\u0634\u200c\u0628\u06cc\u0646\u06cc \u0642\u06cc\u0645\u062a",
    "investment_strategy": "\u0627\u0633\u062a\u0631\u0627\u062a\u0698\u06cc \u0633\u0631\u0645\u0627\u06cc\u0647\u200c\u06af\u0630\u0627\u0631\u06cc",
    "silver": "\u0646\u0642\u0631\u0647",
    "oil": "\u0646\u0641\u062a",
    "crypto_correlation": "\u0647\u0645\u0628\u0633\u062a\u06af\u06cc \u0631\u0645\u0632\u0627\u0631\u0632",
    "de_dollarization": "\u062f\u0644\u0627\u0631\u0632\u062f\u0627\u06cc\u06cc",
    "supply_demand": "\u0639\u0631\u0636\u0647 \u0648 \u062a\u0642\u0627\u0636\u0627",
    "macro": "\u06a9\u0644\u0627\u0646 \u0627\u0642\u062a\u0635\u0627\u062f\u06cc",
    "market_outlook": "\u0686\u0634\u0645\u200c\u0627\u0646\u062f\u0627\u0632 \u0628\u0627\u0632\u0627\u0631",
    "price_analysis": "\u062a\u062d\u0644\u06cc\u0644 \u0642\u06cc\u0645\u062a",
    "futures": "\u0642\u0631\u0627\u0631\u062f\u0627\u062f\u0647\u0627\u06cc \u0622\u062a\u06cc",
    "market_structure": "\u0633\u0627\u062e\u062a\u0627\u0631 \u0628\u0627\u0632\u0627\u0631",
}

# ── Outlook labels in Persian ────────────────────────────────────────────

OUTLOOK_LABELS_FA: dict[str, str] = {
    "bullish": "\u0635\u0639\u0648\u062f\u06cc",
    "bearish": "\u0646\u0632\u0648\u0644\u06cc",
    "neutral": "\u062e\u0646\u062b\u06cc",
    "mixed": "\u062a\u0631\u06a9\u06cc\u0628\u06cc",
}

# ── Time horizon labels ──────────────────────────────────────────────────

TIME_HORIZON_LABELS_FA: dict[str, str] = {
    "short_term": "\u06a9\u0648\u062a\u0627\u0647\u200c\u0645\u062f\u062a",
    "medium_term": "\u0645\u06cc\u0627\u0646\u200c\u0645\u062f\u062a",
    "long_term": "\u0628\u0644\u0646\u062f\u0645\u062f\u062a",
}

# ── Asset labels ─────────────────────────────────────────────────────────

ASSET_LABELS_FA: dict[str, str] = {
    "xauusd": "\u0637\u0644\u0627\u06cc \u062c\u0647\u0627\u0646\u06cc XAU/USD",
    "iran_gold": "\u0637\u0644\u0627\u06cc \u0627\u06cc\u0631\u0627\u0646",
    "usd_irr": "\u062f\u0644\u0627\u0631/\u0631\u06cc\u0627\u0644",
    "silver": "\u0646\u0642\u0631\u0647",
    "dxy": "\u0634\u0627\u062e\u0635 \u062f\u0644\u0627\u0631",
    "oil": "\u0646\u0641\u062a",
    "btc": "\u0628\u06cc\u062a\u200c\u06a9\u0648\u06cc\u0646",
}

# ── Auto-boost source names ─────────────────────────────────────────────

AUTO_BOOST_SOURCES: set[str] = {
    "World Gold Council",
    "Goldman Sachs",
    "JPMorgan",
    "UBS",
    "Citi",
    "HSBC",
    "State Street",
    "Metals Focus",
}

# ── Gold keywords for filtering non-gold articles from generic feeds ─────

GOLD_KEYWORDS: list[str] = [
    "gold", "xau", "bullion", "precious metal", "gold price",
    "gold forecast", "gold outlook", "gold demand", "gold supply",
    "central bank gold", "gold etf", "gold futures", "gold rally",
    "gold mine", "gold mining", "safe haven", "gold reserve",
]

# ── LLM scoring prompt ──────────────────────────────────────────────────

ARTICLE_SCORING_SYSTEM_PROMPT = """\
You are a gold market analyst. Read the article and evaluate it.

Respond in JSON only — no markdown fences, no commentary.

The JSON object must have exactly these keys:
{
  "is_important": true/false,
  "importance_score": 0-100,
  "importance_reason": "why this article matters for gold traders (1 sentence, English)",
  "gold_outlook": "bullish" or "bearish" or "neutral" or "mixed",
  "time_horizon": "short_term" or "medium_term" or "long_term",
  "topics": ["fed_policy", "china_demand", ...],
  "affected_assets": ["xauusd", "iran_gold", ...],
  "summary_fa": "Persian summary, 200-300 words, covering the main argument and data points",
  "title_fa": "Persian translation of the title",
  "key_takeaways_fa": [
    "first point in Persian",
    "second point in Persian",
    "third point in Persian"
  ]
}

Rules:
- importance_score: 80+ for bank research/forecasts, WGC reports, major policy analysis. \
50-79 for good general analysis. Below 50 for generic commentary.
- Only set is_important=true if the article has genuine NEW insight, data, or forecast. \
Generic "gold is up because of uncertainty" articles are NOT important.
- summary_fa must be original — do NOT translate word by word. Summarize the key argument, \
data, and conclusion in your own words in Persian.
- key_takeaways_fa: extract 3-5 specific, actionable points in Persian. Not vague statements.
- topics must be from: fed_policy, ecb_policy, china_demand, india_demand, central_banks, \
etf_flows, mine_supply, geopolitics, sanctions, inflation, dollar, technical_analysis, \
price_forecast, investment_strategy, silver, oil, crypto_correlation, de_dollarization
- affected_assets must be from: xauusd, iran_gold, usd_irr, silver, dxy, oil, btc
"""

ARTICLE_SCORING_USER_TEMPLATE = """\
Article title: {title}
Source: {source_name}
Content:
{content}

Respond with ONLY the JSON object. No extra text.\
"""
