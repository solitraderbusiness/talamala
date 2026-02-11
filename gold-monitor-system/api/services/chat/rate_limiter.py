"""
Rate limiter for the chat endpoint.

Uses Redis for distributed rate limiting:
- Per-IP: max N messages per hour
- Global: max N messages per hour across all users
"""

from __future__ import annotations

import logging
from typing import Any

import redis.asyncio as aioredis

from api.config import settings

logger = logging.getLogger(__name__)


class ChatRateLimiter:
    """Redis-backed rate limiter for the chat API."""

    IP_KEY_PREFIX = "chat:ratelimit:ip:"
    GLOBAL_KEY = "chat:ratelimit:global"
    WINDOW_SECONDS = 3600  # 1 hour

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
            )
        return self._redis

    async def check_rate_limit(self, ip_address: str) -> tuple[bool, str | None]:
        """Check if the request is within rate limits.

        Returns (allowed, error_message) tuple.
        """
        try:
            redis = await self._get_redis()

            # Check IP limit
            ip_key = f"{self.IP_KEY_PREFIX}{ip_address}"
            ip_count = await redis.get(ip_key)
            ip_limit = settings.CHAT_RATE_LIMIT_IP

            if ip_count and int(ip_count) >= ip_limit:
                return False, "تعداد سوالات شما به حد مجاز رسیده. لطفاً کمی صبر کنید."

            # Check global limit
            global_count = await redis.get(self.GLOBAL_KEY)
            global_limit = settings.CHAT_RATE_LIMIT_GLOBAL

            if global_count and int(global_count) >= global_limit:
                return False, "سرویس چت در حال حاضر پرترافیک است. لطفاً بعداً تلاش کنید."

            return True, None

        except Exception as e:
            logger.warning("Rate limiter error (allowing request): %s", e)
            # If Redis is down, allow the request
            return True, None

    async def increment(self, ip_address: str) -> None:
        """Increment rate limit counters after a successful request."""
        try:
            redis = await self._get_redis()

            # Increment IP counter
            ip_key = f"{self.IP_KEY_PREFIX}{ip_address}"
            pipe = redis.pipeline()
            pipe.incr(ip_key)
            pipe.expire(ip_key, self.WINDOW_SECONDS)

            # Increment global counter
            pipe.incr(self.GLOBAL_KEY)
            pipe.expire(self.GLOBAL_KEY, self.WINDOW_SECONDS)

            await pipe.execute()

        except Exception as e:
            logger.warning("Rate limiter increment error: %s", e)

    async def get_ip_remaining(self, ip_address: str) -> int:
        """Get remaining messages for an IP."""
        try:
            redis = await self._get_redis()
            ip_key = f"{self.IP_KEY_PREFIX}{ip_address}"
            count = await redis.get(ip_key)
            used = int(count) if count else 0
            return max(0, settings.CHAT_RATE_LIMIT_IP - used)
        except Exception:
            return settings.CHAT_RATE_LIMIT_IP

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None


# Singleton instance
rate_limiter = ChatRateLimiter()
