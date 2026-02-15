"""Deterministic test: verify live snapshots + outcome seeding for new alerts.

Run inside the API container:
    docker compose exec api python -m api.tests.test_live_snapshot

This script:
1. Creates 5 test alerts (committed to DB, just like the fixed worker)
2. Calls capture_market_snapshot() for each (exactly as the worker fires post-commit)
3. Waits for all captures to finish
4. Queries DB to verify:
   a. All 5 have snapshots
   b. All 5 snapshots are LIVE (no "reconciled" in missing_fields)
   c. All 5 have seeded outcomes (created by snapshot_builder)
5. Cleans up test data
6. Prints PASS/FAIL verdict
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from api.database import AsyncSessionLocal
from api.data_collection.snapshot_builder import capture_market_snapshot


TEST_PREFIX = "TEST_LIVE_SNAP_"


async def main() -> int:
    test_alert_ids: list[str] = []

    print("=" * 60)
    print("DETERMINISTIC LIVE SNAPSHOT TEST")
    print("=" * 60)

    # ── Step 1: Insert 5 test alerts ─────────────────────────
    print("\n[1/5] Creating 5 test alerts...")
    async with AsyncSessionLocal() as db:
        for i in range(5):
            alert_id = str(uuid.uuid4())
            test_alert_ids.append(alert_id)
            await db.execute(
                text(
                    "INSERT INTO alerts "
                    "  (id, title, timestamp_utc, source_name, source_url, "
                    "   matched_rule_ids, summary_fa, why_important_fa, "
                    "   expected_impact, severity, time_horizon, confidence, "
                    "   follow_up_questions, dedupe_key, "
                    "   match_evidence, "
                    "   price_xauusd_at_alert, price_usdirr_at_alert, "
                    "   news_type, event_category, "
                    "   created_at) "
                    "VALUES "
                    "  (:id, :title, :ts, :source_name, :source_url, "
                    "   CAST(:rule_ids AS jsonb), '', '', "
                    "   CAST(:impact AS jsonb), :severity, 'short', 0.5, "
                    "   CAST(:questions AS jsonb), :dedupe_key, "
                    "   CAST(:evidence AS jsonb), "
                    "   :p_xauusd, :p_usdirr, "
                    "   'test', 'test', "
                    "   :now)"
                ),
                {
                    "id": alert_id,
                    "title": f"{TEST_PREFIX}Alert #{i+1}",
                    "ts": datetime.now(timezone.utc),
                    "source_name": "test_live_snapshot",
                    "source_url": f"https://test.local/alert-{i+1}",
                    "rule_ids": json.dumps(["TEST_RULE"]),
                    "impact": json.dumps({}),
                    "questions": json.dumps([]),
                    "evidence": json.dumps({"direction": "bullish", "score": 0.8}),
                    "severity": "medium",
                    "dedupe_key": f"test_live_snap_{alert_id}",
                    "p_xauusd": 2900.0 + i,
                    "p_usdirr": 850000.0,
                    "now": datetime.now(timezone.utc),
                },
            )
            print(f"  Created alert {i+1}: {alert_id[:8]}...")

        # COMMIT — exactly as worker does at line 436
        await db.commit()
        print("  All 5 alerts COMMITTED to DB.")

    # ── Step 2: Fire snapshot captures (post-commit, like the fix) ──
    print("\n[2/5] Firing capture_market_snapshot() for each alert...")
    tasks = []
    for i, alert_id in enumerate(test_alert_ids):
        alert_dict = {
            "id": alert_id,
            "title": f"{TEST_PREFIX}Alert #{i+1}",
            "severity": "medium",
            "matched_rule_ids": ["TEST_RULE"],
            "match_evidence": {"direction": "bullish", "score": 0.8},
        }
        price_snap = {
            "xauusd": 2900.0 + i,
            "usdirr": 850000.0,
            "coin": 95000000.0,
            "gold_18k": 45000000.0,
        }
        tasks.append(capture_market_snapshot(alert_id, alert_dict, price_snap))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, r in enumerate(results):
        status = "OK" if r is None else f"ERROR: {r}"
        print(f"  Snapshot {i+1}: {status}")

    # ── Step 3: Wait briefly for any async cleanup ───────────
    print("\n[3/5] Waiting 2s for async cleanup...")
    await asyncio.sleep(2)

    # ── Step 4: Verify results ───────────────────────────────
    print("\n[4/5] Verifying results in DB...")
    ids_tuple = tuple(test_alert_ids)
    pass_count = 0
    fail_count = 0

    async with AsyncSessionLocal() as db:
        # Check snapshots
        snap_q = await db.execute(
            text(
                "SELECT alert_id::text, snapshot_complete, missing_fields, "
                "       xauusd, gold_rsi_14, sentiment_composite "
                "FROM alert_market_snapshots "
                "WHERE alert_id::text = ANY(:ids)"
            ),
            {"ids": list(test_alert_ids)},
        )
        snapshots = {row[0]: row for row in snap_q.all()}

        # Check outcomes
        outcome_q = await db.execute(
            text(
                "SELECT alert_id::text, status, alert_direction "
                "FROM alert_outcomes "
                "WHERE alert_id::text = ANY(:ids)"
            ),
            {"ids": list(test_alert_ids)},
        )
        outcomes = {row[0]: row for row in outcome_q.all()}

        print(f"\n  {'Alert':<10} {'Snapshot?':<12} {'Source':<14} {'Outcome?':<12} {'Status'}")
        print(f"  {'─'*10} {'─'*12} {'─'*14} {'─'*12} {'─'*12}")

        for i, aid in enumerate(test_alert_ids):
            has_snap = aid in snapshots
            snap_source = "—"
            if has_snap:
                missing = snapshots[aid][2]  # missing_fields
                is_reconciled = (
                    isinstance(missing, list) and "reconciled" in missing
                )
                snap_source = "RECONCILED" if is_reconciled else "LIVE"

            has_outcome = aid in outcomes
            outcome_status = outcomes[aid][1] if has_outcome else "—"

            ok = has_snap and snap_source == "LIVE" and has_outcome
            verdict = "PASS" if ok else "FAIL"
            if ok:
                pass_count += 1
            else:
                fail_count += 1

            print(
                f"  #{i+1:<8} {'YES' if has_snap else 'NO':<12} "
                f"{snap_source:<14} {'YES' if has_outcome else 'NO':<12} "
                f"{outcome_status}"
            )

    # ── Step 5: Cleanup test data ────────────────────────────
    print(f"\n[5/5] Cleaning up {len(test_alert_ids)} test alerts...")
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("DELETE FROM alert_outcomes WHERE alert_id::text = ANY(:ids)"),
            {"ids": list(test_alert_ids)},
        )
        await db.execute(
            text("DELETE FROM alert_market_snapshots WHERE alert_id::text = ANY(:ids)"),
            {"ids": list(test_alert_ids)},
        )
        await db.execute(
            text("DELETE FROM alerts WHERE id::text = ANY(:ids)"),
            {"ids": list(test_alert_ids)},
        )
        await db.commit()
    print("  Cleanup complete.")

    # ── Final verdict ────────────────────────────────────────
    print("\n" + "=" * 60)
    if fail_count == 0:
        print(f"VERDICT: PASS — {pass_count}/5 alerts have LIVE snapshots + outcomes")
        print("=" * 60)
        return 0
    else:
        print(f"VERDICT: FAIL — {pass_count}/5 passed, {fail_count}/5 failed")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
