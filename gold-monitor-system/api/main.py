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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from api.auth import get_password_hash
from api.config import settings
from api.database import AsyncSessionLocal, sync_engine
from api.models import AdminUser, Base, RulesSnapshot

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


# ── Lifespan ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup / shutdown lifecycle."""
    global _STARTUP_TIME  # noqa: PLW0603
    _STARTUP_TIME = time.time()

    logger.info("Starting Gold Monitor API ...")
    _run_migrations()
    await _seed_admin()
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
    from api.routers.rules import router as rules_router
    from api.routers.sources import router as sources_router

    app.include_router(alerts_router, prefix="/api/alerts")
    app.include_router(sources_router, prefix="/api/sources")
    app.include_router(admin_router, prefix="/api/admin")
    app.include_router(rules_router, prefix="/api/rules")
    app.include_router(health_router, prefix="/api/health")

    return app


app = create_app()


def get_startup_time() -> float:
    """Return the UNIX timestamp recorded at startup (used by health check)."""
    return _STARTUP_TIME
