from datetime import date, datetime
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models import Channel, NewsSource, ProcessedNews, RawMessage


# ---------------------------------------------------------------------------
# Channel operations
# ---------------------------------------------------------------------------


async def add_channel(session: AsyncSession, username: str, title: str | None = None, telegram_id: int | None = None) -> Channel:
    """Add a new channel. Returns existing one if already present (reactivates if inactive)."""
    username = username.lstrip("@").lower()
    result = await session.execute(select(Channel).where(Channel.username == username))
    channel = result.scalar_one_or_none()

    if channel:
        channel.is_active = True
        if title:
            channel.title = title
        if telegram_id:
            channel.telegram_id = telegram_id
    else:
        channel = Channel(username=username, title=title, telegram_id=telegram_id, is_active=True)
        session.add(channel)

    await session.commit()
    await session.refresh(channel)
    return channel


async def remove_channel(session: AsyncSession, username: str) -> bool:
    """Deactivate a channel. Returns True if found."""
    username = username.lstrip("@").lower()
    result = await session.execute(select(Channel).where(Channel.username == username))
    channel = result.scalar_one_or_none()
    if not channel:
        return False
    channel.is_active = False
    await session.commit()
    return True


async def get_active_channels(session: AsyncSession) -> list[Channel]:
    result = await session.execute(select(Channel).where(Channel.is_active == True))
    return list(result.scalars().all())


async def get_channel_by_username(session: AsyncSession, username: str) -> Optional[Channel]:
    username = username.lstrip("@").lower()
    result = await session.execute(select(Channel).where(Channel.username == username))
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Raw message operations
# ---------------------------------------------------------------------------


async def save_raw_message(
    session: AsyncSession,
    channel_id: int,
    message_id: int,
    text: str,
    date: datetime,
) -> tuple[RawMessage, bool]:
    """Save a raw message. Returns (message, created) — created=False if duplicate."""
    result = await session.execute(
        select(RawMessage).where(
            RawMessage.channel_id == channel_id,
            RawMessage.message_id == message_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing, False

    msg = RawMessage(
        channel_id=channel_id,
        message_id=message_id,
        text=text,
        date=date,
    )
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return msg, True


async def get_unprocessed_messages(session: AsyncSession, for_date: date) -> list[RawMessage]:
    """Get all unprocessed messages for a given date (UTC)."""
    start = datetime(for_date.year, for_date.month, for_date.day, 0, 0, 0)
    end = datetime(for_date.year, for_date.month, for_date.day, 23, 59, 59)
    result = await session.execute(
        select(RawMessage)
        .options(selectinload(RawMessage.channel))
        .where(
            RawMessage.is_processed == False,
            RawMessage.date >= start,
            RawMessage.date <= end,
        )
        .order_by(RawMessage.date)
    )
    return list(result.scalars().all())


async def get_all_messages_for_date(session: AsyncSession, for_date: date) -> list[RawMessage]:
    """Get all messages (processed or not) for a given date."""
    start = datetime(for_date.year, for_date.month, for_date.day, 0, 0, 0)
    end = datetime(for_date.year, for_date.month, for_date.day, 23, 59, 59)
    result = await session.execute(
        select(RawMessage)
        .options(selectinload(RawMessage.channel))
        .where(RawMessage.date >= start, RawMessage.date <= end)
        .order_by(RawMessage.date)
    )
    return list(result.scalars().all())


async def mark_messages_processed(session: AsyncSession, message_ids: list[int]) -> None:
    if not message_ids:
        return
    await session.execute(
        update(RawMessage).where(RawMessage.id.in_(message_ids)).values(is_processed=True)
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Processed news operations
# ---------------------------------------------------------------------------


async def save_processed_news(
    session: AsyncSession,
    news_date: date,
    title: str,
    summary: str,
    importance_score: float,
    source_count: int,
    raw_message_ids: list[int],
) -> ProcessedNews:
    news = ProcessedNews(
        news_date=news_date,
        title=title,
        summary=summary,
        importance_score=importance_score,
        source_count=source_count,
    )
    session.add(news)
    await session.flush()  # get news.id

    for raw_id in raw_message_ids:
        session.add(NewsSource(news_id=news.id, raw_message_id=raw_id))

    await session.commit()
    await session.refresh(news)
    return news


async def get_top_news_for_date(session: AsyncSession, for_date: date, limit: int = 10) -> list[ProcessedNews]:
    result = await session.execute(
        select(ProcessedNews)
        .where(ProcessedNews.news_date == for_date)
        .order_by(ProcessedNews.importance_score.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def delete_processed_news_for_date(session: AsyncSession, for_date: date) -> int:
    """Delete all processed news for a date (used before re-processing). Returns count deleted."""
    result = await session.execute(
        delete(ProcessedNews).where(ProcessedNews.news_date == for_date)
    )
    await session.commit()
    return result.rowcount
