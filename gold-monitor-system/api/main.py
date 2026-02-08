"""
Gold Monitor System — FastAPI application entry-point.

Startup tasks
-------------
1. Run Alembic migrations (head).
2. Seed the default admin user if it does not exist.
3. Take a snapshot of the current YAML rules file.

Routers
-------
``/api/alerts``   — alert CRUD & filtering
``/api/sources``  — data-source management
``/api/admin``    — login, settings, user management
``/api/rules``    — rule inspection & categories
``/api/health``   — liveness / readiness probes
"""

from __future__ import annotations

import hashlib
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from api.auth import get_password_hash
from api.config import settings
from api.database import AsyncSessionLocal, sync_engine
from api.models import AdminUser, Base, RulesSnapshot, Source

logger = logging.getLogger("gold_monitor")

_STARTUP_TIME: float = 0.0


# ── Startup helpers ─────────────────────────────────────────────────────

def _run_migrations() -> None:
    """Execute Alembic ``upgrade head`` using the sync engine.

    If Alembic is not configured yet the error is logged but the
    application continues — this allows first-time bootstrap where
    tables are created directly from the ORM metadata.
    """
    try:
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", "api/alembic")
        alembic_cfg.set_main_option(
            "sqlalchemy.url", settings.DATABASE_URL_SYNC,
        )
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations applied successfully.")
    except Exception:
        logger.warning(
            "Alembic migration skipped (not configured or failed). "
            "Falling back to metadata.create_all.",
            exc_info=True,
        )
        Base.metadata.create_all(bind=sync_engine)


