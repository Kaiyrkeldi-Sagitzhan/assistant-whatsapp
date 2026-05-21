"""
WhatsApp Listener Module

This module provides functions to listen for incoming WhatsApp messages
and process them through the existing pipeline, including task creation
and notifications.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable, Any, Dict, Any as AnyType

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    InboundChannel,
    InboundMessage,
    Task,
    TaskPriority,
    TaskStatus,
    SourceType,
    User,
)
from app.db.session import SessionLocal
from app.integrations.whatsapp_meta import WhatsAppMetaClient
from app.services.nlp_pipeline import NLPPipeline
from app.services.context_manager import ConversationContext
from app.services.task_service import TaskService
from app.services.reminder_service import ReminderService
from app.workers.jobs import _get_or_create_user, _store_inbound
from app.core.config import get_settings

logger = logging.getLogger(__name__)


# Type for message handler callback
MessageCallback = Callable[[str, str, dict], Awaitable[Any]]


def _normalize_recipient_phone(phone: str) -> str:
    """Normalize phone number to format for sending."""
    if phone.startswith('7777'):
        return '78777' + phone[4:]
    elif phone.startswith('777'):
        return '7877' + phone[3:]
    elif phone.startswith('77'):
        return '787' + phone[2:]
    return phone


class WhatsAppListener:
    """
    Listens for incoming WhatsApp messages and processes them.
    
    This can be used in two modes:
    1. Webhook mode: Messages are received via webhook endpoint
    2. Polling mode: Messages are polled from a queue or database
    """
    
    def __init__(self, on_message: Optional[MessageCallback] = None, demo_mode: bool = False):
        """
        Initialize the WhatsApp listener.
        
        Args:
            on_message: Optional callback to handle incoming messages.
                       Signature: async def callback(text: str, phone: str, metadata: dict)
            demo_mode: If True, don't send actual WhatsApp messages (for testing)
        """
        self.on_message = on_message
        self._running = False
        self._client = WhatsAppMetaClient()
        self.demo_mode = demo_mode
    
    async def process_message(
        self,
        text: str,
        phone: str,
        external_message_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Process an incoming WhatsApp message with full pipeline.
        
        Args:
            text: The message text
            phone: Sender's phone number
            external_message_id: Unique message ID from WhatsApp
            metadata: Additional metadata from the webhook
            
        Returns:
            dict with processing results
        """
        db = SessionLocal()
        try:
            # Get or create user, check if new
            user, is_new_user = _get_or_create_user(db, phone)
            
            # Send welcome template for new users
            if is_new_user and not self.demo_mode:
                try:
                    await self._client.send_welcome_template(phone)
                except Exception as e:
                    logger.error("Failed to send welcome template: %s", e)
            
            # Store inbound message
            if not _store_inbound(
                db,
                channel=InboundChannel.WHATSAPP,
                external_message_id=external_message_id or f"msg_{uuid.uuid4()}",
                user_id=user.id,
                raw_text=text,
                parse_result={"phone": phone, "metadata": metadata or {}},
            ):
                logger.warning("Failed to store inbound message for %s", phone)
            
            # Parse message to determine intent
            pipeline = NLPPipeline()
            parsed = await pipeline.parse_message(text, user.timezone, user_id=str(user.id))
            
            logger.info(
                "Parsed message from %s: intent='%s', title='%s'",
                phone, parsed.intent, parsed.title
            )
            
            # Check for pending clarification
            context_mgr = ConversationContext()
            pending_context = await context_mgr.consume_clarification(str(user.id), text)
            
            # Generate confirmation response
            confirmation = await self._generate_confirmation(
                parsed, user, pending_context, text, pipeline, db, phone
            )
            
            # Send response via WhatsApp (skip for create_task - template already sent)
            if parsed.intent != "create_task":
                await self._send_response(phone, confirmation)
            
            # Call the callback if provided
            if self.on_message:
                await self.on_message(text, phone, parsed.__dict__)
            
            return {
                "status": "processed",
                "user_id": str(user.id),
                "intent": parsed.intent,
                "title": parsed.title,
                "description": parsed.description,
                "datetime": str(parsed.datetime) if parsed.datetime else None,
                "needs_clarification": parsed.needs_clarification,
                "clarification_question": parsed.clarification_question,
                "confirmation": confirmation,
            }
            
        except Exception as e:
            logger.error("Error processing message from %s: %s", phone, e)
            return {"status": "error", "error": str(e)}
        finally:
            db.close()
    
    async def _generate_confirmation(
        self,
        parsed,
        user: User,
        pending_context: Optional[dict],
        text: str,
        pipeline: NLPPipeline,
        db: Session,
        phone: str,
    ) -> str:
        """Generate a confirmation response based on the parsed message."""
        if pending_context:
            # Handle clarification response using the new process_clarification_response method
            clarification_result = pipeline.process_clarification_response(
                clarification_type=pending_context["clarification_type"],
                clarification_response=text,
                original_text=pending_context["original_text"],
                parsed_title=pending_context["parsed_title"],
                parsed_description=pending_context["parsed_description"],
                partial_data=pending_context.get("partial_data", {})
            )
            
            # Create the task with the combined information
            service = TaskService(db)
            task = service.create_task(
                type('TaskCreate', (), {
                    'user_id': user.id,
                    'title': clarification_result["title"],
                    'description': clarification_result["description"],
                    'due_at': clarification_result["datetime"],
                    'priority': TaskPriority.MEDIUM,
                })(),
                parsed_intent="create_task"
            )
            
            # Update source info
            db.query(Task).filter(Task.id == task.id).update({
                Task.source_type: SourceType.WHATSAPP,
                Task.source_ref: f"listener_{uuid.uuid4()}",
            })
            db.commit()
            
            # Auto-create reminders
            reminder_service = ReminderService(db)
            reminder_service.auto_create_reminders(task)
            
            # Format due date
            due_time_display = "не указан"
            if task.due_at:
                from app.core.time import resolve_timezone
                local_tz = resolve_timezone(user.timezone)
                local_due = task.due_at.replace(tzinfo=timezone.utc).astimezone(local_tz)
                due_time_display = local_due.strftime('%d.%m %H:%M')
            
            return f"✅ Задача создана: {task.title} (срок: {due_time_display})"
        
        if parsed.intent == "create_task":
            if parsed.needs_clarification:
                # Store clarification context
                context_mgr = ConversationContext()
                await context_mgr.set_pending_clarification(
                    user_id=str(user.id),
                    original_text=text,
                    parsed_title=parsed.title,
                    parsed_description=parsed.description,
                    clarification_type=parsed.clarification_type,
                    clarification_question=parsed.clarification_question,
                )
                return parsed.clarification_question
            else:
                # Create the task
                service = TaskService(db)
                task = service.create_task(
                    type('TaskCreate', (), {
                        'user_id': user.id,
                        'title': parsed.title,
                        'description': parsed.description,
                        'due_at': parsed.datetime,
                        'priority': TaskPriority.MEDIUM,
                    })(),
                    parsed_intent=parsed.intent
                )
                
                # Update source info
                db.query(Task).filter(Task.id == task.id).update({
                    Task.source_type: SourceType.WHATSAPP,
                    Task.source_ref: f"listener_{uuid.uuid4()}",
                })
                db.commit()
                
                # Auto-create reminders
                reminder_service = ReminderService(db)
                reminder_service.auto_create_reminders(task)
                
                # Format due date
                due_time_display = "не указан"
                if task.due_at:
                    from app.core.time import resolve_timezone
                    local_tz = resolve_timezone(user.timezone)
                    local_due = task.due_at.replace(tzinfo=timezone.utc).astimezone(local_tz)
                    due_time_display = local_due.strftime('%d.%m %H:%M')
                
                # Send task created template (skip in demo mode)
                if not self.demo_mode:
                    try:
                        await self._client.send_task_created_template(phone, task.title, due_time_display)
                    except Exception as e:
                        logger.error("Failed to send task created template: %s", e)
                
                return f"✅ Задача создана: {task.title}"
        
        elif parsed.intent == "list_tasks":
            service = TaskService(SessionLocal())
            tasks = service.list_open_tasks(user.id)
            if not tasks:
                return "✅ У вас нет активных задач."
            # Format task list with priority
            priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢", "critical": "⭐"}.get
            lines = [f"📋 У вас {len(tasks)} активных задач:"]
            for task in tasks[:5]:
                lines.append(f"  {priority_emoji(task.priority.value, '⚪')} {task.title}")
            return "\n".join(lines)
        
        elif parsed.intent == "agenda_select":
            # Send agenda selection template
            if not self.demo_mode:
                try:
                    await self._client.send_agenda_select_template(phone)
                    return "📋 Выберите период для просмотра задач"
                except Exception as e:
                    logger.error("Failed to send agenda select template: %s", e)
            return "📋 Выберите период: День, Неделя или Месяц"

        elif parsed.intent == "help":
            return (
                "🤖 Я ваш умный помощник по управлению задачами!\n\n"
                "📝 УМЕЮ СОЗДАВАТЬ ЗАДАЧИ:\n"
                "• 'Купить молоко завтра в 10 утра'\n"
                "• 'Встреча с клиентом в пятницу 15:00'\n\n"
                "📋 УМЕЮ ПОКАЗЫВАТЬ ЗАДАЧИ:\n"
                "• 'мои задачи' - список всех активных задач\n"
                "• 'повестка' - расписание на сегодня\n\n"
                "✅ УМЕЮ ОТМЕЧАТЬ ВЫПОЛНЕНИЕ:\n"
                "• 'выполнил [название задачи]'\n\n"
                "🔄 УМЕЮ ОБНОВЛЯТЬ ЗАДАЧИ:\n"
                "• 'обнови дату [название] на завтра'\n"
                "• 'поменяй время [название] на 15:00'\n"
                "• 'обнови приоритет [название] на высокий'"
            )
        
        elif parsed.intent == "update_date":
            if parsed.title:
                service = TaskService(db)
                task = service.update_task_date(user.id, parsed.title, parsed.datetime)
                if task:
                    from app.core.time import resolve_timezone
                    local_tz = resolve_timezone(user.timezone)
                    local_due = task.due_at.replace(tzinfo=timezone.utc).astimezone(local_tz)
                    return f"✅ Дата обновлена: {task.title} → {local_due.strftime('%d.%m %H:%M')}"
                else:
                    return f"❌ Задача не найдена: {parsed.title}"
            return "❌ Укажите название задачи и новую дату"
        
        elif parsed.intent == "update_time":
            if parsed.title and parsed.datetime:
                service = TaskService(db)
                task = service.update_task_time(user.id, parsed.title, parsed.datetime)
                if task:
                    from app.core.time import resolve_timezone
                    local_tz = resolve_timezone(user.timezone)
                    local_due = task.due_at.replace(tzinfo=timezone.utc).astimezone(local_tz)
                    return f"✅ Время обновлено: {task.title} → {local_due.strftime('%H:%M')}"
                else:
                    return f"❌ Задача не найдена: {parsed.title}"
            return "❌ Укажите название задачи и новое время"
        
        elif parsed.intent == "update_task":
            if parsed.title and parsed.datetime:
                service = TaskService(db)
                task = service.update_task_time(user.id, parsed.title, parsed.datetime)
                if task:
                    from app.core.time import resolve_timezone
                    local_tz = resolve_timezone(user.timezone)
                    local_due = task.due_at.replace(tzinfo=timezone.utc).astimezone(local_tz)
                    return f"✅ Время обновлено: {task.title} → {local_due.strftime('%H:%M')}"
                else:
                    return f"❌ Задача не найдена: {parsed.title}"
            return "❌ Укажите название задачи и новое время"
        
        elif parsed.intent == "update_priority":
            if parsed.title:
                service = TaskService(db)
                task = service.update_task_priority(user.id, parsed.title, parsed.priority or "medium")
                if task:
                    priority_emoji = {"critical": "🔥", "high": "⚡", "medium": "📌", "low": "📋"}.get(task.priority.value, "📋")
                    return f"✅ Приоритет обновлен: {task.title} {priority_emoji}"
                else:
                    return f"❌ Задача не найдена: {parsed.title}"
            return "❌ Укажите название задачи и новый приоритет"
        
        elif parsed.intent == "complete_task":
            if parsed.title:
                service = TaskService(db)
                task = service.find_task_by_reference(user.id, parsed.title)
                if task:
                    completed_task = service.complete_task(task.id)
                    if completed_task:
                        return f"✅ Задача выполнена: {completed_task.title}"
                    else:
                        return f"❌ Не удалось отметить задачу выполненной: {parsed.title}"
                else:
                    return f"❌ Задача не найдена: {parsed.title}"
            else:
                return "❌ Укажите название задачи, которую вы выполнили"
        
        elif parsed.intent == "unknown":
            # Send welcome template for messages that don't contain tasks
            if not self.demo_mode:
                try:
                    await self._client.send_welcome_template(phone)
                    return "👋 Привет! Я ваш помощник по управлению задачами."
                except Exception as e:
                    logger.error("Failed to send welcome template: %s", e)
            return "👋 Привет! Я ваш помощник по управлению задачами. Напишите 'помощь', чтобы узнать, что я умею."
        
        else:
            return f"🤖 Обработано: {parsed.intent}\n📝 {parsed.title or text}"
    
    async def _send_response(self, phone: str, message: str) -> None:
        """Send a response message via WhatsApp."""
        if self.demo_mode:
            # Demo mode: just log, don't actually send
            logger.info("[Demo] Would send to %s: %s", phone, message[:50])
            return
            
        try:
            recipient = _normalize_recipient_phone(phone)
            await self._client.send_text(recipient, message)
            logger.info("Response sent to %s", recipient)
        except Exception as e:
            logger.error("Failed to send response: %s", e)
    
    async def start_polling(
        self,
        poll_interval: float = 5.0,
        max_messages: int = 100,
    ) -> None:
        """
        Start polling for messages.
        
        This is a simple polling implementation. In production, you would
        typically use webhooks instead.
        
        Args:
            poll_interval: Seconds between polls
            max_messages: Maximum messages to process per poll
        """
        self._running = True
        logger.info("Starting WhatsApp listener polling (interval: %ss)", poll_interval)
        
        while self._running:
            try:
                await asyncio.sleep(poll_interval)
            except asyncio.CancelledError:
                logger.info("Polling cancelled")
                break
            except Exception as e:
                logger.error("Error in polling loop: %s", e)
                await asyncio.sleep(poll_interval)
    
    def stop(self) -> None:
        """Stop the listener."""
        self._running = False
        logger.info("WhatsApp listener stopped")


async def listen_for_messages(
    on_message: MessageCallback,
    poll_interval: float = 5.0,
) -> None:
    """
    Convenience function to start listening for messages.
    
    Args:
        on_message: Callback to handle incoming messages
        poll_interval: Seconds between polls
    """
    listener = WhatsAppListener(on_message=on_message)
    await listener.start_polling(poll_interval=poll_interval)


def create_message_handler(
    send_response: bool = True,
) -> MessageCallback:
    """
    Create a message handler with default processing logic.
    
    Args:
        send_response: Whether to send a response back via WhatsApp
        
    Returns:
        A message handler callback
    """
    async def handler(text: str, phone: str, parsed: dict) -> None:
        logger.info("Handling message from %s: %s", phone, text)
        
        if send_response:
            try:
                client = WhatsAppMetaClient()
                recipient = _normalize_recipient_phone(phone)
                await client.send_text(recipient, f"Получено: {text[:50]}...")
            except Exception as e:
                logger.error("Failed to send response: %s", e)
    
    return handler