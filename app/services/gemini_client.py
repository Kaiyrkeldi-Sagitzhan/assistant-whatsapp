import json
import logging
from typing import Any, cast

import httpx

from app.core.config import get_settings
from app.core.time import now_utc

logger = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.gemini_api_key
        self.model = settings.gemini_model
        self.url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )

    async def extract_task(self, text: str, timezone: str) -> dict[str, Any]:
        current_date = now_utc().strftime("%Y-%m-%d")
        prompt = f"""
You are an AI assistant for task management in Kazakhstan. Parse the user's message and return structured JSON data.

Current date: {current_date}
User timezone: Asia/Almaty (UTC+5/6)

CRITICAL INTENT CLASSIFICATION:
- create_task: ONLY messages that clearly contain tasks, todos, reminders, or work items that need to be done
- create_event: ONLY calendar events, meetings, appointments with specific time mentioned
- unknown: ALL other messages including greetings, questions, status requests, empty messages, unclear text

EXAMPLES OF "unknown" intent (MUST return unknown):
- "Привет", "Здравствуйте", "Добрый день"
- "Как дела?", "Что нового?"
- "Спасибо", "Ок", "Понятно"
- "Мои задачи", "Показать список", "Повестка дня"
- "Помощь", "Что ты умеешь?"
- Empty messages or just emojis
- Questions: "Когда дедлайн?", "Кто участвует?"
- Status requests: "Готово ли?", "Завершено?"
- Random text without actionable items

EXAMPLES OF "create_task" intent:
- "Купить молоко завтра" → create_task
- "Подготовить отчет к пятнице" → create_task
- "Напомнить о встрече" → create_task
- "Позвонить клиенту" → create_task

EXAMPLES OF "create_event" intent:
- "Встреча с клиентом в 15:00 завтра" → create_event
- "Совещание в понедельник 10:00" → create_event
- "Звонок в 14:30" → create_event

DATETIME EXTRACTION (only for create_task/create_event):
- Kazakh time formats: "15 00", "15:00", "3 часа дня"
- Relative dates: завтра=tomorrow, послезавтра=day after tomorrow
- Days: понедельник=Monday, вторник=Tuesday, etc.
- Return datetime in ISO format: "2026-04-22T15:00:00"

EXTRACTION RULES:
- title: Clear, concise task/event name (max 50 chars, 1-3 words) - ONLY for create_task/create_event
- datetime: ISO format (YYYY-MM-DDTHH:MM:SS) or null - ONLY extract if clearly mentioned
- description: Full original message text

STRICT RULES:
- If message doesn't contain a clear actionable task/event → intent: "unknown"
- If message is a greeting, question, or status request → intent: "unknown"
- If message just lists existing tasks or asks for agenda → intent: "unknown"
- For unknown intents: set title="" and datetime=null
- Return ONLY valid JSON with correct datetime format
- Be conservative: when in doubt, classify as "unknown"

RESPONSE FORMAT:
{{
  "intent": "create_task|create_event|unknown",
  "title": "short task title (empty for unknown)",
  "datetime": "2026-04-22T15:00:00 (null for unknown)",
  "description": "full message text"
}}

Message: "{text}"
        """
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.url, json=body)
                response.raise_for_status()
            payload = response.json()
            raw = payload["candidates"][0]["content"]["parts"][0]["text"]

            # Try to parse JSON response
            try:
                return cast(dict[str, Any], json.loads(raw))
            except json.JSONDecodeError:
                # If response is not valid JSON, parse manually
                logger.warning("Gemini returned non-JSON response: %s", raw)
                return {
                    "intent": "unknown",
                    "title": text.strip()[:50],
                    "datetime": None,
                    "description": text,
                }
        except Exception as exc:
            logger.exception("Gemini extraction failed: %s", exc)
            return {
                "intent": "unknown",
                "title": text.strip()[:50],  # Limit title length
                "datetime": None,
                "description": text,
            }
