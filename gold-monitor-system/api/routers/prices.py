"""
Prices router -- real-time gold, currency, and coin market prices.

Fetches live prices from TGJU (tgju.org), the most popular
Iranian gold/currency data provider.  Results are cached in Redis
for 2 minutes to avoid excessive API calls.

TGJU API returns DataTables JSON::

    {
        "data": [["open", "low", "high", "close", "change_html",
                  "change_pct_html", "gregorian_date", "jalali_date"], ...]
    }

Close price is ``data[0][3]`` — a comma-formatted string.
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
CACHE_TTL_SECONDS = 120  # 2 minutes

# TGJU individual indicator endpoint (DataTables format)
TGJU_API_BASE = "https://api.tgju.org/v1/market/indicator/summary-table-data"
# Fallback mirror
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


def _extract_close_price(data: dict[str, Any]) -> float | None:
    """Extract close price from TGJU DataTables response.

    Response format: ``{"data": [["open", "low", "high", "close", ...], ...]}``
    Close price is at index 3 of the first row.
    """
    rows = data.get("data")
    if not isinstance(rows, list) or not rows:
        return None

    first_row = rows[0]
    if not isinstance(first_row, list) or len(first_row) < 4:
        return None

    return _parse_number(first_row[3])


def _format_price(value: float, key: str) -> str:
    """Format price for display."""
    if key == "gold_global":
        # USD price — show with 2 decimals
        return f"{value:,.2f}"
    # Iranian prices are in Rial — convert to Toman (÷10)
    toman = value / 10
    return f"{toman:,.0f}"


async def _fetch_single_price(
    client: httpx.AsyncClient,
    key: str,
    indicator: str,
) -> dict[str, Any] | None:
    """Fetch a single indicator price, trying primary then fallback API."""
    for base_url in (TGJU_API_BASE, ACCESSBAN_API_BASE):
        url = f"{base_url}/{indicator}"
        try:
            resp = await client.get(url, params={"start": "0", "length": "1"})
            resp.raise_for_status()
            data = resp.json()
            price = _extract_close_price(data)
            if price is not None:
                meta = PRICE_META[key]
                return {
                    "value": price,
                    "formatted": _format_price(price, key),
                    "label": meta["label"],
                    "unit": meta["unit"],
                    "icon": meta["icon"],
                }
            logger.warning(
                "Could not parse close price for %s from %s: %s",
                key, base_url, str(data)[:300],
            )
        except httpx.HTTPStatusError as e:
            logger.warning(
                "HTTP %s for %s from %s", e.response.status_code, key, base_url,
            )
        except Exception:
            logger.warning("Failed to fetch %s from %s", key, base_url, exc_info=True)

    return None


async def _fetch_prices_from_tgju() -> dict[str, Any]:
    """Fetch current prices from TGJU indicator endpoints."""
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
            result = await _fetch_single_price(client, key, indicator)
            if result is not None:
                prices[key] = result

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
