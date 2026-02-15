"""Reconciliation job — fills missing snapshots and outcome rows.

Runs every RECONCILE_INTERVAL_SECONDS (default 5 min) from the API process.
Scans alerts from the last RECONCILE_LOOKBACK_DAYS that are missing either:
  - a row in ``alert_market_snapshots``
  - a row in ``alert_outcomes``

For each missing row it creates a minimal seed so the outcome tracker
can pick it up.  Full market context (technicals, sentiment) is only
available when the snapshot is captured live, but at minimum we ensure
every alert has an outcome row tracking price changes.

Idempotent: UNIQUE constraints on ``alert_id`` in both tables prevent
duplicates.  Existing rows are skipped via LEFT JOIN / IS NULL.

Configuration via env vars (see ``api/config.py``):
  - RECONCILE_LOOKBACK_DAYS  (default 7)
  - RECONCILE_BATCH_SIZE     (default 50)
  - RECONCILE_INTERVAL_SECONDS (default 300)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from api.config import settings
from api.database import AsyncSessionLocal

logger = logging.getLogger("gold_monitor.reconciliation")


async def run_reconciliation() -> dict:
    """Find and fill missing snapshots/outcomes for recent alerts.

    Returns stats dict with counts of what was created.
    """
    trace_id = uuid.uuid4().hex[:8]
    stats = {
        "trace_id": trace_id,
        "missing_snapshots_found": 0,
        "snapshots_created": 0,
        "missing_outcomes_found": 0,
        "outcomes_created": 0,
        "errors": 0,
    }

    lookback_days = settings.RECONCILE_LOOKBACK_DAYS
    batch_size = settings.RECONCILE_BATCH_SIZE
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    async with AsyncSessionLocal() as session:
        # ── 1. Find alerts missing outcome rows ──────────────────────
        try:
            missing_outcomes_q = await session.execute(
                text(
                    "SELECT a.id, a.severity, a.timestamp_utc, "
                    "       a.match_evidence->>'direction' AS direction, "
                    "       a.price_xauusd_at_alert "
                    "FROM alerts a "
                    "LEFT JOIN alert_outcomes ao ON ao.alert_id = a.id "
                    "WHERE a.timestamp_utc >= :since "
                    "  AND ao.id IS NULL "
                    "ORDER BY a.timestamp_utc DESC "
                    "LIMIT :batch"
                ),
                {"since": since, "batch": batch_size},
            )
            missing_outcomes = missing_outcomes_q.all()
            stats["missing_outcomes_found"] = len(missing_outcomes)

            for row in missing_outcomes:
                try:
                    alert_id = row[0]
                    severity = row[1]
                    created_at = row[2] or datetime.now(timezone.utc)
                    direction = row[3]
                    price_at_alert = row[4]

                    await session.execute(
                        text(
                            "INSERT INTO alert_outcomes "
                            "  (id, alert_id, alert_direction, alert_severity, "
                            "   price_at_alert, alert_created_at, status, "
                            "   created_at, updated_at) "
                            "VALUES "
                            "  (:id, :alert_id, :direction, :severity, "
                            "   :price, :created_at, 'pending_30min', "
                            "   :now, :now) "
                            "ON CONFLICT (alert_id) DO NOTHING"
                        ),
                        {
                            "id": str(uuid.uuid4()),
                            "alert_id": alert_id,
                            "direction": direction,
                            "severity": severity,
                            "price": price_at_alert,
                            "created_at": created_at,
                            "now": datetime.now(timezone.utc),
                        },
                    )
                    stats["outcomes_created"] += 1
                except Exception:
                    logger.warning(
                        "[%s] Failed to seed outcome for alert %s",
                        trace_id,
                        str(row[0])[:8],
                        exc_info=True,
                    )
                    stats["errors"] += 1

            await session.commit()
        except Exception:
            logger.exception("[%s] Outcome scan failed", trace_id)
            await session.rollback()
            stats["errors"] += 1

        # ── 2. Find alerts missing snapshot rows ─────────────────────
        try:
            missing_snapshots_q = await session.execute(
                text(
                    "SELECT a.id, a.timestamp_utc, "
                    "       a.price_xauusd_at_alert, a.price_usdirr_at_alert, "
                    "       a.price_coin_at_alert, a.price_18k_at_alert, "
                    "       a.severity "
                    "FROM alerts a "
                    "LEFT JOIN alert_market_snapshots ams ON ams.alert_id = a.id "
                    "WHERE a.timestamp_utc >= :since "
                    "  AND ams.id IS NULL "
                    "ORDER BY a.timestamp_utc DESC "
                    "LIMIT :batch"
                ),
                {"since": since, "batch": batch_size},
            )
            missing_snapshots = missing_snapshots_q.all()
            stats["missing_snapshots_found"] = len(missing_snapshots)

            for row in missing_snapshots:
                try:
                    alert_id = row[0]
                    xauusd = row[2]
                    usdirr = row[3]
                    coin = row[4]
                    gold_18k = row[5]

                    # Create a minimal snapshot with prices from the alert
                    # (technicals/sentiment are unavailable retroactively)
                    await session.execute(
                        text(
                            "INSERT INTO alert_market_snapshots "
                            "  (id, alert_id, xauusd, usdirr, coin, gold_18k, "
                            "   snapshot_complete, missing_fields, "
                            "   fetch_duration_ms, created_at) "
                            "VALUES "
                            "  (:id, :alert_id, :xauusd, :usdirr, :coin, :gold_18k, "
                            "   false, CAST(:missing AS jsonb), "
                            "   0, :now) "
                            "ON CONFLICT (alert_id) DO NOTHING"
                        ),
                        {
                            "id": str(uuid.uuid4()),
                            "alert_id": alert_id,
                            "xauusd": xauusd,
                            "usdirr": usdirr,
                            "coin": coin,
                            "gold_18k": gold_18k,
                            "missing": '["technicals","sentiment","alert_context","reconciled"]',
                            "now": datetime.now(timezone.utc),
                        },
                    )
                    stats["snapshots_created"] += 1
                except Exception:
                    logger.warning(
                        "[%s] Failed to create snapshot for alert %s",
                        trace_id,
                        str(row[0])[:8],
                        exc_info=True,
                    )
                    stats["errors"] += 1

            await session.commit()
        except Exception:
            logger.exception("[%s] Snapshot scan failed", trace_id)
            await session.rollback()
            stats["errors"] += 1

    # Always log — every run, not just when items are created
    logger.info(
        "[%s] Reconciliation complete: "
        "outcomes_found=%d created=%d | "
        "snapshots_found=%d created=%d | "
        "errors=%d | lookback=%dd batch=%d",
        trace_id,
        stats["missing_outcomes_found"],
        stats["outcomes_created"],
        stats["missing_snapshots_found"],
        stats["snapshots_created"],
        stats["errors"],
        lookback_days,
        batch_size,
    )

    return stats


async def reconciliation_loop() -> None:
    """Background loop — runs every RECONCILE_INTERVAL_SECONDS."""
    interval = settings.RECONCILE_INTERVAL_SECONDS
    # Initial delay: let the system stabilize before first reconciliation
    await asyncio.sleep(60)
    logger.info(
        "Reconciliation loop started: interval=%ds lookback=%dd batch=%d",
        interval,
        settings.RECONCILE_LOOKBACK_DAYS,
        settings.RECONCILE_BATCH_SIZE,
    )
    while True:
        try:
            await run_reconciliation()
        except Exception:
            logger.exception("Reconciliation loop error")
        await asyncio.sleep(interval)
