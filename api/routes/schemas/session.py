"""Session request/response schemas"""
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class CreateSessionRequest(BaseModel):
    title: Optional[str] = Field(None, description="Optional session title")


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: Optional[str] = None
    created_at: str
    updated_at: str
