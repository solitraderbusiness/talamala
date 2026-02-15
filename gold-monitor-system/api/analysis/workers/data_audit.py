"""Daily data quality audit worker.

Performs three categories of checks that the existing QA system cannot:
1. **Freshness** — verify each data type has recent records
2. **Cross-validation** — compare overlapping data sources for consistency
3. **Drift detection** — flag values >15% from their 30-day moving average

Creates MetricAlert entries for failures/warnings so they appear on the
existing Data Reliability admin page.
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.analysis.models import AssetPriceDaily, CotData, EtfHolding, MacroIndicator
from api.database import AsyncSessionLocal
from api.data_reliability.models import MetricAlert

logger = logging.getLogger("analysis.data_audit")

# ── Freshness thresholds (calendar days) ────────────────────────────────

FRESHNESS_CHECKS: list[dict] = [
    {"metric_id": "price_gc_f", "label": "Gold price", "table": "prices", "filter_key": "GC=F", "max_age_days": 3},
    {"metric_id": "price_dxy", "label": "DXY index", "table": "prices", "filter_key": "DX-Y.NYB", "max_age_days": 3},
    {"metric_id": "price_sp500", "label": "S&P 500", "table": "prices", "filter_key": "^GSPC", "max_age_days": 3},
    {"metric_id": "price_tnx", "label": "10Y yield (Yahoo)", "table": "prices", "filter_key": "^TNX", "max_age_days": 3},
    {"metric_id": "price_btc", "label": "Bitcoin", "table": "prices", "filter_key": "BTC-USD", "max_age_days": 3},
    {"metric_id": "fred_dgs10", "label": "FRED DGS10", "table": "fred", "filter_key": "DGS10", "max_age_days": 5},
    {"metric_id": "fred_dfii10", "label": "FRED DFII10", "table": "fred", "filter_key": "DFII10", "max_age_days": 5},
    {"metric_id": "fred_t10yie", "label": "FRED T10YIE", "table": "fred", "filter_key": "T10YIE", "max_age_days": 5},
    {"metric_id": "etf_gld", "label": "GLD holdings", "table": "etf", "filter_key": "GLD", "max_age_days": 3},
    {"metric_id": "cot_gold", "label": "COT gold", "table": "cot", "filter_key": "gold", "max_age_days": 12},
]

# ── Cross-validation checks ─────────────────────────────────────────────

CROSS_VALIDATION_TOLERANCE = {
    "yield_10y": 0.15,           # FRED DGS10 vs Yahoo ^TNX
    "breakeven_inflation": 0.3,  # (DGS10 - DFII10) vs T10YIE
    "gld_consistency": 0.5,      # today vs yesterday + change (tonnes)
}

# ── Drift detection ─────────────────────────────────────────────────────

DRIFT_THRESHOLD_PCT = 15  # flag if >15% from 30-day MA
DRIFT_WINDOW_DAYS = 30

DRIFT_CHECKS: list[dict] = [
    {"metric_id": "price_gc_f", "table": "prices", "filter_key": "GC=F", "label": "Gold price"},
    {"metric_id": "price_dxy", "table": "prices", "filter_key": "DX-Y.NYB", "label": "DXY"},
    {"metric_id": "price_sp500", "table": "prices", "filter_key": "^GSPC", "label": "S&P 500"},
    {"metric_id": "etf_gld", "table": "etf", "filter_key": "GLD", "label": "GLD holdings"},
]


# ── Helpers ──────────────────────────────────────────────────────────────

async def _get_latest_date(session: AsyncSession, table: str, filter_key: str) -> date | None:
    """Return the most recent date for a given data series."""
    if table == "prices":
        q = select(func.max(AssetPriceDaily.trade_date)).where(AssetPriceDaily.symbol == filter_key)
    elif table == "fred":
        q = select(func.max(MacroIndicator.observation_date)).where(MacroIndicator.series_id == filter_key)
    elif table == "etf":
        q = select(func.max(EtfHolding.holding_date)).where(EtfHolding.fund == filter_key)
    elif table == "cot":
        q = select(func.max(CotData.report_date)).where(CotData.asset == filter_key)
    else:
        return None
    result = await session.execute(q)
    return result.scalar_one_or_none()


async def _get_latest_value(session: AsyncSession, table: str, filter_key: str) -> float | None:
    """Return the most recent value for a data series."""
    if table == "prices":
        q = (
            select(AssetPriceDaily.close)
            .where(AssetPriceDaily.symbol == filter_key)
            .order_by(AssetPriceDaily.trade_date.desc())
            .limit(1)
        )
    elif table == "fred":
        q = (
            select(MacroIndicator.value)
            .where(MacroIndicator.series_id == filter_key)
            .order_by(MacroIndicator.observation_date.desc())
            .limit(1)
        )
    elif table == "etf":
        q = (
            select(EtfHolding.total_tonnes)
            .where(EtfHolding.fund == filter_key)
            .order_by(EtfHolding.holding_date.desc())
            .limit(1)
        )
    else:
        return None
    result = await session.execute(q)
    return result.scalar_one_or_none()


async def _get_recent_values(
    session: AsyncSession, table: str, filter_key: str, days: int,
) -> list[float]:
    """Return recent values for drift detection, oldest first."""
    cutoff = date.today() - timedelta(days=days)
    if table == "prices":
        q = (
            select(AssetPriceDaily.close)
            .where(AssetPriceDaily.symbol == filter_key, AssetPriceDaily.trade_date >= cutoff)
            .order_by(AssetPriceDaily.trade_date.asc())
        )
    elif table == "fred":
        q = (
            select(MacroIndicator.value)
            .where(MacroIndicator.series_id == filter_key, MacroIndicator.observation_date >= cutoff)
            .order_by(MacroIndicator.observation_date.asc())
        )
    elif table == "etf":
        q = (
            select(EtfHolding.total_tonnes)
            .where(EtfHolding.fund == filter_key, EtfHolding.holding_date >= cutoff)
            .order_by(EtfHolding.holding_date.asc())
        )
    else:
        return []
    result = await session.execute(q)
    return [v for (v,) in result.all() if v is not None]


async def _create_audit_alert(
    session: AsyncSession,
    metric_id: str,
    severity: str,
    message: str,
) -> None:
    """Create an audit alert if no unresolved one exists for this metric + type."""
    existing = await session.execute(
        select(MetricAlert).where(
            MetricAlert.metric_id == metric_id,
            MetricAlert.alert_type == "audit",
            MetricAlert.resolved_at.is_(None),
        ).limit(1)
    )
    if not existing.scalar_one_or_none():
        session.add(MetricAlert(
            metric_id=metric_id,
            alert_type="audit",
            severity=severity,
            message=message,
        ))


async def _resolve_audit_alert(session: AsyncSession, metric_id: str) -> None:
    """Resolve any open audit alert for a metric."""
    existing = await session.execute(
        select(MetricAlert).where(
            MetricAlert.metric_id == metric_id,
            MetricAlert.alert_type == "audit",
            MetricAlert.resolved_at.is_(None),
        )
    )
    for alert in existing.scalars().all():
        alert.resolved_at = datetime.now(timezone.utc)


# ── Check runners ────────────────────────────────────────────────────────

async def _check_freshness(session: AsyncSession) -> dict:
    """Check that each data series has recent records."""
    today = date.today()
    passed, warned, failed = 0, 0, 0
    details = []

    for check in FRESHNESS_CHECKS:
        latest = await _get_latest_date(session, check["table"], check["filter_key"])
        mid = check["metric_id"]

        if latest is None:
            status = "fail"
            msg = f"{check['label']}: no data found"
            failed += 1
            await _create_audit_alert(session, mid, "critical", msg)
        else:
            age_days = (today - latest).days
            if age_days > check["max_age_days"]:
                status = "fail"
                msg = f"{check['label']}: {age_days}d old (max {check['max_age_days']}d)"
                failed += 1
                await _create_audit_alert(session, mid, "critical", msg)
            elif age_days > check["max_age_days"] - 1:
                status = "warn"
                msg = f"{check['label']}: {age_days}d old (approaching {check['max_age_days']}d limit)"
                warned += 1
                await _create_audit_alert(session, mid, "warning", msg)
            else:
                status = "pass"
                msg = f"{check['label']}: {age_days}d old"
                passed += 1
                await _resolve_audit_alert(session, mid)

        details.append({"metric_id": mid, "status": status, "message": msg})

    return {"pass": passed, "warn": warned, "fail": failed, "details": details}


async def _check_cross_validation(session: AsyncSession) -> dict:
    """Compare overlapping data sources for consistency."""
    passed, warned, failed = 0, 0, 0
    details = []

    # 1) 10Y yield: FRED DGS10 vs Yahoo ^TNX
    fred_dgs10 = await _get_latest_value(session, "fred", "DGS10")
    yahoo_tnx = await _get_latest_value(session, "prices", "^TNX")
    if fred_dgs10 is not None and yahoo_tnx is not None:
        diff = abs(fred_dgs10 - yahoo_tnx)
        tol = CROSS_VALIDATION_TOLERANCE["yield_10y"]
        if diff > tol:
            status = "fail"
            msg = f"10Y yield mismatch: FRED={fred_dgs10:.3f} vs Yahoo={yahoo_tnx:.3f} (diff={diff:.3f}, tol={tol})"
            failed += 1
            await _create_audit_alert(session, "fred_dgs10", "warning", msg)
        else:
            status = "pass"
            msg = f"10Y yield match: FRED={fred_dgs10:.3f} vs Yahoo={yahoo_tnx:.3f} (diff={diff:.3f})"
            passed += 1
            await _resolve_audit_alert(session, "fred_dgs10")
        details.append({"check": "yield_10y", "status": status, "message": msg})
    else:
        details.append({"check": "yield_10y", "status": "skip", "message": "Missing data for 10Y yield comparison"})

    # 2) Breakeven inflation: (DGS10 - DFII10) vs T10YIE
    fred_dfii10 = await _get_latest_value(session, "fred", "DFII10")
    fred_t10yie = await _get_latest_value(session, "fred", "T10YIE")
    if fred_dgs10 is not None and fred_dfii10 is not None and fred_t10yie is not None:
        computed = fred_dgs10 - fred_dfii10
        diff = abs(computed - fred_t10yie)
        tol = CROSS_VALIDATION_TOLERANCE["breakeven_inflation"]
        if diff > tol:
            status = "fail"
            msg = f"Breakeven mismatch: DGS10-DFII10={computed:.3f} vs T10YIE={fred_t10yie:.3f} (diff={diff:.3f}, tol={tol})"
            failed += 1
            await _create_audit_alert(session, "fred_t10yie", "warning", msg)
        else:
            status = "pass"
            msg = f"Breakeven match: DGS10-DFII10={computed:.3f} vs T10YIE={fred_t10yie:.3f} (diff={diff:.3f})"
            passed += 1
            await _resolve_audit_alert(session, "fred_t10yie")
        details.append({"check": "breakeven_inflation", "status": status, "message": msg})
    else:
        details.append({"check": "breakeven_inflation", "status": "skip", "message": "Missing data for breakeven comparison"})

    # 3) GLD internal consistency: today's tonnes ≈ yesterday's + change
    gld_rows = await session.execute(
        select(EtfHolding.total_tonnes, EtfHolding.change_tonnes)
        .where(EtfHolding.fund == "GLD")
        .order_by(EtfHolding.holding_date.desc())
        .limit(2)
    )
    rows = gld_rows.all()
    if len(rows) == 2 and rows[0][0] is not None and rows[1][0] is not None:
        today_tonnes = rows[0][0]
        yesterday_tonnes = rows[1][0]
        change = rows[0][1] if rows[0][1] is not None else 0.0
        expected = yesterday_tonnes + change
        diff = abs(today_tonnes - expected)
        tol = CROSS_VALIDATION_TOLERANCE["gld_consistency"]
        if diff > tol:
            status = "fail"
            msg = f"GLD inconsistent: today={today_tonnes:.2f}t, yesterday+change={expected:.2f}t (diff={diff:.2f}t)"
            failed += 1
            await _create_audit_alert(session, "etf_gld", "warning", msg)
        else:
            status = "pass"
            msg = f"GLD consistent: today={today_tonnes:.2f}t, yesterday+change={expected:.2f}t"
            passed += 1
            await _resolve_audit_alert(session, "etf_gld")
        details.append({"check": "gld_consistency", "status": status, "message": msg})
    else:
        details.append({"check": "gld_consistency", "status": "skip", "message": "Not enough GLD rows for consistency check"})

    return {"pass": passed, "warn": warned, "fail": failed, "details": details}


async def _check_drift(session: AsyncSession) -> dict:
    """Flag values that deviate >15% from their 30-day moving average."""
    passed, warned, failed = 0, 0, 0
    details = []

    for check in DRIFT_CHECKS:
        values = await _get_recent_values(session, check["table"], check["filter_key"], DRIFT_WINDOW_DAYS)
        mid = check["metric_id"]

        if len(values) < 5:
            details.append({"metric_id": mid, "status": "skip", "message": f"{check['label']}: not enough data ({len(values)} points)"})
            continue

        ma = sum(values) / len(values)
        latest = values[-1]

        if ma == 0:
            details.append({"metric_id": mid, "status": "skip", "message": f"{check['label']}: MA is zero"})
            continue

        deviation_pct = abs(latest - ma) / abs(ma) * 100

        if deviation_pct > DRIFT_THRESHOLD_PCT:
            status = "warn"
            msg = f"{check['label']}: latest={latest:.2f} is {deviation_pct:.1f}% from 30d MA={ma:.2f}"
            warned += 1
            await _create_audit_alert(session, mid, "warning", f"Drift: {msg}")
        else:
            status = "pass"
            msg = f"{check['label']}: latest={latest:.2f} is {deviation_pct:.1f}% from 30d MA={ma:.2f}"
            passed += 1
            # Don't resolve drift alerts here — let freshness/cross-val handle resolution
        details.append({"metric_id": mid, "status": status, "message": msg})

    return {"pass": passed, "warn": warned, "fail": failed, "details": details}


# ── Zero/NaN detection ────────────────────────────────────────────────────

ZERO_CHECKS: list[dict] = [
    {"metric_id": "price_gc_f", "table": "prices", "filter_key": "GC=F", "label": "Gold price", "min_valid": 500},
    {"metric_id": "price_dxy", "table": "prices", "filter_key": "DX-Y.NYB", "label": "DXY index", "min_valid": 50},
    {"metric_id": "price_vix", "table": "prices", "filter_key": "^VIX", "label": "VIX", "min_valid": 1},
    {"metric_id": "etf_gld", "table": "etf", "filter_key": "GLD", "label": "GLD tonnes", "min_valid": 100},
    {"metric_id": "fred_dfii10", "table": "fred", "filter_key": "DFII10", "label": "DFII10", "min_valid": None},
]


async def _check_zero_nan(session: AsyncSession) -> dict:
    """Check that key displayed values are not 0 or NaN when they shouldn't be."""
    passed, warned, failed = 0, 0, 0
    details = []

    for check in ZERO_CHECKS:
        value = await _get_latest_value(session, check["table"], check["filter_key"])
        mid = f"zero_{check['metric_id']}"

        if value is None:
            details.append({"metric_id": mid, "status": "skip", "message": f"{check['label']}: no data"})
            continue

        # Check for NaN (Python float NaN)
        if math.isnan(value):
            status = "fail"
            msg = f"{check['label']}: value is NaN"
            failed += 1
            await _create_audit_alert(session, mid, "critical", msg)
            details.append({"metric_id": mid, "status": status, "message": msg})
            continue

        # Check for zero or below minimum
        if check["min_valid"] is not None and value < check["min_valid"]:
            if value == 0:
                status = "fail"
                msg = f"{check['label']}: value is 0 (expected > {check['min_valid']})"
                failed += 1
                await _create_audit_alert(session, mid, "critical", msg)
            else:
                status = "warn"
                msg = f"{check['label']}: value {value:.2f} is below minimum {check['min_valid']}"
                warned += 1
                await _create_audit_alert(session, mid, "warning", msg)
        else:
            status = "pass"
            msg = f"{check['label']}: value {value:.2f} OK"
            passed += 1
            await _resolve_audit_alert(session, mid)

        details.append({"metric_id": mid, "status": status, "message": msg})

    return {"pass": passed, "warn": warned, "fail": failed, "details": details}


