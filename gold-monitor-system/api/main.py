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
            # ── Global Gold (English RSS) ──────────────────────────
            Source(
                name="Kitco Gold News",
                type="rss",
                base_url="https://www.kitco.com",
                endpoints=["https://www.kitco.com/news/rss"],
                enabled=True,
                poll_interval_seconds=180,
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
                poll_interval_seconds=300,
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
                poll_interval_seconds=180,
                categories=["global_gold"],
                rule_bindings=[
                    "GLOB_US_MACRO_DATA", "GLOB_EQUITY_RISK_OFF",
                    "GLOB_FED_COMM", "GLOB_GEOPOL_RISK",
                ],
                reliability_score=0.8,
                notes="CNBC finance news — macro data, Fed, geopolitics",
            ),
            Source(
                name="Google News — Gold Market",
                type="rss",
                base_url="https://news.google.com",
                endpoints=[
                    "https://news.google.com/rss/search?q=gold+price+market&hl=en-US&gl=US&ceid=US:en",
                ],
                enabled=True,
                poll_interval_seconds=180,
                categories=["global_gold"],
                rule_bindings=[
                    "GLOB_US_MACRO_DATA", "GLOB_EQUITY_RISK_OFF",
                    "GLOB_US_YIELDS", "GLOB_DOLLAR_DXY",
                ],
                reliability_score=0.8,
                notes="Google News — aggregated gold market news",
            ),
            Source(
                name="Google News — Crypto & Gold",
                type="rss",
                base_url="https://news.google.com",
                endpoints=[
                    "https://news.google.com/rss/search?q=bitcoin+gold+safe+haven&hl=en-US&gl=US&ceid=US:en",
                ],
                enabled=True,
                poll_interval_seconds=300,
                categories=["global_gold"],
                rule_bindings=["GLOB_CRYPTO_SHOCKS"],
                reliability_score=0.75,
                notes="Google News — crypto and gold safe-haven flow analysis",
            ),
            Source(
                name="Google News — Gold Mining",
                type="rss",
                base_url="https://news.google.com",
                endpoints=[
                    "https://news.google.com/rss/search?q=gold+mining+supply&hl=en-US&gl=US&ceid=US:en",
                ],
                enabled=True,
                poll_interval_seconds=600,
                categories=["global_gold"],
                rule_bindings=["GLOB_MINING_SUPPLY"],
                reliability_score=0.8,
                notes="Google News — gold mining production, supply, costs",
            ),
            Source(
                name="Google News — Commodities",
                type="rss",
                base_url="https://news.google.com",
                endpoints=[
                    "https://news.google.com/rss/search?q=gold+commodities+dollar&hl=en-US&gl=US&ceid=US:en",
                ],
                enabled=True,
                poll_interval_seconds=180,
                categories=["global_gold"],
                rule_bindings=[
                    "GLOB_RATE_DECISION", "GLOB_DOLLAR_DXY",
                    "GLOB_US_MACRO_DATA", "GLOB_GEOPOL_RISK",
                    "GLOB_CB_GOLD_RESERVES",
                ],
                reliability_score=0.75,
                notes="Google News — commodities, gold, and dollar news",
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
                enabled=True,
                poll_interval_seconds=180,
                categories=["iran_gold", "coin"],
                rule_bindings=[
                    "IR_FX_USD", "IR_GOV_FX_POLICY", "IR_RESERVES_SANCTIONS",
                    "IR_FOREIGN_POLICY", "IR_INTERNAL_POL_SOCIAL",
                ],
                reliability_score=0.85,
                notes="تسنیم — سیاسی/اقتصادی، تحریم‌ها و مذاکرات",
            ),
            Source(
                name="خبرگزاری فارس - اقتصادی",
                type="rss",
                base_url="https://www.farsnews.ir",
                endpoints=["/rss"],
                enabled=True,
                poll_interval_seconds=180,
                categories=["iran_gold", "coin"],
                rule_bindings=[
                    "IR_FX_USD", "IR_MACRO_INFLATION_LIQ",
                    "IR_BUDGET_FISCAL", "IR_FOREIGN_POLICY",
                ],
                reliability_score=0.8,
                notes="فارس — اخبار اقتصادی، بودجه، تورم",
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
                enabled=True,
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
                enabled=True,
                poll_interval_seconds=300,
                categories=["iran_gold", "coin"],
                rule_bindings=[
                    "IR_FX_USD", "COIN_PREMIUM_BUBBLE",
                    "COIN_CB_AUCTIONS", "IR_PHYSICAL_SUPPLY_DEMAND",
                    "COIN_MINT_SUPPLY",
                ],
                reliability_score=0.7,
                notes="تجارت‌نیوز — قیمت طلا و سکه، حباب، حراج",
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
                enabled=True,
                poll_interval_seconds=300,
                categories=["gold_funds"],
                rule_bindings=[
                    "FUNDS_NAV_PREMIUM", "FUNDS_FLOW_VOLUME",
                    "FUNDS_CAPITAL_MARKET_NEWS", "FUNDS_CODAL_NOTICES",
                ],
                reliability_score=0.75,
                notes="بورس‌نیوز — صندوق‌های طلا، NAV، کدال، بازار سرمایه",
            ),
            # ── Google News Persian (guaranteed accessible) ──────────
            Source(
                name="Google News — طلا و ارز",
                type="rss",
                base_url="https://news.google.com",
                endpoints=[
                    "https://news.google.com/rss/search?q=%D8%B7%D9%84%D8%A7+%D8%B3%DA%A9%D9%87+%D8%AF%D9%84%D8%A7%D8%B1&hl=fa&gl=IR&ceid=IR:fa",
                ],
                enabled=True,
                poll_interval_seconds=180,
                categories=["iran_gold", "coin", "gold_funds"],
                rule_bindings=[
                    "IR_FX_USD", "IR_GOV_FX_POLICY",
                    "IR_MACRO_INFLATION_LIQ", "COIN_PREMIUM_BUBBLE",
                    "COIN_SENTIMENT_SOCIAL", "COIN_SEASONAL_DEMAND",
                ],
                reliability_score=0.7,
                notes="Google News — اخبار فارسی طلا، سکه، دلار",
            ),
        ]

        for source in default_sources:
            session.add(source)

        await session.commit()
        logger.info("Seeded %d default news sources.", len(default_sources))


