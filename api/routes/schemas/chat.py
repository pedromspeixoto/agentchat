"""Chat request/response schemas"""
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    prompt: str = Field(..., min_length=1, description="The user's message/prompt")
    session_id: Optional[str] = Field(None, description="Session ID (optional - creates new session if not provided)")

    @field_validator('session_id')
    @classmethod
    def validate_session_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                import uuid
                uuid.UUID(v)
            except ValueError:
                raise ValueError("session_id must be a valid UUID")
        return v


class ChatResponse(BaseModel):
    """Response model for chat creation (non-streaming)"""
    session_id: str = Field(..., description="Session ID (new or existing)")
    message: str = Field(..., description="Status message")
