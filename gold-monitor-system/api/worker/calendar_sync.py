"""
Calendar sync worker — fetches economic calendar events from external APIs.

Runs every 6 hours (configurable via CALENDAR_SYNC_INTERVAL).
Fetches this week's and next week's events, upserts into database.

Data sources (in priority order):
1. JBlanked Calendar API (FxStreet — includes actuals) — requires JBLANKED_API_KEY
2. Finnhub Economic Calendar API — requires FINNHUB_API_KEY (paid plan $50/mo)
3. Forex Factory Calendar (free, no API key) — schedule only, NO actual values

Actuals enrichment:
- ForexFactory JSON does NOT include actual values (confirmed: the field is absent)
- JBlanked FxStreet endpoint includes actuals for released events
- When ForexFactory is the primary source, JBlanked is used to enrich actuals
  (if JBLANKED_API_KEY is set, limited to 1 request/day on free tier)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from sqlalchemy import select, and_, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from api.calendar_config import (
    get_affected_assets,
    translate_event_name,
)
from api.config import settings
from api.database import AsyncSessionLocal
from api.models import EconomicEvent

logger = logging.getLogger("gold_monitor.calendar_sync")

# Cooldown to prevent ForexFactory rate limiting (2 requests per 5 min)
_last_sync_utc: datetime | None = None
_SYNC_COOLDOWN_SECONDS = 300  # 5 minutes

# JBlanked enrichment: track last request to stay within free-tier limit (1/day)
_last_jblanked_enrich_utc: datetime | None = None
_JBLANKED_ENRICH_COOLDOWN = 86400  # 24 hours

# Rate limit: 1 request per second for JBlanked
_RATE_LIMIT_DELAY = 1.1

# Impact level mapping for JBlanked API
_JBLANKED_IMPACT_MAP = {
    "high": "high",
    "medium": "medium",
    "moderate": "medium",
    "low": "low",
    "none": "low",
    "holiday": "low",
    "non-economic": "low",
    # MQL5 uses numeric strength
    "3": "high",
    "2": "medium",
    "1": "low",
    "0": "low",
}

# Finnhub impact mapping
_FINNHUB_IMPACT_MAP = {
    3: "high",
    2: "medium",
    1: "low",
    0: "low",
}


def _normalize_impact(raw: str | int | None) -> str:
    """Normalize an impact value from the API to high/medium/low."""
    if raw is None:
        return "low"
    if isinstance(raw, int):
        return _FINNHUB_IMPACT_MAP.get(raw, "low")
    raw_lower = str(raw).lower().strip()
    return _JBLANKED_IMPACT_MAP.get(raw_lower, "low")


def _parse_datetime(dt_str: str | None) -> datetime | None:
    """Parse a datetime string from various API formats."""
    if not dt_str:
        return None
    # Try multiple formats
    for fmt in [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]:
        try:
            dt = datetime.strptime(dt_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _extract_country_from_currency(currency: str) -> str:
    """Derive a country code from a currency code."""
    mapping = {
        "USD": "US", "EUR": "EU", "GBP": "GB", "JPY": "JP",
        "CHF": "CH", "AUD": "AU", "CAD": "CA", "NZD": "NZ",
        "CNY": "CN", "CNH": "CN", "IRR": "IR", "KRW": "KR",
        "SGD": "SG", "HKD": "HK", "SEK": "SE", "NOK": "NO",
        "DKK": "DK", "PLN": "PL", "TRY": "TR", "ZAR": "ZA",
        "BRL": "BR", "MXN": "MX", "INR": "IN", "RUB": "RU",
    }
    return mapping.get(currency.upper(), "")


# ── Name normalization for matching events across sources ──────────────

_SUFFIX_VARIANTS = {
    " m/m": " mom",
    " q/q": " qoq",
    " y/y": " yoy",
    " (mom)": " mom",
    " (qoq)": " qoq",
    " (yoy)": " yoy",
    " month-over-month": " mom",
    " quarter-over-quarter": " qoq",
    " year-over-year": " yoy",
}

_STRIP_WORDS = {
    "preliminary", "prelim", "revised", "final", "flash",
    "advanced", "adv", "initial", "prel",
}


def _normalize_event_name(name: str) -> str:
    """Normalize event name for cross-source matching."""
    n = name.lower().strip()
    for old, new in _SUFFIX_VARIANTS.items():
        n = n.replace(old, new)
    return n


def _fuzzy_event_match(name_a: str, name_b: str) -> bool:
    """Check if two event names refer to the same event (cross-source matching).

    Handles differences like:
    - "CPI m/m" vs "CPI MoM"
    - "GDP q/q" vs "GDP QoQ (Preliminary)"
    """
    a = _normalize_event_name(name_a)
    b = _normalize_event_name(name_b)

    if a == b:
        return True

    # Strip qualifiers and try again
    a_core = a
    b_core = b
    for word in _STRIP_WORDS:
        a_core = a_core.replace(word, "").strip()
        b_core = b_core.replace(word, "").strip()
    a_core = " ".join(a_core.split())
    b_core = " ".join(b_core.split())

    if a_core == b_core:
        return True

    # Substring match (one contained in the other)
    if len(a_core) > 4 and len(b_core) > 4:
        if a_core in b_core or b_core in a_core:
            return True

    return False


async def _fetch_jblanked_week(
    session: aiohttp.ClientSession,
    endpoint: str,
) -> list[dict[str, Any]]:
    """Fetch events from a JBlanked calendar endpoint."""
    if not settings.JBLANKED_API_KEY:
        return []

    headers = {
        "Authorization": f"Api-Key {settings.JBLANKED_API_KEY}",
        "Accept": "application/json",
    }
    try:
        async with session.get(endpoint, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                data = await resp.json()
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "results" in data:
                    return data["results"]
                elif isinstance(data, dict) and "data" in data:
                    return data["data"]
                return []
            else:
                text = await resp.text()
                logger.warning("JBlanked API returned %d: %s", resp.status, text[:200])
                return []
    except Exception:
        logger.warning("JBlanked API request failed for %s", endpoint, exc_info=True)
        return []


async def _fetch_finnhub_calendar(
    session: aiohttp.ClientSession,
    from_date: str,
    to_date: str,
) -> list[dict[str, Any]]:
    """Fetch events from Finnhub economic calendar API."""
    if not settings.FINNHUB_API_KEY:
        return []

    url = f"https://finnhub.io/api/v1/calendar/economic?from={from_date}&to={to_date}&token={settings.FINNHUB_API_KEY}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                data = await resp.json()
                logger.info("Finnhub raw response keys: %s", list(data.keys()) if isinstance(data, dict) else type(data).__name__)
                if isinstance(data, dict) and "economicCalendar" in data:
                    cal = data["economicCalendar"]
                    # Handle both list and nested dict formats
                    if isinstance(cal, list):
                        return cal
                    elif isinstance(cal, dict):
                        # Some Finnhub responses nest events under "result"
                        return cal.get("result", [])
                return []
            elif resp.status == 403:
                logger.warning(
                    "Finnhub API returned 403 — economic calendar requires "
                    "paid plan ($50/mo). See https://finnhub.io/pricing"
                )
                return []
            else:
                text = await resp.text()
                logger.warning("Finnhub API returned %d: %s", resp.status, text[:300])
                return []
    except Exception:
        logger.warning("Finnhub API request failed", exc_info=True)
        return []


async def _fetch_forexfactory_calendar(
    session: aiohttp.ClientSession,
) -> list[dict[str, Any]]:
    """Fetch events from Forex Factory free JSON endpoint (no API key needed).

    Returns this week's economic events. Rate limit: 2 req / 5 min.
    Fields: title, country (currency code), date (ISO 8601), impact, forecast, previous.
    """
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    try:
        headers = {
            "User-Agent": "GoldMonitor/1.0",
            "Accept": "application/json",
        }
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                data = await resp.json()
                if isinstance(data, list):
                    logger.info("ForexFactory returned %d raw events.", len(data))
                    return data
                return []
            else:
                text = await resp.text()
                logger.warning("ForexFactory returned %d: %s", resp.status, text[:300])
                return []
    except Exception:
        logger.warning("ForexFactory request failed", exc_info=True)
        return []


def _parse_forexfactory_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a Forex Factory calendar event into our model format.

    FF fields: title, country (currency code like USD), date (ISO 8601),
    impact (High/Medium/Low/Holiday), forecast, previous.
    NOTE: "actual" field does not exist in FF JSON exports.
    """
    name = raw.get("title") or ""
    if not name:
        return None

    dt_str = raw.get("date") or ""
    dt = _parse_datetime(dt_str)
    if not dt:
        return None

    # FF uses currency code in "country" field (e.g., "USD", "EUR")
    currency = raw.get("country") or ""
    country = _extract_country_from_currency(currency)
    impact_raw = raw.get("impact") or "Low"

    forecast = raw.get("forecast")
    previous = raw.get("previous")

    if forecast is not None:
        forecast = str(forecast).strip() if str(forecast).strip() else None
    if previous is not None:
        previous = str(previous).strip() if str(previous).strip() else None

    return {
        "event_name": name.strip(),
        "event_name_fa": translate_event_name(name.strip()),
        "country": country.upper()[:10] if country else "",
        "currency": currency.upper()[:10] if currency else "",
        "category": "",
        "datetime_utc": dt,
        "impact": _normalize_impact(impact_raw),
        "actual": None,  # FF never provides actuals
        "forecast": forecast,
        "previous": previous,
        "source": "forexfactory",
        "affected_assets": get_affected_assets(name.strip(), currency),
    }


