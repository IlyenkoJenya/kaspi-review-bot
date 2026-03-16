# News Bot — Claude Project

## Project Overview
Telegram bot that collects news from specified Telegram channels, analyzes them with OpenAI, and sends a daily TOP-10 digest at 21:00.

## Tech Stack
- **aiogram 3.x** — Telegram Bot API
- **Telethon** — reading Telegram channels (as userbot)
- **SQLAlchemy async + aiosqlite** — SQLite database
- **OpenAI API** — news analysis and summarization
- **APScheduler** — daily digest scheduling

## Project Structure
```
src/
├── main.py              # Entry point: starts bot + scheduler + parser listener
├── config.py            # Settings from .env
├── database/
│   ├── connection.py    # Async engine + session factory
│   ├── models.py        # SQLAlchemy ORM models
│   └── repository.py    # All DB operations
├── parsers/
│   └── telegram_parser.py  # Telethon client: parse history + listen new messages
├── bot/
│   ├── handlers.py      # All aiogram command handlers
│   └── keyboards.py     # Inline keyboards
├── ai/
│   └── analyzer.py      # OpenAI: summarize + score + deduplicate news
└── scheduler/
    └── tasks.py         # APScheduler tasks (daily digest at 21:00)
```

## Database Schema
- **channels** — tracked Telegram channels (username, title)
- **raw_messages** — raw messages from channels (dedup by channel_id + message_id)
- **processed_news** — analyzed news with importance score and sources list

## Key Commands
- `/start` — start bot
- `/today` — TOP-10 news for today
- `/date YYYY-MM-DD` — TOP-10 news for specific date
- `/add_channel @username` — add channel to monitoring
- `/remove_channel @username` — remove channel
- `/list_channels` — show monitored channels
- `/parse YYYY-MM-DD` — parse messages for specific date

## Environment Variables
See `.env.example` for all required variables.

## Running
```bash
pip install -r requirements.txt
cp .env .env
# Fill in .env with your credentials
python -m src.main
```

## Architecture Notes
- **Telethon** runs as a userbot (your personal account) to read channels
- **aiogram** runs as the bot account to handle commands
- Both run in the same async event loop via `asyncio.gather`
- APScheduler triggers digest generation at 21:00 daily
- Deduplication: raw_messages unique by (channel_id, message_id); news dedup via OpenAI semantic clustering
