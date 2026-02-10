"""
News type classifier — distinguishes price reports from causal events.

A **price report** just tells you what the price IS (or was). It does NOT
cause gold to go higher or lower. Example: "قیمت طلا به بالای ۵۰۰۰ دلار رسید"

A **causal event** describes something that DRIVES the market — a policy
decision, economic data, geopolitical event, etc. These deserve full
direction/severity/sentiment scoring.

A **mixed** item reports a price AND mentions a cause. Only the causal
part should influence direction scoring.

Classification
--------------
PRICE_REPORT
    Score fixed at 50, severity forced to LOW, excluded from sentiment gauge.
    expected_impact replaced with informational message.

CAUSAL_EVENT
    Full scoring pipeline (direction + severity + sentiment).

MIXED
    Gets full scoring but from the causal part only.
"""

from __future__ import annotations

import re
from typing import Literal

NewsType = Literal["price_report", "causal_event", "mixed"]

# ---------------------------------------------------------------------------
# Price report patterns (Persian + English)
# ---------------------------------------------------------------------------

# Headlines that START with a price-reporting structure
_PRICE_TITLE_PATTERNS: list[re.Pattern[str]] = [
    # "قیمت طلا و سکه امروز" / "قیمت طلا و سکه ۲۱ بهمن"
    re.compile(
        r"^قیمت\s+.{1,30}(امروز|روز|تاریخ|بهمن|اسفند|فروردین|اردیبهشت"
        r"|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی)",
        re.IGNORECASE,
    ),
    # "قیمت طلا [number]" — just a price figure
    re.compile(
        r"^قیمت\s+(طلا|سکه|دلار|ارز|نقره).{0,20}[\d۰-۹]",
        re.IGNORECASE,
    ),
    # "Gold price today / Gold prices on..."
    re.compile(
        r"^gold\s+price[s]?\s+(today|on\s|for\s|at\s|update)",
        re.IGNORECASE,
    ),
    # "XAU/USD at..." / "XAU/USD trading at..."
    re.compile(
        r"^XAU[/\\]?USD\s+(at|trading|trades|holds|hovers|steady)",
        re.IGNORECASE,
    ),
]

# Content-level price reporting signals (can appear anywhere)
_PRICE_CONTENT_PATTERNS: list[re.Pattern[str]] = [
    # Percentage change reports as the main topic
    re.compile(
        r"(افزایش|کاهش|رشد|افت)\s+[\d۰-۹]+[.,٫]?[\d۰-۹]*\s*درصد",
        re.IGNORECASE,
    ),
    # "Gold hits / reaches / touches [number]"
    re.compile(
        r"(gold|طلا).{0,15}(hit[s]?|reach(ed|es)?|touch(ed|es)?|climb(ed|s)?|above|بالای|رسید|رسیده)"
        r"\s+(to\s+)?[\$]?[\d۰-۹,٬]+",
        re.IGNORECASE,
    ),
    # "traded at" / "معامله شد در"
    re.compile(
        r"(معامله\s+شد|traded\s+at|trading\s+at|قیمت\s+.*\s+شد)",
        re.IGNORECASE,
    ),
    # Price listing: "18k gold: 5,000,000 T"
    re.compile(
        r"(طلای?\s*\d+\s*عیار|سکه\s+(امامی|بهار|تمام|نیم|ربع))\s*:?\s*[\d۰-۹,٬.]+",
        re.IGNORECASE,
    ),
    # "قیمت روز" / "نرخ روز" / "لیست قیمت"
    re.compile(
        r"(قیمت\s+روز|نرخ\s+روز|لیست\s+قیمت|جدول\s+قیمت)",
        re.IGNORECASE,
    ),
]

# ---------------------------------------------------------------------------
# Causal indicators — actors, events, and language that DRIVE markets
# ---------------------------------------------------------------------------

