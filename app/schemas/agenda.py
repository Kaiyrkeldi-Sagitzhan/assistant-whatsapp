from datetime import date

from pydantic import BaseModel


class AgendaRequest(BaseModel):
    date: date