# ── Lifespan ────────────────────────────────────────────────────────────


async def _fix_source_urls() -> None:
    """Fix known-broken source URLs for existing deployments."""
    URL_FIXES: dict[str, dict] = {
        "Kitco Gold News": {
            "endpoints": ["https://www.kitco.com/news/rss"],
        },
        "MarketWatch Top Stories": {
            "name": "Google News — Gold Market",
            "base_url": "https://news.google.com",
            "endpoints": [
                "https://news.google.com/rss/search?q=gold+price+market&hl=en-US&gl=US&ceid=US:en",
            ],
        },
        "CoinDesk": {
            "name": "Google News — Crypto & Gold",
            "base_url": "https://news.google.com",
            "endpoints": [
                "https://news.google.com/rss/search?q=bitcoin+gold+safe+haven&hl=en-US&gl=US&ceid=US:en",
            ],
        },
        "Mining.com Gold": {
            "name": "Google News — Gold Mining",
            "base_url": "https://news.google.com",
            "endpoints": [
                "https://news.google.com/rss/search?q=gold+mining+supply&hl=en-US&gl=US&ceid=US:en",
            ],
        },
        "Investing.com Commodities": {
            "name": "Google News — Commodities",
            "base_url": "https://news.google.com",
            "endpoints": [
                "https://news.google.com/rss/search?q=gold+commodities+dollar&hl=en-US&gl=US&ceid=US:en",
            ],
        },
    }
    async with AsyncSessionLocal() as session:
        fixed = 0
        for old_name, fix in URL_FIXES.items():
            result = await session.execute(
                select(Source).where(Source.name == old_name)
            )
            source = result.scalar_one_or_none()
            if source is None:
                continue
            if "name" in fix:
                source.name = fix["name"]
            if "base_url" in fix:
                source.base_url = fix["base_url"]
            if "endpoints" in fix:
                source.endpoints = fix["endpoints"]
            fixed += 1
        if fixed:
            await session.commit()
            logger.info("Fixed URLs for %d source(s).", fixed)


async def _flush_dedup_keys() -> None:
    """One-time flush of Redis dedup keys so previously-failed items
    get re-processed with the now-working rule engine.

    Uses a marker key ``dedup:flushed:v2`` to avoid re-flushing on
    subsequent restarts.
    """
    marker = "dedup:flushed:v2"
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
    await _fix_source_urls()
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
    from api.routers.sources import router as sources_router

    app.include_router(alerts_router, prefix="/api/alerts")
    app.include_router(sources_router, prefix="/api/sources")
    app.include_router(admin_router, prefix="/api/admin")
    app.include_router(rules_router, prefix="/api/rules")
    app.include_router(prices_router, prefix="/api/prices")
    app.include_router(health_router, prefix="/api/health")

    return app


app = create_app()


def get_startup_time() -> float:
    """Return the UNIX timestamp recorded at startup (used by health check)."""
    return _STARTUP_TIME
