"""Telegram channel listener for the Signal Aggregator.

Connects to Telegram via Telethon (user session) and listens to all
channels configured as ``type='telegram'`` + ``active=True`` in the
``signal_sources`` table.  Every new message is persisted as a
``RawPost`` for later parsing.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from telethon import TelegramClient, events

from api.database import AsyncSessionLocal
from api.signal_aggregator.config import (
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
    TELEGRAM_PHONE,
    TELEGRAM_SESSION_PATH,
)
from api.signal_aggregator.models import RawPost, SignalSource
from api.signal_aggregator.utils.deduplication import is_duplicate

logger = logging.getLogger("signal_aggregator.telegram")

# Reconnect back-off parameters
_INITIAL_BACKOFF_S = 5
_MAX_BACKOFF_S = 300


async def _get_active_telegram_sources() -> dict[int | str, SignalSource]:
    """Return a mapping of ``telegram_channel_id -> SignalSource`` for
    every active Telegram source."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SignalSource).where(
                SignalSource.type == "telegram",
                SignalSource.active.is_(True),
            )
        )
        sources = result.scalars().all()

    mapping: dict[int | str, SignalSource] = {}
    for src in sources:
        if src.telegram_channel_id:
            # Telegram channel IDs are typically integers, but store as
            # string in the DB — attempt int conversion for Telethon
            try:
                key = int(src.telegram_channel_id)
            except ValueError:
                key = src.telegram_channel_id
            mapping[key] = src
    return mapping


async def _save_message(
    source: SignalSource,
    message,  # telethon.tl.types.Message
) -> None:
    """Persist a single Telegram message as a ``RawPost``."""
    external_id = str(message.id)

    async with AsyncSessionLocal() as session:
        if await is_duplicate(session, source.id, external_id):
            logger.debug(
                "Duplicate message %s from source %s — skipping",
                external_id,
                source.name,
            )
            return

        # Gather media URLs (photo / document / video)
        media_urls: list[str] = []
        if message.photo:
            media_urls.append(f"telegram://photo/{message.photo.id}")
        if message.document:
            media_urls.append(f"telegram://document/{message.document.id}")

        raw_text = message.text or message.message or ""
        if not raw_text.strip():
            logger.debug(
                "Empty message %s from source %s — skipping",
                external_id,
                source.name,
            )
            return

        posted_at = (
            message.date.replace(tzinfo=timezone.utc)
            if message.date
            else datetime.now(timezone.utc)
        )

        post = RawPost(
            source_id=source.id,
            raw_text=raw_text,
            media_urls=media_urls if media_urls else None,
            external_id=external_id,
            posted_at=posted_at,
        )
        session.add(post)
        await session.commit()
        logger.info(
            "Saved message %s from %s (source=%s)",
            external_id,
            source.telegram_channel_name or source.telegram_channel_id,
            source.name,
        )


async def run_telegram_listener() -> None:
    """Main entry-point.  Connects to Telegram and listens indefinitely,
    reconnecting automatically on failure."""
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        logger.error(
            "TELEGRAM_API_ID and TELEGRAM_API_HASH must be set — aborting listener."
        )
        return

    backoff = _INITIAL_BACKOFF_S

    while True:
        try:
            logger.info("Starting Telegram listener session...")

            client = TelegramClient(
                TELEGRAM_SESSION_PATH,
                int(TELEGRAM_API_ID),
                TELEGRAM_API_HASH,
            )

            await client.start(phone=TELEGRAM_PHONE)
            logger.info("Telegram client connected successfully.")

            # Fetch active sources and resolve channel entities
            source_map = await _get_active_telegram_sources()
            if not source_map:
                logger.warning("No active Telegram sources configured — waiting 60 s.")
                await client.disconnect()
                await asyncio.sleep(60)
                continue

            channel_entities: dict[int, SignalSource] = {}
            for channel_id, source in source_map.items():
                try:
                    entity = await client.get_entity(channel_id)
                    channel_entities[entity.id] = source
                    logger.info(
                        "Resolved channel %s -> entity id %s",
                        source.telegram_channel_name or channel_id,
                        entity.id,
                    )
                except Exception:
                    logger.exception(
                        "Failed to resolve channel %s for source %s",
                        channel_id,
                        source.name,
                    )

            if not channel_entities:
                logger.error("No channels could be resolved — retrying in 60 s.")
                await client.disconnect()
                await asyncio.sleep(60)
                continue

            # Register event handler for new messages in tracked channels
            @client.on(events.NewMessage(chats=list(channel_entities.keys())))
            async def _on_new_message(event: events.NewMessage.Event) -> None:
                chat_id = event.chat_id
                source = channel_entities.get(chat_id)
                if source is None:
                    return
                try:
                    await _save_message(source, event.message)
                except Exception:
                    logger.exception(
                        "Error saving message %s from chat %s",
                        event.message.id,
                        chat_id,
                    )

            logger.info(
                "Listening to %d Telegram channel(s)...", len(channel_entities)
            )
            backoff = _INITIAL_BACKOFF_S  # reset on successful connect

            # Block until disconnected
            await client.run_until_disconnected()

        except Exception:
            logger.exception("Telegram listener crashed — retrying in %d s", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_S)
