"""Enhanced outcome tracker — checks price outcomes at 6 intervals.

Processes pending alert_outcomes in batches of 50, advancing through
status stages: pending_30min → pending_1h → ... → pending_7d → complete.

Runs every 5 minutes from the API process.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from api.database import AsyncSessionLocal
from api.data_collection.models import AlertOutcome
from api.price_snapshot import get_price_snapshot

logger = logging.getLogger("gold_monitor.outcome_tracker")

WINDOWS = [
    ("30min", 0.5, "pending_30min", "pending_1h"),
    ("1h", 1, "pending_1h", "pending_4h"),
    ("4h", 4, "pending_4h", "pending_24h"),
    ("24h", 24, "pending_24h", "pending_48h"),
    ("48h", 48, "pending_48h", "pending_7d"),
    ("7d", 168, "pending_7d", "complete"),
]

BATCH_SIZE = 50


def _check_direction(alert_direction: str | None, change_pct: float) -> bool | None:
    """Check if price moved in the predicted direction."""
    if not alert_direction or alert_direction == "neutral":
        return None
    if alert_direction == "bullish":
        return change_pct > 0
    if alert_direction == "bearish":
        return change_pct < 0
    return None


async def run_outcome_tracker() -> dict:
    """Process pending outcomes. Idempotent, safe to run repeatedly."""
    stats = {"processed": 0, "errors": 0}

    # Get current gold price
    try:
        prices = await get_price_snapshot()
        current_price = prices.get("xauusd")
    except Exception:
        logger.warning("Could not fetch current price for outcome tracking")
        return {"processed": 0, "errors": 0, "reason": "no_price"}

    if not current_price:
        return {"processed": 0, "errors": 0, "reason": "no_price"}

    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        for window_name, hours, current_status, next_status in WINDOWS:
            try:
                # Find outcomes that are ready for this window check
                cutoff = now - timedelta(hours=hours)
                q = (
                    select(AlertOutcome)
                    .where(
                        AlertOutcome.status == current_status,
                        AlertOutcome.alert_created_at <= cutoff,
                    )
                    .limit(BATCH_SIZE)
                )
                result = await session.execute(q)
                outcomes = result.scalars().all()

                for outcome in outcomes:
                    try:
                        price_at_alert = outcome.price_at_alert
                        if not price_at_alert or price_at_alert <= 0:
                            # Can't compute change without base price
                            outcome.status = next_status
                            outcome.updated_at = now
                            continue

                        change_pct = (current_price - price_at_alert) / price_at_alert * 100
                        direction_correct = _check_direction(
                            outcome.alert_direction, change_pct
                        )

                        # Set the window-specific columns
                        setattr(outcome, f"price_{window_name}", current_price)
                        setattr(outcome, f"change_pct_{window_name}", round(change_pct, 4))
                        setattr(outcome, f"direction_correct_{window_name}", direction_correct)
                        setattr(outcome, f"checked_at_{window_name}", now)

                        # On 7d completion, compute magnitude and reversion
                        if next_status == "complete":
                            _compute_final_metrics(outcome)

                        outcome.status = next_status
                        outcome.updated_at = now
                        stats["processed"] += 1

                    except Exception:
                        logger.warning(
                            "Error processing outcome %s", outcome.id, exc_info=True
                        )
                        errors = outcome.errors or []
                        errors.append({
                            "window": window_name,
                            "error": "processing_failed",
                            "at": now.isoformat(),
                        })
                        outcome.errors = errors
                        outcome.updated_at = now
                        stats["errors"] += 1

                await session.commit()

            except Exception:
                logger.exception("Error in outcome tracker window %s", window_name)
                await session.rollback()
                stats["errors"] += 1

    if stats["processed"]:
        logger.info("Outcome tracker: processed=%d errors=%d", stats["processed"], stats["errors"])
    return stats


def _compute_final_metrics(outcome: AlertOutcome) -> None:
    """Compute magnitude and reversion metrics on 7d completion."""
    changes = []
    for wn in ["30min", "1h", "4h", "24h", "48h", "7d"]:
        pct = getattr(outcome, f"change_pct_{wn}", None)
        if pct is not None:
            changes.append((wn, pct))

    if not changes:
        return

    direction = outcome.alert_direction

    # Max favorable / adverse moves
    if direction == "bullish":
        favorable = [c for _, c in changes if c > 0]
        adverse = [c for _, c in changes if c < 0]
    elif direction == "bearish":
        favorable = [c for _, c in changes if c < 0]
        adverse = [c for _, c in changes if c > 0]
    else:
        favorable = [abs(c) for _, c in changes]
        adverse = []

    if favorable:
        outcome.max_favorable_move_pct = round(max(abs(f) for f in favorable), 4)
    if adverse:
        outcome.max_adverse_move_pct = round(max(abs(a) for a in adverse), 4)

    # Time to max favorable
    if favorable and direction in ("bullish", "bearish"):
        hours_map = {"30min": 0.5, "1h": 1, "4h": 4, "24h": 24, "48h": 48, "7d": 168}
        best_pct = max(abs(f) for f in favorable)
        for wn, pct in changes:
            if abs(pct) == best_pct:
                outcome.time_to_max_favorable_hours = hours_map.get(wn)
                break

    # Reversion detection
    correct_1h = outcome.direction_correct_1h
    correct_4h = outcome.direction_correct_4h
    correct_24h = outcome.direction_correct_24h

    outcome.reverted_within_4h = (
        correct_1h is True and correct_4h is False
    ) if correct_1h is not None and correct_4h is not None else None

    outcome.reverted_within_24h = (
        correct_4h is True and correct_24h is False
    ) if correct_4h is not None and correct_24h is not None else None


async def outcome_tracker_loop() -> None:
    """Background loop — runs every 5 minutes."""
    while True:
        try:
            await run_outcome_tracker()
        except Exception:
            logger.exception("Outcome tracker loop error")
        await asyncio.sleep(300)
