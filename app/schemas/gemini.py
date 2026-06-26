"""Pydantic schemas for Gemini API responses."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ExtractedTask(BaseModel):
    """Structured response from Gemini API for task extraction.
    
    This schema is used with Gemini's structured output feature to guarantee
    valid JSON responses that exactly match this structure.
    """
    
    intent: Literal["create_task", "create_event", "schedule_notification", "unknown"] = Field(
        description="Classification of user's intent"
    )
    title: str = Field(
        default="",
        description="Task/event title (empty string for unknown intents)",
        max_length=200
    )
    datetime: Optional[str] = Field(
        default=None,
        description="ISO format datetime string (YYYY-MM-DDTHH:MM:SS) or null if not mentioned",
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$|^null$"
    )
    description: str = Field(
        description="Full message text or task description"
    )
    priority: Optional[Literal["low", "medium", "high"]] = Field(
        default="medium",
        description="Task priority level"
    )
    confidence: float = Field(
        default=0.5,
        description="Confidence score of the extraction (0.0-1.0)",
        ge=0.0,
        le=1.0,
    )


class ChatResponse(BaseModel):
    """Response from Gemini for chat/unknown intents."""
    
    message: str = Field(
        description="Conversational response in Russian"
    )
    confidence: float = Field(
        default=0.8,
        description="Confidence of the response",
        ge=0.0,
        le=1.0,
    )
