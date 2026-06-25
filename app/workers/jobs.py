import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Union

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    CalendarEvent,
    InboundChannel,
    InboundMessage,
    SourceType,
    Task,
    TaskPriority,
    User,
)
from app.db.session import SessionLocal
from app.core.config import get_settings
from app.integrations.calendar_google import GoogleCalendarSync
from app.integrations.email_inbound import EmailInboundParser
from app.integrations.whatsapp_meta import WhatsAppMetaClient
from app.schemas.task import TaskCreate
from app.services.nlp_pipeline import NLPPipeline
from app.services.reminder_service import ReminderService
from app.services.context_manager import ConversationContext
from app.services.task_service import TaskService
from app.services.agenda_service import AgendaService
from app.workers.celery_app import celery_app

USER_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")

logger = logging.getLogger(__name__)


def _get_or_create_user(db: Session, user_external_id: str) -> User:
    user_id = uuid.uuid5(USER_NAMESPACE, user_external_id)
    user = db.get(User, user_id)
    if user:
        return user

    user = User(id=user_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _store_inbound(
    db: Session,
    *,
    channel: InboundChannel,
    external_message_id: str,
    user_id: uuid.UUID,
    raw_text: str,
    parse_result: Union[dict, None] = None,
) -> bool:
    msg = InboundMessage(
        channel=channel,
        external_message_id=external_message_id,
        user_id=user_id,
        raw_text=raw_text,
        normalized_text=raw_text,
        parse_result=parse_result,
    )
    db.add(msg)
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


@celery_app.task(name="app.workers.jobs.process_whatsapp_inbound")
def process_whatsapp_inbound(
    external_message_id: str,
    text: str,
    phone: str,
    metadata: Union[dict, None] = None,
) -> None:
    print("Processing WhatsApp message from", phone, ":", text)
    logger.info("Processing WhatsApp message from %s: %s (metadata: %s)", phone, text, metadata)
    db = SessionLocal()
    try:
        # Use phone number as user identifier
        user = _get_or_create_user(db, phone)
        if not _store_inbound(
            db,
            channel=InboundChannel.WHATSAPP,
            external_message_id=external_message_id,
            user_id=user.id,
            raw_text=text,
            parse_result={"phone": phone, "metadata": metadata},
        ):
            logger.warning("Failed to store inbound message for %s", phone)
            return
        logger.info("Message stored successfully for user %s", user.id)

        # Check for pending clarification
        context_mgr = ConversationContext()
        pending_context = asyncio.run(context_mgr.consume_clarification(str(user.id), text))
        
        # Parse message to determine intent
        try:
            pipeline = NLPPipeline()
            if pending_context:
                # User is responding to a clarification request
                # Combine the original task info with the clarification
                logger.info("Processing clarification response for user %s: %s", user.id, text)
                
                # Parse the clarification response to extract time/date info
                # Combine original text with clarification for proper context
                combined_text = pending_context["original_text"] + " " + text
                clarification_parsed = asyncio.run(pipeline.parse_message(combined_text, user.timezone))
                
                # Use the original task info but update with clarification
                intent = pending_context["intent"]
                title = pending_context["parsed_title"]
                description = pending_context["parsed_description"]
                
                # If clarification provides a datetime, use it
                if clarification_parsed.datetime:
                    datetime_obj = clarification_parsed.datetime
                    due_at = datetime_obj
                else:
                    # Try to extract datetime from the combined text (original + clarification)
                    datetime_obj = pipeline._extract_datetime_from_text(combined_text, user.timezone)
                    due_at = datetime_obj
                
                # If still no datetime, use the original
                if not datetime_obj:
                    datetime_obj = None
                    due_at = None
                
                confidence = 0.8  # Higher confidence for clarified tasks
                
                # Create a parsed message manually
                class SimpleParsed:
                    pass
                parsed = SimpleParsed()
                parsed.intent = intent
                parsed.title = title
                parsed.description = description
                parsed.datetime = datetime_obj
                parsed.due_at = due_at
                parsed.confidence = confidence
                parsed.needs_clarification = False
                
                logger.info("Clarification processed for user %s: task='%s', datetime='%s'", 
                           user.id, title, datetime_obj)
            else:
                # Normal message processing
                parsed = asyncio.run(pipeline.parse_message(text, user.timezone, user_id=str(user.id)))
            logger.info("NLP parsed message: intent='%s', title='%s', datetime='%s'", parsed.intent, parsed.title, parsed.datetime)
            print("Parsed intent:", parsed.intent, "for message:", text)

            if parsed.intent == "daily_agenda":
                # Generate daily agenda
                agenda_service = AgendaService()
                agenda = agenda_service.generate_daily_agenda(str(user.id))

                if "error" in agenda:
                    confirmation = (
                        "😔 Не удалось сформировать повестку дня.\n"
                        "🔄 Попробуйте позже или создайте задачи вручную.\n"
                        "💡 Пример: 'Купить продукты завтра'"
                    )
                else:
                    confirmation = _format_daily_agenda(agenda)

            elif parsed.intent == "weekly_plan":
                # Generate weekly plan
                agenda_service = AgendaService()
                plan = agenda_service.generate_weekly_plan(str(user.id))

                if "error" in plan:
                    confirmation = (
                        "😔 Не удалось сформировать план на неделю.\n"
                        "🔄 Попробуйте позже или создайте задачи вручную.\n"
                        "💡 Пример: 'Подготовить отчет к пятнице'"
                    )
                else:
                    confirmation = _format_weekly_plan(plan)

            elif parsed.intent == "help":
                # Show comprehensive help
                confirmation = (
                    "🤖 Я ваш умный помощник по управлению задачами!\n\n"
                    "📝 **УМЕЮ СОЗДАВАТЬ ЗАДАЧИ:**\n"
                    "• Просто опишите задачу: 'Купить молоко завтра в 10 утра'\n"
                    "• 'Встреча с клиентом в пятницу 15:00'\n"
                    "• 'Написать отчет до конца недели'\n\n"
                    "📋 **УМЕЮ ПОКАЗЫВАТЬ ЗАДАЧИ:**\n"
                    "• 'мои задачи' - список всех активных задач\n"
                    "• 'повестка' или 'agenda' - расписание на сегодня\n"
                    "• 'план на неделю' - обзор на ближайшие 7 дней\n\n"
                    "✅ **УМЕЮ ОТМЕЧАТЬ ВЫПОЛНЕНИЕ:**\n"
                    "• 'выполнил [название задачи]'\n"
                    "• 'готово [название задачи]'\n\n"
                    "📅 **УМЕЮ ПОДКЛЮЧАТЬСЯ К КАЛЕНДАРЮ:**\n"
                    "• Google Календарь для синхронизации встреч\n\n"
                    "📊 **УМЕЮ ОТПРАВЛЯТЬ СВОДКИ В WHATSAPP:**\n"
                    "• Сводка на день - задачи только на сегодня\n"
                    "• Сводка на неделю - все задачи на 7 дней с разбивкой по дням\n"
                    "• Сводка на месяц - все задачи, сгруппированные по неделям\n\n"
                    "🔔 **АВТОМАТИЧЕСКИЕ НАПОМИНАНИЯ:**\n"
                    "• За 1 час до дедлайна (для важных задач)\n"
                    "• За 1 день до дедлайна (для критических задач)\n"
                    "• Утренние и вечерние дайджесты\n\n"
                    "⏰ **УМЕЮ СТАВИТЬ НАПОМИНАНИЯ:**\n"
                    "• 'Напомни мне через 1 минуту'\n"
                    "• 'Уведоми меня в 15:00'\n"
                    "• 'Напомни завтра в 10 утра'\n\n"
                    "💡 **ПРИМЕРЫ КОМАНД:**\n"
                    "• 'Купить продукты завтра'\n"
                    "• 'Выполнил отчет'\n"
                    "• 'Покажи мои задачи'\n"
                    "• 'Какая у меня повестка?'\n"
                    "• 'Свободное время сегодня'\n"
                    "• 'Напомни через 30 минут'\n"
                    "• 'Уведоми меня в 18:00'\n\n"
                    "🆘 **ПОМОЩЬ:**\n"
                    "Напишите 'помощь' в любое время, чтобы увидеть это сообщение снова!"
                )

            elif parsed.intent == "schedule_notification":
                # Schedule a custom notification
                from datetime import datetime, timedelta
                
                # Extract the message (remove notification keywords)
                notification_keywords = ["уведоми", "напомни", "remind", "notify", "напоминание", "уведомление"]
                message_text = text
                for keyword in notification_keywords:
                    message_text = message_text.replace(keyword, "").strip()
                
                # Parse the time from the message
                reminder_service = ReminderService(db)
                
                notify_time = reminder_service.parse_notification_text(text, user.timezone, now_utc())
                
                if notify_time:
                    # Schedule the notification
                    success = reminder_service.schedule_custom_notification(
                        user_id=user.id,
                        message=message_text if message_text else "Напоминание",
                        notify_at=notify_time,
                        title="Напоминание"
                    )
                    
                    if success:
                        time_str = notify_time.strftime("%d.%m %H:%M")
                        confirmation = f"✅ Напоминание запланировано на {time_str}! Я напишу вам в это время."
                    else:
                        confirmation = "❌ Не удалось запланировать напоминание. Попробуйте еще раз."
                else:
                    confirmation = (
                        "❓ Не понял, когда напомнить. Попробуйте так:\n"
                        "• 'Напомни через 1 минуту'\n"
                        "• 'Уведоми меня в 15:00'\n"
                        "• 'Напомни завтра в 10 утра'"
                    )

            elif parsed.intent == "list_tasks":
                # List all tasks with priorities
                service = TaskService(db)
                tasks = service.list_open_tasks(user.id)

                if not tasks:
                    confirmation = (
                        "✅ Отлично! У вас нет активных задач.\n"
                        "🎉 Можно отдохнуть или спланировать новые дела.\n"
                        "💡 Напишите 'помощь', чтобы узнать, что я умею."
                    )
                else:
                    high_priority = [t for t in tasks if t.priority.value == "high"]
                    medium_priority = [t for t in tasks if t.priority.value == "medium"]
                    low_priority = [t for t in tasks if t.priority.value == "low"]

                    total_tasks = len(tasks)
                    response_parts = [f"📋 У вас {total_tasks} активных задач:"]

                    def format_task_time(task_due_at):
                        """Format task due time in user's timezone."""
                        if not task_due_at:
                            return ""
                        try:
                            from app.core.time import resolve_timezone
                            local_tz = resolve_timezone(user.timezone)
                            local_time = task_due_at.replace(tzinfo=timezone.utc).astimezone(local_tz)
                            return f" (до {local_time.strftime('%d.%m %H:%M')})"
                        except Exception:
                            return ""

                    if high_priority:
                        response_parts.append(f"🔥 Высокий приоритет ({len(high_priority)}):")
                        for task in high_priority[:5]:
                            due_info = format_task_time(task.due_at)
                            response_parts.append(f"  • {task.title}{due_info}")

                    if medium_priority:
                        response_parts.append(f"⚡ Средний приоритет ({len(medium_priority)}):")
                        for task in medium_priority[:5]:
                            due_info = format_task_time(task.due_at)
                            response_parts.append(f"  • {task.title}{due_info}")

                    if low_priority:
                        response_parts.append(f"📝 Низкий приоритет ({len(low_priority)}):")
                        for task in low_priority[:3]:
                            due_info = format_task_time(task.due_at)
                            response_parts.append(f"  • {task.title}{due_info}")

                    response_parts.append("\n💡 Чтобы выполнить задачу, скажите 'выполнил [название]'")
                    confirmation = "\n".join(response_parts)

            elif parsed.intent == "complete_task":
                # Mark task as completed
                service = TaskService(db)
                task_name = parsed.title

                # Try to find task by name (simple matching)
                tasks = service.list_open_tasks(user.id)
                matched_task = None

                for task in tasks:
                    if task_name.lower() in task.title.lower() or task.title.lower() in task_name.lower():
                        matched_task = task
                        break

                if matched_task:
                    service.complete_task(matched_task.id)
                    confirmation = f"✅ Отлично! Задача '{matched_task.title}' выполнена! 🎉\n💪 Молодец, продолжайте в том же духе!"
                else:
                    confirmation = f"🤔 Не нашел задачу с названием '{task_name}'. Попробуйте:\n• Проверить орфографию\n• Сказать точнее: 'выполнил купить молоко'\n• Посмотреть список: 'мои задачи'"

            elif parsed.intent == "update_task":
                # Update task (for now just change due date if mentioned)
                confirmation = (
                    f"📝 Функция обновления задач скоро будет готова!\n"
                    f"🔄 Пока что создайте новую задачу с правильными данными.\n"
                    f"💡 Пример: 'Перенести {parsed.title} на завтра 16:00'"
                )

            elif parsed.intent == "delete_task":
                # Delete task
                confirmation = (
                    f"🗑️ Функция удаления задач скоро будет готова!\n"
                    f"✅ Пока что отметьте задачу выполненной: 'выполнил {parsed.title}'\n"
                    f"🔄 Или просто игнорируйте её в списке задач."
                )

            elif parsed.intent == "unknown":
                # Handle messages that don't contain tasks
                logger.info("Message intent: %s - no task detected, using chat mode", parsed.intent)
                try:
                    # Use Gemini to generate a conversational response
                    gemini = GeminiClient()
                    confirmation = asyncio.run(gemini.chat(text, user.timezone))
                except Exception as e:
                    logger.error("Chat generation failed: %s", e)
                    # Fallback to generic help message
                    confirmation = (
                        "👋 Привет! Я ваш помощник по задачам.\n\n"
                        "📝 Я умею:\n"
                        "• Создавать задачи: 'Купить молоко завтра в 10 утра'\n"
                        "• Планировать встречи: 'Встреча с клиентом в пятницу 15:00'\n"
                        "• Показывать задачи: 'мои задачи' или 'повестка'\n"
                        "• Отмечать выполнение: 'выполнил купить молоко'\n\n"
                        "💡 Попробуйте написать задачу, и я её запомню!"
                    )

            elif parsed.intent == "create_task":
                # Check if clarification is needed
                if parsed.needs_clarification:
                    confirmation = parsed.clarification_question
                else:
                    print("Message accepted from", phone, ":", text, "- intent:", parsed.intent)
                    service = TaskService(db)
                    task = service.create_task(
                        TaskCreate(
                            user_id=user.id,
                            title=parsed.title,
                            description=parsed.description,
                            due_at=parsed.datetime,
                            priority=TaskPriority.MEDIUM,  # Default priority
                        ),
                        parsed_intent=parsed.intent
                    )
                    logger.info("Task created: %s", task.title)

                    db.query(Task).filter(Task.id == task.id).update(
                        {
                            Task.source_type: SourceType.WHATSAPP,
                            Task.source_ref: external_message_id,
                            Task.is_follow_up: "после встречи" in text.lower(),
                        }
                    )
                    db.commit()

                    # Auto-create reminders if needed
                    reminder_service = ReminderService(db)
                    reminder_service.auto_create_reminders(task)

                    # Format due date in user's timezone
                    due_time_display = "не указан"
                    if task.due_at:
                        # Convert UTC to user's local timezone for display
                        from app.core.time import resolve_timezone
                        local_tz = resolve_timezone(user.timezone)
                        local_due_at = task.due_at.replace(tzinfo=timezone.utc).astimezone(local_tz)
                        due_time_display = local_due_at.strftime('%d.%m %H:%M')

                    reminder_info = "🔄 Напомню за 30 минут" if task.due_at else "📝 Задача без дедлайна"
                    confirmation = (
                        f"✅ Отлично! Задача '{task.title}' создана.\n"
                        f"📅 Срок: {due_time_display}\n"
                        f"{reminder_info}\n"
                        f"💪 Вы всегда можете попросить список задач, сказав 'мои задачи'"
                    )

            elif parsed.intent == "create_event":
                # Check if clarification is needed
                if parsed.needs_clarification:
                    confirmation = parsed.clarification_question
                else:
                    print("Message accepted from", phone, ":", text, "- intent:", parsed.intent)
                    # For now, treat events as tasks (since no event model exists)
                    service = TaskService(db)
                    task = service.create_task(
                        TaskCreate(
                            user_id=user.id,
                            title=f"Событие: {parsed.title}",
                            description=parsed.description,
                            due_at=parsed.datetime,
                            priority=TaskPriority.HIGH,  # Events are important
                        ),
                        parsed_intent=parsed.intent
                    )
                    logger.info("Event created as task: %s", task.title)

                    db.query(Task).filter(Task.id == task.id).update(
                        {
                            Task.source_type: SourceType.WHATSAPP,
                            Task.source_ref: external_message_id,
                            Task.is_follow_up: False,
                        }
                    )
                    db.commit()

                    # Format event time in user's timezone
                    event_time_display = "не указано"
                    if task.due_at:
                        # Convert UTC to user's local timezone for display
                        from app.core.time import resolve_timezone
                        local_tz = resolve_timezone(user.timezone)
                        local_due_at = task.due_at.replace(tzinfo=timezone.utc).astimezone(local_tz)
                        event_time_display = local_due_at.strftime('%d.%m %H:%M')

                    confirmation = (
                        f"✅ Отлично! Встреча '{parsed.title}' запланирована.\n"
                        f"📅 Время: {event_time_display}\n"
                        f"🔥 Высокий приоритет - не забудьте подготовиться!\n"
                        f"📅 Хотите посмотреть повестку дня? Просто скажите 'повестка'"
                    )

            else:
                logger.info("Message intent: %s - using chat mode", parsed.intent)
                try:
                    # Use Gemini to generate a conversational response
                    gemini = GeminiClient()
                    confirmation = asyncio.run(gemini.chat(text, user.timezone))
                except Exception as e:
                    logger.error("Chat generation failed: %s", e)
                    # Fallback to generic help message
                    confirmation = (
                        "👋 Привет! Я ваш помощник по задачам.\n\n"
                        "📝 Я умею:\n"
                        "• Создавать задачи: 'Купить молоко завтра в 10 утра'\n"
                        "• Планировать встречи: 'Встреча с клиентом в пятницу 15:00'\n"
                        "• Показывать задачи: 'мои задачи' или 'повестка'\n"
                        "• Отмечать выполнение: 'выполнил купить молоко'\n\n"
                        "🤔 Что бы вы хотели сделать?"
                    )

        except Exception as e:
            logger.error("Error processing message: %s", str(e))
            confirmation = (
                "😔 Извините, что-то пошло не так при обработке вашего сообщения.\n"
                "🔄 Попробуйте перефразировать или напишите по-другому.\n"
                "📞 Если проблема persists, попробуйте: 'помощь'"
            )

        # Send confirmation back to user
        config = get_settings()
        
        # Convert sender's phone number to match test recipient format
        # Examples:
        # - 77769707106 -> 787769707106
        # - 77782304206 -> 787782304206
        # Rule: if starts with 777, add 8 after 777 or 7777
        if phone.startswith('7777'):
            recipient_phone = '78777' + phone[4:]
        elif phone.startswith('777'):
            recipient_phone = '7877' + phone[3:]
        elif phone.startswith('77'):
            recipient_phone = '787' + phone[2:]
        else:
            recipient_phone = phone
        
        try:
            whatsapp_client = WhatsAppMetaClient()
            asyncio.run(whatsapp_client.send_text(recipient_phone, confirmation))
            logger.info("Confirmation sent to %s (original sender: %s): %s", recipient_phone, phone, confirmation)
        except Exception as e:
            logger.error("Failed to send confirmation: %s", str(e))

        logger.info("Successfully processed WhatsApp message from %s", phone)
    except Exception as e:
        logger.error("Error processing WhatsApp message from %s: %s", phone, str(e))
        db.rollback()
    finally:
        db.close()

    def _format_daily_agenda(self, agenda: dict) -> str:
        """Format daily agenda for WhatsApp response."""
        lines = ["📋 Ваш день сегодня:"]

        # Meetings
        if agenda.get("meetings"):
            lines.append("\n🌅 Встречи:")
            for meeting in agenda["meetings"][:5]:  # Limit to 5
                lines.append(f"• {meeting['start']}-{meeting['end']}: {meeting['title']}")

        # Today's tasks
        if agenda.get("tasks_today"):
            lines.append("\n📝 Задачи на сегодня:")
            for task in agenda["tasks_today"][:8]:  # Limit to 8
                priority_emoji = {"high": "🔥", "medium": "⚡", "low": "📝"}.get(task["priority"], "📝")
                due_info = f" ({task['due_time']})" if task.get("due_time") else ""
                overdue_marker = " ⏰" if task.get("overdue") else ""
                lines.append(f"{priority_emoji} {task['title']}{due_info}{overdue_marker}")

        # Overdue tasks
        if agenda.get("overdue_tasks"):
            lines.append("\n❌ Просроченные задачи:")
            for task in agenda["overdue_tasks"]:
                days = f" ({task['days_overdue']} дн.)" if task["days_overdue"] > 0 else ""
                lines.append(f"• {task['title']}{days}")

        # Free slots
        if agenda.get("free_slots"):
            lines.append("\n💡 Свободное время:")
            for slot in agenda["free_slots"]:
                lines.append(f"• {slot['start']}-{slot['end']} ({slot['duration']})")

        # Workload level
        workload = agenda.get("workload_level", "moderate")
        workload_messages = {
            "light": "🌤️ Легкий день",
            "moderate": "⚖️ Умеренная нагрузка",
            "heavy": "🏋️ Загруженный день",
            "overloaded": "⚠️ Очень загруженный день!"
        }
        lines.append(f"\n{workload_messages.get(workload, '⚖️ Умеренная нагрузка')}")

        return "\n".join(lines)

    def _format_weekly_plan(self, plan: dict) -> str:
        """Format weekly plan for WhatsApp response."""
        summary = plan.get("summary", {})

        lines = [f"📅 План на неделю ({summary.get('total_tasks', 0)} задач, {summary.get('total_meetings', 0)} встреч)"]

        # Summary stats
        lines.append(f"🔥 Важных задач: {summary.get('high_priority_tasks', 0)}")
        lines.append(f"📊 Среднее встреч в день: {summary.get('avg_daily_meetings', 0)}")

        if summary.get("overloaded_days", 0) > 0:
            lines.append(f"⚠️ Перегруженных дней: {summary['overloaded_days']}")

        # Daily breakdown (key days only)
        daily = plan.get("daily_breakdown", {})
        busy_days = [(day, data) for day, data in daily.items() if data["tasks_count"] > 0 or data["meetings_count"] > 0]

        if busy_days:
            lines.append("\n📋 Ключевые дни:")
            for day, data in busy_days[:4]:  # Limit to 4 days
                status = "🔥" if data["high_priority_tasks"] > 0 else "⚡" if data["meetings_count"] > 2 else "📝"
                lines.append(f"{status} {day}: {data['tasks_count']} задач, {data['meetings_count']} встреч")

        # Recommendations
        recommendations = plan.get("recommendations", [])
        if recommendations:
            lines.append("\n💡 Рекомендации:")
            for rec in recommendations[:3]:  # Limit to 3
                lines.append(f"• {rec}")

        return "\n".join(lines)


@celery_app.task(name="app.workers.jobs.process_email_inbound")
def process_email_inbound(payload: dict) -> None:
    db = SessionLocal()
    try:
        user = _get_or_create_user(db, payload["user_external_id"])
        parser = EmailInboundParser()
        text = parser.parse(payload["text"])

        if not _store_inbound(
            db,
            channel=InboundChannel.EMAIL,
            external_message_id=payload["external_message_id"],
            user_id=user.id,
            raw_text=payload["text"],
        ):
            return

        pipeline = NLPPipeline()
        parsed = asyncio.run(pipeline.parse_message(text, user.timezone))

        task = Task(
            user_id=user.id,
            title=parsed.title,
            description=text,
            due_at=parsed.due_at,
            source_type=SourceType.EMAIL,
            source_ref=payload["external_message_id"],
            confidence=parsed.confidence,
        )
        db.add(task)
        db.commit()
    finally:
        db.close()


@celery_app.task(name="app.workers.jobs.process_calendar_inbound")
def process_calendar_inbound(payload: dict) -> None:
    db = SessionLocal()
    try:
        user = _get_or_create_user(db, payload["user_external_id"])
        normalized = GoogleCalendarSync().normalize_event_payload(payload.get("metadata", {}))

        existing = (
            db.query(CalendarEvent)
            .filter(CalendarEvent.external_event_id == normalized["external_event_id"])
            .one_or_none()
        )
        if existing:
            existing.title = normalized["title"]
            existing.starts_at = datetime.fromisoformat(normalized["starts_at"])
            existing.ends_at = datetime.fromisoformat(normalized["ends_at"])
            existing.attendees_count = normalized["attendees_count"]
        else:
            event = CalendarEvent(
                user_id=user.id,
                external_event_id=normalized["external_event_id"],
                title=normalized["title"],
                starts_at=datetime.fromisoformat(normalized["starts_at"]),
                ends_at=datetime.fromisoformat(normalized["ends_at"]),
                attendees_count=normalized["attendees_count"],
            )
            db.add(event)
        db.commit()
    finally:
        db.close()
