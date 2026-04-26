import logging
import uuid
from typing import Union

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Task, TaskPriority, TaskStatus, User, ReminderKind
from app.core.time import now_utc
from app.schemas.task import TaskCreate, TaskUpdate

logger = logging.getLogger(__name__)


class TaskService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_task(self, payload: TaskCreate) -> Task:
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
            reminder_service.send_first_reminder(task)
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