def _parse_jblanked_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a JBlanked calendar event into our model format."""
    name = raw.get("name") or raw.get("event") or raw.get("title") or ""
    if not name:
        return None

    dt_str = raw.get("date") or raw.get("datetime") or raw.get("time") or ""
    dt = _parse_datetime(dt_str)
    if not dt:
        return None

    currency = raw.get("currency") or raw.get("country") or ""
    impact_raw = raw.get("impact") or raw.get("importance") or raw.get("strength") or "low"
    country = raw.get("country") or _extract_country_from_currency(currency)

    actual = raw.get("actual")
    forecast = raw.get("forecast")
    previous = raw.get("previous")

    # Normalize empty strings to None
    if actual is not None:
        actual = str(actual).strip() if str(actual).strip() else None
    if forecast is not None:
        forecast = str(forecast).strip() if str(forecast).strip() else None
    if previous is not None:
        previous = str(previous).strip() if str(previous).strip() else None

    category = raw.get("category") or raw.get("type") or ""

    return {
        "event_name": name.strip(),
        "event_name_fa": translate_event_name(name.strip()),
        "country": country.upper()[:10] if country else "",
        "currency": currency.upper()[:10] if currency else "",
        "category": category.lower()[:50] if category else "",
        "datetime_utc": dt,
        "impact": _normalize_impact(impact_raw),
        "actual": actual,
        "forecast": forecast,
        "previous": previous,
        "source": "fxstreet",
        "affected_assets": get_affected_assets(name.strip(), currency),
    }


def _parse_finnhub_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a Finnhub calendar event into our model format."""
    name = raw.get("event") or ""
    if not name:
        return None

    dt_str = raw.get("time") or raw.get("date") or ""
    dt = _parse_datetime(dt_str)
    if not dt:
        # Try just date
        date_str = raw.get("date")
        if date_str:
            dt = _parse_datetime(date_str)
    if not dt:
        return None

    currency = raw.get("currency") or raw.get("country") or ""
    impact_raw = raw.get("impact")
    country = raw.get("country") or _extract_country_from_currency(currency)

    actual = raw.get("actual")
    forecast = raw.get("estimate")
    previous = raw.get("prev")

    if actual is not None:
        actual = str(actual).strip() if str(actual).strip() else None
    if forecast is not None:
        forecast = str(forecast).strip() if str(forecast).strip() else None
    if previous is not None:
        previous = str(previous).strip() if str(previous).strip() else None

    return {
        "event_name": name.strip(),
        "event_name_fa": translate_event_name(name.strip()),
        "country": country.upper()[:10] if country else "",
        "currency": currency.upper()[:10] if currency else "",
        "category": "",
        "datetime_utc": dt,
        "impact": _normalize_impact(impact_raw),
        "actual": actual,
        "forecast": forecast,
        "previous": previous,
        "source": "finnhub",
        "affected_assets": get_affected_assets(name.strip(), currency),
    }


