"""
Health router -- system health check covering DB, Redis, and rule engine.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings as app_settings
from api.database import get_db
from api.rule_engine.load_rules import get_rules, load_rules

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("")
async def health_check(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """System health check.

    Checks:
    * **db** -- run ``SELECT 1`` against the database.
    * **redis** -- ping the Redis instance.
    * **rules_loaded** -- number of rules parsed from YAML.
    * **last_worker_run** -- timestamp of the most recent fetch-log entry.

    Returns ``status: "ok"`` when both DB and Redis are reachable, otherwise
    ``status: "degraded"``.
    """

    db_ok = await _check_db(db)
    redis_ok = await _check_redis()
    last_worker_run = await _last_worker_run(db) if db_ok else None
    rules_loaded = _count_rules()

    all_ok = db_ok and redis_ok
    return {
        "status": "ok" if all_ok else "degraded",
        "db": db_ok,
        "redis": redis_ok,
        "last_worker_run": last_worker_run,
        "rules_loaded": rules_loaded,
    }


# -- Internal checks -------------------------------------------------------


async def _check_db(db: AsyncSession) -> bool:
    """Return True if the database is reachable."""
    try:
        await db.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.warning("Health check: database unreachable", exc_info=True)
        return False


async def _check_redis() -> bool:
    """Return True if Redis responds to PING."""
    try:
        import redis.asyncio as aioredis  # type: ignore[import-untyped]

        client = aioredis.from_url(app_settings.REDIS_URL, decode_responses=True)
        try:
            pong = await client.ping()
            return bool(pong)
        finally:
            await client.aclose()
    except Exception:
        logger.warning("Health check: Redis unreachable", exc_info=True)
        return False


async def _last_worker_run(db: AsyncSession) -> str | None:
    """Return the ISO-formatted timestamp of the most recent fetch log."""
    try:
        from api.models import FetchLog
        from sqlalchemy import desc, select

        stmt = select(FetchLog.started_at).order_by(desc(FetchLog.started_at)).limit(1)
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            return row.isoformat()
        return None
    except Exception:
        logger.warning("Health check: could not query last worker run", exc_info=True)
        return None


def _count_rules() -> int:
    """Return the number of rules currently loaded from YAML."""
    try:
        yaml_data = load_rules(app_settings.YAML_PATH)
        rules = get_rules(yaml_data)
        return len(rules)
    except Exception:
        logger.warning("Health check: could not load rules", exc_info=True)
        return 0
