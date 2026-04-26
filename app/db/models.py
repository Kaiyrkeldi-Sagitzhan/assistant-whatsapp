import uuid
from datetime import datetime
from enum import Enum
from typing import Union

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, ForeignKey, Integer, JSON, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.core.time import now_utc


class TaskStatus(str, Enum):
    OPEN = "open"
    DONE = "done"
    CANCELED = "canceled"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SourceType(str, Enum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    MANUAL = "manual"
    CALENDAR = "calendar"


class LinkType(str, Enum):
    FOLLOW_UP = "follow_up"
    PREP = "prep"
    RELATED = "related"


class ReminderKind(str, Enum):
    EXACT = "exact"
    BEFORE_DEADLINE = "before_deadline"
    MORNING_DIGEST = "morning_digest"
    EVENING_DIGEST = "evening_digest"
    OVERDUE = "overdue"


class ReminderStatus(str, Enum):
    SCHEDULED = "scheduled"
    SENT = "sent"
    FAILED = "failed"
    CANCELED = "canceled"


class InboundChannel(str, Enum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Almaty")
    locale: Mapped[str] = mapped_column(String(16), nullable=False, default="ru")
    default_reminder_policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now_utc, onupdate=now_utc
    )

    tasks: Mapped[list["Task"]] = relationship(back_populates="user")
    calendar_events: Mapped[list["CalendarEvent"]] = relationship(back_populates="user")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Union[str, None]] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(SqlEnum(TaskStatus), nullable=False, default=TaskStatus.OPEN)
    priority: Mapped[TaskPriority] = mapped_column(
        SqlEnum(TaskPriority), nullable=False, default=TaskPriority.MEDIUM
    )
    due_at: Mapped[Union[datetime, None]] = mapped_column(DateTime(timezone=True), nullable=True)
    start_at: Mapped[Union[datetime, None]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_follow_up: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[Union[float, None]] = mapped_column(Numeric(3, 2), nullable=True)
    source_type: Mapped[SourceType] = mapped_column(
        SqlEnum(SourceType), nullable=False, default=SourceType.MANUAL
    )
    source_ref: Mapped[Union[str, None]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now_utc, onupdate=now_utc
    )
    completed_at: Mapped[Union[datetime, None]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="tasks")
    tags: Mapped[list["TaskTag"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class TaskTag(Base):
    __tablename__ = "task_tags"

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(String(64), primary_key=True)

    task: Mapped[Task] = relationship(back_populates="tags")


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attendees_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now_utc, onupdate=now_utc
    )

    user: Mapped[User] = relationship(back_populates="calendar_events")


class TaskEventLink(Base):
    __tablename__ = "task_event_links"

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    calendar_event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("calendar_events.id", ondelete="CASCADE"), primary_key=True
    )
    link_type: Mapped[LinkType] = mapped_column(SqlEnum(LinkType), nullable=False)


class InboundMessage(Base):
    __tablename__ = "inbound_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Union[uuid.UUID, None]] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    channel: Mapped[InboundChannel] = mapped_column(SqlEnum(InboundChannel), nullable=False)
    external_message_id: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[Union[str, None]] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    parse_result: Mapped[Union[dict, None]] = mapped_column(JSON, nullable=True)


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    task_id: Mapped[Union[uuid.UUID, None]] = mapped_column(Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=True)
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kind: Mapped[ReminderKind] = mapped_column(SqlEnum(ReminderKind), nullable=False)
    status: Mapped[ReminderStatus] = mapped_column(
        SqlEnum(ReminderStatus), nullable=False, default=ReminderStatus.SCHEDULED
    )