async def _seed_admin() -> None:
    """Create the default admin user if the table is empty."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AdminUser).where(AdminUser.email == settings.ADMIN_EMAIL),
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            logger.info("Admin user '%s' already exists — skipping seed.", settings.ADMIN_EMAIL)
            return

        admin = AdminUser(
            email=settings.ADMIN_EMAIL,
            password_hash=get_password_hash(settings.ADMIN_PASSWORD),
            role="admin",
        )
        session.add(admin)
        await session.commit()
        logger.info("Default admin user '%s' seeded.", settings.ADMIN_EMAIL)


async def _snapshot_rules() -> None:
    """Read the YAML rules file from disk and persist a snapshot row."""
    yaml_path = Path(settings.YAML_PATH)
    if not yaml_path.exists():
        logger.warning("Rules YAML not found at %s — snapshot skipped.", yaml_path)
        return

    content = yaml_path.read_text(encoding="utf-8")
    version = hashlib.sha256(content.encode()).hexdigest()[:12]

    async with AsyncSessionLocal() as session:
        # Avoid duplicate snapshots for the same content
        result = await session.execute(
            select(RulesSnapshot).where(RulesSnapshot.version == version),
        )
        if result.scalar_one_or_none() is not None:
            logger.info("Rules snapshot v%s already exists.", version)
            return

        snapshot = RulesSnapshot(
            version=version,
            yaml_content=content,
            loaded_at=datetime.now(timezone.utc),
        )
        session.add(snapshot)
        await session.commit()
        logger.info("Rules snapshot v%s persisted.", version)


async def _seed_sources() -> None:
    """Seed default news sources if the sources table is empty."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Source).limit(1))
        if result.scalar_one_or_none() is not None:
            logger.info("Sources already exist — skipping seed.")
            return

        default_sources = [
            # ── Global Gold (English RSS — lower frequency) ───────
            Source(
                name="Kitco Gold News",
                type="rss",
                base_url="https://www.kitco.com",
                endpoints=["https://www.kitco.com/news/rss"],
                enabled=False,  # Malformed XML from server
                poll_interval_seconds=600,
                categories=["global_gold"],
                rule_bindings=[
                    "GLOB_RATE_DECISION", "GLOB_CB_GOLD_RESERVES",
                    "GLOB_MINING_SUPPLY", "GLOB_ASIA_PHYSICAL_DEMAND",
                    "GLOB_DOLLAR_DXY",
                ],
                reliability_score=0.85,
                notes="Kitco — leading gold market news and analysis",
            ),
            Source(
                name="Federal Reserve Press Releases",
                type="rss",
                base_url="https://www.federalreserve.gov",
                endpoints=["/feeds/press_all.xml"],
                enabled=True,
                poll_interval_seconds=600,
                categories=["global_gold"],
                rule_bindings=[
                    "GLOB_RATE_DECISION", "GLOB_QE_QT", "GLOB_FED_COMM",
                ],
                reliability_score=0.95,
                notes="Official Federal Reserve press releases",
            ),
            Source(
                name="CNBC Finance",
                type="rss",
                base_url="https://www.cnbc.com",
                endpoints=[
                    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
                ],
                enabled=True,
                poll_interval_seconds=600,
                categories=["global_gold"],
                rule_bindings=[
                    "GLOB_US_MACRO_DATA", "GLOB_EQUITY_RISK_OFF",
                    "GLOB_FED_COMM", "GLOB_GEOPOL_RISK",
                ],
                reliability_score=0.8,
                notes="CNBC finance news — macro data, Fed, geopolitics",
            ),
            # ── Google News (English queries — server is outside Iran,
            #    so Persian locale is silently overridden by Google) ──
            Source(
                name="Google News — Gold & Precious Metals",
                type="rss",
                base_url="https://news.google.com",
                endpoints=[
                    "https://news.google.com/rss/search?q=gold+price+OR+gold+market+OR+gold+futures+OR+%22gold+rally%22+when%3A7d&hl=en-US&gl=US&ceid=US:en",
                ],
                enabled=True,
                poll_interval_seconds=180,
                categories=["global_gold"],
                rule_bindings=[
                    "GLOB_RATE_DECISION", "GLOB_DOLLAR_DXY",
                    "GLOB_US_MACRO_DATA", "GLOB_CB_GOLD_RESERVES",
                    "GLOB_MINING_SUPPLY", "GLOB_ASIA_PHYSICAL_DEMAND",
                ],
                reliability_score=0.8,
                notes="Google News EN — gold price, market, futures",
            ),
            Source(
                name="Google News — Fed & Interest Rates",
                type="rss",
                base_url="https://news.google.com",
                endpoints=[
                    "https://news.google.com/rss/search?q=%22interest+rate%22+OR+%22Fed+rate%22+OR+FOMC+OR+Powell+OR+%22rate+cut%22+OR+%22rate+hike%22+when%3A7d&hl=en-US&gl=US&ceid=US:en",
                ],
                enabled=True,
                poll_interval_seconds=300,
                categories=["global_gold"],
                rule_bindings=[
                    "GLOB_RATE_DECISION", "GLOB_QE_QT", "GLOB_FED_COMM",
                    "GLOB_US_YIELDS",
                ],
                reliability_score=0.8,
                notes="Google News EN — Fed, interest rates, FOMC",
            ),
            Source(
                name="Google News — Iran Sanctions & Geopolitics",
                type="rss",
                base_url="https://news.google.com",
                endpoints=[
                    "https://news.google.com/rss/search?q=Iran+sanctions+OR+Iran+nuclear+OR+Iran+currency+OR+%22Iran+gold%22+when%3A7d&hl=en-US&gl=US&ceid=US:en",
                ],
                enabled=True,
                poll_interval_seconds=300,
                categories=["global_gold", "iran_gold"],
                rule_bindings=[
                    "GLOB_GEOPOL_RISK", "IR_RESERVES_SANCTIONS",
                    "IR_FOREIGN_POLICY",
                ],
                reliability_score=0.75,
                notes="Google News EN — Iran sanctions, nuclear, geopolitics",
            ),
            Source(
                name="Google News — Inflation & Central Banks",
                type="rss",
                base_url="https://news.google.com",
                endpoints=[
                    "https://news.google.com/rss/search?q=inflation+OR+CPI+OR+%22central+bank%22+OR+%22treasury+yields%22+OR+DXY+when%3A7d&hl=en-US&gl=US&ceid=US:en",
                ],
                enabled=True,
                poll_interval_seconds=300,
                categories=["global_gold"],
                rule_bindings=[
                    "GLOB_US_MACRO_DATA", "GLOB_DOLLAR_DXY",
                    "GLOB_US_YIELDS", "GLOB_CB_GOLD_RESERVES",
                ],
                reliability_score=0.75,
                notes="Google News EN — inflation, CPI, central banks, yields",
            ),
            # ── Iran Gold & Coin (Persian RSS) ─────────────────────
            Source(
                name="خبرگزاری ایرنا - اقتصادی",
                type="rss",
                base_url="https://www.irna.ir",
                endpoints=["/rss"],
                enabled=True,
                poll_interval_seconds=180,
                categories=["iran_gold", "coin"],
                rule_bindings=[
                    "IR_FX_USD", "IR_GOV_FX_POLICY", "IR_MACRO_INFLATION_LIQ",
                    "IR_BUDGET_FISCAL", "IR_RATES_CREDIT",
                    "IR_ECON_MANAGEMENT_CHANGES",
                ],
                reliability_score=0.85,
                notes="ایرنا — خبرگزاری جمهوری اسلامی، اخبار اقتصادی",
            ),
            Source(
                name="خبرگزاری تسنیم - اقتصادی",
                type="rss",
                base_url="https://www.tasnimnews.com",
                endpoints=["/fa/rss"],
                enabled=False,  # DNS failure from Docker
                poll_interval_seconds=180,
                categories=["iran_gold", "coin"],
                rule_bindings=[
                    "IR_FX_USD", "IR_GOV_FX_POLICY", "IR_RESERVES_SANCTIONS",
                    "IR_FOREIGN_POLICY", "IR_INTERNAL_POL_SOCIAL",
                ],
                reliability_score=0.85,
                notes="تسنیم — غیرفعال (DNS failure)",
            ),
            Source(
                name="خبرگزاری فارس - اقتصادی",
                type="rss",
                base_url="https://www.farsnews.ir",
                endpoints=["/rss"],
                enabled=False,  # Malformed RSS XML
                poll_interval_seconds=180,
                categories=["iran_gold", "coin"],
                rule_bindings=[
                    "IR_FX_USD", "IR_MACRO_INFLATION_LIQ",
                    "IR_BUDGET_FISCAL", "IR_FOREIGN_POLICY",
                ],
                reliability_score=0.8,
                notes="فارس — غیرفعال (RSS malformed)",
            ),
            Source(
                name="خبرگزاری مهر - اقتصادی",
                type="rss",
                base_url="https://www.mehrnews.com",
                endpoints=["/rss"],
                enabled=True,
                poll_interval_seconds=180,
                categories=["iran_gold", "coin"],
                rule_bindings=[
                    "IR_FX_USD", "IR_GOV_FX_POLICY",
                    "IR_INTERNAL_POL_SOCIAL", "IR_FOREIGN_POLICY",
                    "IR_ECON_MANAGEMENT_CHANGES",
                ],
                reliability_score=0.8,
                notes="مهر — سیاسی/اقتصادی، تغییرات مدیران، سیاست ارزی",
            ),
            Source(
                name="خبرگزاری ایسنا - اقتصادی",
                type="rss",
                base_url="https://www.isna.ir",
                endpoints=["/rss"],
                enabled=False,  # Malformed RSS XML
                poll_interval_seconds=180,
                categories=["iran_gold", "coin", "gold_funds"],
                rule_bindings=[
                    "IR_FX_USD", "IR_MACRO_INFLATION_LIQ",
                    "IR_RATES_CREDIT", "IR_PHYSICAL_SUPPLY_DEMAND",
                ],
                reliability_score=0.8,
                notes="ایسنا — اقتصادی، نرخ سود، عرضه/تقاضای فیزیکی طلا",
            ),
            Source(
                name="تجارت‌نیوز",
                type="html",
                base_url="https://tejaratnews.com",
                endpoints=["/gold-price"],
                enabled=False,  # Disabled — URL returns 404
                poll_interval_seconds=300,
                categories=["iran_gold", "coin"],
                rule_bindings=[
                    "IR_FX_USD", "COIN_PREMIUM_BUBBLE",
                    "COIN_CB_AUCTIONS", "IR_PHYSICAL_SUPPLY_DEMAND",
                    "COIN_MINT_SUPPLY",
                ],
                reliability_score=0.7,
                notes="تجارت‌نیوز — غیرفعال (404)",
            ),
            Source(
                name="اقتصاد آنلاین",
                type="rss",
                base_url="https://www.eghtesadonline.com",
                endpoints=["/rss"],
                enabled=True,
                poll_interval_seconds=300,
                categories=["iran_gold", "coin", "gold_funds"],
                rule_bindings=[
                    "IR_FX_USD", "IR_MACRO_INFLATION_LIQ",
                    "COIN_PREMIUM_BUBBLE", "COIN_SENTIMENT_SOCIAL",
                    "COIN_SEASONAL_DEMAND", "COIN_POLICY_TAX_TARIFF",
                    "FUNDS_FLOW_VOLUME", "FUNDS_CAPITAL_MARKET_NEWS",
                ],
                reliability_score=0.7,
                notes="اقتصاد آنلاین — بازار سکه، صندوق طلا، تحلیل بازار",
            ),
            # ── Gold Funds (بورس) ──────────────────────────────────
            Source(
                name="بورس‌نیوز",
                type="rss",
                base_url="https://www.boursenews.ir",
                endpoints=["/rss"],
                enabled=False,  # Disabled — URL returns 404
                poll_interval_seconds=300,
                categories=["gold_funds"],
                rule_bindings=[
                    "FUNDS_NAV_PREMIUM", "FUNDS_FLOW_VOLUME",
                    "FUNDS_CAPITAL_MARKET_NEWS", "FUNDS_CODAL_NOTICES",
                ],
                reliability_score=0.75,
                notes="بورس‌نیوز — غیرفعال (404)",
            ),
            # ── Google News (geopolitics & risk) ──────────────────
            Source(
                name="Google News — Geopolitics & Risk",
                type="rss",
                base_url="https://news.google.com",
                endpoints=[
                    "https://news.google.com/rss/search?q=war+OR+%22geopolitical+risk%22+OR+%22safe+haven%22+OR+%22stock+market+crash%22+OR+%22bank+crisis%22+when%3A7d&hl=en-US&gl=US&ceid=US:en",
                ],
                enabled=True,
                poll_interval_seconds=300,
                categories=["global_gold"],
                rule_bindings=[
                    "GLOB_GEOPOL_RISK", "GLOB_EQUITY_RISK_OFF",
                    "GLOB_CRYPTO_SHOCKS",
                ],
                reliability_score=0.7,
                notes="Google News EN — geopolitics, risk-off, safe haven",
            ),
        ]

        for source in default_sources:
            session.add(source)

        await session.commit()
        logger.info("Seeded %d default news sources.", len(default_sources))


