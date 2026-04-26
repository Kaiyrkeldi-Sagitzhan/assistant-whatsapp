from celery import Celery

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.app_env)

celery_app = Celery(
    "task_assistant",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.jobs", "app.workers.reminders"],
)
celery_app.conf.update(
    timezone=settings.app_timezone,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    beat_schedule={
        "send-due-reminders": {
            "task": "app.workers.reminders.send_due_reminders",
            "schedule": 60.0,  # Every minute
        },
        "morning-digest": {
            "task": "app.workers.reminders.send_morning_digest",
            "schedule": 60 * 60 * 6,  # Every 6 hours
        },
        "evening-digest": {
            "task": "app.workers.reminders.send_evening_digest",
            "schedule": 60 * 60 * 18,  # Every 18 hours (evening)
        },
        "overdue-reminders": {
            "task": "app.workers.reminders.send_overdue_reminders",
            "schedule": 15 * 60,  # Every 15 minutes
        },
    },
)
