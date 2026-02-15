"""Service layer for money flow derived statistics.

Single async entry point used by both the API router and the chat tool executor.
Queries the DB for raw ETF/COT data and feeds it through the pure-function
calculators in ``derived_money_flow.py``.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.analysis.models import CotData, EtfHolding
from api.analysis.derived_money_flow import (
    classify_combined_signal,
    compute_cot_wow_pct_of_oi,
    compute_percentile_2yr,
    compute_zscore_90d,
)

logger = logging.getLogger("gold_monitor.analysis.money_flow_service")


async def get_money_flow_derived(session: AsyncSession) -> dict:
    """Compute all derived money flow statistics from DB data.

    Returns:
        {
            "etf": { fund, zscore_90d, percentile_2yr, latest_change_tonnes, latest_date, source_url },
            "cot": { wow_change_pct_of_oi, percentile_1yr, percentile_3yr, latest_net, latest_date, source_url },
            "combined_signal": { signal, label_fa, confidence, reasons },
        }
    """
    since_2yr = date.today() - timedelta(days=730)
    since_3yr = date.today() - timedelta(days=1095)

    # ── ETF: last 2 years of GLD data ────────────────────────────────
    etf_q = await session.execute(
        select(EtfHolding)
        .where(EtfHolding.fund == "GLD", EtfHolding.holding_date >= since_2yr)
        .order_by(EtfHolding.holding_date)
    )
    etf_rows = etf_q.scalars().all()

    etf_changes = [
        r.change_tonnes for r in etf_rows
        if r.change_tonnes is not None
    ]

    etf_zscore = compute_zscore_90d(etf_changes)
    etf_percentile = compute_percentile_2yr(etf_changes)

    etf_latest = etf_rows[-1] if etf_rows else None
    etf_result = {
        "fund": "GLD",
        "zscore_90d": etf_zscore,
        "percentile_2yr": etf_percentile,
        "latest_change_tonnes": etf_latest.change_tonnes if etf_latest else None,
        "latest_total_tonnes": etf_latest.total_tonnes if etf_latest else None,
        "latest_date": str(etf_latest.holding_date) if etf_latest else None,
        "source_url": etf_latest.source_url if etf_latest else None,
    }

    # ── COT: last 3 years of gold data ───────────────────────────────
    cot_q = await session.execute(
        select(CotData)
        .where(CotData.asset == "gold", CotData.report_date >= since_3yr)
        .order_by(CotData.report_date)
    )
    cot_rows = cot_q.scalars().all()

    cot_nets = [
        r.non_commercial_net for r in cot_rows
        if r.non_commercial_net is not None
    ]

    cot_latest = cot_rows[-1] if cot_rows else None

    # WoW change as % of OI
    cot_wow_pct = compute_cot_wow_pct_of_oi(
        cot_latest.change_non_commercial_net if cot_latest else None,
        cot_latest.open_interest if cot_latest else None,
    )

    # Percentile (3-year and 1-year)
    cot_pct_3yr = compute_percentile_2yr(cot_nets) if len(cot_nets) >= 30 else None

    # 1-year subset (~52 weeks)
    since_1yr = date.today() - timedelta(days=365)
    cot_nets_1yr = [
        r.non_commercial_net for r in cot_rows
        if r.non_commercial_net is not None and r.report_date >= since_1yr
    ]
    cot_pct_1yr = compute_percentile_2yr(cot_nets_1yr) if len(cot_nets_1yr) >= 30 else None

    cot_result = {
        "wow_change_pct_of_oi": cot_wow_pct,
        "percentile_1yr": cot_pct_1yr,
        "percentile_3yr": cot_pct_3yr,
        "latest_net": cot_latest.non_commercial_net if cot_latest else None,
        "latest_oi": cot_latest.open_interest if cot_latest else None,
        "latest_date": str(cot_latest.report_date) if cot_latest else None,
        "source_url": cot_latest.source_url if cot_latest else None,
    }

    # ── Combined signal ──────────────────────────────────────────────
    combined = classify_combined_signal(etf_zscore, cot_pct_3yr)

    return {
        "etf": etf_result,
        "cot": cot_result,
        "combined_signal": combined,
    }
