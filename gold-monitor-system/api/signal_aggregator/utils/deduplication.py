"""Deduplication utility for raw posts.

Provides a fast check to determine whether a post with a given
``source_id`` + ``external_id`` combination already exists in the
``raw_posts`` table, leveraging the unique constraint
``uq_raw_posts_source_external``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.signal_aggregator.models import RawPost


async def is_duplicate(
    session: AsyncSession,
    source_id: uuid.UUID,
    external_id: str,
) -> bool:
    """Return ``True`` if a ``RawPost`` with the given *source_id* and
    *external_id* already exists.

    Parameters
    ----------
    session:
        An active ``AsyncSession`` — the caller is responsible for
        transaction management.
    source_id:
        UUID of the ``SignalSource``.
    external_id:
        The platform-specific identifier (e.g. Telegram message ID,
        TradingView idea ID).

    Returns
    -------
    bool
    """
    result = await session.execute(
        select(RawPost.id)
        .where(
            RawPost.source_id == source_id,
            RawPost.external_id == external_id,
        )
        .limit(1),
    )
    return result.scalar_one_or_none() is not None