_CAUSAL_PATTERNS: list[re.Pattern[str]] = [
    # Actors & institutions
    re.compile(
        r"(fed|federal\s+reserve|بانک\s+مرکزی|ecb|boj|rbi|pboc"
        r"|رئیس\s*جمهور|president|trump|biden|خامنه|روحانی|رئیسی"
        r"|powell|lagarde|yellen|mnuchin|opec)",
        re.IGNORECASE,
    ),
    # Policy actions
    re.compile(
        r"(تحریم|sanction|tariff|تعرفه|نرخ\s+بهره|interest\s+rate"
        r"|rate\s+(cut|hike|decision|hold)|سیاست\s+پولی|monetary\s+policy"
        r"|quantitative\s+(easing|tightening)|stimulus|محرک)",
        re.IGNORECASE,
    ),
    # Economic data
    re.compile(
        r"(CPI|inflation|تورم|NFP|non.?farm|unemployment|بیکاری"
        r"|GDP|PMI|ISM|retail\s+sales|consumer\s+confidence"
        r"|شاخص\s+بها|jobs?\s+report|payroll)",
        re.IGNORECASE,
    ),
    # Geopolitical events
    re.compile(
        r"(جنگ|war|crisis|بحران|conflict|tension|تنش"
        r"|حمله|attack|missile|موشک|هسته\s*ای|nuclear"
        r"|مذاکر|negotiat|peace\s+talk|آتش\s*بس|ceasefire"
        r"|coup|کودتا|protest|اعتراض)",
        re.IGNORECASE,
    ),
    # Market events (crashes, records NOT price reports)
    re.compile(
        r"(crash|سقوط\s+بازار|رکود|recession|default"
        r"|bank\s+(failure|run|collapse)|ورشکستگی"
        r"|circuit\s+breaker|halt(ed)?|suspend(ed)?)",
        re.IGNORECASE,
    ),
    # Causal language
    re.compile(
        r"(به\s+دلیل|به\s+خاطر|در\s+پی|بر\s+اثر|ناشی\s+از"
        r"|because|due\s+to|amid|driven\s+by|sparked\s+by"
        r"|triggered\s+by|fueled\s+by|on\s+the\s+back\s+of"
        r"|following|after\s+.{1,30}(announce|decision|data|report)"
        r"|caused\s+by|in\s+response\s+to|as\s+a\s+result)",
        re.IGNORECASE,
    ),
    # Supply/demand fundamentals
    re.compile(
        r"(central\s+bank\s+buy|خرید\s+بانک|gold\s+reserve"
        r"|ذخایر\s+طلا|ETF\s+(inflow|outflow)|تقاضا|demand\s+surge"
        r"|mine\s+(output|supply|production)|تولید\s+معدن)",
        re.IGNORECASE,
    ),
]

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_news_type(title: str, content: str = "") -> NewsType:
    """Classify a news item as price_report, causal_event, or mixed.

    Parameters
    ----------
    title:
        The headline / title of the news item.
    content:
        The body text (can be empty).

    Returns
    -------
    NewsType
        One of ``"price_report"``, ``"causal_event"``, or ``"mixed"``.
    """
    has_price = _has_price_pattern(title, content)
    has_causal = _has_causal_indicator(title, content)

    if has_price and not has_causal:
        return "price_report"
    if has_price and has_causal:
        return "mixed"
    return "causal_event"


def _has_price_pattern(title: str, content: str) -> bool:
    """Check if the title or content is a price report."""
    for pat in _PRICE_TITLE_PATTERNS:
        if pat.search(title):
            return True
    # Also check content patterns, but only if title shows price focus
    # (we don't want a deep causal article that mentions a price figure to be misclassified)
    full_text = f"{title} {content[:500]}"
    price_signal_count = sum(1 for pat in _PRICE_CONTENT_PATTERNS if pat.search(full_text))
    # Need 2+ content signals to count as price report when title doesn't match
    return price_signal_count >= 2


def _has_causal_indicator(title: str, content: str) -> bool:
    """Check if the title or content contains causal drivers."""
    full_text = f"{title} {content[:1000]}"
    for pat in _CAUSAL_PATTERNS:
        if pat.search(full_text):
            return True
    return False


# ---------------------------------------------------------------------------
# Price-report overrides for the alert pipeline
# ---------------------------------------------------------------------------

#: Fixed expected_impact for PRICE_REPORT alerts
PRICE_REPORT_IMPACT: list[dict[str, str]] = [
    {
        "asset": "اطلاع‌رسانی قیمت",
        "direction": "neutral",
        "mechanism": "گزارش قیمت — تاثیری بر روند آینده ندارد",
    }
]

#: Fixed severity for PRICE_REPORT
PRICE_REPORT_SEVERITY = "low"

#: Fixed score for PRICE_REPORT (neutral = 50)
PRICE_REPORT_SCORE = 50
