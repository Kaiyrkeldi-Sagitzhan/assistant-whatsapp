import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate, CustomReminderCreate, CustomReminderResponse
from app.services.task_service import TaskService
from app.services.reminder_service import ReminderService
from app.db.models import ReminderKind

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
    from app.db.models import TaskStatus
    
    reminder_service = ReminderService(db)
    task = db.get(Task, task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status != TaskStatus.OPEN:
        raise HTTPException(status_code=400, detail="Task is not open")
    
    # Create an immediate reminder
    from app.core.time import now_utc
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


@router.post("/reminders", response_model=CustomReminderResponse)
def create_custom_reminder(
    payload: CustomReminderCreate,
    db: Session = Depends(get_db),
) -> CustomReminderResponse:
    """Create a custom reminder not tied to a specific task.
    
    Example: "Напомни купить подарок завтра в 15:00"
    """
    from app.db.models import ReminderStatus
    
    reminder_service = ReminderService(db)
    reminder = reminder_service.create_custom_reminder(
        user_id=payload.user_id,
        title=payload.title,
        remind_at=payload.remind_at,
        description=payload.description,
    )
    
    return CustomReminderResponse.model_validate(reminder)
@router.get("/reminders/upcoming/{user_id}", response_model=list[CustomReminderResponse])
def list_upcoming_reminders(user_id: uuid.UUID, db: Session = Depends(get_db)) -> list[CustomReminderResponse]:
    """List upcoming custom reminders for a user."""
    reminder_service = ReminderService(db)
    reminders = reminder_service.get_upcoming_custom_reminders(user_id)
    return [CustomReminderResponse.model_validate(r) for r in reminders]
