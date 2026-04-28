import logging
import uuid
from typing import Union

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Task, TaskPriority, TaskStatus, User, ReminderKind, CalendarEvent
from app.core.time import now_utc
from app.schemas.task import TaskCreate, TaskUpdate

logger = logging.getLogger(__name__)


class TaskService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_task(self, payload: TaskCreate, parsed_intent: str = "create_task") -> Task:
        user = self.db.get(User, payload.user_id)
        if user is None:
            user = User(id=payload.user_id)
            self.db.add(user)
            self.db.flush()

        task = Task(
            user_id=payload.user_id,
            title=payload.title,
            description=payload.description,
            due_at=payload.due_at,
            priority=payload.priority,
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        
        # Auto-create reminders for the task
        from app.services.reminder_service import ReminderService
        reminder_service = ReminderService(self.db)
        reminder_service.auto_create_reminders_for_all_tasks(task)
        
        # Send first reminder about the created task
        try:
            # Use hello_world template for events, default for tasks
            if parsed_intent == "create_event":
                reminder_service.send_first_reminder(task, template="hello_world")
            else:
                reminder_service.send_first_reminder(task, template="default")
        except Exception as e:
            logger.warning(f"Failed to send first reminder for task {task.id}: {e}")
        
        return task

    def list_open_tasks(self, user_id: uuid.UUID) -> list[Task]:
        stmt = select(Task).where(Task.user_id == user_id, Task.status == TaskStatus.OPEN)
        return list(self.db.scalars(stmt).all())

    def update_task(self, task_id: uuid.UUID, payload: TaskUpdate) -> Union[Task, None]:
        task = self.db.get(Task, task_id)
        if not task:
            return None

        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(task, field, value)
        task.updated_at = now_utc()

        self.db.commit()
        self.db.refresh(task)
        return task

    def complete_task(self, task_id: uuid.UUID) -> Union[Task, None]:
        task = self.db.get(Task, task_id)
        if not task:
            return None

        task.status = TaskStatus.DONE
        task.completed_at = now_utc()
        task.updated_at = now_utc()
        self.db.commit()
        self.db.refresh(task)
        return task

    @staticmethod
    def map_priority(priority: str) -> TaskPriority:
        mapping = {
            "low": TaskPriority.LOW,
            "medium": TaskPriority.MEDIUM,
            "high": TaskPriority.HIGH,
            "critical": TaskPriority.CRITICAL,
        }
        return mapping.get(priority.lower(), TaskPriority.MEDIUM)

    def send_task_notification(self, task_id: uuid.UUID, custom_message: str = None) -> bool:
        """
        Send a WhatsApp notification about a specific task to the user.
        
        Args:
            task_id: ID of the task to notify about
            custom_message: Optional custom message to include
            
        Returns:
            True if sent successfully, False otherwise
        """
        from app.integrations.whatsapp_meta import WhatsAppMetaClient
        from app.db.models import InboundMessage, InboundChannel
        from app.core.config import get_settings
        import asyncio
        
        task = self.db.get(Task, task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return False
        
        try:
            # Get user's WhatsApp phone
            stmt = (
                select(InboundMessage)
                .where(
                    InboundMessage.user_id == task.user_id,
                    InboundMessage.channel == InboundChannel.WHATSAPP,
                )
                .order_by(InboundMessage.received_at.desc())
                .limit(1)
            )
            inbound = self.db.scalars(stmt).first()
            
            settings = get_settings()
            phone = None
            if inbound:
                payload = inbound.parse_result or {}
                if isinstance(payload, dict):
                    phone = payload.get("phone")
            
            if not phone:
                phone = settings.whatsapp_test_recipient
            
            if not phone:
                logger.warning(f"No WhatsApp phone found for user {task.user_id}")
                return False
            
            # Build notification message
            priority_emoji = {"critical": "🔥", "high": "⚡", "medium": "📌", "low": "📋"}.get(task.priority.value, "📋")
            
            lines = [f"{priority_emoji} Напоминание о задаче"]
            lines.append(f"📝 {task.title}")
            
            if task.description:
                lines.append(f"📄 {task.description[:100]}")
            
            if task.due_at:
                from app.core.time import resolve_timezone
                local_tz = resolve_timezone(task.user.timezone if hasattr(task, 'user') and task.user else "Asia/Almaty")
                local_due = task.due_at.replace(tzinfo=timezone.utc).astimezone(local_tz)
                lines.append(f"⏰ Срок: {local_due.strftime('%d.%m %H:%M')}")
            
            lines.append(f"Статус: {task.status.value}")
            
            if custom_message:
                lines.append(f"\n💬 {custom_message}")
            
            lines.append("\n💪 Выполнить: 'выполнил {task.title}'")
            
            text = "\n".join(lines)
            
            # Send via WhatsApp
            client = WhatsAppMetaClient()
            asyncio.run(client.send_text(phone, text))
            logger.info(f"Task notification sent for task {task_id} to user {task.user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send task notification for {task_id}: {e}")
            return False

    def send_event_notification(self, event_id: uuid.UUID, reminder_minutes: int = 30) -> bool:
        """
        Send a WhatsApp notification about an upcoming calendar event.
        
        Args:
            event_id: ID of the calendar event
            reminder_minutes: Minutes before event to send reminder
            
        Returns:
            True if sent successfully, False otherwise
        """
        from app.integrations.whatsapp_meta import WhatsAppMetaClient
        from app.db.models import InboundMessage, InboundChannel
        from app.core.config import get_settings
        import asyncio
        from datetime import timedelta
        
        event = self.db.get(CalendarEvent, event_id)
        if not event:
            logger.error(f"Event {event_id} not found")
            return False
        
        try:
            # Get user's WhatsApp phone
            stmt = (
                select(InboundMessage)
                .where(
                    InboundMessage.user_id == event.user_id,
                    InboundMessage.channel == InboundChannel.WHATSAPP,
                )
                .order_by(InboundMessage.received_at.desc())
                .limit(1)
            )
            inbound = self.db.scalars(stmt).first()
            
            settings = get_settings()
            phone = None
            if inbound:
                payload = inbound.parse_result or {}
                if isinstance(payload, dict):
                    phone = payload.get("phone")
            
            if not phone:
                phone = settings.whatsapp_test_recipient
            
            if not phone:
                logger.warning(f"No WhatsApp phone found for user {event.user_id}")
                return False
            
            # Calculate reminder time
            reminder_time = event.starts_at - timedelta(minutes=reminder_minutes)
            
            # Build notification message
            lines = ["📅 Напоминание о встрече"]
            lines.append(f"📌 {event.title}")
            
            if event.description:
                lines.append(f"📄 {event.description[:100]}")
            
            from app.core.time import resolve_timezone
            local_tz = resolve_timezone(event.user.timezone if hasattr(event, 'user') and event.user else "Asia/Almaty")
            local_start = event.starts_at.replace(tzinfo=timezone.utc).astimezone(local_tz)
            local_end = event.ends_at.replace(tzinfo=timezone.utc).astimezone(local_tz)
            
            lines.append(f"⏰ Когда: {local_start.strftime('%d.%m %H:%M')} - {local_end.strftime('%H:%M')}")
            lines.append(f"⏳ Напомню за {reminder_minutes} минут")
            
            if event.attendees_count > 0:
                lines.append(f"👥 Участников: {event.attendees_count}")
            
            text = "\n".join(lines)
            
            # Send via WhatsApp
            client = WhatsAppMetaClient()
            asyncio.run(client.send_text(phone, text))
            logger.info(f"Event notification sent for event {event_id} to user {event.user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send event notification for {event_id}: {e}")
            return False

    def broadcast_message(self, user_ids: list[uuid.UUID], message: str, subject: str = None) -> dict:
        """
        Send a broadcast message to multiple users via WhatsApp.
        
        Args:
            user_ids: List of user UUIDs to send message to
            message: Message content to send
            subject: Optional subject/title for the message
            
        Returns:
            Dictionary with success/failure counts
        """
        from app.integrations.whatsapp_meta import WhatsAppMetaClient
        from app.db.models import InboundMessage, InboundChannel
        from app.core.config import get_settings
        import asyncio
        
        results = {"success": 0, "failed": 0, "errors": []}
        
        for user_id in user_ids:
            try:
                # Get user's WhatsApp phone
                stmt = (
                    select(InboundMessage)
                    .where(
                        InboundMessage.user_id == user_id,
                        InboundMessage.channel == InboundChannel.WHATSAPP,
                    )
                    .order_by(InboundMessage.received_at.desc())
                    .limit(1)
                )
                inbound = self.db.scalars(stmt).first()
                
                settings = get_settings()
                phone = None
                if inbound:
                    payload = inbound.parse_result or {}
                    if isinstance(payload, dict):
                        phone = payload.get("phone")
                
                if not phone:
                    phone = settings.whatsapp_test_recipient
                
                if not phone:
                    logger.warning(f"No WhatsApp phone found for user {user_id}")
                    results["failed"] += 1
                    results["errors"].append(f"User {user_id}: No phone number")
                    continue
                
                # Build message
                lines = []
                if subject:
                    lines.append(f"📢 {subject}")
                    lines.append("")
                
                lines.append(message)
                lines.append("")
                lines.append("💡 Это автоматическое сообщение от вашего помощника")
                
                text = "\n".join(lines)
                
                # Send via WhatsApp
                client = WhatsAppMetaClient()
                asyncio.run(client.send_text(phone, text))
                results["success"] += 1
                logger.info(f"Broadcast message sent to user {user_id}")
                
            except Exception as e:
                logger.error(f"Failed to send broadcast to user {user_id}: {e}")
                results["failed"] += 1
                results["errors"].append(f"User {user_id}: {str(e)}")
        
        return results

    def send_task_digest(self, user_id: uuid.UUID, digest_type: str = "daily") -> bool:
        """
        Send a digest of tasks to user via WhatsApp.
        
        Args:
            user_id: User UUID
            digest_type: Type of digest - "daily", "weekly", or "overdue"
            
        Returns:
            True if sent successfully, False otherwise
        """
        from app.integrations.whatsapp_meta import WhatsAppMetaClient
        from app.db.models import InboundMessage, InboundChannel
        from app.core.config import get_settings
        import asyncio
        from datetime import datetime, timedelta, timezone
        
        try:
            # Get user's WhatsApp phone
            stmt = (
                select(InboundMessage)
                .where(
                    InboundMessage.user_id == user_id,
                    InboundMessage.channel == InboundChannel.WHATSAPP,
                )
                .order_by(InboundMessage.received_at.desc())
                .limit(1)
            )
            inbound = self.db.scalars(stmt).first()
            
            settings = get_settings()
            phone = None
            if inbound:
                payload = inbound.parse_result or {}
                if isinstance(payload, dict):
                    phone = payload.get("phone")
            
            if not phone:
                phone = settings.whatsapp_test_recipient
            
            if not phone:
                logger.warning(f"No WhatsApp phone found for user {user_id}")
                return False
            
            # Get tasks based on digest type
            now = now_utc()
            
            if digest_type == "daily":
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                today_end = today_start + timedelta(days=1)
                
                stmt = select(Task).where(
                    Task.user_id == user_id,
                    Task.status == TaskStatus.OPEN,
                    Task.due_at >= today_start,
                    Task.due_at < today_end
                )
                tasks = list(self.db.scalars(stmt).all())
                title = "📅 Дневной дайджест задач"
                
            elif digest_type == "weekly":
                week_start = now - timedelta(days=now.weekday())
                week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
                week_end = week_start + timedelta(days=7)
                
                stmt = select(Task).where(
                    Task.user_id == user_id,
                    Task.status == TaskStatus.OPEN,
                    Task.due_at >= week_start,
                    Task.due_at < week_end
                )
                tasks = list(self.db.scalars(stmt).all())
                title = "📆 Недельный дайджест задач"
                
            elif digest_type == "overdue":
                stmt = select(Task).where(
                    Task.user_id == user_id,
                    Task.status == TaskStatus.OPEN,
                    Task.due_at < now
                )
                tasks = list(self.db.scalars(stmt).all())
                title = "❌ Просроченные задачи"
                
            else:
                logger.error(f"Invalid digest type: {digest_type}")
                return False
            
            # Build message
            lines = [title, ""]
            
            if not tasks:
                if digest_type == "overdue":
                    lines.append("✅ Нет просроченных задач! Отличная работа!")
                else:
                    lines.append("✅ Нет задач на этот период!")
            else:
                # Group by priority
                high = [t for t in tasks if t.priority == TaskPriority.HIGH or t.priority == TaskPriority.CRITICAL]
                medium = [t for t in tasks if t.priority == TaskPriority.MEDIUM]
                low = [t for t in tasks if t.priority == TaskPriority.LOW]
                
                if high:
                    lines.append(f"🔥 Важные ({len(high)}):")
                    for task in high[:5]:
                        lines.append(f"  • {task.title}")
                        if task.due_at:
                            lines.append(f"    до {task.due_at.strftime('%d.%m %H:%M')}")
                    if len(high) > 5:
                        lines.append(f"  ... и еще {len(high) - 5}")
                    lines.append("")
                
                if medium:
                    lines.append(f"⚡ Средние ({len(medium)}):")
                    for task in medium[:5]:
                        lines.append(f"  • {task.title}")
                    if len(medium) > 5:
                        lines.append(f"  ... и еще {len(medium) - 5}")
                    lines.append("")
                
                if low:
                    lines.append(f"📋 Низкие ({len(low)}):")
                    for task in low[:3]:
                        lines.append(f"  • {task.title}")
                    if len(low) > 3:
                        lines.append(f"  ... и еще {len(low) - 3}")
                    lines.append("")
                
                lines.append(f"Всего: {len(tasks)} задач")
            
            text = "\n".join(lines)
            
            # Send via WhatsApp
            client = WhatsAppMetaClient()
            asyncio.run(client.send_text(phone, text))
            logger.info(f"{digest_type} digest sent to user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send {digest_type} digest to user {user_id}: {e}")
            return False