async def _check_unit_validation(session: AsyncSession) -> dict:
    """Validate that CPIAUCSL is stored as an index (>100), not a percentage."""
    passed, warned, failed = 0, 0, 0
    details = []

    cpi_value = await _get_latest_value(session, "fred", "CPIAUCSL")
    mid = "unit_cpiaucsl"

    if cpi_value is None:
        details.append({"metric_id": mid, "status": "skip", "message": "CPIAUCSL: no data"})
    elif cpi_value < 100:
        # CPI index should be >100 (base year 1982-84 = 100)
        status = "fail"
        msg = f"CPIAUCSL: value {cpi_value:.2f} appears to be a percentage, not an index (should be >100)"
        failed += 1
        await _create_audit_alert(session, mid, "critical", msg)
        details.append({"metric_id": mid, "status": status, "message": msg})
    else:
        status = "pass"
        msg = f"CPIAUCSL: value {cpi_value:.2f} is a valid index level"
        passed += 1
        await _resolve_audit_alert(session, mid)
        details.append({"metric_id": mid, "status": status, "message": msg})

    return {"pass": passed, "warn": warned, "fail": failed, "details": details}


async def _check_score_saturation(session: AsyncSession) -> dict:
    """Check if any sentiment component has score=0 or score=100 in >10% of runs."""
    passed, warned, failed = 0, 0, 0
    details = []

    try:
        from api.data_reliability.models import SentimentCalcLog
    except ImportError:
        details.append({"check": "score_saturation", "status": "skip", "message": "SentimentCalcLog not available"})
        return {"pass": 0, "warn": 0, "fail": 0, "details": details}

    since = date.today() - timedelta(days=60)
    q = await session.execute(
        select(SentimentCalcLog)
        .where(SentimentCalcLog.run_at >= since)
    )
    logs = q.scalars().all()

    if len(logs) < 10:
        details.append({"check": "score_saturation", "status": "skip", "message": f"Only {len(logs)} runs in 60d (need ≥10)"})
        return {"pass": 0, "warn": 0, "fail": 0, "details": details}

    # Parse component scores from each log
    component_scores: dict[str, list[float]] = {}
    for log in logs:
        if not log.components:
            continue
        comps = log.components if isinstance(log.components, list) else []
        for comp in comps:
            if isinstance(comp, dict) and "name" in comp and "score" in comp:
                name = comp["name"]
                score = comp["score"]
                if isinstance(score, (int, float)):
                    component_scores.setdefault(name, []).append(score)

    for name, scores in component_scores.items():
        total = len(scores)
        if total < 10:
            continue
        saturated = sum(1 for s in scores if s == 0 or s == 100)
        pct = saturated / total * 100
        mid = f"saturation_{name}"

        if pct > 10:
            status = "warn"
            msg = f"Component '{name}': {pct:.0f}% of runs at 0 or 100 (saturation warning)"
            warned += 1
            await _create_audit_alert(session, mid, "warning", msg)
        else:
            status = "pass"
            msg = f"Component '{name}': {pct:.0f}% saturation (OK)"
            passed += 1
            await _resolve_audit_alert(session, mid)

        details.append({"metric_id": mid, "status": status, "message": msg})

    return {"pass": passed, "warn": warned, "fail": failed, "details": details}