async def _upsert_events(events: list[dict[str, Any]]) -> int:
    """Upsert parsed events into the database. Returns count of events processed."""
    if not events:
        return 0

    count = 0
    async with AsyncSessionLocal() as session:
        for event_data in events:
            try:
                stmt = pg_insert(EconomicEvent).values(
                    event_name=event_data["event_name"],
                    event_name_fa=event_data["event_name_fa"],
                    country=event_data["country"],
                    currency=event_data["currency"],
                    category=event_data["category"],
                    datetime_utc=event_data["datetime_utc"],
                    impact=event_data["impact"],
                    actual=event_data["actual"],
                    forecast=event_data["forecast"],
                    previous=event_data["previous"],
                    source=event_data["source"],
                    affected_assets=event_data["affected_assets"],
                )
                # On conflict (same event_name + datetime), update fields
                # Use COALESCE to preserve existing actual value if new one is NULL
                update_set = {
                    "event_name_fa": event_data["event_name_fa"],
                    "country": event_data["country"],
                    "currency": event_data["currency"],
                    "category": event_data["category"],
                    "impact": event_data["impact"],
                    "forecast": event_data["forecast"],
                    "previous": event_data["previous"],
                    "affected_assets": event_data["affected_assets"],
                    "updated_at": datetime.now(timezone.utc),
                }
                # Only overwrite actual if new value is non-null
                if event_data["actual"] is not None:
                    update_set["actual"] = event_data["actual"]
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_econ_events_name_datetime",
                    set_=update_set,
                )
                await session.execute(stmt)
                count += 1
            except Exception:
                logger.warning(
                    "Failed to upsert event %s", event_data.get("event_name", "?"),
                    exc_info=True,
                )
        await session.commit()

    return count


