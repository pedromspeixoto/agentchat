"""Database models for chat sessions and messages"""
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Integer, Float, ForeignKey, JSON, BigInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from core.database import Base

CHAT_TITLE_PLACEHOLDER = "New Chat"

class ChatSession(Base):
    """Chat session model"""
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Vendor SDK session ID (e.g., Claude Agent SDK session ID for resuming conversations)
    sdk_session_id = Column(String(255), nullable=True, index=True)

    # Relationships
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    events = relationship("ChatEvent", back_populates="session", cascade="all, delete-orphan")
    usage_stats = relationship("ChatUsage", back_populates="session", cascade="all, delete-orphan")
    artifacts = relationship("ChatArtifact", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ChatSession(id={self.id}, title={self.title})>"


class ChatMessage(Base):
    """Chat message model"""
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(UUID(as_uuid=False), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    message_metadata = Column(JSON, nullable=True)  # For storing additional message metadata (renamed from 'metadata' to avoid SQLAlchemy reserved name)

    # Relationships
    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self):
        return f"<ChatMessage(id={self.id}, role={self.role}, chat_id={self.chat_id})>"


class ChatUsage(Base):
    """Chat usage statistics (token usage, cost, etc.)"""
    __tablename__ = "chat_usage"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(UUID(as_uuid=False), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)
    cost_usd = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    session = relationship("ChatSession", back_populates="usage_stats")

    def __repr__(self):
        return f"<ChatUsage(id={self.id}, chat_id={self.chat_id}, total_tokens={self.total_tokens})>"


class ChatEvent(Base):
    """Chat event model for logging agent events (tool calls, thinking, errors, etc.)"""
    __tablename__ = "chat_events"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(UUID(as_uuid=False), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    message_id = Column(UUID(as_uuid=False), ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(100), nullable=False)  # e.g., 'tool_call', 'tool_result', 'thinking', 'error', 'status'
    event_name = Column(String(255), nullable=True)  # e.g., tool name, error type
    event_data = Column(JSON, nullable=True)  # Flexible payload for event-specific data
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    session = relationship("ChatSession", back_populates="events")

    def __repr__(self):
        return f"<ChatEvent(id={self.id}, chat_id={self.chat_id}, event_type={self.event_type})>"


class ChatArtifact(Base):
    """Artifact generated during a chat session (CSV, PDF, JSON, etc.)"""
    __tablename__ = "chat_artifacts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(UUID(as_uuid=False), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(512), nullable=False)
    kind = Column(String(50), nullable=False)  # 'csv', 'pdf', 'json', 'txt', 'xlsx', 'other'
    size = Column(BigInteger, nullable=True)   # bytes
    url = Column(Text, nullable=True)          # download URL
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    session = relationship("ChatSession", back_populates="artifacts")

    def __repr__(self):
        return f"<ChatArtifact(id={self.id}, chat_id={self.chat_id}, name={self.name}, kind={self.kind})>"
