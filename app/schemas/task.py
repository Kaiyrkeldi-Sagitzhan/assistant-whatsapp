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
    reminder_time: Union[datetime, None] = None  # New field for custom reminder time

class TaskUpdate(BaseModel):
    title: Union[str, None] = None
    description: Union[str, None] = None
    due_at: Union[datetime, None] = None
    priority: Union[TaskPriority, None] = None
    reminder_time: Union[datetime, None] = None  # Add to update schema

class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    description: Union[str, None]
    status: TaskStatus
    priority: TaskPriority
    due_at: Union[datetime, None]
    reminder_time: Union[datetime, None] = None  # Add to response schema

class CustomReminderCreate(BaseModel):
    user_id: uuid.UUID
    title: str
    remind_at: datetime
    description: Union[str, None] = None


class CustomReminderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    remind_at: datetime
    description: Union[str, None]
    task_id: Union[uuid.UUID, None] = None
