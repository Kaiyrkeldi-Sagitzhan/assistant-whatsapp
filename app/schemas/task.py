import uuid
from datetime import datetime
from typing import Union

from pydantic import BaseModel, ConfigDict

from app.db.models import TaskPriority, TaskStatus


class TaskCreate(BaseModel):
    user_id: uuid.UUID
    title: str
    description: Union[str, None] = None
    due_at: Union[datetime, None] = None
    priority: TaskPriority = TaskPriority.MEDIUM


class TaskUpdate(BaseModel):
    title: Union[str, None] = None
    description: Union[str, None] = None
    due_at: Union[datetime, None] = None
    priority: Union[TaskPriority, None] = None


class TaskResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    description: Union[str, None]
    status: TaskStatus
    priority: TaskPriority
    due_at: Union[datetime, None]

    model_config = ConfigDict(from_attributes=True)


class CustomReminderCreate(BaseModel):
    """Schema for creating a custom reminder (not tied to a task)."""
    user_id: uuid.UUID
    title: str
    remind_at: datetime
    description: Union[str, None] = None


class CustomReminderResponse(BaseModel):
    """Schema for custom reminder response."""
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    description: Union[str, None]
    remind_at: datetime
    status: str

    model_config = ConfigDict(from_attributes=True)
