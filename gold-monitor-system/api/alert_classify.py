"""
Classify alerts by news_type and event_category based on matched rule IDs.

Used by the worker to stamp alerts with structured metadata for
future analytics (accuracy tracking, category-level sentiment, etc.).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Rule ID → event category mapping
# ---------------------------------------------------------------------------

RULE_TO_CATEGORY: dict[str, str] = {
    # Global gold — Fed / monetary policy
    "GLOB_RATE_DECISION": "fed_policy",
    "GLOB_QE_QT": "fed_policy",
    "GLOB_FED_COMM": "fed_policy",
    # Global gold — rates & dollar
    "GLOB_US_YIELDS": "rates_bonds",
    "GLOB_DOLLAR_DXY": "dollar",
    # Global gold — economic data
    "GLOB_US_MACRO_DATA": "economic_data",
    # Global gold — geopolitics
    "GLOB_GEOPOL_RISK": "geopolitics",
    # Global gold — supply & demand
    "GLOB_MINING_SUPPLY": "supply_demand",
    "GLOB_CB_GOLD_RESERVES": "central_banks",
    "GLOB_ASIA_PHYSICAL_DEMAND": "supply_demand",
    # Global gold — risk & crypto
    "GLOB_EQUITY_RISK_OFF": "risk_sentiment",
    "GLOB_CRYPTO_SHOCKS": "crypto",
    # Global / Iran — price movement
    "GLOB_GOLD_PRICE": "price_movement",
    "IR_GOLD_COIN_PRICE": "price_movement",
    # Iran — forex
    "IR_FX_USD": "iran_forex",
    "IR_GOV_FX_POLICY": "iran_forex",
    # Iran — sanctions & geopolitics
    "IR_RESERVES_SANCTIONS": "sanctions",
    "IR_FOREIGN_POLICY": "geopolitics",
    # Iran — economy
    "IR_MACRO_INFLATION_LIQ": "iran_economy",
    "IR_BUDGET_FISCAL": "iran_economy",
    "IR_RATES_CREDIT": "iran_economy",
    # Iran — politics
    "IR_INTERNAL_POL_SOCIAL": "iran_politics",
    "IR_ECON_MANAGEMENT_CHANGES": "iran_politics",
    # Iran — physical supply
    "IR_PHYSICAL_SUPPLY_DEMAND": "supply_demand",
    # Coin market
    "COIN_PREMIUM_BUBBLE": "coin_market",
    "COIN_CB_AUCTIONS": "coin_market",
    "COIN_MINT_SUPPLY": "coin_market",
    "COIN_SEASONAL_DEMAND": "coin_market",
    "COIN_POLICY_TAX_TARIFF": "coin_market",
    "COIN_SENTIMENT_SOCIAL": "coin_market",
    # Gold funds
    "GF_ETF_FLOWS": "etf_flows",
    "GF_IRN_FUND_PERFORMANCE": "etf_flows",
    "GF_NAV_PREMIUM": "etf_flows",
    "GF_NEW_FUND": "etf_flows",
    "GF_REGULATION_POLICY": "etf_flows",
}

# Rule IDs that indicate a "price report" rather than a causal event
_PRICE_RULE_IDS = {"GLOB_GOLD_PRICE", "IR_GOLD_COIN_PRICE"}


def classify_alert(
    matched_rule_ids: list[str],
) -> tuple[str, str]:
    """Determine ``news_type`` and ``event_category`` for an alert.

    Parameters
    ----------
    matched_rule_ids:
        List of rule IDs that matched (highest-score first).

    Returns
    -------
    tuple[str, str]
        ``(news_type, event_category)`` where news_type is one of
        ``'price_report'``, ``'causal_event'``, ``'mixed'``, ``'commentary'``
        and event_category is a descriptive slug.
    """
    if not matched_rule_ids:
        return "commentary", "other"

    has_price = any(rid in _PRICE_RULE_IDS for rid in matched_rule_ids)
    has_causal = any(rid not in _PRICE_RULE_IDS for rid in matched_rule_ids)

    if has_price and has_causal:
        news_type = "mixed"
    elif has_price:
        news_type = "price_report"
    elif has_causal:
        news_type = "causal_event"
    else:
        news_type = "commentary"

    # Event category from the highest-priority (first) matched rule
    event_category = "other"
    for rid in matched_rule_ids:
        cat = RULE_TO_CATEGORY.get(rid)
        if cat:
            event_category = cat
            break

    return news_type, event_category
