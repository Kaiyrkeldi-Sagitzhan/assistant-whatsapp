import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.agenda_service import AgendaService
from app.services.reminder_service import ReminderService

router = APIRouter()


@router.get("/day")
def get_day_agenda(user_id: uuid.UUID, target_date: date, db: Session = Depends(get_db)) -> dict:
    service = AgendaService(db)
    return service.get_day_agenda(user_id, target_date)


@router.get("/week")
def get_week_agenda(user_id: uuid.UUID, pivot_date: date, db: Session = Depends(get_db)) -> dict:
    service = AgendaService(db)
    return service.get_week_agenda(user_id, pivot_date)


@router.get("/summary/day")
def get_day_summary(user_id: uuid.UUID, target_date: date = None, db: Session = Depends(get_db)) -> dict:
    """Get daily summary - tasks only for today's date."""
    service = AgendaService(db)
    return service.get_day_summary(str(user_id), target_date)


@router.get("/summary/week")
def get_week_summary(user_id: uuid.UUID, pivot_date: date = None, db: Session = Depends(get_db)) -> dict:
    """Get weekly summary - tasks for the next 7 days, grouped by day with date and day of week."""
    service = AgendaService(db)
    return service.get_week_summary(str(user_id), pivot_date)


@router.get("/summary/month")
def get_month_summary(user_id: uuid.UUID, pivot_date: date = None, db: Session = Depends(get_db)) -> dict:
    """Get monthly summary - tasks grouped by 7-day weeks."""
    service = AgendaService(db)
    return service.get_month_summary(str(user_id), pivot_date)


@router.post("/send-summary/{summary_type}")
def send_summary_via_whatsapp(
    user_id: uuid.UUID,
    summary_type: str,
    target_date: date = None,
    db: Session = Depends(get_db)
) -> dict:
    """
    Generate and send a task summary to user via WhatsApp.
    
    Args:
        user_id: User UUID
        summary_type: Type of summary - "day", "week", or "month"
        target_date: Target date (defaults to today)
    
    Returns:
        Dictionary with success status and message
    """
    service = ReminderService(db)
    success = service.send_summary_via_whatsapp(str(user_id), summary_type, target_date)
    
    if success:
        return {"success": True, "message": f"{summary_type} summary sent successfully"}
    else:
        return {"success": False, "message": f"Failed to send {summary_type} summary"}
