import logging
from dataclasses import dataclass
import re
from datetime import datetime as DateTime, timedelta
from typing import Any, cast, Union

from dateutil import parser as date_parser  # type: ignore[import-untyped]
from dateutil.relativedelta import relativedelta  # type: ignore[import-untyped]

from app.core.time import now_utc, resolve_timezone, to_utc
from app.services.gemini_client import GeminiClient
from app.services.context_manager import ConversationContext

logger = logging.getLogger(__name__)


@dataclass
class ParsedMessage:
    intent: str
    title: str
    datetime: Union[DateTime, None]
    description: str
    due_at: Union[DateTime, None] = None
    confidence: float = 0.0
    needs_clarification: bool = False
    clarification_type: str = ""  # "time", "date", "title", "details"
    clarification_question: str = ""


class NLPPipeline:
    def __init__(self) -> None:
        self.gemini = GeminiClient()

    async def parse_message(self, text: str, timezone: str, user_id: Union[str, None] = None) -> ParsedMessage:
        # First check for rule-based intents (commands)
        intent = self._detect_intent(text)

        if intent in ["agenda", "daily_agenda", "weekly_plan", "list_tasks"]:
            # These are command intents, don't need Gemini parsing
            return ParsedMessage(
                intent=intent,
                title="",
                datetime=None,
                description=text,
                confidence=1.0,
            )
        elif intent in ["complete_task", "update_task", "delete_task"]:
            # Task management commands - parse task reference
            task_ref = self._extract_task_reference(text)
            return ParsedMessage(
                intent=intent,
                title=task_ref,
                datetime=None,
                description=text,
                confidence=0.8,
            )
        elif intent == "schedule_notification":
            # Custom notification scheduling
            return ParsedMessage(
                intent=intent,
                title="",
                datetime=None,
                description=text,
                confidence=0.9,
            )
        else:
            # First try rule-based time extraction for better accuracy
            rule_datetime = self._extract_datetime_from_text(text, timezone)

            # Use Gemini for task creation and complex parsing with timeout
            try:
                import asyncio
                extracted: dict[str, Any] = await asyncio.wait_for(
                    self.gemini.extract_task(text, timezone),
                    timeout=10.0  # 10 second timeout
                )
                
                intent = str(extracted.get("intent", "create_task"))

                # Handle unknown intents - check if it might be a task using rule-based parsing
                if intent == "unknown":
                    # Check if text looks like a task using rule-based parsing
                    if rule_datetime or self._looks_like_task(text):
                        # Treat as create_task but ask for clarification
                        title = self._clean_title(text.strip()[:50])
                        description = text
                        confidence = float(extracted.get("confidence", 0.5))
                        datetime_obj = rule_datetime
                        
                        # Check if clarification is needed
                        clarification = self._check_needs_clarification(title, datetime_obj, text, "create_task")
                        if clarification:
                            return ParsedMessage(
                                intent="create_task",
                                title=title,
                                datetime=datetime_obj,
                                description=description,
                                due_at=datetime_obj,
                                confidence=confidence,
                                needs_clarification=True,
                                clarification_type=clarification["type"],
                                clarification_question=clarification["question"],
                            )
                        
                        return ParsedMessage(
                            intent="create_task",
                            title=title,
                            datetime=datetime_obj,
                            description=description,
                            due_at=datetime_obj,
                            confidence=confidence,
                        )
                    else:
                        # Truly unknown - not a task
                        return ParsedMessage(
                            intent="unknown",
                            title="",
                            datetime=None,
                            description=text,
                            confidence=float(extracted.get("confidence", 0.9)),
                        )

                title = self._clean_title(str(extracted.get("title", text.strip()[:50])))
                datetime_str = extracted.get("datetime")
                description = str(extracted.get("description", text))
                confidence = float(extracted.get("confidence", 0.5))

                # Parse datetime - prefer rule-based extraction, fallback to Gemini
                datetime_obj = rule_datetime
                if not datetime_obj and datetime_str:
                    try:
                        # Gemini might return dates in various formats
                        datetime_obj = self._parse_datetime_safely(datetime_str, timezone)
                    except Exception:
                        datetime_obj = None
            except asyncio.TimeoutError:
                # Fallback to rule-based parsing when Gemini is unavailable
                logger.warning("Gemini API timeout, using rule-based fallback for: %s", text)
                intent = "create_task"
                title = self._clean_title(text.strip()[:50])
                description = text
                confidence = 0.3
                datetime_obj = rule_datetime
            except Exception as e:
                # Fallback for any other Gemini errors
                logger.warning("Gemini API error (%s), using rule-based fallback for: %s", e, text)
                intent = "create_task"
                title = self._clean_title(text.strip()[:50])
                description = text
                confidence = 0.3
                datetime_obj = rule_datetime

            # Check if clarification is needed
            clarification = self._check_needs_clarification(title, datetime_obj, text, intent)
            if clarification:
                # Store context for follow-up
                if user_id:
                    context_mgr = ConversationContext()
                    await context_mgr.set_pending_clarification(
                        user_id=user_id,
                        original_text=text,
                        parsed_title=title,
                        parsed_description=description,
                        clarification_type=clarification["type"],
                        clarification_question=clarification["question"],
                        intent=intent
                    )
                return ParsedMessage(
                    intent=intent,
                    title=title,
                    datetime=datetime_obj,
                    description=description,
                    due_at=datetime_obj,
                    confidence=confidence,
                    needs_clarification=True,
                    clarification_type=clarification["type"],
                    clarification_question=clarification["question"],
                )

            return ParsedMessage(
                intent=intent,
                title=title,
                datetime=datetime_obj,
                description=description,
                due_at=datetime_obj,
                confidence=confidence,
            )

    def _detect_intent(self, text: str) -> str:
        """Detect intent from text using rule-based patterns."""
        text_lower = text.lower().strip()

        # Agenda and planning commands
        if any(keyword in text_lower for keyword in ["повестка", "agenda", "план", "что сегодня", "что у меня", "собери день"]):
            if any(word in text_lower for word in ["недел", "week", "на неделю"]):
                return "weekly_plan"
            else:
                return "daily_agenda"

        # Task list commands
        if any(keyword in text_lower for keyword in ["список задач", "мои задачи", "задачи", "list tasks", "tasks", "что есть"]):
            return "list_tasks"

        # Task completion commands
        if any(keyword in text_lower for keyword in ["выполнил", "готово", "сделал", "завершил", "complete", "done", "отметил"]):
            return "complete_task"

        # Task update commands
        if any(keyword in text_lower for keyword in ["измени", "перенеси", "обнови", "change", "update", "move"]):
            return "update_task"

        # Task deletion commands
        if any(keyword in text_lower for keyword in ["удали", "delete", "remove"]):
            return "delete_task"

        # Help commands
        if any(keyword in text_lower for keyword in ["помощь", "help", "что ты умеешь", "что умеешь", "команды", "функции", "возможности"]):
            return "help"

        # Notification/reminder commands
        if any(keyword in text_lower for keyword in ["уведоми", "напомни", "remind", "notify", "напоминание", "уведомление"]):
            return "schedule_notification"

        # Default to task creation
        return "create_task"

    def _extract_task_reference(self, text: str) -> str:
        """Extract task reference from management commands."""
        # Try to find task name after keywords
        patterns = [
            r"(?:выполнил|отметил|завершил|измени|перенеси|удали)\s+(.+)",
            r"(?:complete|done|change|update|delete|remove)\s+(.+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return text.strip()[:100]  # Fallback to first 100 chars

    def _check_needs_clarification(self, title: str, datetime_obj: Union[DateTime, None],
                                 original_text: str, intent: str) -> Union[dict, None]:
        """Check if the parsed information needs clarification."""

        # Check for unclear titles
        unclear_title_keywords = ["что-то", "кое-что", "дело", "штука", "вещь"]
        if any(keyword in title.lower() for keyword in unclear_title_keywords):
            return {
                "type": "title",
                "question": "❓ Что именно нужно сделать? Можете описать задачу подробнее?"
            }

        # Check for very short or generic titles
        if len(title.strip()) < 5 and title.lower() not in ["встреча", "совещание", "звонок"]:
            return {
                "type": "title",
                "question": "🤔 Что именно нужно сделать? Расскажите подробнее, и я создам задачу."
            }

        # Check for missing time in events/meetings
        if intent == "create_event" and not datetime_obj:
            return {
                "type": "time",
                "question": "⏰ Когда состоится встреча? Укажите время, например: 'завтра в 15:00' или 'в понедельник утром'."
            }

        # Check for unclear time references
        if datetime_obj and "встреча" in original_text.lower():
            current_time = now_utc().astimezone(resolve_timezone("Asia/Almaty"))
            time_diff = datetime_obj.astimezone(resolve_timezone("Asia/Almaty")) - current_time

            # If meeting is within next 2 hours but no specific time mentioned
            if timedelta(hours=0) < time_diff < timedelta(hours=2):
                if not any(word in original_text.lower() for word in ["в", "час", "мин", ":"]):
                    return {
                        "type": "time",
                        "question": "⏰ Можете уточнить точное время встречи? Например, 'в 14:30' или 'через час'."
                    }

        # Check for missing deadlines in important tasks
        important_keywords = ["важно", "срочно", "критично", "обязательно", "необходимо"]
        if any(keyword in original_text.lower() for keyword in important_keywords) and not datetime_obj:
            return {
                "type": "deadline",
                "question": "⏰ К какому сроку это нужно выполнить? Укажите дедлайн, чтобы я мог правильно спланировать."
            }

        # Check for follow-up tasks without context
        if "после" in original_text.lower() and not datetime_obj:
            return {
                "type": "context",
                "question": "🔗 После какой встречи или события нужно выполнить эту задачу? Уточните, и я свяжу их."
            }

        # Check for missing time in tasks (general tasks without deadlines)
        if not datetime_obj and intent == "create_task":
            # Check if task mentions time-sensitive keywords
            time_sensitive_keywords = ["сегодня", "завтра", "понедельник", "вторник", "среда", "четверг",
                                       "пятница", "суббота", "воскресенье", "утро", "день", "вечер",
                                       "ночь", "час", "минут", "срок", "дедлайн"]
            if any(keyword in original_text.lower() for keyword in time_sensitive_keywords):
                return {
                    "type": "time",
                    "question": "⏰ Во сколько или к какому сроку нужно выполнить задачу? Укажите время, например: 'сегодня в 15:00', 'завтра к вечеру' или 'до конца недели'."
                }
            
            # Check for meeting/event keywords without time
            meeting_keywords = ["встреча", "совещание", "переговор", "событие", "мероприятие", "интервью"]
            if any(keyword in original_text.lower() for keyword in meeting_keywords):
                return {
                    "type": "time",
                    "question": "⏰ Когда состоится встреча/мероприятие? Укажите точное время и дату, например: 'завтра в 14:00' или 'в пятницу в 10:30'."
                }
            
            # For important tasks without deadlines
            important_keywords = ["важно", "срочно", "нужно", "надо", "обязательно", "критично"]
            if any(keyword in original_text.lower() for keyword in important_keywords):
                return {
                    "type": "deadline",
                    "question": "⏰ К какому сроку это нужно выполнить? Укажите дедлайн, чтобы я мог правильно спланировать и напомнить вовремя."
                }

        # Check for missing time when date is specified but time is midnight (00:00:00)
        if datetime_obj and intent == "create_task":
            # Check if time is midnight (00:00:00) and date is not today
            almaty_tz = resolve_timezone("Asia/Almaty")
            datetime_almaty = datetime_obj.astimezone(almaty_tz)
            current_time_almaty = now_utc().astimezone(almaty_tz)
            
            # Check if time is midnight (00:00:00) or very close to it
            time_is_midnight = datetime_almaty.hour == 0 and datetime_almaty.minute == 0 and datetime_almaty.second == 0
            
            # Check if date is not today (to avoid asking for time when user just says "today")
            date_is_not_today = datetime_almaty.date() != current_time_almaty.date()
            
            if time_is_midnight and date_is_not_today:
                return {
                    "type": "time",
                    "question": "⏰ Во сколько нужно выполнить задачу? Укажите точное время, например: 'в 15:00' или 'утром'."
                }

        # Check for vague time references that need clarification
        if datetime_obj and intent == "create_task":
            current_time = now_utc().astimezone(resolve_timezone("Asia/Almaty"))
            time_diff = datetime_obj.astimezone(resolve_timezone("Asia/Almaty")) - current_time
            
            # If time is very soon (within 2 hours) but not specific
            if timedelta(hours=0) < time_diff < timedelta(hours=2):
                vague_time_words = ["скоро", "близко", "через немного", "вдруг"]
                if any(word in original_text.lower() for word in vague_time_words):
                    return {
                        "type": "time",
                        "question": "⏰ Можете уточнить точное время? Например, 'в 15:30' или 'через 45 минут'."
                    }

        return None

    def _looks_like_task(self, text: str) -> bool:
        """Check if text looks like it could be a task."""
        # Keywords that suggest this is a task
        task_keywords = [
            "купить", "сделать", "выполнить", "напомнить", "задача", "дело",
            "позвонить", "отправить", "приготовить", "купить", "заказать",
            "записаться", "отправиться", "успеть", "спланировать", "организовать",
            "подготовить", "создать", "добавить", "запланировать",
            "совещание", "встреча", "поговорить", "обсудить", "собрание"
        ]
        
        # Check for task-related keywords
        text_lower = text.lower()
        if any(keyword in text_lower for keyword in task_keywords):
            return True
        
        # Check for verbs that suggest action
        action_verbs = ["нужно", "надо", "хочу", "планирую", "должен", "нужно", "надо"]
        if any(verb in text_lower for verb in action_verbs):
            return True
        
        # Check if it's a short imperative sentence (likely a task)
        if len(text.split()) <= 5 and any(word in text_lower for word in ["купить", "сделать", "выполнить", "позвонить"]):
            return True
        
        return False

    def _extract_datetime_from_text(self, text: str, timezone: str) -> Union[DateTime, None]:
        """Extract datetime from text using rule-based patterns for Kazakh locale."""
        text_lower = text.lower()
        now = now_utc().astimezone(resolve_timezone(timezone))

        # Extract time patterns like "15 00", "15:00", "3 часа", "15.00"
        time_match = re.search(r'(\d{1,2})[ :.](\d{2})', text)
        if time_match:
            hours = int(time_match.group(1))
            minutes = int(time_match.group(2))

            # Handle 12-hour format and invalid hours, with AM/PM detection
            # Normalize hours > 23
            if hours > 23:
                hours = hours % 12
            # Detect AM/PM indicators in text
            am_keywords = ['am', 'утра', 'утром', 'ночи', 'раннего']
            pm_keywords = ['pm', 'вечера', 'дня', 'после полудня']
            has_am = any(kw in text_lower for kw in am_keywords)
            has_pm = any(kw in text_lower for kw in pm_keywords)
            # Check for direct am/pm attached to time (e.g., "1:04pm")
            ampm_match = re.search(r'(\d{1,2})[ :.](\d{2})\s*([ap]m)', text_lower)
            if ampm_match:
                if ampm_match.group(3) == 'pm':
                    has_pm = True
                else:
                    has_am = True
            # Adjust hours based on indicators
            if has_pm and not has_am:
                if hours < 12:
                    hours += 12
            elif has_am and not has_pm:
                if hours == 12:
                    hours = 0
            elif 0 < hours < 6:
                # No explicit indicator, use current time heuristic
                current_hour = now.hour
                # Assume PM only if currently daytime (6 AM - 10 PM)
                if 6 <= current_hour < 22:
                    hours += 12
                # else keep as AM (early morning)

            # Determine date based on context
            if "завтра" in text_lower:
                date_base = now + timedelta(days=1)
            elif "послезавтра" in text_lower:
                date_base = now + timedelta(days=2)
            elif any(word in text_lower for word in ["сегодня", "вечером", "утром"]):
                date_base = now
            else:
                # Default to today if time is mentioned
                date_base = now

            try:
                datetime_obj = date_base.replace(hour=hours, minute=minutes, second=0, microsecond=0)
                return to_utc(datetime_obj, timezone)
            except ValueError:
                pass

        # Fallback to relative date extraction
        return self._normalize_date(None, text, timezone)

    def _clean_title(self, title: str) -> str:
        """Remove time and date expressions from title to keep it clean."""
        if not title:
            return title
        # Patterns to remove (time with optional AM/PM, date words)
        patterns = [
            r'(?:в|на|к)\s+\d{1,2}[ :.]\d{2}\s*(?:[ap]m|утра|вечера|дня|ночи)?',  # в 1:04, в 1:04 pm, в 13:04
            r'\d{1,2}[ :.]\d{2}\s*[ap]m',  # 1:04pm
            r'\b(?:завтра|послезавтра|сегодня)\b',
            r'в\s+(?:пятницу|понедельник|вторник|среду|четверг|субботу|воскресенье)',
            r'на\s+следующей\s+неделе',
            r'через\s+неделю',
            r'через\s+день',
            r'через\s+два\s+дня',
            r'через\s+три\s+дня',
            r'в\s+утра',
            r'в\s+вечера',
        ]
        cleaned = title
        for pat in patterns:
            cleaned = re.sub(pat, '', cleaned, flags=re.IGNORECASE)
        # Collapse multiple spaces and strip punctuation
        cleaned = re.sub(r'\s+', ' ', cleaned).strip(' .,;:!?')
        return cleaned if cleaned else "Задача"

    def _parse_datetime_safely(self, datetime_str: str, timezone: str) -> Union[DateTime, None]:
        """Safely parse datetime string with proper timezone handling."""
        try:
            # Try parsing as-is first
            parsed = date_parser.parse(datetime_str)

            # If it has timezone info, convert to UTC
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc)
            else:
                # Assume it's in local timezone
                return to_utc(parsed, timezone)
        except Exception:
            return None

    def _normalize_date(
        self, due_text: Union[str, None], full_context: str = "", timezone_name: str = "UTC"
    ) -> Union[DateTime, None]:
        if not due_text:
            # Check for relative date patterns in full context
            due_text = self._extract_relative_date(full_context, timezone_name)

        if not due_text:
            return None

        try:
            # Try parsing with fuzzy logic
            parsed = cast(DateTime, date_parser.parse(due_text, fuzzy=True))
            return to_utc(parsed, timezone_name)
        except (ValueError, OverflowError):
            return None

    def _extract_relative_date(self, text: str, timezone_name: str = "UTC") -> Union[str, None]:
        """Extract relative dates like 'завтра', 'в пятницу', 'на следующей неделе'."""
        text_lower = text.lower()
        now = now_utc().astimezone(resolve_timezone(timezone_name))

        if "завтра" in text_lower:
            dt = now + timedelta(days=1)
            return dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        elif "сегодня" in text_lower:
            return now.isoformat()
        elif "пятниц" in text_lower:
            days_ahead = 4 - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            dt = now + timedelta(days=days_ahead)
            return dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        elif "на следующей неделе" in text_lower or "через неделю" in text_lower:
            dt = now + timedelta(weeks=1)
            return dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        elif "на этой неделе" in text_lower or "на неделе" in text_lower:
            days_ahead = 6 - now.weekday()
            dt = now + timedelta(days=max(1, days_ahead))
            return dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        elif "до конца дня" in text_lower or "к концу дня" in text_lower:
            return now.isoformat()
        elif "до конца недели" in text_lower:
            days_ahead = 5 - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            dt = now + timedelta(days=days_ahead)
            return dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        elif "месяц" in text_lower or "через месяц" in text_lower:
            next_month = cast(DateTime, now + relativedelta(months=1))
            return next_month.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        elif "через день" in text_lower:
            dt = now + timedelta(days=1)
            return dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        elif "через два дня" in text_lower:
            dt = now + timedelta(days=2)
            return dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        elif "через три дня" in text_lower:
            dt = now + timedelta(days=3)
            return dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        elif "через неделю" in text_lower:
            dt = now + timedelta(weeks=1)
            return dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

        # Check for date numbers like "25 числа", "до 20-го"
        match = re.search(r"(\d{1,2})[-го]*\s*числа", text_lower)
        if match:
            day = int(match.group(1))
            try:
                dt = now.replace(day=day)
                return dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            except ValueError:
                pass

        return None