"""Configuration for the gold videos module.

Contains LLM settings, category/topic labels, seed data for live streams
and monitored channels, gold relevance keywords, and chat rate limits.
"""

from __future__ import annotations

import os

# ── OpenRouter config ────────────────────────────────────────────────────

OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
VIDEO_LLM_MODEL: str = os.environ.get(
    "ARTICLE_LLM_MODEL", "anthropic/claude-haiku-4.5"
)
VIDEO_LLM_TEMPERATURE: float = 0.2
VIDEO_LLM_MAX_TOKENS: int = 1500

# ── Scoring thresholds ──────────────────────────────────────────────────

PUBLISH_THRESHOLD: float = 30.0       # relevance_score >= this → is_published
TRANSCRIPT_MAX_CHARS: int = 3000      # max chars of transcript sent to LLM

# ── Fetch intervals ─────────────────────────────────────────────────────

SCAN_INTERVAL_SECONDS: int = 60 * 60  # 1 hour

# ── Chat rate limits ────────────────────────────────────────────────────

CHAT_RATE_LIMIT_PER_VIDEO_IP_DAY: int = 10

# ── Category labels in Persian ──────────────────────────────────────────

CATEGORY_LABELS_FA: dict[str, str] = {
    "analysis": "تحلیل بازار",
    "news": "اخبار",
    "education": "آموزشی",
    "interview": "مصاحبه",
    "documentary": "مستند",
    "podcast": "پادکست",
}

# ── Topic labels in Persian ─────────────────────────────────────────────

TOPIC_LABELS_FA: dict[str, str] = {
    "gold_price": "قیمت طلا",
    "fed_policy": "سیاست فدرال رزرو",
    "central_banks": "بانک‌های مرکزی",
    "geopolitics": "ژئوپلیتیک",
    "inflation": "تورم",
    "dollar": "دلار",
    "technical_analysis": "تحلیل تکنیکال",
    "market_outlook": "چشم‌انداز بازار",
    "silver": "نقره",
    "mining": "معدن",
    "etf_flows": "جریان ETF",
    "recession": "رکود",
    "debt_crisis": "بحران بدهی",
    "de_dollarization": "دلارزدایی",
    "supply_demand": "عرضه و تقاضا",
    "crypto": "رمزارز",
    "oil": "نفت",
    "china": "چین",
    "investment_strategy": "استراتژی سرمایه‌گذاری",
}

# ── Outlook labels in Persian ───────────────────────────────────────────

OUTLOOK_LABELS_FA: dict[str, str] = {
    "bullish": "صعودی",
    "bearish": "نزولی",
    "neutral": "خنثی",
    "mixed": "ترکیبی",
}

# ── Seed data: Live stream channels ─────────────────────────────────────

SEED_LIVE_STREAMS: list[dict] = [
    {
        "name": "Bloomberg Television",
        "name_fa": "بلومبرگ",
        "youtube_channel_id": "UCIALMKvObZNtJ6AmdCLP7Lg",
        "sort_order": 1,
    },
    {
        "name": "CNBC Television",
        "name_fa": "سی‌ان‌بی‌سی",
        "youtube_channel_id": "UCvJJ_dzjViJCoLf5uKUTwoA",
        "sort_order": 2,
    },
    {
        "name": "Yahoo Finance",
        "name_fa": "یاهو فایننس",
        "youtube_channel_id": "UCEAZeUIeJs0IjQiqTCdVSIg",
        "sort_order": 3,
    },
]

# ── Seed data: Monitored YouTube channels ───────────────────────────────

