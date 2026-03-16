import json
import logging
from dataclasses import dataclass
from datetime import date

from openai import AsyncOpenAI

from src.config import config
from src.database.models import RawMessage

logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=config.openai_api_key)


@dataclass
class NewsItem:
    title: str
    summary: str
    importance_score: float       # 0.0 – 10.0
    source_count: int
    raw_message_ids: list[int]    # which raw messages were merged into this news


async def analyze_and_summarize(messages: list[RawMessage], news_date: date, top_n: int = 10) -> list[NewsItem]:
    """
    Takes a list of raw messages for a given date, sends them to OpenAI,
    returns a list of NewsItem sorted by importance_score descending.

    OpenAI does:
      1. Deduplicate / cluster messages about the same event
      2. Summarize each cluster into a title + 2-3 sentence summary
      3. Score importance 0–10
      4. Return top_n most important
    """
    if not messages:
        return []

    # Build the payload for GPT — keep it compact to save tokens
    messages_payload = []
    for msg in messages:
        channel_name = msg.channel.username if msg.channel else "unknown"
        messages_payload.append({
            "id": msg.id,
            "channel": f"@{channel_name}",
            "date": msg.date.strftime("%H:%M"),
            "text": msg.text[:800] if msg.text else "",  # truncate very long messages
        })

    prompt = f"""You are a professional news editor. Below are {len(messages_payload)} Telegram messages collected on {news_date}.

Your tasks:
1. Cluster messages that cover the **same event** into one news item.
2. For each cluster, write:
   - "title": short headline (max 100 chars, in Russian)
   - "summary": 2-3 sentences summarizing the key facts (in Russian)
   - "importance_score": float 0.0–10.0 (10 = global breaking news, 1 = minor local event)
   - "source_count": how many messages are in this cluster
   - "message_ids": list of message IDs from the input that belong to this cluster
3. Scoring criteria:
   - High score: affects many people, major political/economic/crisis event, covered by multiple sources
   - Low score: entertainment, minor local news, ads, reposts of old news
4. Return ONLY the top {top_n} most important news items.
5. Output a valid JSON array (no markdown, no explanation), each element matching the schema above.

Messages:
{json.dumps(messages_payload, ensure_ascii=False, indent=2)}

Return format (example):
[
  {{
    "title": "Заголовок новости",
    "summary": "Краткое описание события в 2-3 предложениях.",
    "importance_score": 8.5,
    "source_count": 3,
    "message_ids": [42, 57, 103]
  }}
]"""

    try:
        response = await client.chat.completions.create(
            model=config.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4000,
            response_format={"type": "json_object"},
        )

        raw_json = response.choices[0].message.content or "{}"

        # OpenAI with json_object may wrap in a key — handle both cases
        parsed = json.loads(raw_json)
        if isinstance(parsed, dict):
            # Find the list inside
            for v in parsed.values():
                if isinstance(v, list):
                    parsed = v
                    break
            else:
                parsed = []

        news_items: list[NewsItem] = []
        for item in parsed:
            try:
                news_items.append(
                    NewsItem(
                        title=str(item.get("title", "Без заголовка")),
                        summary=str(item.get("summary", "")),
                        importance_score=float(item.get("importance_score", 0.0)),
                        source_count=int(item.get("source_count", 1)),
                        raw_message_ids=[int(mid) for mid in item.get("message_ids", [])],
                    )
                )
            except (KeyError, ValueError, TypeError) as e:
                logger.warning("Skipping malformed news item: %s | error: %s", item, e)

        news_items.sort(key=lambda x: x.importance_score, reverse=True)
        return news_items[:top_n]

    except json.JSONDecodeError as e:
        logger.error("Failed to parse OpenAI JSON response: %s", e)
        return []
    except Exception as e:
        logger.error("OpenAI API error: %s", e)
        return []


def format_digest(news_items: list[NewsItem], news_date: date) -> str:
    """Format the TOP-N news list into a Telegram-ready message."""
    if not news_items:
        return f"📭 За {news_date.strftime('%d.%m.%Y')} новостей не найдено."

    lines = [f"📰 <b>ТОП-{len(news_items)} новостей за {news_date.strftime('%d.%m.%Y')}</b>\n"]

    for i, item in enumerate(news_items, start=1):
        score_bar = _score_to_emoji(item.importance_score)
        sources = f"📡 {item.source_count} источн." if item.source_count > 1 else ""
        lines.append(
            f"{i}. {score_bar} <b>{item.title}</b>\n"
            f"   {item.summary}"
            + (f"\n   <i>{sources}</i>" if sources else "")
        )

    return "\n\n".join(lines)


def _score_to_emoji(score: float) -> str:
    if score >= 9:
        return "🔴"
    if score >= 7:
        return "🟠"
    if score >= 5:
        return "🟡"
    return "🟢"