# ── Lifespan ────────────────────────────────────────────────────────────


async def _migrate_sources_to_persian() -> None:
    """Switch English Google News feeds to Persian, fix broken sources.

    Runs once per deployment (tracked via settings table marker).
    """
    marker_key = "migration:persian_sources_v1"
    async with AsyncSessionLocal() as session:
        # Check if already applied
        result = await session.execute(
            text("SELECT key FROM settings WHERE key = :k"),
            {"k": marker_key},
        )
        if result.scalar_one_or_none() is not None:
            return

        # --- Switch English Google News to Persian ---
        PERSIAN_FEEDS: dict[str, dict] = {
            "Google News — Gold Market": {
                "name": "Google News — طلا و قیمت جهانی",
                "endpoints": [
                    "https://news.google.com/rss/search?q=%D8%B7%D9%84%D8%A7+%D8%A7%D9%88%D9%86%D8%B3+%D9%82%DB%8C%D9%85%D8%AA+%D8%AC%D9%87%D8%A7%D9%86%DB%8C+when%3A7d&hl=fa&gl=IR&ceid=IR:fa",
                ],
                "categories": ["global_gold", "iran_gold"],
                "rule_bindings": [
                    "GLOB_RATE_DECISION", "GLOB_DOLLAR_DXY",
                    "GLOB_US_MACRO_DATA", "GLOB_CB_GOLD_RESERVES",
                    "IR_FX_USD",
                ],
            },
            "Google News — Commodities": {
                "name": "Google News — تحریم و مذاکرات",
                "endpoints": [
                    "https://news.google.com/rss/search?q=%D8%AA%D8%AD%D8%B1%DB%8C%D9%85+%D8%A7%DB%8C%D8%B1%D8%A7%D9%86+%D9%85%D8%B0%D8%A7%DA%A9%D8%B1%D8%A7%D8%AA+%D8%A7%D8%B1%D8%B2+when%3A7d&hl=fa&gl=IR&ceid=IR:fa",
                ],
                "categories": ["iran_gold"],
                "rule_bindings": [
                    "IR_RESERVES_SANCTIONS", "IR_FOREIGN_POLICY",
                    "IR_GOV_FX_POLICY", "IR_FX_USD",
                ],
            },
            "Google News — Crypto & Gold": {
                "name": "Google News — تورم و بانک مرکزی",
                "endpoints": [
                    "https://news.google.com/rss/search?q=%D8%AA%D9%88%D8%B1%D9%85+%D9%86%D9%82%D8%AF%DB%8C%D9%86%DA%AF%DB%8C+%D8%A8%D8%A7%D9%86%DA%A9+%D9%85%D8%B1%DA%A9%D8%B2%DB%8C+%D9%86%D8%B1%D8%AE+%D8%A8%D9%87%D8%B1%D9%87+when%3A7d&hl=fa&gl=IR&ceid=IR:fa",
                ],
                "categories": ["iran_gold", "coin"],
                "rule_bindings": [
                    "IR_MACRO_INFLATION_LIQ", "IR_RATES_CREDIT",
                    "IR_BUDGET_FISCAL", "IR_ECON_MANAGEMENT_CHANGES",
                ],
            },
            "Google News — Gold Mining": {
                "name": "Google News — بورس و صندوق طلا",
                "endpoints": [
                    "https://news.google.com/rss/search?q=%D8%B5%D9%86%D8%AF%D9%88%D9%82+%D8%B7%D9%84%D8%A7+%D8%A8%D9%88%D8%B1%D8%B3+%D8%B3%D8%B1%D9%85%D8%A7%DB%8C%D9%87+%DA%AF%D8%B0%D8%A7%D8%B1%DB%8C+when%3A7d&hl=fa&gl=IR&ceid=IR:fa",
                ],
                "categories": ["gold_funds"],
                "rule_bindings": [
                    "FUNDS_NAV_PREMIUM", "FUNDS_FLOW_VOLUME",
                    "FUNDS_CAPITAL_MARKET_NEWS", "FUNDS_CODAL_NOTICES",
                ],
            },
        }

        fixed = 0
        for old_name, updates in PERSIAN_FEEDS.items():
            result = await session.execute(
                select(Source).where(Source.name == old_name)
            )
            source = result.scalar_one_or_none()
            if source is None:
                continue
            source.name = updates["name"]
            source.endpoints = updates["endpoints"]
            source.categories = updates.get("categories", source.categories)
            source.rule_bindings = updates.get("rule_bindings", source.rule_bindings)
            fixed += 1

        # --- Disable broken sources ---
        for broken_name in ("تجارت\u200cنیوز", "بورس\u200cنیوز"):
            result = await session.execute(
                select(Source).where(Source.name == broken_name)
            )
            source = result.scalar_one_or_none()
            if source is not None:
                source.enabled = False
                fixed += 1

        # --- Reduce English source frequency ---
        for en_name in ("Kitco Gold News", "CNBC Finance", "Federal Reserve Press Releases"):
            result = await session.execute(
                select(Source).where(Source.name == en_name)
            )
            source = result.scalar_one_or_none()
            if source is not None:
                source.poll_interval_seconds = 600  # 10 min instead of 3 min
                fixed += 1

        # --- Delete all old alerts (one-time fresh start) ---
        await session.execute(text("DELETE FROM alerts"))
        logger.info("Cleared all old alerts for fresh Persian start.")

        # --- Mark migration as done ---
        await session.execute(
            text("INSERT INTO settings (key, value, updated_at) "
                 "VALUES (:k, '\"done\"', NOW())"),
            {"k": marker_key},
        )
        await session.commit()
        logger.info("Migrated %d source(s) to Persian feeds.", fixed)