SEED_MONITORED_CHANNELS: list[dict] = [
    {
        "name": "Kitco NEWS",
        "youtube_channel_id": "UC9ijza42jVR3T6b8bColgvg",
        "always_relevant": True,
        "auto_publish": False,
    },
    {
        "name": "Bloomberg Television",
        "youtube_channel_id": "UCIALMKvObZNtJ6AmdCLP7Lg",
        "always_relevant": False,
        "auto_publish": False,
    },
    {
        "name": "Principles by Ray Dalio",
        "youtube_channel_id": "UCqvaXJ1K3HheTPNjH-KpwXQ",
        "always_relevant": False,
        "auto_publish": False,
    },
    {
        "name": "CNBC Television",
        "youtube_channel_id": "UCvJJ_dzjViJCoLf5uKUTwoA",
        "always_relevant": False,
        "auto_publish": False,
    },
    {
        "name": "Stansberry Research",
        "youtube_channel_id": "UCVgL_VeHteGecp5nn0NRztQ",
        "always_relevant": False,
        "auto_publish": False,
    },
    {
        "name": "Peter Schiff",
        "youtube_channel_id": "UCIjuLiLHdFxYtFmWlbTGQRQ",
        "always_relevant": True,
        "auto_publish": False,
    },
]

# ── Seed data: Initial curated videos ───────────────────────────────────

SEED_CURATED_VIDEOS: list[str] = [
    "1HmGLV46L60",  # Stansberry: gold outlook
]

# ── Gold relevance keywords (for filtering general channels) ────────────

GOLD_KEYWORDS: list[str] = [
    "gold", "xau", "bullion", "precious metal", "gold price",
    "gold forecast", "gold outlook", "gold demand", "gold supply",
    "central bank gold", "gold etf", "gold futures", "gold rally",
    "gold mine", "gold mining", "safe haven", "gold reserve",
    "silver", "platinum", "palladium", "commodity",
    "inflation hedge", "store of value", "monetary policy",
]

# ── LLM scoring prompt ──────────────────────────────────────────────────

VIDEO_SCORING_SYSTEM_PROMPT = """\
You are a gold market analyst. Evaluate the video based on the information provided.

Respond in JSON only — no markdown fences, no commentary.

The JSON object must have exactly these keys:
{
  "relevance_score": 0-100,
  "gold_outlook": "bullish" or "bearish" or "neutral" or "mixed",
  "category": "analysis" or "news" or "education" or "interview" or "documentary" or "podcast",
  "topics": ["gold_price", "fed_policy", ...],
  "summary_fa": "Persian summary",
  "title_fa": "Persian translation of the title",
  "key_points_fa": [
    "first point in Persian",
    "second point in Persian",
    "third point in Persian"
  ]
}

Rules:
- relevance_score: 80+ for expert forecasts, bank analysis, major policy discussion. \
50-79 for good general gold/macro analysis. Below 50 for generic commentary.
- If a transcript is provided, write a detailed 150-250 word summary_fa covering arguments and data.
- If only the title is provided (no transcript), write a brief 30-60 word summary_fa based on \
the title and channel, and be conservative with relevance_score (cap at 60 without transcript).
- summary_fa must be original — do NOT translate word by word. Write in your own words in Persian.
- key_points_fa: extract 3-5 specific points in Persian (fewer if only title is available).
- topics must be from: gold_price, fed_policy, central_banks, geopolitics, inflation, dollar, \
technical_analysis, market_outlook, silver, mining, etf_flows, recession, debt_crisis, \
de_dollarization, supply_demand, crypto, oil, china, investment_strategy
"""

VIDEO_SCORING_USER_TEMPLATE_WITH_TRANSCRIPT = """\
Video title: {title}
Channel: {channel}
Transcript (first {max_chars} chars):
{transcript}

Respond with ONLY the JSON object. No extra text.\
"""

VIDEO_SCORING_USER_TEMPLATE_TITLE_ONLY = """\
Video title: {title}
Channel: {channel}
(No transcript available — score based on title and channel only)

Respond with ONLY the JSON object. No extra text.\
"""

# ── Chat system prompt ──────────────────────────────────────────────────

VIDEO_CHAT_SYSTEM_PROMPT = """\
You are an expert gold market analyst assistant. A user is watching a video \
about gold/economics and has questions. Use the video transcript below to \
answer their question in Persian. Be concise, specific, and reference the \
video content when possible.

Video title: {title}
Channel: {channel}

Transcript (excerpt):
{transcript}
"""
