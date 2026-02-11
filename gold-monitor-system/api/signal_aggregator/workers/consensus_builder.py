"""Consensus builder for the Signal Aggregator.

Generates weighted consensus snapshots across four views — scalp,
intraday, swing, and position — by aggregating active parsed signals
and their source weights.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select

from api.database import AsyncSessionLocal
from api.signal_aggregator.config import (
    ALL_CONSENSUS_VIEWS,
    CONSENSUS_INTERVAL_SECONDS,
    CONSENSUS_TIMEFRAMES,
)
from api.signal_aggregator.models import (
    ConsensusSnapshot,
    ParsedSignal,
    SignalSource,
)

logger = logging.getLogger("signal_aggregator.consensus")

# If one side's weighted score exceeds the other by this factor, a
# directional consensus is declared.
_DIRECTION_THRESHOLD = 1.2


async def generate_consensus(
    asset: str = "XAUUSD",
    consensus_view: str = "intraday",
) -> ConsensusSnapshot | None:
    """Build a single consensus snapshot for *consensus_view* and persist
    it to the database.  Returns the snapshot or ``None`` if there are
    no qualifying signals."""
    now = datetime.now(timezone.utc)
    timeframes = CONSENSUS_TIMEFRAMES.get(consensus_view, [])
    if not timeframes:
        logger.warning("Unknown consensus view: %s", consensus_view)
        return None

    # ── 1. Query active signals in the relevant timeframes ──────────
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ParsedSignal).where(
                ParsedSignal.asset == asset,
                ParsedSignal.status == "active",
                ParsedSignal.timeframe.in_(timeframes),
                ParsedSignal.valid_until > now,
            )
        )
        signals = result.scalars().all()

    if not signals:
        logger.debug("No active signals for %s/%s", asset, consensus_view)
        return None

    # ── 2. Fetch source weights ─────────────────────────────────────
    source_ids = {s.source_id for s in signals}
    source_weights: dict = {}
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SignalSource).where(SignalSource.id.in_(source_ids))
        )
        for src in result.scalars().all():
            source_weights[src.id] = src.current_weight or 0.5

    # ── 3. Calculate weighted scores ────────────────────────────────
    weighted_buy = 0.0
    weighted_sell = 0.0
    buy_count = 0
    sell_count = 0
    entry_prices: list[float] = []
    sl_prices: list[float] = []
    tp_prices: list[float] = []
    all_reasons: list[str] = []
    tf_counter: Counter[str] = Counter()

    for sig in signals:
        weight = source_weights.get(sig.source_id, 0.5)
        # Scale by confidence_raw (1-10 -> 0.1-1.0)
        confidence_factor = (sig.confidence_raw or 5) / 10.0
        effective_weight = weight * confidence_factor

        if sig.direction == "BUY":
            weighted_buy += effective_weight
            buy_count += 1
        elif sig.direction == "SELL":
            weighted_sell += effective_weight
            sell_count += 1

        if sig.entry_price:
            entry_prices.append(sig.entry_price)
        if sig.stop_loss:
            sl_prices.append(sig.stop_loss)
        if sig.take_profit_1:
            tp_prices.append(sig.take_profit_1)
        if sig.take_profit_2:
            tp_prices.append(sig.take_profit_2)
        if sig.take_profit_3:
            tp_prices.append(sig.take_profit_3)

        if sig.key_reasons:
            reasons = sig.key_reasons if isinstance(sig.key_reasons, list) else []
            all_reasons.extend(reasons)

        tf_counter[sig.timeframe] += 1

    # ── 4. Determine direction and strength ─────────────────────────
    total_weight = weighted_buy + weighted_sell
    if total_weight == 0:
        return None

    if weighted_buy > weighted_sell * _DIRECTION_THRESHOLD:
        direction = "BUY"
    elif weighted_sell > weighted_buy * _DIRECTION_THRESHOLD:
        direction = "SELL"
    else:
        direction = "NEUTRAL"

    # Strength: 0-100 based on how dominant the winning side is
    if direction == "NEUTRAL":
        strength = 0
    else:
        dominant = max(weighted_buy, weighted_sell)
        minority = min(weighted_buy, weighted_sell)
        # Ratio-based strength: 1.2x -> ~17, 2.0x -> ~50, 5.0x -> ~80+
        if minority > 0:
            ratio = dominant / minority
            strength = min(100, int((ratio - 1) * 50))
        else:
            strength = 100

    # ── 5. Price consensus ──────────────────────────────────────────
    avg_entry = statistics.mean(entry_prices) if entry_prices else None
    median_entry = statistics.median(entry_prices) if entry_prices else None
    avg_sl = statistics.mean(sl_prices) if sl_prices else None
    avg_tp = statistics.mean(tp_prices) if tp_prices else None

    # ── 6. Dominant reasons (top 3) ─────────────────────────────────
    reason_counter = Counter(all_reasons)
    dominant_reasons = [r for r, _ in reason_counter.most_common(3)]

    # ── 7. Dominant timeframe ───────────────────────────────────────
    dominant_tf = tf_counter.most_common(1)[0][0] if tf_counter else None

    # ── 8. Timeframe alignment across all 4 views ───────────────────
    timeframe_alignment = await _compute_alignment(asset)

    # ── 9. Persist snapshot ─────────────────────────────────────────
    snapshot = ConsensusSnapshot(
        asset=asset,
        consensus_view=consensus_view,
        timeframes_included=timeframes,
        signals_count=len(signals),
        buy_count=buy_count,
        sell_count=sell_count,
        weighted_buy_score=round(weighted_buy, 4),
        weighted_sell_score=round(weighted_sell, 4),
        consensus_direction=direction,
        consensus_strength=strength,
        avg_entry_price=round(avg_entry, 2) if avg_entry else None,
        median_entry_price=round(median_entry, 2) if median_entry else None,
        avg_stop_loss=round(avg_sl, 2) if avg_sl else None,
        avg_take_profit=round(avg_tp, 2) if avg_tp else None,
        dominant_timeframe=dominant_tf,
        dominant_reasons=dominant_reasons if dominant_reasons else None,
        timeframe_alignment=timeframe_alignment,
    )

    async with AsyncSessionLocal() as session:
        session.add(snapshot)
        await session.commit()
        await session.refresh(snapshot)

    logger.info(
        "Consensus [%s/%s]: %s (strength=%d, signals=%d, buy=%.2f, sell=%.2f)",
        asset,
        consensus_view,
        direction,
        strength,
        len(signals),
        weighted_buy,
        weighted_sell,
    )
    return snapshot


async def _compute_alignment(asset: str) -> dict[str, str]:
    """Return a dict mapping each consensus view to its latest direction
    so the snapshot can report cross-timeframe alignment."""
    now = datetime.now(timezone.utc)
    alignment: dict[str, str] = {}

    async with AsyncSessionLocal() as session:
        for view, timeframes in CONSENSUS_TIMEFRAMES.items():
            result = await session.execute(
                select(ParsedSignal).where(
                    ParsedSignal.asset == asset,
                    ParsedSignal.status == "active",
                    ParsedSignal.timeframe.in_(timeframes),
                    ParsedSignal.valid_until > now,
                )
            )
            sigs = result.scalars().all()

            # Quick weighted tally
            source_result = await session.execute(
                select(SignalSource).where(
                    SignalSource.id.in_({s.source_id for s in sigs})
                )
            ) if sigs else None

            weights: dict = {}
            if source_result:
                for src in source_result.scalars().all():
                    weights[src.id] = src.current_weight or 0.5

            buy_w = 0.0
            sell_w = 0.0
            for s in sigs:
                w = weights.get(s.source_id, 0.5) * ((s.confidence_raw or 5) / 10.0)
                if s.direction == "BUY":
                    buy_w += w
                else:
                    sell_w += w

            if buy_w > sell_w * _DIRECTION_THRESHOLD:
                alignment[view] = "BUY"
            elif sell_w > buy_w * _DIRECTION_THRESHOLD:
                alignment[view] = "SELL"
            else:
                alignment[view] = "NEUTRAL"

    return alignment


async def generate_all_consensus(asset: str = "XAUUSD") -> list[ConsensusSnapshot]:
    """Generate consensus snapshots for all four views and return them."""
    snapshots: list[ConsensusSnapshot] = []
    for view in ALL_CONSENSUS_VIEWS:
        snapshot = await generate_consensus(asset=asset, consensus_view=view)
        if snapshot:
            snapshots.append(snapshot)
    return snapshots


async def run_consensus_builder() -> None:
    """Main loop — generates all consensus views on a fixed schedule
    (``CONSENSUS_INTERVAL_SECONDS``) until cancelled."""
    logger.info(
        "Starting consensus builder — interval %d s", CONSENSUS_INTERVAL_SECONDS
    )

    while True:
        try:
            snapshots = await generate_all_consensus()
            logger.info("Generated %d consensus snapshot(s).", len(snapshots))
        except Exception:
            logger.exception("Consensus builder cycle failed")

        await asyncio.sleep(CONSENSUS_INTERVAL_SECONDS)
