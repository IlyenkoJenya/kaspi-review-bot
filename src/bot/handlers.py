import logging
from datetime import date

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.ai import analyzer
from src.bot.keyboards import channels_list_kb, confirm_remove_channel_kb
from src.config import config
from src.database import repository
from src.database.connection import get_session

logger = logging.getLogger(__name__)
router = Router()


# ---------------------------------------------------------------------------
# Admin filter — proper aiogram 3.x way
# ---------------------------------------------------------------------------

class AdminFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id == config.admin_user_id


# ---------------------------------------------------------------------------
# FSM states
# ---------------------------------------------------------------------------

class AddChannelState(StatesGroup):
    waiting_for_username = State()


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------

@router.message(Command("start"), AdminFilter())
async def cmd_start(message: Message) -> None:
    text = (
        "👋 <b>News Bot запущен!</b>\n\n"
        "Доступные команды:\n"
        "/today — ТОП новостей за сегодня\n"
        "/date YYYY-MM-DD — новости за конкретную дату\n"
        "/add_channel — добавить канал для мониторинга\n"
        "/remove_channel — удалить канал\n"
        "/list_channels — список отслеживаемых каналов\n"
        "/parse YYYY-MM-DD — спарсить сообщения за дату\n"
    )
    await message.answer(text, parse_mode="HTML")


# ---------------------------------------------------------------------------
# /today
# ---------------------------------------------------------------------------

@router.message(Command("today"), AdminFilter())
async def cmd_today(message: Message) -> None:
    await _send_news_for_date(message, date.today())


# ---------------------------------------------------------------------------
# /date YYYY-MM-DD
# ---------------------------------------------------------------------------

