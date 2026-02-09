"""
Prices router -- real-time gold, currency, and coin market prices.

Fetches live prices from TGJU (tgju.org), the most popular
Iranian gold/currency data provider.  Results are cached in Redis
for 30 seconds to avoid excessive API calls.

Primary endpoint: ``https://call4.tgju.org/ajax.json``
Returns all current prices in a single call::

    {
        "current": {
            "ons": {"p": "5,013.53", "h": "...", "l": "...", "d": "52.38", "dp": 1.06, ...},
            "geram18": {"p": "187,804,000", ...},
            "price_dollar_rl": {"p": "1,589,500", ...},
            "sekee": {"p": "1,909,950,000", ...}
        }
    }

The ``p`` field is the current live price.
Iranian prices are in **Rial** (divide by 10 for Toman).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter

from api.config import settings as app_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["prices"])

# ── Configuration ─────────────────────────────────────────────────────

CACHE_KEY = "prices:latest"
CACHE_TTL_SECONDS = 30  # 30s cache — real-time prices update frequently

# TGJU real-time endpoint (returns all prices in one call)
TGJU_REALTIME_URL = "https://call4.tgju.org/ajax.json"
# Fallback: individual indicator endpoints (daily candle data, less fresh)
TGJU_API_BASE = "https://api.tgju.org/v1/market/indicator/summary-table-data"
ACCESSBAN_API_BASE = "https://api.accessban.com/v1/market/indicator/summary-table-data"

# Map our price keys to TGJU indicator slugs
INDICATORS = {
    "gold_global": "ons",             # اونس جهانی طلا — USD/oz
    "gold_18k": "geram18",            # طلای ۱۸ عیار — ریال/گرم
    "usd": "price_dollar_rl",         # دلار آمریکا — ریال
    "emami_coin": "sekee",            # سکه امامی — ریال
}

# Display metadata for the frontend
PRICE_META = {
    "gold_global": {"label": "طلای جهانی", "unit": "USD/oz", "icon": "🌍"},
    "gold_18k": {"label": "طلای ۱۸ عیار", "unit": "تومان/گرم", "icon": "💛"},
    "usd": {"label": "دلار", "unit": "تومان", "icon": "💵"},
    "emami_coin": {"label": "سکه امامی", "unit": "تومان", "icon": "🪙"},
}


# ── Price parsing ────────────────────────────────────────────────────


def _parse_number(raw: Any) -> float | None:
    """Best-effort extraction of a numeric value from various formats."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        cleaned = raw.strip().replace(",", "").replace("٬", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _format_price(value: float, key: str) -> str:
    """Format price for display."""
    if key == "gold_global":
        # USD price — show with 2 decimals
        return f"{value:,.2f}"
    # Iranian prices are in Rial — convert to Toman (÷10)
    toman = value / 10
    return f"{toman:,.0f}"


def _format_change(change: float, change_pct: float, key: str) -> dict[str, str]:
    """Format price change for display."""
    if key == "gold_global":
        return {
            "change": f"{change:+,.2f}",
            "change_pct": f"{change_pct:+.2f}%",
        }
    change_toman = change / 10
    return {
        "change": f"{change_toman:+,.0f}",
        "change_pct": f"{change_pct:+.2f}%",
    }


# ── Real-time price fetching (primary) ───────────────────────────────