# ── Main entry point ─────────────────────────────────────────────────────

async def run() -> dict:
    """Run all audit checks and return summary."""
    async with AsyncSessionLocal() as session:
        freshness = await _check_freshness(session)
        cross_val = await _check_cross_validation(session)
        drift = await _check_drift(session)
        zero_nan = await _check_zero_nan(session)
        unit_val = await _check_unit_validation(session)
        saturation = await _check_score_saturation(session)

        await session.commit()

    # Determine overall status
    all_sections = [freshness, cross_val, drift, zero_nan, unit_val, saturation]
    total_fail = sum(s["fail"] for s in all_sections)
    total_warn = sum(s["warn"] for s in all_sections)

    if total_fail > 0:
        overall = "fail"
    elif total_warn > 0:
        overall = "warning"
    else:
        overall = "pass"

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "freshness": {k: v for k, v in freshness.items() if k != "details"},
        "cross_validation": {k: v for k, v in cross_val.items() if k != "details"},
        "drift": {k: v for k, v in drift.items() if k != "details"},
        "zero_nan": {k: v for k, v in zero_nan.items() if k != "details"},
        "unit_validation": {k: v for k, v in unit_val.items() if k != "details"},
        "score_saturation": {k: v for k, v in saturation.items() if k != "details"},
        "overall": overall,
    }

    logger.info(
        "Data audit complete: overall=%s | freshness(P=%d W=%d F=%d) | cross_val(P=%d W=%d F=%d) | drift(P=%d W=%d F=%d) | zero_nan(P=%d W=%d F=%d) | unit(P=%d W=%d F=%d) | saturation(P=%d W=%d F=%d)",
        overall,
        freshness["pass"], freshness["warn"], freshness["fail"],
        cross_val["pass"], cross_val["warn"], cross_val["fail"],
        drift["pass"], drift["warn"], drift["fail"],
        zero_nan["pass"], zero_nan["warn"], zero_nan["fail"],
        unit_val["pass"], unit_val["warn"], unit_val["fail"],
        saturation["pass"], saturation["warn"], saturation["fail"],
    )

    # Log details for any non-pass items
    named_sections = [
        ("freshness", freshness), ("cross_validation", cross_val), ("drift", drift),
        ("zero_nan", zero_nan), ("unit_validation", unit_val), ("score_saturation", saturation),
    ]
    for section_name, section in named_sections:
        for detail in section["details"]:
            if detail.get("status") not in ("pass", "skip"):
                logger.warning("  [%s] %s", section_name, detail.get("message", ""))

    return summary
