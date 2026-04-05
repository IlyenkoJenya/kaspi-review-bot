# News Bot

Telegram-бот, который собирает новости из указанных Telegram-каналов, анализирует их с помощью OpenAI и каждый день в 21:00 отправляет дайджест TOP-10.

## Как это работает

```
Telegram-каналы  →  Telethon (userbot)  →  SQLite
                                               ↓
                                          OpenAI GPT
                                               ↓
                                    aiogram Bot → дайджест
```

1. **Telethon** читает указанные каналы от имени вашего аккаунта и сохраняет сырые сообщения в базу.
2. **OpenAI** кластеризует сообщения об одном событии, пишет заголовок + краткую сводку и ставит оценку важности (0–10).
3. **aiogram** отправляет итоговый дайджест в нужный чат по расписанию или по команде.

## Стек

| Компонент | Библиотека |
|---|---|
| Telegram Bot API | aiogram 3.x |
| Чтение каналов (userbot) | Telethon |
| База данных | SQLAlchemy async + aiosqlite (SQLite) |
| Анализ новостей | OpenAI API (gpt-4o-mini по умолчанию) |
| Расписание | APScheduler |

## Требования

- Python 3.11+
- Telegram Bot Token (`@BotFather`)
- Telegram API ID + Hash (https://my.telegram.org)
- OpenAI API Key

## Установка

```bash
git clone <repo>
cd news_bot

pip install -r requirements.txt

cp .env.example .env
# Заполните .env своими данными (см. раздел ниже)
```

## Настройка `.env`

```env
# Telegram Bot
BOT_TOKEN=           # токен от @BotFather
ADMIN_USER_ID=       # ваш Telegram user ID (числовой)

# Куда слать дайджест (по умолчанию — ADMIN_USER_ID)
# Для группы/супергруппы используйте отрицательный ID (-100xxxxxxxxxx)
TARGET_CHAT_ID=

# Telethon (userbot — ваш личный аккаунт)
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_PHONE=      # +7xxxxxxxxxx

# OpenAI
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini   # можно заменить на gpt-4o и т.д.

# Расписание
DIGEST_HOUR=21
DIGEST_MINUTE=0
TIMEZONE=Europe/Moscow

# Поведение
TOP_NEWS_COUNT=10
PARSE_HOURS_BACK=24
```

> **Как получить `TARGET_CHAT_ID` группы**: перешлите любое сообщение из группы боту `@userinfobot` — он покажет правильный ID.  
> Бот должен быть **добавлен в группу**, иначе получите ошибку `chat not found`.

## Запуск

```bash
python -m src.main
```

При первом запуске Telethon попросит ввести код подтверждения из Telegram.

## Команды бота

| Команда | Описание |
|---|---|
| `/start` | Приветствие и список команд |
| `/today` | TOP-10 новостей за сегодня |
| `/date YYYY-MM-DD` | TOP-10 новостей за указанную дату |
| `/parse [YYYY-MM-DD]` | Спарсить каналы и сразу проанализировать |
| `/add_channel @username` | Добавить канал в мониторинг |
| `/remove_channel @username` | Удалить канал |
| `/list_channels` | Список отслеживаемых каналов |

Все команды доступны только администратору (`ADMIN_USER_ID`).

## Структура проекта

```
src/
├── main.py                   # Точка входа: бот + планировщик + парсер
├── config.py                 # Настройки из .env
├── database/
│   ├── connection.py         # Async engine + фабрика сессий
│   ├── models.py             # ORM-модели
│   └── repository.py        # Все операции с БД
├── parsers/
│   └── telegram_parser.py   # Telethon: история + слушатель новых сообщений
├── bot/
│   ├── handlers.py           # Обработчики команд aiogram
│   └── keyboards.py         # Inline-клавиатуры
├── ai/
│   └── analyzer.py          # OpenAI: суммаризация + оценка + дедупликация
└── scheduler/
    └── tasks.py             # APScheduler: дайджест в 21:00, парсинг раз в час
```

## Схема базы данных

```
channels          — отслеживаемые каналы (username, title, telegram_id)
raw_messages      — сырые сообщения (дедупликация по channel_id + message_id)
processed_news    — обработанные новости (заголовок, сводка, оценка важности)
news_sources      — связь processed_news → raw_messages
```

## Расписание

- **Каждый час в :00** — фоновый парсинг всех каналов за текущий день
- **Ежедневно в 21:00** — полный цикл: парсинг → анализ → отправка дайджеста
