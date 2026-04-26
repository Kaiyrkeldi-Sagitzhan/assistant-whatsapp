import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.agenda_service import AgendaService

router = APIRouter()


@router.get("/day")
def get_day_agenda(user_id: uuid.UUID, target_date: date, db: Session = Depends(get_db)) -> dict:
    service = AgendaService(db)
    return service.get_day_agenda(user_id, target_date)


@router.get("/week")
def get_week_agenda(user_id: uuid.UUID, pivot_date: date, db: Session = Depends(get_db)) -> dict:
    service = AgendaService(db)
    return service.get_week_agenda(user_id, pivot_date)