async def _migrate_sources_v2() -> None:
    """Add when:7d filter to Google News, disable failing Iranian sources.

    Runs once (tracked via settings marker).
    """
    marker_key = "migration:sources_v2"
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT key FROM settings WHERE key = :k"),
            {"k": marker_key},
        )
        if result.scalar_one_or_none() is not None:
            return

        # --- Add when:7d to ALL Google News feeds ---
        GOOGLE_NEWS_UPDATES: dict[str, str] = {
            "Google News — طلا و قیمت جهانی":
                "https://news.google.com/rss/search?q=%D8%B7%D9%84%D8%A7+%D8%A7%D9%88%D9%86%D8%B3+%D9%82%DB%8C%D9%85%D8%AA+%D8%AC%D9%87%D8%A7%D9%86%DB%8C+when%3A7d&hl=fa&gl=IR&ceid=IR:fa",
            "Google News — تحریم و مذاکرات":
                "https://news.google.com/rss/search?q=%D8%AA%D8%AD%D8%B1%DB%8C%D9%85+%D8%A7%DB%8C%D8%B1%D8%A7%D9%86+%D9%85%D8%B0%D8%A7%DA%A9%D8%B1%D8%A7%D8%AA+%D8%A7%D8%B1%D8%B2+when%3A7d&hl=fa&gl=IR&ceid=IR:fa",
            "Google News — تورم و بانک مرکزی":
                "https://news.google.com/rss/search?q=%D8%AA%D9%88%D8%B1%D9%85+%D9%86%D9%82%D8%AF%DB%8C%D9%86%DA%AF%DB%8C+%D8%A8%D8%A7%D9%86%DA%A9+%D9%85%D8%B1%DA%A9%D8%B2%DB%8C+%D9%86%D8%B1%D8%AE+%D8%A8%D9%87%D8%B1%D9%87+when%3A7d&hl=fa&gl=IR&ceid=IR:fa",
            "Google News — بورس و صندوق طلا":
                "https://news.google.com/rss/search?q=%D8%B5%D9%86%D8%AF%D9%88%D9%82+%D8%B7%D9%84%D8%A7+%D8%A8%D9%88%D8%B1%D8%B3+%D8%B3%D8%B1%D9%85%D8%A7%DB%8C%D9%87+%DA%AF%D8%B0%D8%A7%D8%B1%DB%8C+when%3A7d&hl=fa&gl=IR&ceid=IR:fa",
            "Google News — طلا و ارز":
                "https://news.google.com/rss/search?q=%D8%B7%D9%84%D8%A7+%D8%B3%DA%A9%D9%87+%D8%AF%D9%84%D8%A7%D8%B1+%D8%A7%D8%B1%D8%B2+%D8%A8%D8%A7%D8%B2%D8%A7%D8%B1+when%3A7d&hl=fa&gl=IR&ceid=IR:fa",
        }

        fixed = 0
        for name, new_url in GOOGLE_NEWS_UPDATES.items():
            result = await session.execute(
                select(Source).where(Source.name == name)
            )
            source = result.scalar_one_or_none()
            if source is not None:
                source.endpoints = [new_url]
                fixed += 1

        # --- Disable consistently failing Iranian sources ---
        for name in (
            "خبرگزاری تسنیم - اقتصادی",   # DNS failure from Docker
            "خبرگزاری فارس - اقتصادی",     # Malformed RSS XML
            "خبرگزاری ایسنا - اقتصادی",    # Malformed RSS XML
        ):
            result = await session.execute(
                select(Source).where(Source.name == name)
            )
            source = result.scalar_one_or_none()
            if source is not None:
                source.enabled = False
                fixed += 1

        # --- Clear old alerts for fresh start ---
        await session.execute(text("DELETE FROM alerts"))

        # --- Mark as done ---
        await session.execute(
            text("INSERT INTO settings (key, value, updated_at) "
                 "VALUES (:k, '\"done\"', NOW())"),
            {"k": marker_key},
        )
        await session.commit()
        logger.info("Migration v2: updated %d source(s), cleared alerts.", fixed)


