"""
Prices router -- real-time gold, currency, and coin market prices.

Primary source: **BrsAPI** (``brsapi.ir/Api/Market/Gold_Currency.php``)
- Returns gold, currency, and crypto prices in a single call
- Requires an API key (``BRSAPI_KEY`` env var)
- Prices are already in Toman (no Rial conversion needed)

Fallback: **TGJU** (``call4.tgju.org/ajax.json``)
- Used when BrsAPI key is not configured or request fails
- Returns all prices in one call, prices in Rial (÷10 for Toman)

Results are cached in Redis for 60 seconds.
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
CACHE_TTL_SECONDS = 60  # 60s cache

# BrsAPI endpoint
BRSAPI_URL = "https://brsapi.ir/Api/Market/Gold_Currency.php"

# TGJU fallback
TGJU_REALTIME_URL = "https://call4.tgju.org/ajax.json"

# Display metadata for the frontend
PRICE_META = {
    "gold_global": {"label": "طلای جهانی", "unit": "USD/oz", "icon": "🌍"},
    "gold_18k": {"label": "طلای ۱۸ عیار", "unit": "تومان/گرم", "icon": "💛"},
    "usd": {"label": "دلار تتر", "unit": "تومان", "icon": "💵"},
    "emami_coin": {"label": "سکه بهار آزادی", "unit": "تومان", "icon": "🪙"},
}

# Map BrsAPI symbols to our price keys
BRSAPI_SYMBOL_MAP = {
    "XAUUSD": "gold_global",
    "IR_GOLD_18K": "gold_18k",
    "USDT_IRT": "usd",
    "IR_COIN_EMAMI": "emami_coin",
}

# Map TGJU indicator slugs to our price keys (fallback)
TGJU_INDICATORS = {
    "gold_global": "ons",
    "gold_18k": "geram18",
    "usd": "usdt-irr",
    "emami_coin": "sekee",
}


# ── Price parsing helpers ────────────────────────────────────────────


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


def _format_toman(value: float) -> str:
    """Format a Toman value with commas."""
    return f"{value:,.0f}"


def _format_usd(value: float) -> str:
    """Format a USD value with 2 decimals."""
    return f"{value:,.2f}"


# ── BrsAPI price fetching (primary) ──────────────────────────────────


async def _fetch_prices_brsapi() -> dict[str, Any]:
    """Fetch prices from BrsAPI.

    Response is an array with one element containing ``gold`` and
    ``currency`` arrays.  Each item has: symbol, name, price,
    change_value, change_percent, unit.

    Prices are already in Toman (gold) or Toman (currency).
    Gold ounce is in USD.
    """
    api_key = app_settings.BRSAPI_KEY
    if not api_key:
        return {}

    prices: dict[str, Any] = {}

    async with httpx.AsyncClient(
        timeout=10.0,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; GoldMonitor/1.0)",
            "Accept": "application/json",
        },
    ) as client:
        try:
            resp = await client.get(BRSAPI_URL, params={"key": api_key})
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.warning("Failed to fetch prices from BrsAPI", exc_info=True)
            return prices

    # Response is a list with one element
    if isinstance(data, list) and len(data) > 0:
        container = data[0]
    elif isinstance(data, dict):
        container = data
    else:
        logger.warning("BrsAPI unexpected format: %s", type(data))
        return prices

    # Process gold items
    gold_items = container.get("gold", [])
    currency_items = container.get("currency", [])
    all_items = gold_items + currency_items

    for item in all_items:
        if not isinstance(item, dict):
            continue

        symbol = item.get("symbol", "")
        our_key = BRSAPI_SYMBOL_MAP.get(symbol)
        if not our_key:
            continue

        price = _parse_number(item.get("price"))
        if price is None:
            continue

        meta = PRICE_META[our_key]
        is_usd = our_key == "gold_global"

        entry: dict[str, Any] = {
            "value": price,
            "formatted": _format_usd(price) if is_usd else _format_toman(price),
            "label": meta["label"],
            "unit": meta["unit"],
            "icon": meta["icon"],
        }

        # Add change info
        change_value = _parse_number(item.get("change_value"))
        change_pct = _parse_number(item.get("change_percent"))
        if change_value is not None and change_pct is not None:
            if is_usd:
                entry["change"] = f"{change_value:+,.2f}"
            else:
                entry["change"] = f"{change_value:+,.0f}"
            entry["change_pct"] = f"{change_pct:+.2f}%"
            entry["direction"] = (
                "up" if change_value > 0
                else "down" if change_value < 0
                else "flat"
            )

        prices[our_key] = entry

    return prices


# ── TGJU fallback ────────────────────────────────────────────────────


async def _fetch_prices_tgju() -> dict[str, Any]:
    """Fallback: fetch prices from TGJU real-time endpoint.

    TGJU prices are in Rial — divide by 10 for Toman.
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
            logger.warning("Failed to fetch prices from TGJU", exc_info=True)
            return prices

    current = data.get("current", data)

    for key, slug in TGJU_INDICATORS.items():
        indicator_data = current.get(slug)
        if not indicator_data or not isinstance(indicator_data, dict):
            continue

        price = _parse_number(indicator_data.get("p"))
        if price is None:
            continue

        meta = PRICE_META[key]
        is_usd = key == "gold_global"

        entry: dict[str, Any] = {
            "value": price,
            "formatted": _format_usd(price) if is_usd else _format_toman(price / 10),
            "label": meta["label"],
            "unit": meta["unit"],
            "icon": meta["icon"],
        }

        # Add change info if available
        change = _parse_number(indicator_data.get("d"))
        change_pct = _parse_number(indicator_data.get("dp"))
        if change is not None and change_pct is not None:
            if is_usd:
                entry["change"] = f"{change:+,.2f}"
                entry["change_pct"] = f"{change_pct:+.2f}%"
            else:
                entry["change"] = f"{change / 10:+,.0f}"
                entry["change_pct"] = f"{change_pct:+.2f}%"
            entry["direction"] = "up" if change > 0 else "down" if change < 0 else "flat"

        prices[key] = entry

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

    Prices are cached for 60 seconds.  Primary source is BrsAPI;
    falls back to TGJU real-time endpoint.
    """
    # Try cache first
    cached = await _get_cached_prices()
    if cached:
        return cached

    # Try BrsAPI first (primary)
    source = "brsapi.ir"
    prices = await _fetch_prices_brsapi()

    # Fallback to TGJU if BrsAPI failed or returned nothing
    if not prices:
        logger.info("BrsAPI prices empty, trying TGJU fallback")
        source = "tgju.org"
        prices = await _fetch_prices_tgju()

    result = {
        "prices": prices,
        "updated_at": time.time(),
        "source": source,
    }

    # Cache the result (even if partial)
    if prices:
        await _set_cached_prices(result)

    return result


# ── All-prices endpoint (full BrsAPI data) ───────────────────────────


ALL_CACHE_KEY = "prices:all"
ALL_CACHE_TTL_SECONDS = 60


async def _fetch_all_prices_brsapi() -> dict[str, Any] | None:
    """Fetch the full BrsAPI response with all gold, currency, crypto items."""
    api_key = app_settings.BRSAPI_KEY
    if not api_key:
        return None

    async with httpx.AsyncClient(
        timeout=10.0,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; GoldMonitor/1.0)",
            "Accept": "application/json",
        },
    ) as client:
        try:
            resp = await client.get(BRSAPI_URL, params={"key": api_key})
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.warning("Failed to fetch all prices from BrsAPI", exc_info=True)
            return None

    if isinstance(data, list) and len(data) > 0:
        container = data[0]
    elif isinstance(data, dict):
        container = data
    else:
        return None

    def _build_items(raw_items: list) -> list[dict[str, Any]]:
        result_items: list[dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            price = _parse_number(item.get("price"))
            if price is None:
                continue
            entry: dict[str, Any] = {
                "symbol": item.get("symbol", ""),
                "name": item.get("name", ""),
                "name_en": item.get("name_en", ""),
                "price": price,
                "unit": item.get("unit", ""),
                "date": item.get("date", ""),
                "time": item.get("time", ""),
            }
            change_value = _parse_number(item.get("change_value"))
            change_pct = _parse_number(item.get("change_percent"))
            if change_pct is not None:
                entry["change_percent"] = change_pct
                entry["direction"] = (
                    "up" if (change_value or 0) > 0
                    else "down" if (change_value or 0) < 0
                    else "flat"
                )
            if change_value is not None:
                entry["change_value"] = change_value
            # Crypto items may have description and market_cap icon
            if item.get("description"):
                entry["description"] = item["description"]
            if item.get("market_cap") and isinstance(item["market_cap"], str) and item["market_cap"].startswith("http"):
                entry["icon_url"] = item["market_cap"]
            result_items.append(entry)
        return result_items

    return {
        "gold": _build_items(container.get("gold", [])),
        "currency": _build_items(container.get("currency", [])),
        "cryptocurrency": _build_items(container.get("cryptocurrency", [])),
    }


@router.get("/all")
async def get_all_prices() -> dict[str, Any]:
    """Return all available prices grouped by category (gold, currency, crypto).

    Uses BrsAPI as the sole source since TGJU doesn't provide full data.
    Cached for 60 seconds.
    """
    # Try cache first
    try:
        r = await _get_redis()
        raw = await r.get(ALL_CACHE_KEY)
        await r.aclose()
        if raw:
            return json.loads(raw)
    except Exception:
        pass

    data = await _fetch_all_prices_brsapi()
    if data is None:
        return {"gold": [], "currency": [], "cryptocurrency": [], "updated_at": time.time(), "source": "unavailable"}

    result = {
        **data,
        "updated_at": time.time(),
        "source": "brsapi.ir",
    }

    # Cache
    try:
        r = await _get_redis()
        await r.setex(ALL_CACHE_KEY, ALL_CACHE_TTL_SECONDS, json.dumps(result))
        await r.aclose()
    except Exception:
        pass

    return result