async def _enrich_actuals_from_jblanked(http_session: aiohttp.ClientSession) -> int:
    """Enrich past events with actual values from JBlanked FxStreet API.

    JBlanked FxStreet endpoint includes actual values for released events.
    Free tier allows 1 request/day, so we rate-limit accordingly.
    Uses fuzzy name matching to handle naming differences between FF and FxStreet.

    Returns the number of events updated.
    """
    global _last_jblanked_enrich_utc

    if not settings.JBLANKED_API_KEY:
        return 0

    now = datetime.now(timezone.utc)

    # Rate limit: 1 request per day for free tier
    if _last_jblanked_enrich_utc:
        elapsed = (now - _last_jblanked_enrich_utc).total_seconds()
        if elapsed < _JBLANKED_ENRICH_COOLDOWN:
            remaining_h = (_JBLANKED_ENRICH_COOLDOWN - elapsed) / 3600
            logger.info(
                "JBlanked enrichment cooldown: %.1fh remaining (free tier: 1 req/day).",
                remaining_h,
            )
            return 0

    # Fetch this week's events from FxStreet (includes actuals)
    logger.info("Fetching actuals from JBlanked FxStreet endpoint...")
    fxstreet_events = await _fetch_jblanked_week(
        http_session,
        "https://www.jblanked.com/news/api/fxstreet/calendar/week/",
    )
    _last_jblanked_enrich_utc = datetime.now(timezone.utc)

    if not fxstreet_events:
        logger.warning("JBlanked FxStreet returned no events for actuals enrichment.")
        return 0

    # Parse events and collect those with actuals
    actuals_map: list[tuple[str, str, datetime | None, str]] = []
    for raw in fxstreet_events:
        parsed = _parse_jblanked_event(raw)
        if parsed and parsed["actual"]:
            actuals_map.append((
                parsed["event_name"],
                parsed["currency"],
                parsed["datetime_utc"],
                parsed["actual"],
            ))

    if not actuals_map:
        logger.info(
            "JBlanked FxStreet returned %d events but none have actuals yet.",
            len(fxstreet_events),
        )
        return 0

    logger.info(
        "JBlanked FxStreet: %d events with actuals (from %d total).",
        len(actuals_map), len(fxstreet_events),
    )

    # Find DB events without actuals from the past week
    total_updated = 0
    async with AsyncSessionLocal() as db_session:
        week_ago = now - timedelta(days=7)
        stmt = select(EconomicEvent).where(
            and_(
                EconomicEvent.datetime_utc >= week_ago,
                EconomicEvent.datetime_utc < now,
                EconomicEvent.actual.is_(None),
            )
        )
        result = await db_session.execute(stmt)
        events = result.scalars().all()

        if not events:
            logger.info("No past events without actuals to enrich.")
            return 0

        logger.info("Found %d past events without actuals to enrich.", len(events))

        for event in events:
            for fx_name, fx_currency, fx_dt, fx_actual in actuals_map:
                # Currency must match
                if event.currency and fx_currency and event.currency != fx_currency:
                    continue

                # Names must match (fuzzy)
                if not _fuzzy_event_match(event.event_name, fx_name):
                    continue

                # Datetime should be within 2 hours (same event, different timezone offsets)
                if fx_dt and event.datetime_utc:
                    dt_diff = abs((event.datetime_utc - fx_dt).total_seconds())
                    if dt_diff > 7200:
                        continue

                event.actual = fx_actual
                total_updated += 1
                break

        if total_updated:
            await db_session.commit()

    logger.warning("Actuals enrichment done: %d events updated from JBlanked FxStreet.", total_updated)
    return total_updated