async def _migrate_sources_v3() -> None:
    """Switch Google News from Persian to English queries.

    The server is outside Iran, so Google silently overrides hl=fa to
    hl=en-US, returning 0 results for Persian keywords with when:7d.
    English queries work reliably and match the English keywords in our
    global rules.  Also disables Kitco (malformed XML).

    Runs once (tracked via settings marker).
    """
    marker_key = "migration:sources_v3"
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT key FROM settings WHERE key = :k"),
            {"k": marker_key},
        )
        if result.scalar_one_or_none() is not None:
            return

        # --- Replace Persian Google News feeds with English ones ---
        # Old Persian feed names → new English feeds
        OLD_TO_NEW: dict[str, dict] = {
            "Google News — طلا و قیمت جهانی": {
                "name": "Google News — Gold & Precious Metals",
                "endpoints": [
                    "https://news.google.com/rss/search?q=gold+price+OR+gold+market+OR+gold+futures+OR+%22gold+rally%22+when%3A7d&hl=en-US&gl=US&ceid=US:en",
                ],
                "categories": ["global_gold"],
                "rule_bindings": [
                    "GLOB_RATE_DECISION", "GLOB_DOLLAR_DXY",
                    "GLOB_US_MACRO_DATA", "GLOB_CB_GOLD_RESERVES",
                    "GLOB_MINING_SUPPLY", "GLOB_ASIA_PHYSICAL_DEMAND",
                ],
                "poll_interval_seconds": 180,
            },
            "Google News — تحریم و مذاکرات": {
                "name": "Google News — Fed & Interest Rates",
                "endpoints": [
                    "https://news.google.com/rss/search?q=%22interest+rate%22+OR+%22Fed+rate%22+OR+FOMC+OR+Powell+OR+%22rate+cut%22+OR+%22rate+hike%22+when%3A7d&hl=en-US&gl=US&ceid=US:en",
                ],
                "categories": ["global_gold"],
                "rule_bindings": [
                    "GLOB_RATE_DECISION", "GLOB_QE_QT", "GLOB_FED_COMM",
                    "GLOB_US_YIELDS",
                ],
                "poll_interval_seconds": 300,
            },
            "Google News — تورم و بانک مرکزی": {
                "name": "Google News — Iran Sanctions & Geopolitics",
                "endpoints": [
                    "https://news.google.com/rss/search?q=Iran+sanctions+OR+Iran+nuclear+OR+Iran+currency+OR+%22Iran+gold%22+when%3A7d&hl=en-US&gl=US&ceid=US:en",
                ],
                "categories": ["global_gold", "iran_gold"],
                "rule_bindings": [
                    "GLOB_GEOPOL_RISK", "IR_RESERVES_SANCTIONS",
                    "IR_FOREIGN_POLICY",
                ],
                "poll_interval_seconds": 300,
            },
            "Google News — بورس و صندوق طلا": {
                "name": "Google News — Inflation & Central Banks",
                "endpoints": [
                    "https://news.google.com/rss/search?q=inflation+OR+CPI+OR+%22central+bank%22+OR+%22treasury+yields%22+OR+DXY+when%3A7d&hl=en-US&gl=US&ceid=US:en",
                ],
                "categories": ["global_gold"],
                "rule_bindings": [
                    "GLOB_US_MACRO_DATA", "GLOB_DOLLAR_DXY",
                    "GLOB_US_YIELDS", "GLOB_CB_GOLD_RESERVES",
                ],
                "poll_interval_seconds": 300,
            },
            "Google News — طلا و ارز": {
                "name": "Google News — Geopolitics & Risk",
                "endpoints": [
                    "https://news.google.com/rss/search?q=war+OR+%22geopolitical+risk%22+OR+%22safe+haven%22+OR+%22stock+market+crash%22+OR+%22bank+crisis%22+when%3A7d&hl=en-US&gl=US&ceid=US:en",
                ],
                "categories": ["global_gold"],
                "rule_bindings": [
                    "GLOB_GEOPOL_RISK", "GLOB_EQUITY_RISK_OFF",
                    "GLOB_CRYPTO_SHOCKS",
                ],
                "poll_interval_seconds": 300,
            },
        }

        fixed = 0
        for old_name, updates in OLD_TO_NEW.items():
            result = await session.execute(
                select(Source).where(Source.name == old_name)
            )
            source = result.scalar_one_or_none()
            if source is not None:
                source.name = updates["name"]
                source.endpoints = updates["endpoints"]
                source.categories = updates.get("categories", source.categories)
                source.rule_bindings = updates.get("rule_bindings", source.rule_bindings)
                source.poll_interval_seconds = updates.get("poll_interval_seconds", source.poll_interval_seconds)
                fixed += 1

        # --- Disable Kitco (malformed XML) ---
        result = await session.execute(
            select(Source).where(Source.name == "Kitco Gold News")
        )
        kitco = result.scalar_one_or_none()
        if kitco is not None:
            kitco.enabled = False
            fixed += 1

        # --- Clear old alerts for fresh start ---
        await session.execute(text("DELETE FROM alerts"))
        await session.execute(text("DELETE FROM raw_items"))

        # --- Mark as done ---
        await session.execute(
            text("INSERT INTO settings (key, value, updated_at) "
                 "VALUES (:k, '\"done\"', NOW())"),
            {"k": marker_key},
        )
        await session.commit()
        logger.info("Migration v3: switched %d source(s) to English Google News, cleared data.", fixed)


