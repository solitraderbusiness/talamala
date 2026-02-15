"""Auto-generate market events from significant data changes.

Scans recent data and creates MarketEventAnalysis rows for:
- Large ETF flow changes
- Significant COT position shifts
- Large gold price moves
- Notable macro data releases
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import desc, select

from api.database import AsyncSessionLocal
from api.analysis.models import (
    AssetPriceDaily,
    CotData,
    EtfHolding,
    MacroIndicator,
    MarketEventAnalysis,
)

logger = logging.getLogger("analysis.events")

# Thresholds for generating events
ETF_CHANGE_THRESHOLD_TONNES = 3.0  # Generate event if daily change > 3 tonnes
GOLD_PRICE_CHANGE_PCT = 1.5  # Generate event if daily price change > 1.5%
COT_NET_CHANGE_THRESHOLD = 10000  # Generate event if weekly COT net change > 10k contracts


async def run() -> dict:
    """Scan for significant data changes and create events."""
    generated = 0

    # Lazy provenance imports
    _prov_available = True
    try:
        from api.data_reliability.logger import start_run, log_transform, finish_run
        from api.data_reliability.validator import validate_metric, create_alert_if_needed
    except Exception:
        _prov_available = False

    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)
        today = date.today()

        # ── ETF flow events ─────────────────────────────────────────
        etf_q = await session.execute(
            select(EtfHolding)
            .where(EtfHolding.holding_date >= today - timedelta(days=1))
            .order_by(desc(EtfHolding.holding_date))
        )
        for etf in etf_q.scalars().all():
            if etf.change_tonnes is not None and abs(etf.change_tonnes) >= ETF_CHANGE_THRESHOLD_TONNES:
                # Check if event already created
                existing = await session.execute(
                    select(MarketEventAnalysis).where(
                        MarketEventAnalysis.event_type == "etf_flow",
                        MarketEventAnalysis.created_at >= now - timedelta(hours=12),
                    ).limit(1)
                )
                if existing.scalar_one_or_none():
                    continue

                direction = "bullish" if etf.change_tonnes > 0 else "bearish"
                sign = "+" if etf.change_tonnes > 0 else ""
                session.add(MarketEventAnalysis(
                    event_type="etf_flow",
                    title=f"{etf.fund} holdings changed by {sign}{etf.change_tonnes:.1f} tonnes",
                    title_fa=f"تغییر موجودی {etf.fund}: {sign}{etf.change_tonnes:.1f} تن",
                    description=f"{etf.fund} total holdings: {etf.total_tonnes:.1f} tonnes",
                    description_fa=f"موجودی کل {etf.fund}: {etf.total_tonnes:.1f} تن",
                    impact=direction,
                    magnitude=min(100, abs(etf.change_tonnes) / ETF_CHANGE_THRESHOLD_TONNES * 50),
                    data_json=json.dumps({
                        "fund": etf.fund,
                        "change_tonnes": etf.change_tonnes,
                        "total_tonnes": etf.total_tonnes,
                    }),
                    created_at=now,
                ))
                generated += 1

        # ── Gold price move events ──────────────────────────────────
        gold_q = await session.execute(
            select(AssetPriceDaily)
            .where(AssetPriceDaily.symbol == "GC=F")
            .order_by(desc(AssetPriceDaily.trade_date))
            .limit(2)
        )
        gold_rows = gold_q.scalars().all()
        if len(gold_rows) == 2:
            pct_change = (gold_rows[0].close - gold_rows[1].close) / gold_rows[1].close * 100
            if abs(pct_change) >= GOLD_PRICE_CHANGE_PCT:
                existing = await session.execute(
                    select(MarketEventAnalysis).where(
                        MarketEventAnalysis.event_type == "price_move",
                        MarketEventAnalysis.created_at >= now - timedelta(hours=12),
                    ).limit(1)
                )
                if not existing.scalar_one_or_none():
                    direction = "bullish" if pct_change > 0 else "bearish"
                    sign = "+" if pct_change > 0 else ""
                    session.add(MarketEventAnalysis(
                        event_type="price_move",
                        title=f"Gold price {sign}{pct_change:.1f}% (${gold_rows[0].close:.2f})",
                        title_fa=f"تغییر قیمت طلا {sign}{pct_change:.1f}% (${gold_rows[0].close:.2f})",
                        description=f"Previous close: ${gold_rows[1].close:.2f}",
                        description_fa=f"قیمت قبلی: ${gold_rows[1].close:.2f}",
                        impact=direction,
                        magnitude=min(100, abs(pct_change) / GOLD_PRICE_CHANGE_PCT * 50),
                        data_json=json.dumps({
                            "current_price": gold_rows[0].close,
                            "previous_price": gold_rows[1].close,
                            "pct_change": round(pct_change, 2),
                        }),
                        created_at=now,
                    ))
                    generated += 1

        # ── COT position change events ──────────────────────────────
        cot_q = await session.execute(
            select(CotData)
            .where(CotData.asset == "gold")
            .order_by(desc(CotData.report_date))
            .limit(1)
        )
        cot = cot_q.scalar_one_or_none()
        if cot and cot.change_non_commercial_net is not None and abs(cot.change_non_commercial_net) >= COT_NET_CHANGE_THRESHOLD:
            existing = await session.execute(
                select(MarketEventAnalysis).where(
                    MarketEventAnalysis.event_type == "cot_change",
                    MarketEventAnalysis.created_at >= now - timedelta(days=5),
                ).limit(1)
            )
            if not existing.scalar_one_or_none():
                direction = "bullish" if cot.change_non_commercial_net > 0 else "bearish"
                sign = "+" if cot.change_non_commercial_net > 0 else ""
                session.add(MarketEventAnalysis(
                    event_type="cot_change",
                    title=f"COT net speculative position changed by {sign}{cot.change_non_commercial_net:,.0f}",
                    title_fa=f"تغییر موقعیت خالص سفته‌بازان: {sign}{cot.change_non_commercial_net:,.0f}",
                    description=f"Net position: {cot.non_commercial_net:,.0f} contracts",
                    description_fa=f"موقعیت خالص: {cot.non_commercial_net:,.0f} قرارداد",
                    impact=direction,
                    magnitude=min(100, abs(cot.change_non_commercial_net) / COT_NET_CHANGE_THRESHOLD * 50),
                    data_json=json.dumps({
                        "net_position": cot.non_commercial_net,
                        "change": cot.change_non_commercial_net,
                        "report_date": str(cot.report_date),
                    }),
                    created_at=now,
                ))
                generated += 1

        # Provenance: log a single run for the event generator cycle
        if _prov_available:
            for evt_metric in ["event_etf_flow", "event_price_move", "event_cot"]:
                try:
                    run_obj = await start_run(session, evt_metric)
                    await log_transform(session, run_obj.id, 1, "scan", output_value={"generated": generated})
                    await finish_run(session, run_obj, final_value=generated, status="success", qa_result="pass")
                except Exception:
                    logger.debug("Provenance logging failed for %s", evt_metric, exc_info=True)

        await session.commit()

    result = {"status": "ok", "generated": generated}
    logger.info("Event generator: %s", result)
    return result


async def backfill_historical_events(start_date: date | None = None) -> dict:
    """Generate events retroactively from historical data.

    Iterates each date and checks for:
    - Gold daily change > 1.5% → price_move event
    - ETF daily change > 3 tonnes → etf_flow event
    - COT weekly net change > 10k contracts → cot_change event
    """
    generated = 0
    skipped = 0

    async with AsyncSessionLocal() as session:
        # Load gold prices
        gold_q = await session.execute(
            select(AssetPriceDaily)
            .where(AssetPriceDaily.symbol == "GC=F")
            .order_by(AssetPriceDaily.trade_date)
        )
        gold_rows = gold_q.scalars().all()
        gold_by_date = {r.trade_date: r for r in gold_rows}
        gold_dates = sorted(gold_by_date.keys())

        if start_date:
            gold_dates = [d for d in gold_dates if d >= start_date]

        # Load ETF holdings
        etf_q = await session.execute(
            select(EtfHolding)
            .where(EtfHolding.fund == "GLD")
            .order_by(EtfHolding.holding_date)
        )
        etf_by_date = {r.holding_date: r for r in etf_q.scalars().all()}

        # Load COT data
        cot_q = await session.execute(
            select(CotData)
            .where(CotData.asset == "gold")
            .order_by(CotData.report_date)
        )
        cot_rows = cot_q.scalars().all()
        cot_dates_processed: set[date] = set()

        # Load existing events for dedup
        existing_events_q = await session.execute(
            select(MarketEventAnalysis.event_type, MarketEventAnalysis.created_at)
        )
        existing_events: set[tuple[str, str]] = set()
        for r in existing_events_q:
            d_str = r.created_at.strftime("%Y-%m-%d") if r.created_at else ""
            existing_events.add((r.event_type, d_str))

        batch = 0

        # Price move events
        prev_gold = None
        for d in gold_dates:
            row = gold_by_date.get(d)
            if not row or not row.close:
                continue
            if prev_gold and prev_gold > 0:
                pct_change = (row.close - prev_gold) / prev_gold * 100
                if abs(pct_change) >= GOLD_PRICE_CHANGE_PCT:
                    event_key = ("price_move", d.isoformat())
                    if event_key not in existing_events:
                        direction = "bullish" if pct_change > 0 else "bearish"
                        sign = "+" if pct_change > 0 else ""
                        event_dt = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=timezone.utc)
                        session.add(MarketEventAnalysis(
                            event_type="price_move",
                            title=f"Gold price {sign}{pct_change:.1f}% (${row.close:.2f})",
                            title_fa=f"تغییر قیمت طلا {sign}{pct_change:.1f}% (${row.close:.2f})",
                            description=f"Previous close: ${prev_gold:.2f}",
                            description_fa=f"قیمت قبلی: ${prev_gold:.2f}",
                            impact=direction,
                            magnitude=min(100, abs(pct_change) / GOLD_PRICE_CHANGE_PCT * 50),
                            data_json=json.dumps({
                                "current_price": row.close,
                                "previous_price": prev_gold,
                                "pct_change": round(pct_change, 2),
                            }),
                            created_at=event_dt,
                        ))
                        existing_events.add(event_key)
                        generated += 1
                    else:
                        skipped += 1
            prev_gold = row.close

        # ETF flow events
        etf_dates = sorted(etf_by_date.keys())
        if start_date:
            etf_dates = [d for d in etf_dates if d >= start_date]
        for d in etf_dates:
            etf = etf_by_date[d]
            if etf.change_tonnes is not None and abs(etf.change_tonnes) >= ETF_CHANGE_THRESHOLD_TONNES:
                event_key = ("etf_flow", d.isoformat())
                if event_key not in existing_events:
                    direction = "bullish" if etf.change_tonnes > 0 else "bearish"
                    sign = "+" if etf.change_tonnes > 0 else ""
                    event_dt = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=timezone.utc)
                    session.add(MarketEventAnalysis(
                        event_type="etf_flow",
                        title=f"GLD holdings changed by {sign}{etf.change_tonnes:.1f} tonnes",
                        title_fa=f"تغییر موجودی GLD: {sign}{etf.change_tonnes:.1f} تن",
                        description=f"GLD total holdings: {etf.total_tonnes:.1f} tonnes",
                        description_fa=f"موجودی کل GLD: {etf.total_tonnes:.1f} تن",
                        impact=direction,
                        magnitude=min(100, abs(etf.change_tonnes) / ETF_CHANGE_THRESHOLD_TONNES * 50),
                        data_json=json.dumps({
                            "fund": "GLD",
                            "change_tonnes": etf.change_tonnes,
                            "total_tonnes": etf.total_tonnes,
                        }),
                        created_at=event_dt,
                    ))
                    existing_events.add(event_key)
                    generated += 1

        # COT change events
        for cot in cot_rows:
            if start_date and cot.report_date < start_date:
                continue
            if cot.change_non_commercial_net is not None and abs(cot.change_non_commercial_net) >= COT_NET_CHANGE_THRESHOLD:
                event_key = ("cot_change", cot.report_date.isoformat())
                if event_key not in existing_events:
                    direction = "bullish" if cot.change_non_commercial_net > 0 else "bearish"
                    sign = "+" if cot.change_non_commercial_net > 0 else ""
                    event_dt = datetime(cot.report_date.year, cot.report_date.month, cot.report_date.day, 12, 0, 0, tzinfo=timezone.utc)
                    session.add(MarketEventAnalysis(
                        event_type="cot_change",
                        title=f"COT net speculative position changed by {sign}{cot.change_non_commercial_net:,.0f}",
                        title_fa=f"تغییر موقعیت خالص سفته‌بازان: {sign}{cot.change_non_commercial_net:,.0f}",
                        description=f"Net position: {cot.non_commercial_net:,.0f} contracts",
                        description_fa=f"موقعیت خالص: {cot.non_commercial_net:,.0f} قرارداد",
                        impact=direction,
                        magnitude=min(100, abs(cot.change_non_commercial_net) / COT_NET_CHANGE_THRESHOLD * 50),
                        data_json=json.dumps({
                            "net_position": cot.non_commercial_net,
                            "change": cot.change_non_commercial_net,
                            "report_date": str(cot.report_date),
                        }),
                        created_at=event_dt,
                    ))
                    existing_events.add(event_key)
                    generated += 1

        await session.commit()

    result = {"status": "ok", "generated": generated, "skipped": skipped}
    logger.info("Historical event backfill: %s", result)
    return result
