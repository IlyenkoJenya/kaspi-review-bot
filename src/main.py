"""
News Bot — entry point.

Starts three concurrent components:
  1. aiogram Bot (handles Telegram commands)
  2. Telethon userbot (reads channels, listens for new messages)
  3. APScheduler (daily digest at 21:00, hourly parse)
"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import config
from src.database.connection import close_db, init_db
from src.bot.handlers import setup_router
from src.parsers import telegram_parser as parser_module
from src.parsers.telegram_parser import TelegramParser
from src.scheduler.tasks import setup_scheduler, start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Initializing database...")
    await init_db()

    # --- Telethon parser ---
    parser = TelegramParser()
    parser_module._parser_instance = parser  # make available to handlers/scheduler
    await parser.start()

    # --- aiogram bot ---
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    setup_router(dp)

    # --- Scheduler ---
    setup_scheduler()
    start_scheduler()

    logger.info("Bot started. Waiting for messages...")

    try:
        # Run aiogram polling and Telethon listener concurrently
        await asyncio.gather(
            dp.start_polling(bot, allowed_updates=["message", "callback_query"]),
            parser.run_until_disconnected(),
        )
    finally:
        logger.info("Shutting down...")
        stop_scheduler()
        await close_db()
        await bot.session.close()
        await parser.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
