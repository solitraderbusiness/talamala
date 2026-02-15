"""Backfill daily sentiment scores from historical data.

For each date in the specified range, computes the 6-component sentiment
score using point-in-time data (no look-ahead bias), and stores it in
the ``sentiment_timeline`` table.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from api.database import AsyncSessionLocal
from api.analysis.models import AssetPriceDaily, CotData, EtfHolding, MacroIndicator
from api.data_collection.models import SentimentTimeline
from api.data_collection.sentiment_calculator import COMPONENT_CONFIG, _normalize_score

logger = logging.getLogger("analysis.sentiment_backfill")


async def backfill_daily_sentiment(start_date: str = "2014-01-01") -> dict:
    """Compute daily sentiment for each date using point-in-time data.

    Stores in ``sentiment_timeline`` with ``recorded_at`` = midnight of each date.
    Skips dates where fewer than 3 components have data.
    """
    start = date.fromisoformat(start_date)
    end = date.today()
    inserted = 0
    skipped = 0

    async with AsyncSessionLocal() as session:
        # Load all data into memory for fast lookup
        # Gold prices
        gold_q = await session.execute(
            select(AssetPriceDaily.trade_date, AssetPriceDaily.close)
            .where(AssetPriceDaily.symbol == "GC=F", AssetPriceDaily.close > 0)
            .order_by(AssetPriceDaily.trade_date)
        )
        gold_by_date: dict[date, float] = {r.trade_date: r.close for r in gold_q}

        # DXY prices
        dxy_q = await session.execute(
            select(AssetPriceDaily.trade_date, AssetPriceDaily.close)
            .where(AssetPriceDaily.symbol == "DX-Y.NYB", AssetPriceDaily.close > 0)
            .order_by(AssetPriceDaily.trade_date)
        )
        dxy_by_date: dict[date, float] = {r.trade_date: r.close for r in dxy_q}

        # VIX prices
        vix_q = await session.execute(
            select(AssetPriceDaily.trade_date, AssetPriceDaily.close)
            .where(AssetPriceDaily.symbol == "^VIX", AssetPriceDaily.close > 0)
            .order_by(AssetPriceDaily.trade_date)
        )
        vix_by_date: dict[date, float] = {r.trade_date: r.close for r in vix_q}

        # GLD ETF holdings
        etf_q = await session.execute(
            select(EtfHolding.holding_date, EtfHolding.change_tonnes)
            .where(EtfHolding.fund == "GLD")
            .order_by(EtfHolding.holding_date)
        )
        etf_by_date: dict[date, float | None] = {r.holding_date: r.change_tonnes for r in etf_q}

        # COT data
        cot_q = await session.execute(
            select(CotData.report_date, CotData.non_commercial_net)
            .where(CotData.asset == "gold")
            .order_by(CotData.report_date)
        )
        cot_rows = list(cot_q)

        # FRED DFII10
        dfii_q = await session.execute(
            select(MacroIndicator.observation_date, MacroIndicator.value)
            .where(MacroIndicator.series_id == "DFII10")
            .order_by(MacroIndicator.observation_date)
        )
        dfii_by_date: dict[date, float] = {r.observation_date: r.value for r in dfii_q}

        # Existing sentiment entries for dedup
        existing_q = await session.execute(
            select(SentimentTimeline.recorded_at)
        )
        existing_dates: set[str] = set()
        for r in existing_q:
            if r.recorded_at:
                existing_dates.add(r.recorded_at.strftime("%Y-%m-%d"))

        # Helper: get sorted dates from dict within range
        all_gold_dates = sorted(gold_by_date.keys())

        # Build COT lookup (latest report on or before date)
        cot_sorted = sorted(cot_rows, key=lambda x: x.report_date)

        def _latest_cot_before(d: date) -> float | None:
            result = None
            for row in cot_sorted:
                if row.report_date > d:
                    break
                if row.non_commercial_net is not None:
                    result = row.non_commercial_net
            return result

        def _latest_dfii_before(d: date) -> float | None:
            # Walk backwards from date
            for offset in range(10):
                check = d - timedelta(days=offset)
                if check in dfii_by_date:
                    return dfii_by_date[check]
            return None

        batch = 0
        current = start
        while current <= end:
            date_str = current.isoformat()

            if date_str in existing_dates:
                skipped += 1
                current += timedelta(days=1)
                continue

            components = []
            total_score = 0.0
            total_weight = 0

            # 1. ETF flows: 5-day avg GLD change
            cfg = COMPONENT_CONFIG["etf_flows"]
            etf_changes = []
            for offset in range(5):
                check = current - timedelta(days=offset)
                if check in etf_by_date and etf_by_date[check] is not None:
                    etf_changes.append(etf_by_date[check])
            if etf_changes:
                avg_change = sum(etf_changes) / len(etf_changes)
                score = _normalize_score(avg_change, cfg)
                total_score += score * cfg["weight"]
                total_weight += cfg["weight"]
                components.append({"name": "etf_flows", "score": round(score), "raw": round(avg_change, 4)})

            # 2. COT positioning
            cfg = COMPONENT_CONFIG["cot_positioning"]
            cot_net = _latest_cot_before(current)
            if cot_net is not None:
                cot_score = max(0, min(100, (cot_net / cfg["scale_divisor"]) * cfg["scale_multiplier"] + cfg["center"]))
                total_score += cot_score * cfg["weight"]
                total_weight += cfg["weight"]
                components.append({"name": "cot_positioning", "score": round(cot_score), "raw": cot_net})

            # 3. Real rates
            cfg = COMPONENT_CONFIG["real_rates"]
            dfii_val = _latest_dfii_before(current)
            if dfii_val is not None:
                rr_score = _normalize_score(dfii_val, cfg)
                total_score += rr_score * cfg["weight"]
                total_weight += cfg["weight"]
                components.append({"name": "real_rates", "score": round(rr_score), "raw": dfii_val})

            # 4. Dollar strength: 5-day DXY change
            cfg = COMPONENT_CONFIG["dollar_strength"]
            dxy_now = None
            dxy_5ago = None
            for offset in range(3):
                check = current - timedelta(days=offset)
                if check in dxy_by_date:
                    dxy_now = dxy_by_date[check]
                    break
            for offset in range(5, 10):
                check = current - timedelta(days=offset)
                if check in dxy_by_date:
                    dxy_5ago = dxy_by_date[check]
                    break
            if dxy_now is not None and dxy_5ago is not None:
                dxy_change = dxy_now - dxy_5ago
                dxy_score = _normalize_score(dxy_change, cfg)
                total_score += dxy_score * cfg["weight"]
                total_weight += cfg["weight"]
                components.append({"name": "dollar_strength", "score": round(dxy_score), "raw": round(dxy_change, 4)})

            # 5. VIX
            cfg = COMPONENT_CONFIG["risk_sentiment"]
            vix_val = None
            for offset in range(3):
                check = current - timedelta(days=offset)
                if check in vix_by_date:
                    vix_val = vix_by_date[check]
                    break
            if vix_val is not None:
                vix_score = _normalize_score(vix_val, cfg)
                total_score += vix_score * cfg["weight"]
                total_weight += cfg["weight"]
                components.append({"name": "risk_sentiment", "score": round(vix_score), "raw": vix_val})

            # 6. Gold momentum: 10-day % change
            cfg = COMPONENT_CONFIG["price_momentum"]
            gold_now = None
            gold_10ago = None
            for offset in range(3):
                check = current - timedelta(days=offset)
                if check in gold_by_date:
                    gold_now = gold_by_date[check]
                    break
            for offset in range(10, 15):
                check = current - timedelta(days=offset)
                if check in gold_by_date:
                    gold_10ago = gold_by_date[check]
                    break
            if gold_now is not None and gold_10ago is not None and gold_10ago > 0:
                pct = (gold_now - gold_10ago) / gold_10ago * 100
                mom_score = _normalize_score(pct, cfg)
                total_score += mom_score * cfg["weight"]
                total_weight += cfg["weight"]
                components.append({"name": "price_momentum", "score": round(mom_score), "raw": round(pct, 4)})

            # Need at least 3 components
            if len(components) >= 3 and total_weight > 0:
                composite = round(total_score / total_weight)
                if composite >= 55:
                    direction = "bullish"
                elif composite >= 45:
                    direction = "neutral"
                else:
                    direction = "bearish"
                recorded_at = datetime(current.year, current.month, current.day, 0, 0, 0, tzinfo=timezone.utc)
                session.add(SentimentTimeline(
                    composite_score=composite,
                    direction=direction,
                    gold_price=gold_by_date.get(current),
                    recorded_at=recorded_at,
                ))
                inserted += 1
            else:
                skipped += 1

            batch += 1
            if batch % 200 == 0:
                await session.commit()
                logger.info("Sentiment backfill: processed %d days, %d inserted", batch, inserted)

            current += timedelta(days=1)

        await session.commit()

    result = {
        "status": "ok",
        "days_processed": batch,
        "inserted": inserted,
        "skipped": skipped,
    }
    logger.info("Sentiment backfill: %s", result)
    return result
