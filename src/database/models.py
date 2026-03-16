from datetime import datetime, date

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Channel(Base):
    """Tracked Telegram channel."""

    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), unique=True, nullable=False)  # e.g. "durov" (without @)
    title = Column(String(512), nullable=True)                    # display name fetched from Telegram
    telegram_id = Column(BigInteger, nullable=True)               # internal Telegram channel ID
    is_active = Column(Boolean, default=True, nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    raw_messages = relationship("RawMessage", back_populates="channel", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Channel @{self.username}>"


class RawMessage(Base):
    """Raw message collected from a channel."""

    __tablename__ = "raw_messages"
    __table_args__ = (
        UniqueConstraint("channel_id", "message_id", name="uq_channel_message"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(Integer, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False)
    message_id = Column(BigInteger, nullable=False)   # Telegram message ID
    text = Column(Text, nullable=True)
    date = Column(DateTime, nullable=False)           # UTC datetime of the original message
    parsed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_processed = Column(Boolean, default=False, nullable=False)

    channel = relationship("Channel", back_populates="raw_messages")
    news_sources = relationship("NewsSource", back_populates="raw_message", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<RawMessage channel={self.channel_id} msg={self.message_id}>"


class ProcessedNews(Base):
    """Analyzed and summarized news item."""

    __tablename__ = "processed_news"

    id = Column(Integer, primary_key=True, autoincrement=True)
    news_date = Column(Date, nullable=False, index=True)  # date the news belongs to
    title = Column(String(512), nullable=False)           # short headline
    summary = Column(Text, nullable=False)                # 2-3 sentence summary
    importance_score = Column(Float, nullable=False, default=0.0)  # 0.0 – 10.0
    source_count = Column(Integer, default=1, nullable=False)       # how many channels covered it
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    sources = relationship("NewsSource", back_populates="news", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ProcessedNews [{self.news_date}] score={self.importance_score:.1f} '{self.title[:40]}'>"


class NewsSource(Base):
    """Join table: which raw messages contributed to a processed news item."""

    __tablename__ = "news_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    news_id = Column(Integer, ForeignKey("processed_news.id", ondelete="CASCADE"), nullable=False)
    raw_message_id = Column(Integer, ForeignKey("raw_messages.id", ondelete="CASCADE"), nullable=False)

    news = relationship("ProcessedNews", back_populates="sources")
    raw_message = relationship("RawMessage", back_populates="news_sources")