async def _fetch_prices_realtime() -> dict[str, Any]:
    """Fetch all current prices from TGJU real-time endpoint.

    Returns all prices in a single HTTP call. The ``current`` object
    contains each indicator with ``p`` (price), ``d`` (change),
    ``dp`` (change %), ``h`` (high), ``l`` (low).
    """
    prices: dict[str, Any] = {}

    async with httpx.AsyncClient(
        timeout=10.0,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; GoldMonitor/1.0)",
            "Accept": "application/json",
        },
        follow_redirects=True,
    ) as client:
        try:
            resp = await client.get(TGJU_REALTIME_URL)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.warning("Failed to fetch real-time prices from TGJU", exc_info=True)
            return prices

    current = data.get("current", data)

    for key, slug in INDICATORS.items():
        indicator_data = current.get(slug)
        if not indicator_data or not isinstance(indicator_data, dict):
            continue

        price = _parse_number(indicator_data.get("p"))
        if price is None:
            continue

        meta = PRICE_META[key]
        entry: dict[str, Any] = {
            "value": price,
            "formatted": _format_price(price, key),
            "label": meta["label"],
            "unit": meta["unit"],
            "icon": meta["icon"],
        }

        # Add change info if available
        change = _parse_number(indicator_data.get("d"))
        change_pct = _parse_number(indicator_data.get("dp"))
        if change is not None and change_pct is not None:
            entry.update(_format_change(change, change_pct, key))
            entry["direction"] = "up" if change > 0 else "down" if change < 0 else "flat"

        prices[key] = entry

    return prices


# ── Fallback: individual indicator endpoints (daily data) ────────────


def _extract_close_price(data: dict[str, Any]) -> float | None:
    """Extract close price from TGJU DataTables response (fallback)."""
    rows = data.get("data")
    if not isinstance(rows, list) or not rows:
        return None
    first_row = rows[0]
    if not isinstance(first_row, list) or len(first_row) < 4:
        return None
    return _parse_number(first_row[3])


async def _fetch_prices_fallback() -> dict[str, Any]:
    """Fallback: fetch prices from individual indicator endpoints (daily candle)."""
    prices: dict[str, Any] = {}

    async with httpx.AsyncClient(
        timeout=15.0,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; GoldMonitor/1.0)",
            "Accept": "application/json",
        },
        follow_redirects=True,
    ) as client:
        for key, indicator in INDICATORS.items():
            for base_url in (TGJU_API_BASE, ACCESSBAN_API_BASE):
                url = f"{base_url}/{indicator}"
                try:
                    resp = await client.get(url, params={"start": "0", "length": "1"})
                    resp.raise_for_status()
                    data = resp.json()
                    price = _extract_close_price(data)
                    if price is not None:
                        meta = PRICE_META[key]
                        prices[key] = {
                            "value": price,
                            "formatted": _format_price(price, key),
                            "label": meta["label"],
                            "unit": meta["unit"],
                            "icon": meta["icon"],
                        }
                        break
                except Exception:
                    continue

    return prices


# ── Redis cache helpers ───────────────────────────────────────────────


async def _get_redis() -> aioredis.Redis:
    """Get a Redis connection."""
    return aioredis.from_url(app_settings.REDIS_URL, decode_responses=True)


async def _get_cached_prices() -> dict[str, Any] | None:
    """Return cached prices if available."""
    try:
        r = await _get_redis()
        raw = await r.get(CACHE_KEY)
        await r.aclose()
        if raw:
            return json.loads(raw)
    except Exception:
        logger.debug("Redis cache miss or error", exc_info=True)
    return None


async def _set_cached_prices(prices: dict[str, Any]) -> None:
    """Store prices in Redis cache."""
    try:
        r = await _get_redis()
        await r.setex(CACHE_KEY, CACHE_TTL_SECONDS, json.dumps(prices))
        await r.aclose()
    except Exception:
        logger.debug("Redis cache set failed", exc_info=True)


# ── API Endpoint ──────────────────────────────────────────────────────


@router.get("")
async def get_prices() -> dict[str, Any]:
    """Return current market prices.

    Prices are cached for 30 seconds.  Primary source is the TGJU
    real-time endpoint; falls back to individual indicator endpoints.
    """
    # Try cache first
    cached = await _get_cached_prices()
    if cached:
        return cached

    # Try real-time endpoint first
    prices = await _fetch_prices_realtime()

    # Fallback to individual endpoints if real-time failed
    if not prices:
        logger.info("Real-time prices empty, trying fallback endpoints")
        prices = await _fetch_prices_fallback()

    result = {
        "prices": prices,
        "updated_at": time.time(),
        "source": "tgju.org",
    }

    # Cache the result (even if partial)
    if prices:
        await _set_cached_prices(result)

    return result
