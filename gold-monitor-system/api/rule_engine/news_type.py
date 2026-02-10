"""
News type classifier — distinguishes price reports, background context,
and causal events.

Four news types
---------------
PRICE_REPORT
    Just reports the price (Fix #8).  Score=50, severity=LOW, excluded
    from sentiment gauge.

BACKGROUND_CONTEXT  (Fix #9)
    Routine calendar events, anniversary articles, opinion/commentary
    with no genuinely new market-moving information.  Keywords like
    "تحریم" or "تنش" appearing as *background context* (describing
    existing conditions) are NOT new events.  Score=50, severity=LOW,
    excluded from sentiment gauge.

CAUSAL_EVENT
    NEW event that DRIVES the market — a policy decision, economic
    data release, geopolitical escalation, etc.  Full scoring pipeline.

MIXED
    Reports a price AND mentions a cause.  Gets full scoring.

Classification order
--------------------
1. Check BACKGROUND_CONTEXT first (anniversaries, commentary, etc.)
   — but only if no genuinely-new-event language is present
2. Check PRICE_REPORT patterns
3. Default to CAUSAL_EVENT

Key principle: **Only NEW information moves markets.**
"Iran has sanctions" → old, priced in.
"New sanctions imposed on Iran" → new, affects market.
"""

from __future__ import annotations

import re
from typing import Literal

NewsType = Literal["price_report", "causal_event", "mixed", "background_context"]

# ---------------------------------------------------------------------------
# Price report patterns (Persian + English) — from Fix #8
# ---------------------------------------------------------------------------

_PRICE_TITLE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"^قیمت\s+.{1,30}(امروز|روز|تاریخ|بهمن|اسفند|فروردین|اردیبهشت"
        r"|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^قیمت\s+(طلا|سکه|دلار|ارز|نقره).{0,20}[\d۰-۹]",
        re.IGNORECASE,
    ),
    re.compile(
        r"^gold\s+price[s]?\s+(today|on\s|for\s|at\s|update)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^XAU[/\\]?USD\s+(at|trading|trades|holds|hovers|steady)",
        re.IGNORECASE,
    ),
]

_PRICE_CONTENT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(افزایش|کاهش|رشد|افت)\s+[\d۰-۹]+[.,٫]?[\d۰-۹]*\s*درصد",
        re.IGNORECASE,
    ),
    re.compile(
        r"(gold|طلا).{0,15}(hit[s]?|reach(ed|es)?|touch(ed|es)?|climb(ed|s)?|above|بالای|رسید|رسیده)"
        r"\s+(to\s+)?[\$]?[\d۰-۹,٬]+",
        re.IGNORECASE,
    ),
    re.compile(
        r"(معامله\s+شد|traded\s+at|trading\s+at|قیمت\s+.*\s+شد)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(طلای?\s*\d+\s*عیار|سکه\s+(امامی|بهار|تمام|نیم|ربع))\s*:?\s*[\d۰-۹,٬.]+",
        re.IGNORECASE,
    ),
    re.compile(
        r"(قیمت\s+روز|نرخ\s+روز|لیست\s+قیمت|جدول\s+قیمت)",
        re.IGNORECASE,
    ),
]

# ---------------------------------------------------------------------------
# Background / contextual patterns — Fix #9
# ---------------------------------------------------------------------------

# Title patterns that indicate background/calendar/commentary content
_BACKGROUND_TITLE_PATTERNS: list[re.Pattern[str]] = [
    # Anniversaries & commemorations
    re.compile(r"(سالگرد|سالروز|anniversary|یادبود|بزرگداشت)", re.IGNORECASE),
    # Routine calendar events
    re.compile(r"(مراسم|ceremony|جشن|celebration)", re.IGNORECASE),
    # Historical / educational / review content
    re.compile(
        r"(تاریخچه|مروری\s+بر|نگاهی\s+به|آموزش|آشنایی\s+با"
        r"|history\s+of|a\s+look\s+at|overview\s+of|introduction\s+to)",
        re.IGNORECASE,
    ),
    # Pure opinion / editorial
    re.compile(
        r"(commentary|editorial|op[- ]?ed|ستون\s+نظر|سرمقاله|یادداشت)",
        re.IGNORECASE,
    ),
]

