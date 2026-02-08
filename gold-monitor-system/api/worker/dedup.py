"""
Deduplication checker backed by Redis (fast path) and PostgreSQL (durable).

* **Raw items** are deduplicated by ``content_hash``.  A Redis key
  ``raw_items:hash:<hash>`` is set with a 24-hour TTL.  The DB is also
  checked so that items survive beyond the cache window.

* **Alerts** are deduplicated by ``dedupe_key``.  A Redis key
  ``alert:dedup:<key>`` is set with a configurable TTL (default 6 hours,
  read from the ``settings`` table).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Redis key prefixes
_RAW_HASH_PREFIX = "raw_items:hash:"
_ALERT_DEDUP_PREFIX = "alert:dedup:"

# Defaults
_RAW_HASH_TTL_SECONDS = 86_400  # 24 hours
_DEFAULT_DEDUPE_WINDOW_HOURS = 6


class DedupChecker:
    """Stateless helper — holds references to Redis and a DB session."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        db_session: AsyncSession,
    ) -> None:
        self._redis = redis_client
        self._db = db_session

    # ------------------------------------------------------------------
    # Raw-item dedup (by content_hash)
    # ------------------------------------------------------------------

    async def is_raw_item_duplicate(self, content_hash: str) -> bool:
        """Return ``True`` if *content_hash* has been seen recently.

        Checks Redis first for speed, then falls back to the DB so that
        items older than the Redis TTL are still caught.
        """
        redis_key = f"{_RAW_HASH_PREFIX}{content_hash}"

        # 1. Fast check — Redis
        try:
            if await self._redis.exists(redis_key):
                return True
        except Exception:
            logger.warning(
                "Redis lookup failed for raw hash %s, falling back to DB",
                content_hash,
                exc_info=True,
            )

        # 2. Durable check — PostgreSQL
        try:
            result = await self._db.execute(
                text(
                    "SELECT 1 FROM raw_items "
                    "WHERE content_hash = :hash LIMIT 1"
                ),
                {"hash": content_hash},
            )
            if result.scalar_one_or_none() is not None:
                # Back-fill the Redis cache so the next check is fast.
                await self._safe_redis_setex(
                    redis_key, _RAW_HASH_TTL_SECONDS, "1"
                )
                return True
        except Exception:
            logger.warning(
                "DB lookup failed for raw hash %s",
                content_hash,
                exc_info=True,
            )

        return False

    async def mark_raw_item(self, content_hash: str) -> None:
        """Record *content_hash* in Redis with a 24-hour TTL."""
        redis_key = f"{_RAW_HASH_PREFIX}{content_hash}"
        await self._safe_redis_setex(redis_key, _RAW_HASH_TTL_SECONDS, "1")

    # ------------------------------------------------------------------
    # Alert dedup (by dedupe_key)
    # ------------------------------------------------------------------

    async def is_alert_duplicate(self, dedupe_key: str) -> bool:
        """Return ``True`` if an alert with this *dedupe_key* was already
        generated within the current deduplication window.
        """
        redis_key = f"{_ALERT_DEDUP_PREFIX}{dedupe_key}"

        # 1. Redis fast path
        try:
            if await self._redis.exists(redis_key):
                return True
        except Exception:
            logger.warning(
                "Redis lookup failed for alert dedup key %s, falling back to DB",
                dedupe_key,
                exc_info=True,
            )

        # 2. DB fallback — look for an alert created within the window
        window_hours = await self.get_dedupe_window()
        try:
            result = await self._db.execute(
                text(
                    "SELECT 1 FROM alerts "
                    "WHERE dedupe_key = :key "
                    "  AND created_at >= NOW() - MAKE_INTERVAL(hours => :hours) "
                    "LIMIT 1"
                ),
                {"key": dedupe_key, "hours": window_hours},
            )
            if result.scalar_one_or_none() is not None:
                # Back-fill Redis
                ttl = window_hours * 3600
                await self._safe_redis_setex(redis_key, ttl, "1")
                return True
        except Exception:
            logger.warning(
                "DB lookup failed for alert dedup key %s",
                dedupe_key,
                exc_info=True,
            )

        return False

    async def mark_alert(
        self,
        dedupe_key: str,
        window_hours: int | None = None,
    ) -> None:
        """Mark *dedupe_key* as seen for *window_hours* (default from settings)."""
        if window_hours is None:
            window_hours = await self.get_dedupe_window()
        ttl = window_hours * 3600
        redis_key = f"{_ALERT_DEDUP_PREFIX}{dedupe_key}"
        await self._safe_redis_setex(redis_key, ttl, "1")

    # ------------------------------------------------------------------
    # Settings helper
    # ------------------------------------------------------------------

    async def get_dedupe_window(self) -> int:
        """Read ``dedupe_window_hours`` from the ``settings`` table.

        Falls back to ``_DEFAULT_DEDUPE_WINDOW_HOURS`` (6) if the key is
        missing or the table does not exist.
        """
        try:
            result = await self._db.execute(
                text(
                    "SELECT value FROM settings "
                    "WHERE key = 'dedupe_window_hours' LIMIT 1"
                )
            )
            row = result.scalar_one_or_none()
            if row is not None:
                return int(row)
        except Exception:
            logger.debug(
                "Could not read dedupe_window_hours from settings table, "
                "using default %d",
                _DEFAULT_DEDUPE_WINDOW_HOURS,
                exc_info=True,
            )
        return _DEFAULT_DEDUPE_WINDOW_HOURS

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _safe_redis_setex(
        self, key: str, ttl_seconds: int, value: str
    ) -> None:
        """Set a Redis key with TTL, swallowing errors so the caller is
        not affected by transient Redis issues.
        """
        try:
            await self._redis.setex(key, ttl_seconds, value)
        except Exception:
            logger.warning(
                "Failed to set Redis key %s (TTL=%ds)",
                key,
                ttl_seconds,
                exc_info=True,
            )
