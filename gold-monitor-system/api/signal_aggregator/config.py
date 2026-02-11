"""Signal Aggregator configuration — env vars and constants."""

from __future__ import annotations

import os

# ── Telegram ─────────────────────────────────────────────────────────────
TELEGRAM_API_ID: str = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH: str = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_PHONE: str = os.getenv("TELEGRAM_PHONE", "")
TELEGRAM_SESSION_PATH: str = os.getenv("TELEGRAM_SESSION_PATH", "/app/data/telegram_session")

# ── Anthropic (Claude API for parsing) ───────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
SIGNAL_PARSE_MODEL: str = os.getenv("SIGNAL_PARSE_MODEL", "claude-sonnet-4-20250514")

# ── TradingView ──────────────────────────────────────────────────────────
TRADINGVIEW_COOKIE: str = os.getenv("TRADINGVIEW_COOKIE", "")

# ── Timeframe mappings ───────────────────────────────────────────────────
# Each consensus view pulls from a range of signal timeframes.
CONSENSUS_TIMEFRAMES: dict[str, list[str]] = {
    "scalp": ["5min", "15min", "30min"],
    "intraday": ["15min", "30min", "1h", "4h"],
    "swing": ["4h", "daily"],
    "position": ["daily", "weekly"],
}

ALL_TIMEFRAMES = ["5min", "15min", "30min", "1h", "4h", "daily", "weekly"]
ALL_CONSENSUS_VIEWS = ["scalp", "intraday", "swing", "position"]

# ── Valid hours defaults by timeframe ────────────────────────────────────
DEFAULT_VALID_HOURS: dict[str, int] = {
    "5min": 3,
    "15min": 4,
    "30min": 8,
    "1h": 12,
    "4h": 48,
    "daily": 120,
    "weekly": 336,
}

# ── Worker intervals (seconds) ───────────────────────────────────────────
PARSE_INTERVAL_SECONDS: int = 120       # Check for unparsed posts every 2 min
PARSE_BATCH_SIZE: int = 10              # Max posts per batch
TRADINGVIEW_INTERVAL_SECONDS: int = 1800  # Scrape every 30 min
CONSENSUS_INTERVAL_SECONDS: int = 900   # Generate consensus every 15 min
PRICE_CHECK_INTERVAL_SECONDS: int = 300  # Check prices every 5 min
DAILY_PERF_HOUR_UTC: int = 22           # Run daily aggregation at 22:00 UTC

# ── Signal parser prompt ─────────────────────────────────────────────────
SIGNAL_PARSER_SYSTEM_PROMPT = """You are a trading signal parser. Extract structured trading data from \
the following analyst post about gold (XAUUSD).

Return ONLY valid JSON with this structure:
{
  "has_signal": true/false,
  "direction": "BUY" or "SELL",
  "entry_price": number or null,
  "stop_loss": number or null,
  "take_profit_1": number or null,
  "take_profit_2": number or null,
  "take_profit_3": number or null,
  "timeframe": "5min"|"15min"|"30min"|"1h"|"4h"|"daily"|"weekly",
  "timeframe_confidence": "explicit" or "inferred",
  "analysis_type": "technical"|"fundamental"|"sentiment"|"mixed",
  "confidence": 1-10,
  "key_reasons": ["reason1", "reason2", "reason3"],
  "valid_hours": number (how many hours this signal stays valid)
}

Rules for timeframe detection:
- If chart shows M5/M15/M30/H1/H4/D1/W1, use that (explicit)
- If not stated, infer from TP/SL distance:
  - SL < 30 pips -> 5min or 15min
  - SL 30-80 pips -> 30min or 1h
  - SL 80-200 pips -> 4h
  - SL > 200 pips -> daily or weekly
- If TP distance is very tight (< 50 pips), likely scalp (5min-15min)
- Words like "scalp" -> 5min/15min, "intraday" -> 1h, "swing" -> 4h/daily

Rules for valid_hours:
- Scalp signals: 2-4 hours
- Intraday: 8-16 hours
- Swing: 48-120 hours
- Position: 168-720 hours

If the post is not a trading signal (just news, commentary, or ads), \
set has_signal=false and leave other fields null.

The post language may be English, Farsi, Arabic, Russian, or any other \
language. Parse regardless of language."""
