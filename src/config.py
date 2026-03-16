from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
import os

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Required environment variable '{key}' is not set")
    return value


@dataclass
class Config:
    # Telegram Bot
    bot_token: str = field(default_factory=lambda: _require("BOT_TOKEN"))
    admin_user_id: int = field(default_factory=lambda: int(_require("ADMIN_USER_ID")))
    # Chat/group where the daily digest is published (defaults to admin_user_id if not set)
    target_chat_id: int = field(
        default_factory=lambda: int(os.getenv("TARGET_CHAT_ID") or _require("ADMIN_USER_ID"))
    )

    # Telethon (userbot)
    telegram_api_id: int = field(default_factory=lambda: int(_require("TELEGRAM_API_ID")))
    telegram_api_hash: str = field(default_factory=lambda: _require("TELEGRAM_API_HASH"))
    telegram_phone: str = field(default_factory=lambda: _require("TELEGRAM_PHONE"))

    # OpenAI
    openai_api_key: str = field(default_factory=lambda: _require("OPENAI_API_KEY"))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    # Database
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./news_bot.db")
    )

    # Scheduler
    digest_hour: int = field(default_factory=lambda: int(os.getenv("DIGEST_HOUR", "21")))
    digest_minute: int = field(default_factory=lambda: int(os.getenv("DIGEST_MINUTE", "0")))
    timezone: str = field(default_factory=lambda: os.getenv("TIMEZONE", "Europe/Moscow"))

    # Behavior
    top_news_count: int = field(default_factory=lambda: int(os.getenv("TOP_NEWS_COUNT", "10")))
    parse_hours_back: int = field(default_factory=lambda: int(os.getenv("PARSE_HOURS_BACK", "24")))

    # Telethon session file path
    session_path: str = field(
        default_factory=lambda: os.getenv("SESSION_PATH", str(Path(__file__).parent.parent / "telethon_session"))
    )


config = Config()
