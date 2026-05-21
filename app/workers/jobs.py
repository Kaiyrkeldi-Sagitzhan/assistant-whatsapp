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


def _get_or_create_user(db: Session, user_external_id: str) -> tuple[User, bool]:
    user_id = uuid.uuid5(USER_NAMESPACE, user_external_id)
    user = db.get(User, user_id)
    if user:
        return user, False

    user = User(id=user_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, True


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
        user, is_new_user = _get_or_create_user(db, phone)
        
        # Send welcome template for new users
        if is_new_user:
            try:
                client = WhatsAppMetaClient()
                asyncio.run(client.send_welcome_template(phone))
            except Exception as e:
                logger.error("Failed to send welcome template: %s", e)
        
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

        # Initialize context manager for message processing
        context_mgr = ConversationContext()
        
        # Store message context for potential multi-message tasks
        asyncio.run(context_mgr.store_message_context(str(user.id), text, {"intent": None, "title": None}))

        # Check for pending clarification
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

            if parsed.intent == "agenda_select":
                # Send agenda selection template
                try:
                    client = WhatsAppMetaClient()
                    asyncio.run(client.send_agenda_select_template(phone))
                    return
                except Exception as e:
                    logger.error("Failed to send agenda select template: %s", e)
                    # Fallback to text
                    confirmation = "📋 Выберите период:\n• День - задачи на сегодня\n• Неделя - план на 7 дней"

            elif parsed.intent == "daily_agenda":
                # Get tasks for today and send via template
                service = TaskService(db)
                tasks = service.list_open_tasks(user.id)
                
                # Filter tasks for today
                from app.core.time import resolve_timezone, now_utc
                local_tz = resolve_timezone(user.timezone)
                today = now_utc().astimezone(local_tz).date()
                
                today_tasks = []
                for task in tasks:
                    if task.due_at:
                        task_date = task.due_at.replace(tzinfo=timezone.utc).astimezone(local_tz).date()
                        if task_date == today:
                            today_tasks.append(task)
                
                # Sort by priority (high to low) then by time
                priority_order = {"high": 0, "medium": 1, "low": 2}
                today_tasks.sort(key=lambda t: (
                    priority_order.get(t.priority.value, 3),
                    t.due_at or datetime.max.replace(tzinfo=timezone.utc)
                ))
                
                # Format tasks list
                if not today_tasks:
                    tasks_list = "Нет задач на сегодня"
                else:
                    task_lines = []
                    for task in today_tasks:
                        time_str = ""
                        if task.due_at:
                            local_time = task.due_at.replace(tzinfo=timezone.utc).astimezone(local_tz)
                            time_str = local_time.strftime("%H:%M")
                        # Add priority indicator
                        priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢", "critical": "⭐"}.get(task.priority.value, "⚪")
                        task_lines.append(f"{priority_emoji} {task.title} ({time_str})" if time_str else f"{priority_emoji} {task.title}")
                    tasks_list = "\n".join(task_lines)
                
                # Send template
                try:
                    client = WhatsAppMetaClient()
                    asyncio.run(client.send_tasks_day_template(phone, tasks_list))
                    return
                except Exception as e:
                    logger.error("Failed to send tasks day template: %s", e)
                    # Fallback to text
                    if not today_tasks:
                        confirmation = "✅ Отлично! У вас нет задач на сегодня."
                    else:
                        confirmation = f"📋 Задачи на сегодня:\n{tasks_list}"

            elif parsed.intent == "weekly_plan":
                # Get tasks for the next 7 days
                service = TaskService(db)
                tasks = service.list_open_tasks(user.id)
                
                from app.core.time import resolve_timezone, now_utc
                local_tz = resolve_timezone(user.timezone)
                today = now_utc().astimezone(local_tz).date()
                
                # Group tasks by day
                from datetime import timedelta
                days_tasks = {}
                for i in range(7):
                    day_date = today + timedelta(days=i)
                    days_tasks[day_date] = []
                
                for task in tasks:
                    if task.due_at:
                        task_date = task.due_at.replace(tzinfo=timezone.utc).astimezone(local_tz).date()
                        if task_date in days_tasks:
                            days_tasks[task_date].append(task)
                
                # Format tasks list for each day with priority
                priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢", "critical": "⭐"}.get
                day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
                
                day_lines = []
                for i in range(7):
                    day_date = today + timedelta(days=i)
                    day_name = day_names[day_date.weekday()]
                    day_str = day_date.strftime("%d.%m")
                    
                    day_task_list = days_tasks[day_date]
                    # Sort by priority
                    priority_order = {"high": 0, "medium": 1, "low": 2, "critical": 0}
                    day_task_list.sort(key=lambda t: (
                        priority_order.get(t.priority.value, 3),
                        t.due_at or datetime.max.replace(tzinfo=timezone.utc)
                    ))
                    
                    if day_task_list:
                        task_parts = []
                        for task in day_task_list:
                            time_str = ""
                            if task.due_at:
                                local_time = task.due_at.replace(tzinfo=timezone.utc).astimezone(local_tz)
                                time_str = local_time.strftime("%H:%M")
                            task_parts.append(f"{priority_emoji(task.priority.value, '⚪')} {task.title} ({time_str})" if time_str else f"{priority_emoji(task.priority.value, '⚪')} {task.title}")
                        day_lines.append(f"{day_name}({day_str}): {' | '.join(task_parts)}")
                    else:
                        day_lines.append(f"{day_name}({day_str}):")
                
                tasks_list = " ||| ".join(day_lines)
                
                # Send template
                try:
                    client = WhatsAppMetaClient()
                    asyncio.run(client.send_tasks_week_template(phone, tasks_list))
                    return
                except Exception as e:
                    logger.error("Failed to send tasks week template: %s", e)
                    confirmation = _format_weekly_plan(agenda_service.generate_weekly_plan(str(user.id)))

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
                # Show all tasks directly
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
                # Update task - change due date/time
                if parsed.title and parsed.datetime:
                    service = TaskService(db)
                    # Extract just the task name (remove time specification like "на 13 30")
                    task_name = parsed.title
                    # Remove time patterns from task name
                    import re
                    task_name = re.sub(r'\s+на\s+\d{1,2}\s+\d{1,2}\s*$', '', task_name)
                    task_name = re.sub(r'\s+на\s+завтра.*$', '', task_name)
                    task_name = re.sub(r'\s+на\s+.*$', '', task_name)
                    
                    task = service.find_task_by_reference(user.id, task_name)
                    if task:
                        # Update the task's due date/time
                        task.due_at = parsed.datetime
                        # Use now_utc() from app.core.time
                        from app.core.time import now_utc
                        task.updated_at = now_utc()
                        db.commit()
                        db.refresh(task)
                        
                        # Format confirmation message
                        from app.core.time import resolve_timezone
                        local_tz = resolve_timezone(user.timezone)
                        local_due = task.due_at.replace(tzinfo=timezone.utc).astimezone(local_tz)
                        confirmation = f"✅ Задача обновлена: {task.title} → {local_due.strftime('%d.%m %H:%M')}"
                    else:
                        confirmation = f"❌ Задача не найдена: {task_name}"
                else:
                    confirmation = "❌ Укажите название задачи и новое время/дату"

            elif parsed.intent == "delete_task":
                # Delete task
                confirmation = (
                    f"🗑️ Функция удаления задач скоро будет готова!\n"
                    f"✅ Пока что отметьте задачу выполненной: 'выполнил {parsed.title}'\n"
                    f"🔄 Или просто игнорируйте её в списке задач."
                )

            elif parsed.intent == "unknown":
                # Send welcome template for messages that don't contain tasks
                logger.info("Message intent: %s - no task detected, sending welcome template", parsed.intent)
                try:
                    client = WhatsAppMetaClient()
                    asyncio.run(client.send_welcome_template(phone))
                    return  # Exit early, template already sent
                except Exception as e:
                    logger.error("Failed to send welcome template: %s", e)
                    # Fallback to text message
                    confirmation = "👋 Привет! Я ваш помощник по управлению задачами. Напишите 'помощь', чтобы узнать, что я умею."

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

                    # Format due date for template
                    due_date_display = "не указан"
                    if task.due_at:
                        from app.core.time import resolve_timezone
                        local_tz = resolve_timezone(user.timezone)
                        local_due_at = task.due_at.replace(tzinfo=timezone.utc).astimezone(local_tz)
                        due_date_display = local_due_at.strftime('%d.%m %H:%M')

                    # Send template
                    try:
                        client = WhatsAppMetaClient()
                        asyncio.run(client.send_task_created_template(phone, task.title, due_date_display))
                        return
                    except Exception as e:
                        logger.error("Failed to send task created template: %s", e)
                        # Fallback to text
                        due_time_display = "не указан"
                        if task.due_at:
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

                    # Format event time for template
                    event_date_display = "не указано"
                    if task.due_at:
                        from app.core.time import resolve_timezone
                        local_tz = resolve_timezone(user.timezone)
                        local_due_at = task.due_at.replace(tzinfo=timezone.utc).astimezone(local_tz)
                        event_date_display = local_due_at.strftime('%d.%m %H:%M')

                    # Send template
                    try:
                        client = WhatsAppMetaClient()
                        asyncio.run(client.send_task_created_template(phone, f"Событие: {parsed.title}", event_date_display))
                        return
                    except Exception as e:
                        logger.error("Failed to send event created template: %s", e)
                        # Fallback to text
                        event_time_display = "не указано"
                        if task.due_at:
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
                    # Fallback to welcome template
                    try:
                        client = WhatsAppMetaClient()
                        asyncio.run(client.send_welcome_template(phone))
                        return  # Exit early, template already sent
                    except Exception as template_error:
                        logger.error("Failed to send welcome template: %s", template_error)
                        # Try one more time
                        try:
                            client = WhatsAppMetaClient()
                            asyncio.run(client.send_welcome_template(phone))
                            return
                        except Exception:
                            pass  # Give up, no more fallbacks

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