async def sync_calendar(force: bool = False) -> dict[str, Any]:
    """Main sync function — fetch events from APIs and upsert into DB.

    Returns a summary dict with counts.
    Uses a 5-minute cooldown to prevent ForexFactory rate limiting.
    Pass force=True to bypass cooldown (used by manual sync endpoint).
    """
    global _last_sync_utc

    now = datetime.now(timezone.utc)

    # Cooldown check — ForexFactory only allows 2 requests per 5 minutes
    if not force and _last_sync_utc:
        elapsed = (now - _last_sync_utc).total_seconds()
        if elapsed < _SYNC_COOLDOWN_SECONDS:
            # Still try actuals enrichment during cooldown
            enriched = 0
            try:
                async with aiohttp.ClientSession() as s:
                    enriched = await _enrich_actuals_from_jblanked(s)
            except Exception:
                pass
            return {
                "source": "cooldown",
                "fetched": 0,
                "upserted": 0,
                "enriched_actuals": enriched,
                "note": f"Cooldown active, {int(_SYNC_COOLDOWN_SECONDS - elapsed)}s remaining",
            }

    # Fetch this week + next week
    week_start = now - timedelta(days=now.weekday())  # Monday
    from_date = week_start.strftime("%Y-%m-%d")
    to_date = (week_start + timedelta(days=13)).strftime("%Y-%m-%d")

    logger.warning(
        "Calendar sync: range=%s..%s, JBlanked=%s, Finnhub=%s",
        from_date, to_date,
        "SET" if settings.JBLANKED_API_KEY else "no",
        "SET" if settings.FINNHUB_API_KEY else "no",
    )

    all_events: list[dict[str, Any]] = []
    source_used = "none"

    async with aiohttp.ClientSession() as http_session:
        # Try JBlanked first (FxStreet endpoint — includes actuals)
        if settings.JBLANKED_API_KEY:
            logger.info("Fetching calendar from JBlanked FxStreet API...")
            # This week (FxStreet — includes actuals for released events)
            this_week = await _fetch_jblanked_week(
                http_session,
                "https://www.jblanked.com/news/api/fxstreet/calendar/week/",
            )
            for raw in this_week:
                parsed = _parse_jblanked_event(raw)
                if parsed:
                    all_events.append(parsed)

            await asyncio.sleep(_RATE_LIMIT_DELAY)

            # Next week via date range (MQL5 range endpoint as fallback)
            next_week_start = week_start + timedelta(days=7)
            next_week_end = next_week_start + timedelta(days=6)
            next_week = await _fetch_jblanked_week(
                http_session,
                f"https://www.jblanked.com/news/api/mql5/calendar/range/?from={next_week_start.strftime('%Y-%m-%d')}&to={next_week_end.strftime('%Y-%m-%d')}",
            )
            for raw in next_week:
                parsed = _parse_jblanked_event(raw)
                if parsed:
                    all_events.append(parsed)

            if all_events:
                actuals_count = sum(1 for e in all_events if e.get("actual"))
                source_used = "jblanked_fxstreet"
                logger.info(
                    "JBlanked returned %d events (%d with actuals).",
                    len(all_events), actuals_count,
                )

        # Fallback to Finnhub (requires paid plan for economic calendar)
        if not all_events and settings.FINNHUB_API_KEY:
            logger.info("Falling back to Finnhub API...")
            finnhub_events = await _fetch_finnhub_calendar(
                http_session, from_date, to_date,
            )
            logger.info("Finnhub raw events: %d", len(finnhub_events))
            if finnhub_events:
                logger.info("Finnhub first event sample: %s", str(finnhub_events[0])[:300])
            for raw in finnhub_events:
                parsed = _parse_finnhub_event(raw)
                if parsed:
                    all_events.append(parsed)

            logger.info("Finnhub parsed events: %d (from %d raw)", len(all_events), len(finnhub_events))
            if all_events:
                source_used = "finnhub"

        # Fallback to Forex Factory (free, no API key needed)
        # NOTE: FF provides schedule/dates/impact/forecast/previous but NEVER actuals
        if not all_events:
            if not settings.JBLANKED_API_KEY:
                logger.warning(
                    "Using ForexFactory (no actuals). "
                    "Set JBLANKED_API_KEY for actual values — "
                    "free key at https://www.jblanked.com/news/api/docs/calendar/"
                )
            logger.info("Falling back to ForexFactory (free)...")
            ff_events = await _fetch_forexfactory_calendar(http_session)
            for raw in ff_events:
                parsed = _parse_forexfactory_event(raw)
                if parsed:
                    all_events.append(parsed)

            if all_events:
                source_used = "forexfactory"
                logger.info("ForexFactory parsed %d events (no actuals available).", len(all_events))

    # Mark sync time AFTER fetching to prevent rate limiting on next call
    _last_sync_utc = datetime.now(timezone.utc)

    if not all_events:
        logger.warning("No calendar events fetched from any source.")
        # Still try enrichment even if no new events
        enriched = 0
        try:
            async with aiohttp.ClientSession() as s:
                enriched = await _enrich_actuals_from_jblanked(s)
        except Exception:
            pass
        return {"source": source_used, "fetched": 0, "upserted": 0, "enriched_actuals": enriched}

    # Upsert into database
    upserted = await _upsert_events(all_events)
    logger.warning("Calendar sync complete: %d fetched, %d upserted from %s.",
                len(all_events), upserted, source_used)

    # Enrich past events with actuals from JBlanked FxStreet
    # (only when FF is the primary source — JBlanked primary already has actuals)
    enriched = 0
    if source_used == "forexfactory" and settings.JBLANKED_API_KEY:
        try:
            async with aiohttp.ClientSession() as enrich_session:
                enriched = await _enrich_actuals_from_jblanked(enrich_session)
        except Exception as exc:
            logger.warning("Actuals enrichment failed: %s", str(exc)[:200])
    elif source_used == "forexfactory" and not settings.JBLANKED_API_KEY:
        # Log how many past events lack actuals
        try:
            async with AsyncSessionLocal() as db_session:
                week_ago = now - timedelta(days=7)
                stmt = select(func.count()).select_from(EconomicEvent).where(
                    and_(
                        EconomicEvent.datetime_utc >= week_ago,
                        EconomicEvent.datetime_utc < now,
                        EconomicEvent.actual.is_(None),
                    )
                )
                result = await db_session.execute(stmt)
                missing_count = result.scalar() or 0
                if missing_count > 0:
                    logger.warning(
                        "%d past events have no actual values. "
                        "ForexFactory does not provide actuals. "
                        "Set JBLANKED_API_KEY for actuals enrichment — "
                        "free key at https://www.jblanked.com/news/api/docs/calendar/",
                        missing_count,
                    )
        except Exception:
            pass

    return {
        "source": source_used,
        "fetched": len(all_events),
        "upserted": upserted,
        "enriched_actuals": enriched,
    }


async def calendar_sync_loop() -> None:
    """Run the calendar sync in a loop (every CALENDAR_SYNC_INTERVAL seconds).

    Intended to be run as an asyncio task from the worker or API startup.
    """
    interval = settings.CALENDAR_SYNC_INTERVAL
    logger.info("Calendar sync loop started (interval=%ds).", interval)

    while True:
        try:
            result = await sync_calendar()
            logger.info("Calendar sync result: %s", result)
        except Exception:
            logger.error("Calendar sync failed", exc_info=True)
        await asyncio.sleep(interval)
