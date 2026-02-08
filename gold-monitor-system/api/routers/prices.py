"""
Prices router -- real-time gold, currency, and coin market prices.

Fetches live prices from TGJU (tgju.org), the most popular
Iranian gold/currency data provider.  Results are cached in Redis
for 2 minutes to avoid excessive API calls.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, status

from api.config import settings as app_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["prices"])

# ── Configuration ─────────────────────────────────────────────────────

CACHE_KEY = "prices:latest"
CACHE_TTL_SECONDS = 120  # 2 minutes

# TGJU main page data endpoint — returns all market indicators
TGJU_URL = "https://api.tgju.org/v1/data/sana/json"

# Fallback: individual indicator endpoints
TGJU_INDICATOR_BASE = "https://api.tgju.org/v1/market/indicator/summary-table-data"

# Map our price keys to TGJU indicator slugs
INDICATORS = {
    "gold_global": "ons",             # اونس جهانی طلا — USD/oz
    "gold_18k": "geram18",            # طلای ۱۸ عیار — تومان/گرم
    "usd": "price_dollar_rl",         # دلار آمریکا — تومان
    "emami_coin": "sekee",            # سکه امامی — تومان
}

# Display metadata for the frontend
PRICE_META = {
    "gold_global": {"label": "طلای جهانی", "unit": "USD/oz", "icon": "🌍"},
    "gold_18k": {"label": "طلای ۱۸ عیار", "unit": "تومان/گرم", "icon": "💛"},
    "usd": {"label": "دلار", "unit": "تومان", "icon": "💵"},
    "emami_coin": {"label": "سکه امامی", "unit": "تومان", "icon": "🪙"},
}


# ── Price fetching ────────────────────────────────────────────────────


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


def _extract_price_from_indicator(data: Any) -> float | None:
    """Extract price from a TGJU indicator API response.

    TGJU responses vary; we try several known structures.
    """
    if not isinstance(data, dict):
        return None

    # Structure 1: {"current": {"p": "2345.6"}}
    current = data.get("current")
    if isinstance(current, dict):
        p = _parse_number(current.get("p"))
        if p is not None:
            return p

    # Structure 2: {"data": {"p": "2345.6"}}
    d = data.get("data")
    if isinstance(d, dict):
        p = _parse_number(d.get("p"))
        if p is not None:
            return p

    # Structure 3: nested in response
    resp = data.get("response")
    if isinstance(resp, dict):
        for v in resp.values():
            if isinstance(v, dict):
                p = _parse_number(v.get("p"))
                if p is not None:
                    return p

    # Structure 4: top-level "p"
    p = _parse_number(data.get("p"))
    if p is not None:
        return p

    return None


async def _fetch_prices_from_tgju() -> dict[str, Any]:
    """Fetch current prices from TGJU individual indicator endpoints."""
    prices: dict[str, Any] = {}

    async with httpx.AsyncClient(
        timeout=10.0,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; GoldMonitor/1.0)",
            "Accept": "application/json",
        },
        follow_redirects=True,
    ) as client:
        for key, indicator in INDICATORS.items():
            url = f"{TGJU_INDICATOR_BASE}/{indicator}"
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                price = _extract_price_from_indicator(data)
                if price is not None:
                    meta = PRICE_META[key]
                    prices[key] = {
                        "value": price,
                        "formatted": _format_price(price, key),
                        "label": meta["label"],
                        "unit": meta["unit"],
                        "icon": meta["icon"],
                    }
                else:
                    logger.warning(
                        "Could not parse price for %s from TGJU response: %s",
                        key,
                        str(data)[:200],
                    )
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "TGJU HTTP error for %s: %s %s",
                    key, e.response.status_code, url,
                )
            except Exception:
                logger.warning("Failed to fetch %s price from TGJU", key, exc_info=True)

    return prices


def _format_price(value: float, key: str) -> str:
    """Format price for display."""
    if key == "gold_global":
        # USD price — show with 2 decimals
        return f"{value:,.2f}"
    else:
        # Toman — show whole numbers with thousand separators
        # TGJU returns values in Rial; convert to Toman (÷10)
        toman = value / 10 if value > 100_000 else value
        return f"{toman:,.0f}"


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

    Prices are cached for 2 minutes.  If the external API is unreachable,
    stale cache is returned (if available) or an empty response.
    """
    # Try cache first
    cached = await _get_cached_prices()
    if cached:
        return cached

    # Fetch fresh prices
    prices = await _fetch_prices_from_tgju()

    result = {
        "prices": prices,
        "updated_at": time.time(),
        "source": "tgju.org",
    }

    # Cache the result (even if partial)
    if prices:
        await _set_cached_prices(result)

    return result
