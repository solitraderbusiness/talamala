"""Price checker and signal outcome evaluator for the Signal Aggregator.

Periodically fetches the current XAUUSD price, records a tick, and then
walks through all active ``ParsedSignal`` rows to check whether any
take-profit, stop-loss, or expiry condition has been met.  Updates both
the signal status and the corresponding source statistics.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update

from api.database import AsyncSessionLocal
from api.signal_aggregator.config import PRICE_CHECK_INTERVAL_SECONDS
from api.signal_aggregator.models import ParsedSignal, SignalPriceTick, SignalSource
from api.signal_aggregator.utils.weight_calculator import calculate_source_weight

logger = logging.getLogger("signal_aggregator.price_checker")

_BINANCE_URL = "https://api.binance.com/api/v3/ticker/price"
_FALLBACK_URL = "https://data-asg.goldprice.org/dbXRates/USD"
_REQUEST_TIMEOUT = 15.0

# Gold pip = 0.1 USD (10 pips = $1)
_PIP_SIZE = 0.1


async def _fetch_price_binance(client: httpx.AsyncClient) -> float | None:
    """Fetch XAUUSD(T) price from Binance."""
    try:
        resp = await client.get(
            _BINANCE_URL,
            params={"symbol": "XAUUSDT"},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        price = float(data["price"])
        logger.debug("Binance XAUUSDT price: %.2f", price)
        return price
    except Exception:
        logger.warning("Failed to fetch price from Binance", exc_info=True)
        return None


async def _fetch_price_fallback(client: httpx.AsyncClient) -> float | None:
    """Fallback: fetch gold price from goldprice.org."""
    try:
        resp = await client.get(
            _FALLBACK_URL,
            timeout=_REQUEST_TIMEOUT,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        # goldprice.org returns items list with xauPrice
        items = data.get("items", [])
        if items:
            price = float(items[0].get("xauPrice", 0))
            if price > 0:
                logger.debug("Goldprice.org XAUUSD price: %.2f", price)
                return price
    except Exception:
        logger.warning("Failed to fetch price from fallback source", exc_info=True)
    return None


async def fetch_current_price() -> tuple[float | None, str]:
    """Return ``(price, source_name)`` or ``(None, '')`` if all sources
    fail."""
    async with httpx.AsyncClient() as client:
        price = await _fetch_price_binance(client)
        if price is not None:
            return price, "binance"

        price = await _fetch_price_fallback(client)
        if price is not None:
            return price, "goldprice"

    logger.error("All price sources failed — no price available")
    return None, ""


async def _save_tick(price: float, source_name: str) -> None:
    """Record a price tick."""
    async with AsyncSessionLocal() as session:
        tick = SignalPriceTick(
            asset="XAUUSD",
            price=price,
            source=source_name,
        )
        session.add(tick)
        await session.commit()


def _calculate_pips(entry: float, current: float, direction: str) -> float:
    """Return pips (signed) from entry to current for the given
    direction.  Positive = profit, negative = loss."""
    if direction == "BUY":
        return (current - entry) / _PIP_SIZE
    else:  # SELL
        return (entry - current) / _PIP_SIZE


async def _check_signals(price: float) -> None:
    """Evaluate all active signals against the current price."""
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ParsedSignal).where(ParsedSignal.status == "active")
        )
        signals = result.scalars().all()

    if not signals:
        logger.debug("No active signals to check.")
        return

    logger.info("Checking %d active signal(s) against price %.2f", len(signals), price)

    for signal in signals:
        new_status: str | None = None
        outcome_price = price

        # ── Expiry check ────────────────────────────────────────────
        if signal.valid_until and signal.valid_until < now:
            new_status = "expired"
            logger.info("Signal %s expired", signal.id)

        # ── TP / SL checks ──────────────────────────────────────────
        elif signal.direction == "BUY":
            if signal.take_profit_3 and price >= signal.take_profit_3:
                new_status = "tp3_hit"
            elif signal.take_profit_2 and price >= signal.take_profit_2:
                new_status = "tp2_hit"
            elif signal.take_profit_1 and price >= signal.take_profit_1:
                new_status = "tp1_hit"
            elif signal.stop_loss and price <= signal.stop_loss:
                new_status = "sl_hit"

        elif signal.direction == "SELL":
            if signal.take_profit_3 and price <= signal.take_profit_3:
                new_status = "tp3_hit"
            elif signal.take_profit_2 and price <= signal.take_profit_2:
                new_status = "tp2_hit"
            elif signal.take_profit_1 and price <= signal.take_profit_1:
                new_status = "tp1_hit"
            elif signal.stop_loss and price >= signal.stop_loss:
                new_status = "sl_hit"

        if new_status is None:
            continue  # signal still active

        # Calculate outcome pips
        outcome_pips: float | None = None
        if signal.entry_price:
            outcome_pips = _calculate_pips(
                signal.entry_price, outcome_price, signal.direction
            )

        # Persist signal outcome
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(ParsedSignal)
                .where(ParsedSignal.id == signal.id)
                .values(
                    status=new_status,
                    outcome_price=outcome_price,
                    outcome_pips=outcome_pips,
                    outcome_at=now,
                )
            )
            await session.commit()

        logger.info(
            "Signal %s -> %s  (pips=%.1f, price=%.2f)",
            signal.id,
            new_status,
            outcome_pips or 0.0,
            outcome_price,
        )

        # Update source statistics
        await _update_source_stats(signal.source_id, new_status, outcome_pips)


async def _update_source_stats(
    source_id,
    status: str,
    outcome_pips: float | None,
) -> None:
    """Increment the relevant counters on the signal source and
    recalculate its weight."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SignalSource).where(SignalSource.id == source_id)
        )
        source = result.scalars().first()
        if source is None:
            return

        # Classify outcome
        is_win = status in ("tp1_hit", "tp2_hit", "tp3_hit")
        is_loss = status == "sl_hit"
        is_expired = status == "expired"

        if is_win:
            source.correct_signals += 1
        elif is_loss:
            source.wrong_signals += 1
        elif is_expired:
            source.expired_signals += 1

        # Recalculate accuracy rate
        closed = source.correct_signals + source.wrong_signals
        if closed > 0:
            source.accuracy_rate = source.correct_signals / closed

        # Update average profit/loss pips
        if is_win and outcome_pips is not None:
            if source.avg_profit_pips is None:
                source.avg_profit_pips = outcome_pips
            else:
                source.avg_profit_pips = (source.avg_profit_pips + outcome_pips) / 2

        if is_loss and outcome_pips is not None:
            if source.avg_loss_pips is None:
                source.avg_loss_pips = abs(outcome_pips)
            else:
                source.avg_loss_pips = (source.avg_loss_pips + abs(outcome_pips)) / 2

        # Profit factor
        if source.avg_loss_pips and source.avg_loss_pips > 0 and source.avg_profit_pips:
            total_profit = source.avg_profit_pips * source.correct_signals
            total_loss = source.avg_loss_pips * source.wrong_signals
            if total_loss > 0:
                source.profit_factor = total_profit / total_loss

        # Recalculate weight: base_weight * recency_factor * volume_factor
        source.current_weight = calculate_source_weight(
            accuracy_rate=source.accuracy_rate,
            total_signals=source.total_signals,
            last_signal_at=source.last_signal_at,
        )

        await session.commit()
        logger.debug(
            "Updated source %s stats — accuracy=%.2f, weight=%.3f",
            source.name,
            source.accuracy_rate or 0.0,
            source.current_weight,
        )


async def run_price_checker() -> None:
    """Main entry-point.  Fetches price and checks signals on a fixed
    schedule (``PRICE_CHECK_INTERVAL_SECONDS``) until cancelled."""
    logger.info(
        "Starting price checker — interval %d s", PRICE_CHECK_INTERVAL_SECONDS
    )

    while True:
        try:
            price, source_name = await fetch_current_price()
            if price is not None:
                await _save_tick(price, source_name)
                await _check_signals(price)
            else:
                logger.warning("Skipping signal check — no price available")
        except Exception:
            logger.exception("Price checker cycle failed")

        await asyncio.sleep(PRICE_CHECK_INTERVAL_SECONDS)
