"""Delete operation response schemas"""
from typing import Optional
from pydantic import BaseModel, Field


class DeleteSessionResponse(BaseModel):
    """Response model for deleting a session"""
    message: str = Field(..., description="Success message")
    deleted_id: Optional[str] = Field(None, description="Deleted session ID")


class DeleteAllSessionsResponse(BaseModel):
    """Response model for deleting all sessions"""
    message: str = Field(..., description="Success message")
    deleted_count: int = Field(..., ge=0, description="Number of sessions deleted")
