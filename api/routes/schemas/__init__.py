"""Pydantic schemas for API request/response validation"""
from routes.schemas.chat import ChatRequest, ChatResponse
from routes.schemas.session import ChatSessionResponse, CreateSessionRequest
from routes.schemas.message import (
    ChatMessageResponse,
    ChatMessageCreate,
    PaginatedMessagesResponse,
)
from routes.schemas.usage import (
    ChatUsageResponse,
    ChatUsageCreate,
    ChatContextResponse,
)
from routes.schemas.delete import (
    DeleteSessionResponse,
    DeleteAllSessionsResponse,
)
from routes.schemas.event import (
    ChatEventResponse,
    ChatEventCreate,
    PaginatedEventsResponse,
)
from routes.schemas.artifact import ArtifactResponse

__all__ = [
    # Chat schemas
    "ChatRequest",
    "ChatResponse",
    # Session schemas
    "ChatSessionResponse",
    "CreateSessionRequest",
    # Message schemas
    "ChatMessageResponse",
    "ChatMessageCreate",
    "PaginatedMessagesResponse",
    # Usage schemas
    "ChatUsageResponse",
    "ChatUsageCreate",
    "ChatContextResponse",
    # Delete schemas
    "DeleteSessionResponse",
    "DeleteAllSessionsResponse",
    # Event schemas
    "ChatEventResponse",
    "ChatEventCreate",
    "PaginatedEventsResponse",
    # Artifact schemas
    "ArtifactResponse",
]
