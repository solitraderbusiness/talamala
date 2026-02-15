"""Configuration for the gold articles module.

Contains article source definitions, topic labels (Persian), quality rules,
and scoring thresholds.
"""

from __future__ import annotations

import os

# ── OpenRouter config (reuses existing project config) ───────────────────

OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
ARTICLE_LLM_MODEL: str = os.environ.get(
    "ARTICLE_LLM_MODEL", "anthropic/claude-haiku-4.5"
)
ARTICLE_LLM_TEMPERATURE: float = 0.2
ARTICLE_LLM_MAX_TOKENS: int = 1500

# ── Budget limits ────────────────────────────────────────────────────────

DAILY_LLM_BUDGET_USD: float = float(os.environ.get("ARTICLE_DAILY_BUDGET", "1.0"))

# ── Scoring thresholds ──────────────────────────────────────────────────

PUBLISH_THRESHOLD: float = 20.0       # importance_score >= this → is_published
MIN_WORD_COUNT: int = 50              # articles shorter than this are rejected
MAX_ARTICLE_AGE_DAYS: int = 7         # articles older than this are rejected
ARTICLE_CONTENT_MAX_CHARS: int = 2000 # max chars sent to LLM

# ── Fetch intervals ─────────────────────────────────────────────────────

FETCH_INTERVAL_SECONDS: int = 4 * 60 * 60  # 4 hours

# ── Article sources ──────────────────────────────────────────────────────