@router.message(Command("date"), AdminFilter())
async def cmd_date(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❗ Укажите дату: /date YYYY-MM-DD")
        return

    try:
        target_date = date.fromisoformat(parts[1].strip())
    except ValueError:
        await message.answer("❗ Неверный формат даты. Используйте YYYY-MM-DD")
        return

    await _send_news_for_date(message, target_date)


async def _send_news_for_date(message: Message, target_date: date) -> None:
    session = await get_session()
    try:
        news_items_db = await repository.get_top_news_for_date(session, target_date, config.top_news_count)
    finally:
        await session.close()

    if not news_items_db:
        await message.answer(
            f"📭 За {target_date.strftime('%d.%m.%Y')} нет обработанных новостей.\n"
            f"Используйте /parse {target_date} чтобы спарсить сообщения."
        )
        return

    from src.ai.analyzer import NewsItem
    items = [
        NewsItem(
            title=n.title,
            summary=n.summary,
            importance_score=n.importance_score,
            source_count=n.source_count,
            raw_message_ids=[],
        )
        for n in news_items_db
    ]

    text = analyzer.format_digest(items, target_date)
    for chunk in _split_message(text):
        await message.answer(chunk, parse_mode="HTML")


# ---------------------------------------------------------------------------
# /list_channels
# ---------------------------------------------------------------------------

@router.message(Command("list_channels"), AdminFilter())
async def cmd_list_channels(message: Message) -> None:
    session = await get_session()
    try:
        channels = await repository.get_active_channels(session)
    finally:
        await session.close()

    if not channels:
        await message.answer("📋 Список отслеживаемых каналов пуст.")
        return

    lines = ["📋 <b>Отслеживаемые каналы:</b>\n"]
    for ch in channels:
        title = f" — {ch.title}" if ch.title else ""
        lines.append(f"• @{ch.username}{title}")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ---------------------------------------------------------------------------
# /add_channel (FSM)
# ---------------------------------------------------------------------------

@router.message(Command("add_channel"), AdminFilter())
async def cmd_add_channel(message: Message, state: FSMContext) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        await _do_add_channel(message, parts[1].strip(), state)
    else:
        await message.answer("✏️ Введите username канала (например: @durov или durov):")
        await state.set_state(AddChannelState.waiting_for_username)


@router.message(AddChannelState.waiting_for_username)
async def fsm_add_channel_username(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _do_add_channel(message, message.text.strip(), state)


async def _do_add_channel(message: Message, username: str, state: FSMContext) -> None:
    username = username.lstrip("@").lower()
    if not username:
        await message.answer("❗ Username не может быть пустым.")
        return

    await message.answer(f"⏳ Проверяю канал @{username}...")

    from src.parsers.telegram_parser import _parser_instance
    title = None
    telegram_id = None

    if _parser_instance:
        info = await _parser_instance.fetch_channel_info(username)
        if info:
            title, telegram_id = info
        else:
            await message.answer(
                f"⚠️ Не удалось получить информацию о @{username}. "
                "Убедитесь что канал существует и доступен вашему аккаунту.\n"
                "Канал будет добавлен, но парсинг может не работать."
            )

    session = await get_session()
    try:
        channel = await repository.add_channel(session, username, title=title, telegram_id=telegram_id)
    finally:
        await session.close()

    display = f"@{channel.username}" + (f" ({channel.title})" if channel.title else "")
    await message.answer(f"✅ Канал {display} добавлен!")


# ---------------------------------------------------------------------------
# /remove_channel
# ---------------------------------------------------------------------------

@router.message(Command("remove_channel"), AdminFilter())
async def cmd_remove_channel(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        username = parts[1].strip().lstrip("@").lower()
        await message.answer(
            f"Удалить канал @{username}?",
            reply_markup=confirm_remove_channel_kb(username),
        )
        return

    session = await get_session()
    try:
        channels = await repository.get_active_channels(session)
    finally:
        await session.close()

    if not channels:
        await message.answer("📋 Нет отслеживаемых каналов.")
        return

    await message.answer(
        "Выберите канал для удаления:",
        reply_markup=channels_list_kb([ch.username for ch in channels]),
    )


@router.callback_query(F.data.startswith("remove_select:"))
async def cb_remove_select(callback: CallbackQuery) -> None:
    if callback.from_user.id != config.admin_user_id:
        await callback.answer()
        return
    username = callback.data.split(":", 1)[1]
    await callback.message.edit_text(
        f"Удалить канал @{username}?",
        reply_markup=confirm_remove_channel_kb(username),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("remove_confirm:"))
async def cb_remove_confirm(callback: CallbackQuery) -> None:
    if callback.from_user.id != config.admin_user_id:
        await callback.answer()
        return
    username = callback.data.split(":", 1)[1]
    session = await get_session()
    try:
        removed = await repository.remove_channel(session, username)
    finally:
        await session.close()

    if removed:
        await callback.message.edit_text(f"✅ Канал @{username} удалён.")
    else:
        await callback.message.edit_text(f"❗ Канал @{username} не найден.")
    await callback.answer()


@router.callback_query(F.data == "remove_cancel")
async def cb_remove_cancel(callback: CallbackQuery) -> None:
    await callback.message.edit_text("❌ Отменено.")
    await callback.answer()


# ---------------------------------------------------------------------------
# /parse YYYY-MM-DD
# ---------------------------------------------------------------------------

@router.message(Command("parse"), AdminFilter())
async def cmd_parse(message: Message) -> None:
    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        target_date = date.today()
    else:
        try:
            target_date = date.fromisoformat(parts[1].strip())
        except ValueError:
            await message.answer("❗ Неверный формат даты. Используйте YYYY-MM-DD")
            return

    await message.answer(f"⏳ Парсю сообщения за {target_date.strftime('%d.%m.%Y')}...")

    from src.parsers.telegram_parser import _parser_instance
    if not _parser_instance:
        await message.answer("❗ Telethon клиент не инициализирован.")
        return

    results = await _parser_instance.parse_all_channels_for_date(target_date)

    if not results:
        await message.answer("❗ Нет активных каналов для парсинга.")
        return

    total = sum(results.values())
    lines = [f"✅ <b>Парсинг за {target_date.strftime('%d.%m.%Y')} завершён:</b>\n"]
    for username, count in results.items():
        lines.append(f"• @{username}: {count} новых сообщений")
    lines.append(f"\n📊 Всего: {total} сообщений")

    await message.answer("\n".join(lines), parse_mode="HTML")

    if total > 0:
        await message.answer("🤖 Анализирую новости...")
        await _run_analysis(message, target_date)


async def _run_analysis(message: Message, target_date: date) -> None:
    session = await get_session()
    try:
        deleted = await repository.delete_processed_news_for_date(session, target_date)
        if deleted:
            logger.info("Deleted %d old news items for %s", deleted, target_date)
        messages = await repository.get_all_messages_for_date(session, target_date)
    finally:
        await session.close()

    if not messages:
        await message.answer("📭 Нет сообщений для анализа.")
        return

    news_items = await analyzer.analyze_and_summarize(messages, target_date, config.top_news_count)

    if not news_items:
        await message.answer("😕 Не удалось проанализировать новости.")
        return

    session = await get_session()
    try:
        for item in news_items:
            await repository.save_processed_news(
                session,
                news_date=target_date,
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

    text = analyzer.format_digest(news_items, target_date)
    for chunk in _split_message(text):
        await message.answer(chunk, parse_mode="HTML")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_message(text: str, limit: int = 4000) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:limit])
        text = text[limit:]
    return chunks


def setup_router(dp: Dispatcher) -> None:
    dp.include_router(router)
