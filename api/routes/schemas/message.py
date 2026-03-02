"""Message request/response schemas"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatMessageResponse(BaseModel):
    """Response model for chat message"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str = Field(..., description="Message UUID")
    chat_id: str = Field(..., description="Chat session UUID")
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    created_at: str = Field(..., description="ISO format creation timestamp")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional message metadata")
    
    @field_validator('role')
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate role is either 'user' or 'assistant'"""
        if v not in ['user', 'assistant']:
            raise ValueError("role must be either 'user' or 'assistant'")
        return v


class ChatMessageCreate(BaseModel):
    """Request model for creating a chat message"""
    chat_id: str = Field(..., description="Chat session UUID")
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., min_length=1, description="Message content")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional message metadata")
    
    @field_validator('role')
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate role is either 'user' or 'assistant'"""
        if v not in ['user', 'assistant']:
            raise ValueError("role must be either 'user' or 'assistant'")
        return v


class PaginatedMessagesResponse(BaseModel):
    """Response model for paginated messages"""
    messages: List[ChatMessageResponse] = Field(..., description="List of messages")
    total: int = Field(..., ge=0, description="Total number of messages")
    limit: int = Field(..., ge=1, le=100, description="Number of messages per page")
    offset: int = Field(..., ge=0, description="Offset for pagination")
    has_more: bool = Field(..., description="Whether there are more messages")
