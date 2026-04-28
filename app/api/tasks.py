import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate, CustomReminderCreate, CustomReminderResponse
from app.services.task_service import TaskService
from app.services.reminder_service import ReminderService
from app.db.models import ReminderKind, Task, TaskStatus, TaskPriority
from app.core.time import now_utc

import logging
logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=TaskResponse)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> TaskResponse:
    service = TaskService(db)
    task = service.create_task(payload)
    return TaskResponse.model_validate(task)


@router.get("/open/{user_id}", response_model=list[TaskResponse])
def list_open_tasks(user_id: uuid.UUID, db: Session = Depends(get_db)) -> list[TaskResponse]:
    service = TaskService(db)
    tasks = service.list_open_tasks(user_id)
    return [TaskResponse.model_validate(task) for task in tasks]


@router.get("/all/{user_id}", response_model=list[TaskResponse])
def list_all_tasks(user_id: uuid.UUID, db: Session = Depends(get_db)) -> list[TaskResponse]:
    """List all tasks for a user (for reminder purposes)."""
    reminder_service = ReminderService(db)
    tasks = reminder_service.get_user_tasks(user_id)
    return [TaskResponse.model_validate(task) for task in tasks]


@router.get("/today/{user_id}", response_model=list[TaskResponse])
def list_today_tasks(user_id: uuid.UUID, db: Session = Depends(get_db)) -> list[TaskResponse]:
    """List tasks due today for a user."""
    reminder_service = ReminderService(db)
    tasks = reminder_service.get_tasks_due_today(user_id)
    return [TaskResponse.model_validate(task) for task in tasks]


@router.get("/overdue/{user_id}", response_model=list[TaskResponse])
def list_overdue_tasks(user_id: uuid.UUID, db: Session = Depends(get_db)) -> list[TaskResponse]:
    """List overdue tasks for a user."""
    reminder_service = ReminderService(db)
    tasks = reminder_service.get_overdue_tasks(user_id)
    return [TaskResponse.model_validate(task) for task in tasks]


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(task_id: uuid.UUID, payload: TaskUpdate, db: Session = Depends(get_db)) -> TaskResponse:
    service = TaskService(db)
    task = service.update_task(task_id, payload)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.model_validate(task)


@router.post("/{task_id}/complete", response_model=TaskResponse)
def complete_task(task_id: uuid.UUID, db: Session = Depends(get_db)) -> TaskResponse:
    service = TaskService(db)
    task = service.complete_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.model_validate(task)