ARTICLE_SOURCES: list[dict] = [
    # === TIER 1: Top quality, always check ===
    {
        "name": "World Gold Council",
        "name_fa": "شورای جهانی طلا",
        "url": "https://www.gold.org/goldhub/gold-focus",
        "type": "rss_or_scrape",
        "rss_url": "https://www.gold.org/rss.xml",
        "check_interval_hours": 6,
        "default_importance_boost": 15,
        "topics": ["supply_demand", "central_banks", "etf_flows", "market_outlook"],
    },
    {
        "name": "Kitco News Analysis",
        "name_fa": "کیتکو",
        "url": "https://www.kitco.com/news/gold/",
        "type": "rss",
        "rss_url": "https://www.kitco.com/feed/rss/news/gold",
        "check_interval_hours": 4,
        "default_importance_boost": 0,
        "topics": ["price_analysis", "market_outlook", "technical_analysis"],
    },
    {
        "name": "Reuters Commodities",
        "name_fa": "رویترز",
        "url": "https://www.reuters.com/markets/commodities/",
        "type": "rss",
        "rss_url": "https://news.google.com/rss/search?q=site%3Areuters.com+gold+OR+%22precious+metals%22+when%3A3d&hl=en-US&gl=US&ceid=US:en",
        "check_interval_hours": 4,
        "default_importance_boost": 10,
        "topics": ["market_outlook", "central_banks", "geopolitics"],
    },
    {
        "name": "Bloomberg Commodities",
        "name_fa": "بلومبرگ",
        "url": "https://www.bloomberg.com/commodities",
        "type": "rss_or_scrape",
        "rss_url": "https://news.google.com/rss/search?q=site%3Abloomberg.com+gold+forecast+OR+%22gold+outlook%22+when%3A3d&hl=en-US&gl=US&ceid=US:en",
        "check_interval_hours": 6,
        "default_importance_boost": 10,
        "topics": ["market_outlook", "macro", "central_banks"],
    },
    {
        "name": "Seeking Alpha - Gold",
        "name_fa": "سیکینگ آلفا",
        "url": "https://seekingalpha.com/market-outlook/gold-and-precious-metals",
        "type": "rss_or_scrape",
        "rss_url": "https://news.google.com/rss/search?q=site%3Aseekingalpha.com+gold+analysis+when%3A3d&hl=en-US&gl=US&ceid=US:en",
        "check_interval_hours": 6,
        "default_importance_boost": 0,
        "topics": ["price_analysis", "investment_strategy", "etf_flows"],
    },
    {
        "name": "GoldSeek",
        "name_fa": "گلدسیک",
        "url": "https://www.goldseek.com/",
        "type": "rss",
        "rss_url": "https://goldseek.com/rss/news",
        "check_interval_hours": 6,
        "default_importance_boost": 0,
        "topics": ["price_analysis", "technical_analysis", "market_outlook"],
    },
    {
        "name": "Metals Focus",
        "name_fa": "متالز فوکوس",
        "url": "https://www.metalsfocus.com/",
        "type": "rss_or_scrape",
        "rss_url": None,
        "check_interval_hours": 12,
        "default_importance_boost": 15,
        "topics": ["supply_demand", "market_outlook"],
    },
    {
        "name": "CME Group - Gold",
        "name_fa": "گروه CME",
        "url": "https://www.cmegroup.com/articles.html",
        "type": "scrape",
        "rss_url": None,
        "check_interval_hours": 12,
        "default_importance_boost": 10,
        "topics": ["futures", "technical_analysis", "market_structure"],
    },
    {
        "name": "Sprott",
        "name_fa": "اسپرات",
        "url": "https://sprott.com/insights/",
        "type": "rss_or_scrape",
        "rss_url": "https://sprott.com/insights/feed/",
        "check_interval_hours": 12,
        "default_importance_boost": 5,
        "topics": ["investment_strategy", "market_outlook", "mine_supply"],
    },
    {
        "name": "Zero Hedge - Commodities",
        "name_fa": "زیرو هج",
        "url": "https://www.zerohedge.com/commodities",
        "type": "rss",
        "rss_url": "https://feeds.feedburner.com/zerohedge/feed",
        "check_interval_hours": 6,
        "default_importance_boost": -5,
        "topics": ["macro", "geopolitics", "price_analysis"],
    },
    {
        "name": "Investing.com - Gold Analysis",
        "name_fa": "اینوستینگ",
        "url": "https://www.investing.com/analysis/commodities",
        "type": "rss_or_scrape",
        "rss_url": "https://www.investing.com/rss/news_14.rss",
        "check_interval_hours": 6,
        "default_importance_boost": 0,
        "topics": ["technical_analysis", "price_analysis"],
    },
    {
        "name": "FXStreet - Gold",
        "name_fa": "اف‌ایکس استریت",
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
        "name_fa": "استیت استریت",
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
    "fed_policy": "سیاست فدرال رزرو",
    "ecb_policy": "سیاست بانک مرکزی اروپا",
    "china_demand": "تقاضای چین",
    "india_demand": "تقاضای هند",
    "central_banks": "بانک‌های مرکزی",
    "etf_flows": "جریان ETF",
    "mine_supply": "عرضه معدنی",
    "geopolitics": "ژئوپلیتیک",
    "sanctions": "تحریم‌ها",
    "inflation": "تورم",
    "dollar": "دلار",
    "technical_analysis": "تحلیل تکنیکال",
    "price_forecast": "پیش‌بینی قیمت",
    "investment_strategy": "استراتژی سرمایه‌گذاری",
    "silver": "نقره",
    "oil": "نفت",
    "crypto_correlation": "همبستگی رمزارز",
    "de_dollarization": "دلارزدایی",
    "supply_demand": "عرضه و تقاضا",
    "macro": "کلان اقتصادی",
    "market_outlook": "چشم‌انداز بازار",
    "price_analysis": "تحلیل قیمت",
    "futures": "قراردادهای آتی",
    "market_structure": "ساختار بازار",
}

# ── Outlook labels in Persian ────────────────────────────────────────────

OUTLOOK_LABELS_FA: dict[str, str] = {
    "bullish": "صعودی",
    "bearish": "نزولی",
    "neutral": "خنثی",
    "mixed": "ترکیبی",
}

# ── Time horizon labels ──────────────────────────────────────────────────

TIME_HORIZON_LABELS_FA: dict[str, str] = {
    "short_term": "کوتاه‌مدت",
    "medium_term": "میان‌مدت",
    "long_term": "بلندمدت",
}

# ── Asset labels ─────────────────────────────────────────────────────────

ASSET_LABELS_FA: dict[str, str] = {
    "xauusd": "طلای جهانی XAU/USD",
    "iran_gold": "طلای ایران",
    "usd_irr": "دلار/ریال",
    "silver": "نقره",
    "dxy": "شاخص دلار",
    "oil": "نفت",
    "btc": "بیت‌کوین",
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
