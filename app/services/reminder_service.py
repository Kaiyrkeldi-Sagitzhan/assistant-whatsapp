import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Union

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.time import now_utc
from app.db.models import Reminder, ReminderKind, ReminderStatus, Task, TaskPriority, TaskStatus

logger = logging.getLogger(__name__)


class ReminderService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_reminder(
        self,
        user_id: uuid.UUID,
        task_id: Union[uuid.UUID, None],
        remind_at: datetime,
        kind: ReminderKind,
    ) -> Reminder:
        reminder = Reminder(
            user_id=user_id,
            task_id=task_id,
            remind_at=remind_at,
            kind=kind,
            status=ReminderStatus.SCHEDULED,
        )
        self.db.add(reminder)
        self.db.commit()
        self.db.refresh(reminder)
        return reminder

    def get_due_reminders(self) -> list[Reminder]:
        """Get all reminders that are due to be sent."""
        now = now_utc()
        stmt = select(Reminder).where(
            and_(
                Reminder.status == ReminderStatus.SCHEDULED,
                Reminder.remind_at <= now,
            )
        )
        return list(self.db.scalars(stmt).all())

    def update_reminder_status(
        self, reminder_id: uuid.UUID, status: ReminderStatus
    ) -> Union[Reminder, None]:
        reminder = self.db.get(Reminder, reminder_id)
        if not reminder:
            return None

        reminder.status = status
        self.db.commit()
        self.db.refresh(reminder)
        return reminder

    def auto_create_reminders(self, task: Task) -> None:
        """Automatically create reminders based on task due_at and priority."""
        if not task.due_at:
            return

        user_id = task.user_id

        if task.priority in [TaskPriority.CRITICAL, TaskPriority.HIGH]:
            # Exact reminder at due time
            self.create_reminder(
                user_id=user_id,
                task_id=task.id,
                remind_at=task.due_at,
                kind=ReminderKind.EXACT,
            )

            # Pre-deadline reminder: 1 hour before
            self.create_reminder(
                user_id=user_id,
                task_id=task.id,
                remind_at=task.due_at - timedelta(hours=1),
                kind=ReminderKind.BEFORE_DEADLINE,
            )

    def get_overdue_tasks(self, user_id: uuid.UUID) -> list[Task]:
        """Get all overdue open tasks for a user."""
        now = now_utc()
        stmt = select(Task).where(
            and_(
                Task.user_id == user_id,
                Task.status == TaskStatus.OPEN,
                Task.due_at < now,
            )
        )
        return list(self.db.scalars(stmt).all())

    def get_user_tasks(self, user_id: uuid.UUID, status: Union[TaskStatus, None] = None) -> list[Task]:
        """Get all tasks for a user, optionally filtered by status."""
        now = now_utc()
        stmt = select(Task).where(Task.user_id == user_id)
        if status:
            stmt = stmt.where(Task.status == status)
        stmt = stmt.order_by(Task.priority.desc(), Task.due_at.asc().nullslast())
        return list(self.db.scalars(stmt).all())

    def get_user_open_tasks(self, user_id: uuid.UUID) -> list[Task]:
        """Get all open tasks for a user."""
        return self.get_user_tasks(user_id, TaskStatus.OPEN)

    def get_user_completed_tasks(self, user_id: uuid.UUID) -> list[Task]:
        """Get all completed tasks for a user."""
        return self.get_user_tasks(user_id, TaskStatus.DONE)

    def get_tasks_due_today(self, user_id: uuid.UUID) -> list[Task]:
        """Get all tasks due today for a user."""
        now = now_utc()
        # Calculate start and end of today in UTC
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        
        stmt = select(Task).where(
            and_(
                Task.user_id == user_id,
                Task.status == TaskStatus.OPEN,
                Task.due_at >= today_start,
                Task.due_at < today_end
            )
        ).order_by(Task.priority.desc(), Task.due_at.asc())
        return list(self.db.scalars(stmt).all())

    def get_overdue_tasks_with_reminders(self, user_id: uuid.UUID) -> list[Task]:
        """Get overdue tasks that haven't been reminded today."""
        now = now_utc()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get overdue open tasks
        stmt = select(Task).where(
            and_(
                Task.user_id == user_id,
                Task.status == TaskStatus.OPEN,
                Task.due_at < today_start
            )
        ).order_by(Task.due_at.asc())
        return list(self.db.scalars(stmt).all())

    def auto_create_reminders_for_all_tasks(self, task: Task) -> None:
        """Automatically create reminders for all tasks based on priority and due date."""
        if not task.due_at:
            return

        user_id = task.user_id
        now = now_utc()

        # Don't create reminders for past due dates
        if task.due_at < now:
            return

        # Create different types of reminders based on priority
        if task.priority in [TaskPriority.CRITICAL, TaskPriority.HIGH]:
            # Exact reminder at due time
            self.create_reminder(
                user_id=user_id,
                task_id=task.id,
                remind_at=task.due_at,
                kind=ReminderKind.EXACT,
            )

            # Pre-deadline reminder: 1 hour before
            self.create_reminder(
                user_id=user_id,
                task_id=task.id,
                remind_at=task.due_at - timedelta(hours=1),
                kind=ReminderKind.BEFORE_DEADLINE,
            )

            # Additional reminder for critical tasks: 1 day before
            if task.priority == TaskPriority.CRITICAL:
                self.create_reminder(
                    user_id=user_id,
                    task_id=task.id,
                    remind_at=task.due_at - timedelta(days=1),
                    kind=ReminderKind.BEFORE_DEADLINE,
                )

        elif task.priority == TaskPriority.MEDIUM:
            # Single reminder 2 hours before
            self.create_reminder(
                user_id=user_id,
                task_id=task.id,
                remind_at=task.due_at - timedelta(hours=2),
                kind=ReminderKind.BEFORE_DEADLINE,
            )

        else:  # LOW priority
            # Single reminder 1 day before (if due date is far enough)
            if task.due_at > now + timedelta(days=1):
                self.create_reminder(
                    user_id=user_id,
                    task_id=task.id,
                    remind_at=task.due_at - timedelta(days=1),
                    kind=ReminderKind.BEFORE_DEADLINE,
                )

    def format_reminder_text(self, reminder: Reminder, task: Union[Task, None] = None) -> str:
        """Format reminder text for user."""
        if reminder.kind == ReminderKind.OVERDUE:
            return f"⚠️ Просроченная задача: {task.title if task else 'Задача'}"
        elif reminder.kind == ReminderKind.MORNING_DIGEST:
            return "🌅 Доброе утро! Вот ваши приоритеты на сегодня..."
        elif reminder.kind == ReminderKind.EVENING_DIGEST:
            return "🌙 Вечерний отчет: что вы выполнили, что осталось..."
        elif reminder.kind == ReminderKind.EXACT:
            return f"⏰ Пора: {task.title if task else 'Задача'}"
        elif reminder.kind == ReminderKind.BEFORE_DEADLINE:
            if task and task.due_at and reminder.remind_at:
                delta = task.due_at - reminder.remind_at
                total_hours = int(delta.total_seconds() // 3600)
                total_days = total_hours // 24
                if total_days >= 1:
                    return f"📌 Через {total_days} дн.: {task.title}"
                elif total_hours >= 1:
                    return f"📌 Через {total_hours} час: {task.title}"
                else:
                    total_minutes = int(delta.total_seconds() // 60)
                    return f"📌 Через {total_minutes} мин: {task.title}"
            return f"📌 Напоминание: {task.title if task else 'Задача'}"
        return "📬 Напоминание"

    def create_custom_reminder(
        self,
        user_id: uuid.UUID,
        title: str,
        remind_at: datetime,
        description: Union[str, None] = None,
    ) -> Reminder:
        """Create a custom reminder not tied to a specific task."""
        reminder = Reminder(
            user_id=user_id,
            task_id=None,
            remind_at=remind_at,
            kind=ReminderKind.EXACT,
            status=ReminderStatus.SCHEDULED,
            description=description,
        )
        self.db.add(reminder)
        self.db.commit()
        self.db.refresh(reminder)
        return reminder

    def get_upcoming_custom_reminders(self, user_id: uuid.UUID, limit: int = 10) -> list[Reminder]:
        """Get upcoming custom reminders for a user."""
        now = now_utc()
        stmt = select(Reminder).where(
            and_(
                Reminder.user_id == user_id,
                Reminder.task_id.is_(None),  # Only custom reminders (not tied to tasks)
                Reminder.status == ReminderStatus.SCHEDULED,
                Reminder.remind_at >= now,
            )
        ).order_by(Reminder.remind_at.asc()).limit(limit)
        return list(self.db.scalars(stmt).all())

    def format_digest_text(self, user_id: uuid.UUID, digest_kind: ReminderKind) -> str:
        """Format digest text with actual task lists for morning/evening digests."""
        now = now_utc()
        
        if digest_kind == ReminderKind.MORNING_DIGEST:
            # Get today's tasks and overdue tasks for morning digest
            tasks_today = self.get_tasks_due_today(user_id)
            overdue_tasks = self.get_overdue_tasks(user_id)
            all_open_tasks = self.get_user_open_tasks(user_id)
            
            lines = ["🌅 Доброе утро! Вот ваши приоритеты на сегодня:\n"]
            
            if overdue_tasks:
                lines.append("🚨 ПРОСРОЧЕНО (срочно!):")
                for task in overdue_tasks[:5]:  # Limit to 5
                    lines.append(f"  ❌ {task.title} (дедлайн: {task.due_at.strftime('%d.%m %H:%M') if task.due_at else 'без срока'})")
                if len(overdue_tasks) > 5:
                    lines.append(f"  ... и еще {len(overdue_tasks) - 5} просроченных задач")
                lines.append("")
            
            if tasks_today:
                lines.append("📅 ЗАДАЧИ НА СЕГОДНЯ:")
                for task in sorted(tasks_today, key=lambda t: t.priority.value, reverse=True):
                    priority_emoji = {"critical": "🔥", "high": "⚡", "medium": "📌", "low": "📋"}.get(task.priority.value, "📋")
                    time_str = task.due_at.strftime('%H:%M') if task.due_at else "без срока"
                    lines.append(f"  {priority_emoji} {task.title} (до {time_str})")
                lines.append("")
            
            # Show other open tasks
            other_tasks = [t for t in all_open_tasks if t not in tasks_today and t not in overdue_tasks]
            if other_tasks:
                lines.append("📋 ДРУГИЕ АКТИВНЫЕ ЗАДАЧИ:")
                for task in other_tasks[:5]:  # Limit to 5
                    priority_emoji = {"critical": "🔥", "high": "⚡", "medium": "📌", "low": "📋"}.get(task.priority.value, "📋")
                    lines.append(f"  {priority_emoji} {task.title}")
                if len(other_tasks) > 5:
                    lines.append(f"  ... и еще {len(other_tasks) - 5} задач")
                lines.append("")
            
            if not overdue_tasks and not tasks_today and not other_tasks:
                lines.append("✅ Отлично! У вас нет задач на сегодня!")
            
            lines.append(f"\nВсего активных задач: {len(all_open_tasks)}")
            return "\n".join(lines)
        
        elif digest_kind == ReminderKind.EVENING_DIGEST:
            # Get completed tasks and remaining tasks for evening digest
            completed_today = self.get_user_completed_tasks(user_id)
            remaining_tasks = self.get_user_open_tasks(user_id)
            
            lines = ["🌙 Вечерний отчет:\n"]
            
            if completed_today:
                lines.append("✅ ВЫПОЛНЕНО ЗА ДЕНЬ:")
                for task in completed_today[-10:]:  # Show last 10 completed
                    lines.append(f"  ✅ {task.title}")
                if len(completed_today) > 10:
                    lines.append(f"  ... и еще {len(completed_today) - 10} выполненных задач")
                lines.append("")
            else:
                lines.append("📭 Сегодня не было выполнено задач\n")
            
            if remaining_tasks:
                lines.append("📝 ОСТАЛОСЬ ДОСДЕЛАТЬ:")
                overdue = [t for t in remaining_tasks if t.due_at and t.due_at < now]
                urgent = [t for t in remaining_tasks if t not in overdue and t.priority in [TaskPriority.CRITICAL, TaskPriority.HIGH]]
                normal = [t for t in remaining_tasks if t not in overdue and t not in urgent]
                
                if overdue:
                    lines.append("  🚨 Просроченные:")
                    for task in overdue[:5]:
                        lines.append(f"    ❌ {task.title}")
                
                if urgent:
                    lines.append("  ⚡ Важные:")
                    for task in urgent[:5]:
                        lines.append(f"    ⚡ {task.title}")
                
                if normal:
                    lines.append("  📋 Остальные:")
                    for task in normal[:5]:
                        lines.append(f"    📋 {task.title}")
                
                if len(remaining_tasks) > 15:
                    lines.append(f"  ... и еще {len(remaining_tasks) - 15} задач")
                lines.append("")
            else:
                lines.append("🎉 Отличная работа! Все задачи выполнены!\n")
            
            lines.append(f"Всего активных задач: {len(remaining_tasks)}")
            return "\n".join(lines)
        
        return "📬 Напоминание"

    def send_first_reminder(self, task: Task) -> None:
        """Send immediate first reminder about a newly created task."""
        from app.db.models import InboundMessage, InboundChannel
        from app.integrations.whatsapp_meta import WhatsAppMetaClient
        from app.core.config import get_settings
        import asyncio
        
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
            logger.warning(f"No WhatsApp phone found for user {task.user_id}, skipping first reminder")
            return
        
        # Format first reminder text
        due_info = ""
        if task.due_at:
            from app.core.time import resolve_timezone
            local_tz = resolve_timezone(task.user.timezone if hasattr(task, 'user') and task.user else "Asia/Almaty")
            local_due_at = task.due_at.replace(tzinfo=timezone.utc).astimezone(local_tz)
            due_info = f"\n📅 Срок: {local_due_at.strftime('%d.%m %H:%M')}"
        
        priority_emoji = {"critical": "🔥", "high": "⚡", "medium": "📌", "low": "📋"}.get(task.priority.value, "📋")
        text = f"✅ Задача создана{priority_emoji}\n\n📝 {task.title}{due_info}\n\n💪 Выполнить: 'выполнил {task.title}'"
        
        try:
            client = WhatsAppMetaClient()
            asyncio.run(client.send_text(phone, text))
            logger.info(f"First reminder sent for task {task.id} to user {task.user_id}")
        except Exception as e:
            logger.error(f"Failed to send first reminder for task {task.id}: {e}")
