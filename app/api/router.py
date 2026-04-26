from fastapi import APIRouter

from app.api import agenda, health, tasks, webhooks

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(webhooks.router, tags=["webhooks"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(agenda.router, prefix="/agenda", tags=["agenda"])
