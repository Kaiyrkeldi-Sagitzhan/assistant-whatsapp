import asyncio
import logging
import uuid
from typing import Any, Union

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.db.models import InboundChannel, InboundMessage, ReminderStatus, Task, TaskStatus
from app.core.config import get_settings
from app.core.time import now_utc
from app.integrations.whatsapp_meta import WhatsAppMetaClient
from app.db.session import SessionLocal
from app.services.reminder_service import ReminderService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.reminders.send_due_reminders")
def send_due_reminders() -> None:
    """Send all due reminders."""
    db = SessionLocal()
    try:
        reminder_service = ReminderService(db)
        due_reminders = reminder_service.get_due_reminders()

        for reminder in due_reminders:
            try:
                task = db.get(Task, reminder.task_id) if reminder.task_id else None
                text = reminder_service.format_reminder_text(reminder, task)

                _send_reminder_to_user(db, reminder.user_id, text)

                reminder_service.update_reminder_status(reminder.id, ReminderStatus.SENT)
            except Exception:
                reminder_service.update_reminder_status(reminder.id, ReminderStatus.FAILED)
    finally:
        db.close()


@celery_app.task(name="app.workers.reminders.send_morning_digest")
def send_morning_digest() -> None:
    """Send morning digest to all users with open tasks."""
    db = SessionLocal()
    try:
        from app.db.models import User
        
        reminder_service = ReminderService(db)
        
        # Get all users who have open tasks
        users = db.query(User).join(User.tasks).filter(
            Task.status == TaskStatus.OPEN
        ).distinct().all()
        
        for user in users:
            try:
                # Check if user has any tasks due today or overdue
                tasks_today = reminder_service.get_tasks_due_today(user.id)
                overdue_tasks = reminder_service.get_overdue_tasks(user.id)
                
                if tasks_today or overdue_tasks:
                    text = reminder_service.format_digest_text(user.id, ReminderKind.MORNING_DIGEST)
                    _send_reminder_to_user(db, user.id, text)
                    logger.info("Morning digest sent to user %s", user.id)
            except Exception as e:
                logger.error("Failed to send morning digest to user %s: %s", user.id, e)
    finally:
        db.close()


@celery_app.task(name="app.workers.reminders.send_evening_digest")
def send_evening_digest() -> None:
    """Send evening digest to all users with tasks."""
    db = SessionLocal()
    try:
        from app.db.models import User
        
        reminder_service = ReminderService(db)
        
        # Get all users who have tasks (completed or open)
        users = db.query(User).join(User.tasks).distinct().all()
        
        for user in users:
            try:
                # Check if user has any tasks
                all_tasks = reminder_service.get_user_tasks(user.id)
                
                if all_tasks:
                    text = reminder_service.format_digest_text(user.id, ReminderKind.EVENING_DIGEST)
                    _send_reminder_to_user(db, user.id, text)
                    logger.info("Evening digest sent to user %s", user.id)
            except Exception as e:
                logger.error("Failed to send evening digest to user %s: %s", user.id, e)
    finally:
        db.close()


@celery_app.task(name="app.workers.reminders.send_overdue_reminders")
def send_overdue_reminders() -> None:
    """Send reminders for overdue tasks."""
    db = SessionLocal()
    try:
        from app.db.models import User
        
        reminder_service = ReminderService(db)
        
        # Get all users who have overdue tasks
        users = db.query(User).join(User.tasks).filter(
            and_(
                Task.status == TaskStatus.OPEN,
                Task.due_at < now_utc()
            )
        ).distinct().all()
        
        for user in users:
            try:
                overdue_tasks = reminder_service.get_overdue_tasks_with_reminders(user.id)
                
                if overdue_tasks:
                    for task in overdue_tasks:
                        try:
                            # Create an overdue reminder
                            reminder = reminder_service.create_reminder(
                                user_id=user.id,
                                task_id=task.id,
                                remind_at=now_utc(),
                                kind=ReminderKind.OVERDUE,
                            )
                            
                            text = reminder_service.format_reminder_text(reminder, task)
                            _send_reminder_to_user(db, user.id, text)
                            
                            reminder_service.update_reminder_status(reminder.id, ReminderStatus.SENT)
                            logger.info("Overdue reminder sent for task %s to user %s", task.id, user.id)
                        except Exception as e:
                            logger.error("Failed to send overdue reminder for task %s: %s", task.id, e)
            except Exception as e:
                logger.error("Failed to send overdue reminders to user %s: %s", user.id, e)
    finally:
        db.close()


def _send_reminder_to_user(db: Session, user_id: uuid.UUID, text: str) -> None:
    """Send reminder text to user via WhatsApp."""
    settings = get_settings()
    phone = _get_latest_whatsapp_phone(db, user_id) or settings.whatsapp_test_recipient
    if not phone:
        raise ValueError(f"No WhatsApp phone found for user {user_id}")

    client = WhatsAppMetaClient()
    asyncio.run(client.send_text(phone, text))


def _get_latest_whatsapp_phone(db: Session, user_id: uuid.UUID) -> Union[str, None]:
    stmt = (
        select(InboundMessage)
        .where(
            InboundMessage.user_id == user_id,
            InboundMessage.channel == InboundChannel.WHATSAPP,
        )
        .order_by(InboundMessage.received_at.desc())
        .limit(1)
    )
    inbound = db.scalars(stmt).first()
    if inbound is None:
        logger.info("No inbound WhatsApp message found for user_id=%s", user_id)
        return None

    payload: Any = inbound.parse_result or {}
    phone = payload.get("phone") if isinstance(payload, dict) else None
    if isinstance(phone, str) and phone:
        return phone
    logger.info("Inbound message has no phone in parse_result for user_id=%s", user_id)
    return None