async def _flush_dedup_keys() -> None:
    """One-time flush of Redis dedup keys so previously-failed items
    get re-processed with the now-working rule engine.

    Uses a marker key ``dedup:flushed:v2`` to avoid re-flushing on
    subsequent restarts.
    """
    marker = "dedup:flushed:v5"
    try:
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        if await r.exists(marker):
            await r.aclose()
            return

        # Flush raw_items:hash:* and alert:dedup:* keys
        count = 0
        async for key in r.scan_iter("raw_items:hash:*", count=500):
            await r.delete(key)
            count += 1
        async for key in r.scan_iter("alert:dedup:*", count=500):
            await r.delete(key)
            count += 1

        # Set marker to never flush again (30 days TTL)
        await r.setex(marker, 86400 * 30, "1")
        await r.aclose()

        if count:
            logger.info("Flushed %d Redis dedup keys (one-time reset).", count)
    except Exception:
        logger.warning("Redis dedup flush failed", exc_info=True)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup / shutdown lifecycle."""
    global _STARTUP_TIME  # noqa: PLW0603
    _STARTUP_TIME = time.time()

    logger.info("Starting Gold Monitor API ...")
    _run_migrations()
    await _seed_admin()
    await _seed_sources()
    await _migrate_sources_to_persian()
    await _migrate_sources_v2()
    await _migrate_sources_v3()
    await _flush_dedup_keys()
    await _snapshot_rules()
    logger.info("Startup complete.")

    yield  # application is running

    logger.info("Shutting down Gold Monitor API ...")


# ── Application factory ────────────────────────────────────────────────

def create_app() -> FastAPI:
    """Build and return the fully configured FastAPI instance."""

    app = FastAPI(
        title="Gold Monitor System API",
        description="Real-time gold-market intelligence & alerting back-end.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # -- CORS (permissive for development) ----------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Routers ------------------------------------------------------
    from api.routers.admin import router as admin_router
    from api.routers.alerts import router as alerts_router
    from api.routers.health import router as health_router
    from api.routers.prices import router as prices_router
    from api.routers.rules import router as rules_router
    from api.routers.sentiment import router as sentiment_router
    from api.routers.sources import router as sources_router

    app.include_router(alerts_router, prefix="/api/alerts")
    app.include_router(sources_router, prefix="/api/sources")
    app.include_router(admin_router, prefix="/api/admin")
    app.include_router(rules_router, prefix="/api/rules")
    app.include_router(prices_router, prefix="/api/prices")
    app.include_router(sentiment_router, prefix="/api/sentiment")
    app.include_router(health_router, prefix="/api/health")

    return app


app = create_app()


def get_startup_time() -> float:
    """Return the UNIX timestamp recorded at startup (used by health check)."""
    return _STARTUP_TIME
