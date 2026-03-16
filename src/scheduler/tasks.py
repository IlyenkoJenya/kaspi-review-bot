import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from src.config import config

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _daily_parse_and_digest() -> None:
    """
    Job running at 21:00:
    1. Parse all channels for today
    2. Analyze messages with OpenAI
    3. Send digest to admin
    """
    from aiogram import Bot
    from src.ai import analyzer
    from src.database import repository
    from src.database.connection import get_session
    from src.parsers.telegram_parser import _parser_instance

    today = date.today()
    logger.info("Starting daily digest for %s", today)

    bot = Bot(token=config.bot_token)

    try:
        # Step 1: parse all channels
        if _parser_instance:
            results = await _parser_instance.parse_all_channels_for_date(today)
            total_parsed = sum(results.values())
            logger.info("Parsed %d new messages for %s", total_parsed, today)
        else:
            logger.warning("Telethon parser not available, skipping parse step")

        # Step 2: fetch messages and analyze
        session = await get_session()
        try:
            await repository.delete_processed_news_for_date(session, today)
            messages = await repository.get_all_messages_for_date(session, today)
        finally:
            await session.close()

        if not messages:
            await bot.send_message(config.target_chat_id, "📭 Сообщений за сегодня не найдено.")
            return

        news_items = await analyzer.analyze_and_summarize(messages, today, config.top_news_count)

        if not news_items:
            await bot.send_message(config.target_chat_id, "😕 Не удалось проанализировать новости.")
            return

        # Step 3: save and send
        session = await get_session()
        try:
            for item in news_items:
                await repository.save_processed_news(
                    session,
                    news_date=today,
                    title=item.title,
                    summary=item.summary,
                    importance_score=item.importance_score,
                    source_count=item.source_count,
                    raw_message_ids=item.raw_message_ids,
                )
            all_ids = [mid for item in news_items for mid in item.raw_message_ids]
            await repository.mark_messages_processed(session, all_ids)
        finally:
            await session.close()

        text = analyzer.format_digest(news_items, today)
        limit = 4000
        while text:
            await bot.send_message(config.target_chat_id, text[:limit], parse_mode="HTML")
            text = text[limit:]

        logger.info("Daily digest sent to chat %s", config.target_chat_id)

    except Exception as e:
        logger.error("Error in daily digest job: %s", e, exc_info=True)
        try:
            await bot.send_message(config.admin_user_id, f"❌ Ошибка при формировании дайджеста: {e}")
        except Exception:
            pass
    finally:
        await bot.session.close()


async def _hourly_parse() -> None:
    """Job running every hour: parse all active channels to collect fresh messages."""
    from src.parsers.telegram_parser import _parser_instance

    if not _parser_instance:
        return

    today = date.today()
    try:
        results = await _parser_instance.parse_all_channels_for_date(today)
        total = sum(results.values())
        if total > 0:
            logger.info("Hourly parse: collected %d new messages", total)
    except Exception as e:
        logger.error("Hourly parse error: %s", e)


def setup_scheduler() -> AsyncIOScheduler:
    global _scheduler

    tz = pytz.timezone(config.timezone)
    _scheduler = AsyncIOScheduler(timezone=tz)

    # Daily digest at configured time
    _scheduler.add_job(
        _daily_parse_and_digest,
        trigger=CronTrigger(hour=config.digest_hour, minute=config.digest_minute, timezone=tz),
        id="daily_digest",
        replace_existing=True,
        name="Daily news digest",
    )

    # Hourly background parse
    _scheduler.add_job(
        _hourly_parse,
        trigger=CronTrigger(minute=0, timezone=tz),  # every hour at :00
        id="hourly_parse",
        replace_existing=True,
        name="Hourly channel parse",
    )

    return _scheduler


def start_scheduler() -> None:
    if _scheduler:
        _scheduler.start()
        logger.info(
            "Scheduler started. Daily digest at %02d:%02d %s",
            config.digest_hour,
            config.digest_minute,
            config.timezone,
        )


def stop_scheduler() -> None:
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
        logger.info("Scheduler stopped")
