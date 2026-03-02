"""Event request/response schemas for agent event logging"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class ChatEventResponse(BaseModel):
    """Response model for chat event"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str = Field(..., description="Event UUID")
    chat_id: str = Field(..., description="Chat session UUID")
    message_id: Optional[str] = Field(None, description="Associated message UUID")
    event_type: str = Field(..., description="Event type: 'tool_call', 'tool_result', 'thinking', 'error', 'status'")
    event_name: Optional[str] = Field(None, description="Event name (e.g., tool name, error type)")
    event_data: Optional[Dict[str, Any]] = Field(None, description="Event-specific data payload")
    created_at: str = Field(..., description="ISO format creation timestamp")


class ChatEventCreate(BaseModel):
    """Request model for creating a chat event"""
    chat_id: str = Field(..., description="Chat session UUID")
    message_id: Optional[str] = Field(None, description="Associated message UUID")
    event_type: str = Field(..., description="Event type: 'tool_call', 'tool_result', 'thinking', 'error', 'status'")
    event_name: Optional[str] = Field(None, description="Event name (e.g., tool name, error type)")
    event_data: Optional[Dict[str, Any]] = Field(None, description="Event-specific data payload")


class PaginatedEventsResponse(BaseModel):
    """Response model for paginated events"""
    events: List[ChatEventResponse] = Field(..., description="List of events")
    total: int = Field(..., ge=0, description="Total number of events")
    limit: int = Field(..., ge=1, le=100, description="Number of events per page")
    offset: int = Field(..., ge=0, description="Offset for pagination")
    has_more: bool = Field(..., description="Whether there are more events")