# Content patterns that suggest background description (not new events)
_BACKGROUND_CONTENT_PATTERNS: list[re.Pattern[str]] = [
    # "continue to..." / "still..." / "remain..." — describing status quo
    re.compile(
        r"(همچنان|ادامه\s+دارد|تداوم|continue[sd]?\s+to|still\s+face"
        r"|remain[s]?\s|ongoing|existing)",
        re.IGNORECASE,
    ),
    # Analysts/experts commentary without new data
    re.compile(
        r"(تحلیلگران\s+معتقدند|کارشناسان\s+می.گویند|experts?\s+say"
        r"|analysts?\s+(say|believe|think)|به\s+گفته\s+کارشناسان)",
        re.IGNORECASE,
    ),
    # General predictions / forecasts without new trigger
    re.compile(
        r"(پیش.بینی\s+می.شود|forecast[s]?\s|outlook\s+for|may\s+continue"
        r"|could\s+continue|is\s+expected\s+to\s+continue)",
        re.IGNORECASE,
    ),
]

# ---------------------------------------------------------------------------
# "New event" indicators — if present, override background detection
# These signal genuinely NEW market-moving information
# ---------------------------------------------------------------------------

_NEW_EVENT_PATTERNS: list[re.Pattern[str]] = [
    # New / just announced / breaking
    re.compile(
        r"(جدید|تازه|اعلام\s+شد|اعلام\s+کرد|تصویب\s+شد|تصمیم\s+گرفت"
        r"|new\s|just\s+announced|breaking|latest\s+decision"
        r"|approved|enacted|signed\s+into|announced\s+today)",
        re.IGNORECASE,
    ),
    # Specific actions (imposed, cut, raised, launched)
    re.compile(
        r"(اعمال\s+شد|وضع\s+شد|افزایش\s+داد|کاهش\s+داد|حمله\s+کرد"
        r"|imposed|launched|struck|attacked|cut\s+rates?"
        r"|hike[sd]?\s+rate|raise[sd]?\s+rate|deploy|invade[sd]?)",
        re.IGNORECASE,
    ),
    # Data releases with specific numbers
    re.compile(
        r"(came\s+in\s+at|reported\s+at|data\s+show[sed]"
        r"|اعلام\s+شد\s+[\d۰-۹]|رسید\s+به\s+[\d۰-۹]"
        r"|beat\s+expectations|missed\s+expectations|surprised)",
        re.IGNORECASE,
    ),
    # Escalation / de-escalation language
    re.compile(
        r"(تشدید\s+شد|وخیم\s+شد|escalat|de-?escalat|intensif|broke\s+out"
        r"|erupted|collapsed|surge[sd]?\s+after)",
        re.IGNORECASE,
    ),
]

# ---------------------------------------------------------------------------
# Causal indicators — actors, events, and language that DRIVE markets
# ---------------------------------------------------------------------------

_CAUSAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(fed|federal\s+reserve|بانک\s+مرکزی|ecb|boj|rbi|pboc"
        r"|رئیس\s*جمهور|president|trump|biden|خامنه|روحانی|رئیسی"
        r"|powell|lagarde|yellen|mnuchin|opec)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(تحریم|sanction|tariff|تعرفه|نرخ\s+بهره|interest\s+rate"
        r"|rate\s+(cut|hike|decision|hold)|سیاست\s+پولی|monetary\s+policy"
        r"|quantitative\s+(easing|tightening)|stimulus|محرک)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(CPI|inflation|تورم|NFP|non.?farm|unemployment|بیکاری"
        r"|GDP|PMI|ISM|retail\s+sales|consumer\s+confidence"
        r"|شاخص\s+بها|jobs?\s+report|payroll)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(جنگ|war|crisis|بحران|conflict|tension|تنش"
        r"|حمله|attack|missile|موشک|هسته\s*ای|nuclear"
        r"|مذاکر|negotiat|peace\s+talk|آتش\s*بس|ceasefire"
        r"|coup|کودتا|protest|اعتراض)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(crash|سقوط\s+بازار|رکود|recession|default"
        r"|bank\s+(failure|run|collapse)|ورشکستگی"
        r"|circuit\s+breaker|halt(ed)?|suspend(ed)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(به\s+دلیل|به\s+خاطر|در\s+پی|بر\s+اثر|ناشی\s+از"
        r"|because|due\s+to|amid|driven\s+by|sparked\s+by"
        r"|triggered\s+by|fueled\s+by|on\s+the\s+back\s+of"
        r"|following|after\s+.{1,30}(announce|decision|data|report)"
        r"|caused\s+by|in\s+response\s+to|as\s+a\s+result)",
        re.IGNORECASE,
    ),
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
    """Classify a news item into one of four types.

    Classification order:
    1. BACKGROUND_CONTEXT — if title/content shows calendar/commentary
       patterns AND no genuinely-new-event indicators are present
    2. PRICE_REPORT — if title/content is a price listing
    3. MIXED — price report + causal indicators
    4. CAUSAL_EVENT — default (new market-moving information)

    Parameters
    ----------
    title:
        The headline / title of the news item.
    content:
        The body text (can be empty).

    Returns
    -------
    NewsType
        One of ``"price_report"``, ``"causal_event"``, ``"mixed"``,
        or ``"background_context"``.
    """
    # Step 1: Check for background/contextual content FIRST
    has_background = _has_background_pattern(title, content)
    has_new_event = _has_new_event_indicator(title, content)

    if has_background and not has_new_event:
        return "background_context"

    # Step 2: Check price report patterns
    has_price = _has_price_pattern(title, content)
    has_causal = _has_causal_indicator(title, content)

    if has_price and not has_causal:
        return "price_report"
    if has_price and has_causal:
        return "mixed"

    return "causal_event"


