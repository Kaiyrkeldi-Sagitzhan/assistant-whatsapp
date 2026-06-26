"""Gemini API client with structured output support and retry logic."""

import logging
import asyncio
from typing import Any, Optional

from google.api_core import exceptions as google_exceptions
import google.generativeai as genai
from google.generativeai.types import GenerationConfig, HarmCategory, HarmBlockThreshold
from pydantic import ValidationError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from app.core.config import get_settings
from app.core.time import now_utc
from app.schemas.gemini import ExtractedTask, ChatResponse

logger = logging.getLogger(__name__)


RETRYABLE_GEMINI_ERRORS = (
    google_exceptions.DeadlineExceeded,
    google_exceptions.InternalServerError,
    google_exceptions.ServiceUnavailable,
)


def _is_configured_key(api_key: str) -> bool:
    return bool(api_key and api_key != "replace_me")


class GeminiClient:
    """
    Gemini API client with structured output support.
    
    Features:
    - Uses official google-generativeai SDK
    - Structured output for guaranteed JSON in schema format
    - Automatic retry with exponential backoff
    - Type-safe responses with Pydantic validation
    - Graceful fallback on errors
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.gemini_api_key
        self.model_name = settings.gemini_model
        self.enabled = _is_configured_key(self.api_key)
        if not self.enabled:
            logger.warning("Gemini API key is not configured; rule-based fallback will be used.")
            self.model = None
            self.safety_settings = []
            return
        
        # Configure Generative AI
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(self.model_name)
        
        # Safety settings - allow all content (assistant context)
        self.safety_settings = [
            {
                "category": HarmCategory.HARM_CATEGORY_HARASSMENT,
                "threshold": HarmBlockThreshold.BLOCK_NONE,
            },
            {
                "category": HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                "threshold": HarmBlockThreshold.BLOCK_NONE,
            },
            {
                "category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                "threshold": HarmBlockThreshold.BLOCK_NONE,
            },
            {
                "category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                "threshold": HarmBlockThreshold.BLOCK_NONE,
            },
        ]

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(RETRYABLE_GEMINI_ERRORS),
    )
    def _extract_task_internal(self, text: str, timezone: str) -> dict[str, Any]:
        """Internal method with retry decorator for extract_task."""
        current_date = now_utc().strftime("%Y-%m-%d")
        if not self.enabled or self.model is None:
            raise RuntimeError("Gemini is not configured")
        
        prompt = f"""You are an AI assistant for task management in Kazakhstan. Parse the user's message and return JSON data.

Current date: {current_date}
User timezone: {timezone}

INTENT CLASSIFICATION RULES:
- create_task: Clear actionable task/todo/reminder that needs to be done (e.g., "Купить молоко завтра")
- create_event: Calendar events, meetings, appointments with specific time (e.g., "Встреча в 15:00")
- schedule_notification: Custom reminder/notification request (e.g., "Напомни в 15:00", "Уведоми за 2 часа до 15:00")
- unknown: Greetings, questions, status requests, agenda queries, empty messages

ALWAYS CLASSIFY AS UNKNOWN:
- "Привет", "Здравствуйте", "Как дела?"
- "Мои задачи", "Покажи повестку", "Помощь"
- "Спасибо", "Понятно", "Ок"
- Random questions or status checks

DATETIME HANDLING:
- Extract in ISO format: YYYY-MM-DDTHH:MM:SS
- Russian formats: "завтра"=tomorrow, "послезавтра"=day after tomorrow
- Days: "понедельник"=Monday, etc.
- Time: "15:00", "15 часов", "3 часа дня"
- Relative: "через 1 минуту", "через 2 часа", "через день"
- Return null if datetime not mentioned

CRITICAL EXAMPLES:
1. "Купить молоко завтра в 10" → create_task, title="Купить молоко", datetime based on current date + 1 day at 10:00
2. "Встреча с боссом завтра в 15 часов" → create_event, title="Встреча с боссом", datetime based on current date + 1 day at 15:00
3. "Напомни в 15:00 проверить духовку" → schedule_notification, title="проверить духовку", datetime today at 15:00 or tomorrow if already past
4. "Как дела?" → unknown, title="", datetime=null
5. "В 15:00 встреча, напомни за 2 часа" → schedule_notification, title="Встреча", datetime two hours before 15:00

STRICT RULES:
- If message doesn't contain a clear actionable task/event → intent: "unknown"
- If message is a greeting, question, or status request → intent: "unknown"
- For unknown intents: set title="" and datetime=null
- Always return valid JSON matching the schema
- Be conservative: when in doubt, classify as "unknown"

