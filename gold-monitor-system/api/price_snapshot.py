"""
Lightweight price snapshot — grabs raw numeric prices for stamping on alerts
and for the price outcome tracker.

Tries three sources in order:
1. Redis cache (populated by the /api/prices endpoint, 60s TTL)
2. BrsAPI (primary, requires BRSAPI_KEY)
3. TGJU (fallback, no key needed)
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from api.config import settings

logger = logging.getLogger(__name__)

BRSAPI_URL = "https://brsapi.ir/Api/Market/Gold_Currency.php"
TGJU_URL = "https://call4.tgju.org/ajax.json"
REDIS_CACHE_KEY = "prices:latest"

BRSAPI_SYMBOL_MAP = {
    "XAUUSD": "xauusd",
    "IR_GOLD_18K": "gold_18k",
    "USDT_IRT": "usdirr",
    "IR_COIN_EMAMI": "coin",
}

TGJU_INDICATORS = {
    "xauusd": "ons",
    "gold_18k": "geram18",
    "usdirr": "usdt-irr",
    "coin": "sekee",
}


def _parse_number(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        cleaned = raw.strip().replace(",", "").replace("\u066c", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


async def get_price_snapshot(
    redis_conn=None,
) -> dict[str, float | None]:
    """Return current prices as raw numeric values.

    Keys: ``xauusd`` (USD/oz), ``usdirr`` (Toman), ``coin`` (Toman),
    ``gold_18k`` (Toman/gram).

    Returns a dict with ``None`` for any price that could not be fetched.
    """
    result: dict[str, float | None] = {
        "xauusd": None,
        "usdirr": None,
        "coin": None,
        "gold_18k": None,
    }

    # --- 1. Try Redis cache (fastest, no HTTP call) ---
    if redis_conn is not None:
        try:
            raw = await redis_conn.get(REDIS_CACHE_KEY)
            if raw:
                data = json.loads(raw)
                prices = data.get("prices", {})
                result["xauusd"] = prices.get("gold_global", {}).get("value")
                result["gold_18k"] = prices.get("gold_18k", {}).get("value")
                result["usdirr"] = prices.get("usd", {}).get("value")
                result["coin"] = prices.get("emami_coin", {}).get("value")
                if any(v is not None for v in result.values()):
                    return result
        except Exception:
            logger.debug("Redis price cache miss", exc_info=True)

    # --- 2. Try BrsAPI (primary) ---
    if settings.BRSAPI_KEY:
        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                headers={"User-Agent": "GoldMonitor/1.0"},
            ) as client:
                resp = await client.get(
                    BRSAPI_URL, params={"key": settings.BRSAPI_KEY}
                )
                resp.raise_for_status()
                data = resp.json()

            container = data[0] if isinstance(data, list) and data else data
            if isinstance(container, dict):
                for item in container.get("gold", []) + container.get(
                    "currency", []
                ):
                    if not isinstance(item, dict):
                        continue
                    symbol = item.get("symbol", "")
                    key = BRSAPI_SYMBOL_MAP.get(symbol)
                    if key:
                        result[key] = _parse_number(item.get("price"))

            if any(v is not None for v in result.values()):
                return result
        except Exception:
            logger.debug("BrsAPI price fetch failed", exc_info=True)

    # --- 3. Fallback to TGJU ---
    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            headers={"User-Agent": "GoldMonitor/1.0"},
            follow_redirects=True,
        ) as client:
            resp = await client.get(TGJU_URL)
            resp.raise_for_status()
            data = resp.json()

        current = data.get("current", data)
        for key, slug in TGJU_INDICATORS.items():
            ind = current.get(slug)
            if ind and isinstance(ind, dict):
                val = _parse_number(ind.get("p"))
                if val is not None:
                    # TGJU prices are in Rial; divide by 10 for Toman
                    # (except xauusd which is already in USD)
                    result[key] = val if key == "xauusd" else val / 10
    except Exception:
        logger.debug("TGJU price fetch failed", exc_info=True)

    return result
