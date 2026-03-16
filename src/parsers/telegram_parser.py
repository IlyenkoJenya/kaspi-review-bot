import asyncio
import logging
from datetime import datetime, timezone, date
from typing import Callable, Awaitable

from telethon import TelegramClient, events
from telethon.tl.types import Channel as TelegramChannel, Message

from src.config import config
from src.database.connection import get_session
from src.database import repository

logger = logging.getLogger(__name__)

# Global instance, set in main.py after initialization
_parser_instance: "TelegramParser | None" = None


class TelegramParser:
    """
    Userbot based on Telethon.
    - Parses historical messages for a given date range
    - Listens for new messages in real time
    """

    def __init__(self) -> None:
        self._client = TelegramClient(
            config.session_path,
            config.telegram_api_id,
            config.telegram_api_hash,
        )
        self._new_message_callback: Callable[[str, str, datetime], Awaitable[None]] | None = None

    async def start(self) -> None:
        await self._client.start(phone=config.telegram_phone)
        logger.info("Telethon client started")
        await self._register_listeners()

    async def stop(self) -> None:
        await self._client.disconnect()
        logger.info("Telethon client disconnected")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_channel_info(self, username: str) -> tuple[str, int] | None:
        """Return (title, telegram_id) for a channel, or None if not found."""
        try:
            entity = await self._client.get_entity(username)
            if isinstance(entity, TelegramChannel):
                return entity.title, entity.id
        except Exception as e:
            logger.warning("Could not fetch channel info for @%s: %s", username, e)
        return None

    async def parse_history(self, username: str, for_date: date) -> int:
        """
        Fetch all messages from `username` that were posted on `for_date` (UTC).
        Returns the number of new messages saved to DB.
        """
        session = await get_session()
        try:
            channel = await repository.get_channel_by_username(session, username)
            if not channel:
                logger.warning("Channel @%s not found in DB", username)
                return 0

            start_dt = datetime(for_date.year, for_date.month, for_date.day, 0, 0, 0, tzinfo=timezone.utc)
            end_dt = datetime(for_date.year, for_date.month, for_date.day, 23, 59, 59, tzinfo=timezone.utc)

            saved_count = 0
            async for message in self._client.iter_messages(
                username,
                reverse=True,
                offset_date=start_dt,
                limit=None,
            ):
                if not isinstance(message, Message):
                    continue
                msg_date = message.date.replace(tzinfo=timezone.utc) if message.date.tzinfo is None else message.date
                if msg_date > end_dt:
                    break
                if not message.text:
                    continue

                _, created = await repository.save_raw_message(
                    session,
                    channel_id=channel.id,
                    message_id=message.id,
                    text=message.text,
                    date=msg_date.replace(tzinfo=None),  # store as naive UTC
                )
                if created:
                    saved_count += 1

            logger.info("Parsed @%s for %s: %d new messages", username, for_date, saved_count)
            return saved_count
        finally:
            await session.close()

    async def parse_all_channels_for_date(self, for_date: date) -> dict[str, int]:
        """Parse all active channels for a specific date. Returns {username: count}."""
        session = await get_session()
        try:
            channels = await repository.get_active_channels(session)
        finally:
            await session.close()

        results: dict[str, int] = {}
        for channel in channels:
            try:
                count = await self.parse_history(channel.username, for_date)
                results[channel.username] = count
            except Exception as e:
                logger.error("Error parsing @%s: %s", channel.username, e)
                results[channel.username] = 0

        return results

    # ------------------------------------------------------------------
    # Real-time listener
    # ------------------------------------------------------------------

    async def _register_listeners(self) -> None:
        @self._client.on(events.NewMessage)
        async def handler(event: events.NewMessage.Event) -> None:
            if not event.message.text:
                return

            try:
                chat = await event.get_chat()
                if not isinstance(chat, TelegramChannel):
                    return

                username = getattr(chat, "username", None)
                if not username:
                    return

                session = await get_session()
                try:
                    channel = await repository.get_channel_by_username(session, username)
                    if not channel or not channel.is_active:
                        return

                    msg_date = event.message.date
                    if msg_date.tzinfo is not None:
                        msg_date = msg_date.replace(tzinfo=None)

                    _, created = await repository.save_raw_message(
                        session,
                        channel_id=channel.id,
                        message_id=event.message.id,
                        text=event.message.text,
                        date=msg_date,
                    )
                    if created:
                        logger.debug("New message saved from @%s (id=%d)", username, event.message.id)
                finally:
                    await session.close()

            except Exception as e:
                logger.error("Error handling new message: %s", e)

        logger.info("Real-time listener registered")

    async def run_until_disconnected(self) -> None:
        await self._client.run_until_disconnected()