User message: "{text}"
"""
        
        try:
            # Use structured output with response schema for guaranteed JSON
            response = self.model.generate_content(
                prompt,
                generation_config=GenerationConfig(
                    response_mime_type="application/json",
                    response_schema=ExtractedTask,
                    temperature=0.1,
                    max_output_tokens=500,
                ),
                safety_settings=self.safety_settings,
            )
            
            response_text = response.text
            logger.debug("Gemini raw response: %s", response_text)
            
            # Parse response with Pydantic validation
            try:
                task = ExtractedTask.model_validate_json(response_text)
                result = task.model_dump()
                logger.info("Successfully extracted task: intent=%s", result["intent"])
                return result
            except ValidationError as e:
                logger.warning("Validation error parsing Gemini response: %s", e)
                # Return fallback with unknown intent
                return {
                    "intent": "unknown",
                    "title": "",
                    "datetime": None,
                    "description": text,
                    "priority": "medium",
                    "confidence": 0.3,
                }
                
        except Exception as e:
            logger.warning("Error in extract_task with Gemini: %s", e)
            raise  # Let retry decorator handle it

    async def extract_task(self, text: str, timezone: str) -> dict[str, Any]:
        """
        Extract structured task information from user message using Gemini API.
        
        Uses structured output to guarantee valid JSON response matching ExtractedTask schema.
        Includes automatic retry with exponential backoff for reliability.
        
        Args:
            text: User message text
            timezone: User's timezone (e.g., "Asia/Almaty")
            
        Returns:
            Dictionary matching ExtractedTask schema (guaranteed valid JSON)
            Falls back to unknown intent on errors.
        """
        try:
            # Run retry-decorated function in thread pool
            result = await asyncio.to_thread(
                self._extract_task_internal,
                text,
                timezone,
            )
            return result
        except Exception as e:
            logger.warning("extract_task failed; using rule-based fallback: %s", e)
            # Final graceful fallback
            return {
                "intent": "unknown",
                "title": "",
                "datetime": None,
                "description": text,
                "priority": "medium",
                "confidence": 0.0,
            }

    @retry(
        stop=stop_after_attempt(1),
        wait=wait_exponential(multiplier=1, min=1, max=2),
        retry=retry_if_exception_type(RETRYABLE_GEMINI_ERRORS),
    )
    def _chat_internal(self, text: str, system_prompt: Optional[str] = None) -> str:
        """Internal method with retry decorator for chat."""
        if not self.enabled or self.model is None:
            raise RuntimeError("Gemini is not configured")

        if system_prompt is None:
            system_prompt = """You are a friendly task management assistant for Kazakhstani users. 
Respond in Russian. Keep responses to 1-3 sentences. Use warm tone with occasional emojis.
Always be helpful and encourage task management."""

        prompt = f"{system_prompt}\n\nUser: {text}"

        try:
            response = self.model.generate_content(
                prompt,
                generation_config=GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=300,
                ),
                safety_settings=self.safety_settings,
            )
            
            return response.text
            
        except Exception as e:
            logger.warning("Error in chat with Gemini: %s", e)
            raise  # Let retry decorator handle it

    async def chat(
        self,
        text: str,
        timezone: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Generate conversational response using Gemini API.
        
        Includes automatic retry with exponential backoff for reliability.
        
        Args:
            text: User message
            timezone: User timezone kept for compatibility with old call sites
            system_prompt: Optional system prompt override
            
        Returns:
            Conversational response in Russian
            Returns error message on final failure.
        """
        try:
            response = await asyncio.to_thread(
                self._chat_internal,
                text,
                system_prompt,
            )
            return response
        except Exception as e:
            logger.warning("chat failed; using local fallback: %s", e)
            # Final fallback message
            return (
                "Я на месте. Могу записать задачу, поставить напоминание или показать список задач. "
                "Например: 'напомни через 10 минут проверить духовку'."
            )

    async def is_healthy(self) -> bool:
        """
        Check if Gemini API is accessible with retry logic.
        
        Returns:
            True if API is working, False otherwise
        """
        try:
            if not self.enabled or self.model is None:
                return False
            response = await asyncio.to_thread(
                self.model.generate_content,
                "Ответь одним словом: Привет",
                generation_config=GenerationConfig(max_output_tokens=10),
            )
            is_healthy = bool(response.text)
            logger.info(f"Gemini health check: {'OK' if is_healthy else 'FAILED'}")
            return is_healthy
        except Exception as e:
            logger.error(f"Gemini health check failed: {e}")
            return False