@router.post("/{task_id}/remind")
def trigger_reminder(task_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Manually trigger a reminder for a specific task."""
    reminder_service = ReminderService(db)
    task = db.get(Task, task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status != TaskStatus.OPEN:
        raise HTTPException(status_code=400, detail="Task is not open")
    
    # Create an immediate reminder
    reminder = reminder_service.create_reminder(
        user_id=task.user_id,
        task_id=task.id,
        remind_at=now_utc(),
        kind=ReminderKind.EXACT,
    )
    
    return {
        "message": "Reminder triggered",
        "task_id": str(task.id),
        "task_title": task.title,
        "reminder_id": str(reminder.id),
    }


@router.post("/{task_id}/notify")
def send_task_notification(task_id: uuid.UUID, custom_message: str = None, db: Session = Depends(get_db)) -> dict:
    """
    Send a WhatsApp notification about a specific task to the user.
    
    This sends an immediate notification to the user's WhatsApp with task details.
    """
    service = TaskService(db)
    success = service.send_task_notification(task_id, custom_message)
    
    if success:
        return {"success": True, "message": "Notification sent successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send notification")


@router.post("/{task_id}/event-notify")
def send_event_notification(
    task_id: uuid.UUID,
    reminder_minutes: int = 30,
    db: Session = Depends(get_db)
) -> dict:
    """
    Send a WhatsApp notification about an upcoming calendar event.
    
    Args:
        task_id: ID of the calendar event (stored as task)
        reminder_minutes: Minutes before event to send reminder
    """
    service = TaskService(db)
    success = service.send_event_notification(task_id, reminder_minutes)
    
    if success:
        return {"success": True, "message": "Event notification sent successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send event notification")


@router.post("/broadcast")
def broadcast_to_users(
    user_ids: list[uuid.UUID],
    message: str,
    subject: str = None,
    db: Session = Depends(get_db)
) -> dict:
    """
    Send a broadcast message to multiple users via WhatsApp.
    
    This is useful for sending announcements or reminders to multiple users at once.
    """
    service = TaskService(db)
    results = service.broadcast_message(user_ids, message, subject)
    
    return {
        "success": True,
        "sent": results["success"],
        "failed": results["failed"],
        "errors": results["errors"]
    }


@router.post("/{user_id}/digest")
def send_task_digest(
    user_id: uuid.UUID,
    digest_type: str = "daily",
    db: Session = Depends(get_db)
) -> dict:
    """
    Send a digest of tasks to user via WhatsApp.
    
    Args:
        user_id: User UUID
        digest_type: Type of digest - "daily", "weekly", or "overdue"
    """
    service = TaskService(db)
    success = service.send_task_digest(user_id, digest_type)
    
    if success:
        return {"success": True, "message": f"{digest_type} digest sent successfully"}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to send {digest_type} digest")


@router.post("/{user_id}/auto-reminders")
def setup_auto_reminders(
    user_id: uuid.UUID,
    task_ids: list[uuid.UUID],
    reminder_type: str = "all",
    db: Session = Depends(get_db)
) -> dict:
    """
    Set up automatic reminders for multiple tasks.
    
    Args:
        user_id: User UUID
        task_ids: List of task IDs to set reminders for
        reminder_type: Type of reminders - "exact", "before_deadline", "all"
    """
    reminder_service = ReminderService(db)
    tasks = db.query(Task).filter(
        Task.id.in_(task_ids),
        Task.user_id == user_id,
        Task.status == TaskStatus.OPEN
    ).all()
    
    created = 0
    for task in tasks:
        try:
            if reminder_type in ["exact", "all"]:
                if task.priority in [TaskPriority.CRITICAL, TaskPriority.HIGH]:
                    reminder_service.create_reminder(
                        user_id=user_id,
                        task_id=task.id,
                        remind_at=task.due_at,
                        kind=ReminderKind.EXACT,
                    )
                    created += 1
            
            if reminder_type in ["before_deadline", "all"]:
                if task.due_at and task.due_at > now_utc():
                    if task.priority in [TaskPriority.CRITICAL, TaskPriority.HIGH]:
                        reminder_service.create_reminder(
                            user_id=user_id,
                            task_id=task.id,
                            remind_at=task.due_at - timedelta(hours=1),
                            kind=ReminderKind.BEFORE_DEADLINE,
                        )
                        created += 1
        except Exception as e:
            logger.error(f"Failed to create reminder for task {task.id}: {e}")
    
    return {
        "success": True,
        "message": f"Created {created} reminders for {len(tasks)} tasks"
    }


@router.post("/{user_id}/schedule-notification")
def schedule_custom_notification(
    user_id: uuid.UUID,
    message: str,
    notify_at: str = None,
    minutes: int = None,
    hours: int = None,
    days: int = None,
    db: Session = Depends(get_db)
) -> dict:
    """
    Schedule a custom notification to be sent via WhatsApp at a specific time.
    
    Args:
        user_id: User UUID
        message: Notification message content
        notify_at: Specific time to send (ISO format or "HH:MM")
        minutes: Send in X minutes (alternative to notify_at)
        hours: Send in X hours (alternative to notify_at)
        days: Send in X days (alternative to notify_at)
    """
    from app.services.reminder_service import ReminderService
    from datetime import datetime, timedelta
    
    service = ReminderService(db)
    
    # Calculate notification time
    if notify_at:
        try:
            # Try parsing as ISO format
            notify_time = datetime.fromisoformat(notify_at.replace('Z', '+00:00'))
        except:
            try:
                # Try parsing as HH:MM
                from app.core.time import now_utc
                now = now_utc()
                parts = notify_at.split(':')
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
                notify_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if notify_time <= now:
                    notify_time = notify_time + timedelta(days=1)
            except:
                raise HTTPException(status_code=400, detail="Invalid time format. Use ISO format or HH:MM")
    elif minutes or hours or days:
        from app.core.time import now_utc
        notify_time = now_utc()
        if minutes:
            notify_time = notify_time + timedelta(minutes=minutes)
        if hours:
            notify_time = notify_time + timedelta(hours=hours)
        if days:
            notify_time = notify_time + timedelta(days=days)
    else:
        raise HTTPException(status_code=400, detail="Must specify notify_at or minutes/hours/days")
    
    success = service.schedule_custom_notification(
        user_id=user_id,
        message=message,
        notify_at=notify_time,
        title="Напоминание"
    )
    
    if success:
        return {
            "success": True,
            "message": "Notification scheduled successfully",
            "notify_at": notify_time.isoformat()
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to schedule notification")