# ---------------------------------------------------------------------------
# Pattern checkers
# ---------------------------------------------------------------------------


def _has_price_pattern(title: str, content: str) -> bool:
    """Check if the title or content is a price report."""
    for pat in _PRICE_TITLE_PATTERNS:
        if pat.search(title):
            return True
    full_text = f"{title} {content[:500]}"
    price_signal_count = sum(1 for pat in _PRICE_CONTENT_PATTERNS if pat.search(full_text))
    return price_signal_count >= 2


def _has_causal_indicator(title: str, content: str) -> bool:
    """Check if the title or content contains causal drivers."""
    full_text = f"{title} {content[:1000]}"
    for pat in _CAUSAL_PATTERNS:
        if pat.search(full_text):
            return True
    return False


def _has_background_pattern(title: str, content: str) -> bool:
    """Check if the title or content indicates background/contextual news.

    Requires a title-level match (anniversary, commentary, etc.).
    Content patterns alone aren't enough — many causal articles also
    contain status-quo language.
    """
    # Must have a title-level background indicator
    title_match = any(pat.search(title) for pat in _BACKGROUND_TITLE_PATTERNS)
    if title_match:
        return True

    # If title doesn't match, check for heavy content-level background signals
    # (need 2+ content matches to be confident it's background)
    full_text = f"{title} {content[:1000]}"
    content_hits = sum(1 for pat in _BACKGROUND_CONTENT_PATTERNS if pat.search(full_text))
    return content_hits >= 2


def _has_new_event_indicator(title: str, content: str) -> bool:
    """Check if the text contains genuinely-new-event language.

    This overrides background classification — if an anniversary article
    also announces a new policy, it should be treated as a causal event.
    """
    full_text = f"{title} {content[:1000]}"
    for pat in _NEW_EVENT_PATTERNS:
        if pat.search(full_text):
            return True
    return False


# ---------------------------------------------------------------------------
# Override constants for non-causal types
# ---------------------------------------------------------------------------

#: Fixed expected_impact for PRICE_REPORT alerts
PRICE_REPORT_IMPACT: list[dict[str, str]] = [
    {
        "asset": "اطلاع‌رسانی قیمت",
        "direction": "neutral",
        "mechanism": "گزارش قیمت — تاثیری بر روند آینده ندارد",
    }
]

#: Fixed expected_impact for BACKGROUND_CONTEXT alerts
BACKGROUND_CONTEXT_IMPACT: list[dict[str, str]] = [
    {
        "asset": "اطلاعات زمینه‌ای",
        "direction": "neutral",
        "mechanism": "اطلاعات موجود — قبلاً در قیمت لحاظ شده",
    }
]

#: Fixed severity for non-causal types
NON_CAUSAL_SEVERITY = "low"

#: Fixed score for non-causal types (neutral = 50)
NON_CAUSAL_SCORE = 50

# Keep old names for backwards compatibility
PRICE_REPORT_SEVERITY = NON_CAUSAL_SEVERITY
PRICE_REPORT_SCORE = NON_CAUSAL_SCORE
