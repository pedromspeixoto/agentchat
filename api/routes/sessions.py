"""API routes for chat session management."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

from core.database import get_db
from core.logging import get_logger
from core.utils import to_iso8601
from models.chat import CHAT_TITLE_PLACEHOLDER, ChatSession, ChatMessage, ChatUsage, ChatArtifact
from routes.schemas import (
    ChatSessionResponse,
    CreateSessionRequest,
    ChatMessageResponse,
    PaginatedMessagesResponse,
    ChatContextResponse,
    DeleteSessionResponse,
    DeleteAllSessionsResponse,
    ArtifactResponse,
)

router = APIRouter()
logger = get_logger(__name__)


@router.get("/", response_model=list[ChatSessionResponse])
async def list_sessions(
    db: AsyncSession = Depends(get_db)
):
    """Get list of all chat sessions, ordered by most recently updated"""
    logger.info("Fetching all chat sessions")
    try:
        result = await db.execute(
            select(ChatSession).order_by(ChatSession.created_at.desc())
        )
        sessions = result.scalars().all()
        
        return [ChatSessionResponse(
            id=str(session.id),
            title=session.title,
            created_at=to_iso8601(session.created_at),
            updated_at=to_iso8601(session.updated_at),
        ) for session in sessions]
    except Exception as e:
        logger.error(f"Error fetching sessions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching sessions: {str(e)}")

@router.post("/", response_model=ChatSessionResponse)
async def create_session(
    request: CreateSessionRequest,
    db: AsyncSession = Depends(get_db)
):
    """Create a new chat session"""
    try:
        session = ChatSession(
            id=str(uuid.uuid4()),
            title=request.title or CHAT_TITLE_PLACEHOLDER,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return ChatSessionResponse(
            id=str(session.id),
            title=session.title,
            created_at=to_iso8601(session.created_at),
            updated_at=to_iso8601(session.updated_at),
        )
    except Exception as e:
        logger.error(f"Error creating session: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating session: {str(e)}")

@router.get("/{chat_id}/messages", response_model=PaginatedMessagesResponse)
async def get_chat_messages(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(30, ge=1, le=100, description="Number of messages to return"),
    offset: int = Query(0, ge=0, description="Number of messages to skip")
):
    """Get paginated messages for a specific chat session
    
    Returns messages ordered by created_at ASC (oldest first).
    Default behavior: returns last 30 messages when offset=0.
    For infinite scroll: calculate offset based on total count minus desired messages.
    """
    logger.info(f"Fetching messages for chat {chat_id} with limit={limit}, offset={offset}")
    try:
        # Verify session exists
        session_result = await db.execute(
            select(ChatSession).where(ChatSession.id == chat_id)
        )
        session = session_result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail=f"Chat session {chat_id} not found")
        
        # Get total count of messages
        count_result = await db.execute(
            select(func.count(ChatMessage.id))
            .where(ChatMessage.chat_id == chat_id)
        )
        total = count_result.scalar() or 0
        
        # If no messages, return empty response
        if total == 0:
            return PaginatedMessagesResponse(
                messages=[],
                total=0,
                limit=limit,
                offset=0,
                has_more=False
            )
        
        # Calculate actual offset for "last N messages" behavior
        # When offset=0, we want the last `limit` messages
        # We'll order by DESC, take the last N, then reverse to ASC order
        if offset == 0:
            # Get the last `limit` messages (newest first)
            result = await db.execute(
                select(ChatMessage)
                .where(ChatMessage.chat_id == chat_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(limit)
            )
            messages = list(result.scalars().all())
            # Reverse to get oldest first (for display)
            messages.reverse()
            actual_offset = max(0, total - limit)
        else:
            # For pagination (loading older messages), fetch from offset
            result = await db.execute(
                select(ChatMessage)
                .where(ChatMessage.chat_id == chat_id)
                .order_by(ChatMessage.created_at.asc())
                .offset(offset)
                .limit(limit)
            )
            messages = result.scalars().all()
            actual_offset = offset
        
        message_responses = [ChatMessageResponse(
            id=str(msg.id),
            chat_id=str(msg.chat_id),
            role=msg.role,
            content=msg.content,
            created_at=to_iso8601(msg.created_at),
            metadata=getattr(msg, 'message_metadata', None)  # Map message_metadata to metadata in API response
        ) for msg in messages]
        
        has_more = actual_offset + len(messages) < total
        
        return PaginatedMessagesResponse(
            messages=message_responses,
            total=total,
            limit=limit,
            offset=actual_offset,
            has_more=has_more
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching messages: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching messages: {str(e)}")

@router.get("/{chat_id}/context", response_model=ChatContextResponse)
async def get_chat_context(
    chat_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get aggregated usage statistics (context) for a chat session"""
    logger.info(f"Fetching context for chat {chat_id}")
    try:
        # Verify session exists
        session_result = await db.execute(
            select(ChatSession).where(ChatSession.id == chat_id)
        )
        session = session_result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail=f"Chat session {chat_id} not found")
        
        # Aggregate usage statistics
        result = await db.execute(
            select(ChatUsage)
            .where(ChatUsage.chat_id == chat_id)
        )
        usage_records = result.scalars().all()
        
        total_input = sum(u.input_tokens for u in usage_records)
        total_output = sum(u.output_tokens for u in usage_records)
        total_tokens = sum(u.total_tokens for u in usage_records)
        total_cost = sum(u.cost_usd for u in usage_records)

        return ChatContextResponse(
            chat_id=chat_id,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_tokens=total_tokens,
            total_cost_usd=total_cost,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching context: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching context: {str(e)}")

@router.get("/{chat_id}/artifacts", response_model=list[ArtifactResponse])
async def get_chat_artifacts(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all artifacts for a specific chat session, ordered by creation time."""
    logger.info(f"Fetching artifacts for chat {chat_id}")
    try:
        session_result = await db.execute(
            select(ChatSession).where(ChatSession.id == chat_id)
        )
        if not session_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail=f"Chat session {chat_id} not found")

        result = await db.execute(
            select(ChatArtifact)
            .where(ChatArtifact.chat_id == chat_id)
            .order_by(ChatArtifact.created_at.asc())
        )
        artifacts = result.scalars().all()
        return [ArtifactResponse(
            id=str(a.id),
            chat_id=str(a.chat_id),
            name=a.name,
            kind=a.kind,
            size=a.size,
            url=a.url,
            created_at=to_iso8601(a.created_at),
        ) for a in artifacts]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching artifacts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching artifacts: {str(e)}")


@router.delete("/{chat_id}", response_model=DeleteSessionResponse)
async def delete_session(
    chat_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a specific chat session and all its messages (cascade delete)"""
    logger.info(f"Deleting chat session {chat_id}")
    try:
        # Verify session exists
        result = await db.execute(
            select(ChatSession).where(ChatSession.id == chat_id)
        )
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(status_code=404, detail=f"Chat session {chat_id} not found")
        
        # Delete using delete statement (cascade will handle related records)
        await db.execute(delete(ChatSession).where(ChatSession.id == chat_id))
        await db.commit()
        
        logger.info(f"Successfully deleted chat session {chat_id}")
        return DeleteSessionResponse(
            message=f"Chat session {chat_id} deleted successfully",
            deleted_id=chat_id
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting session: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting session: {str(e)}")

@router.delete("/", response_model=DeleteAllSessionsResponse)
async def delete_all_sessions(
    db: AsyncSession = Depends(get_db)
):
    """Delete all chat sessions and their associated messages"""
    logger.info("Deleting all chat sessions")
    try:
        # Get count before deletion
        count_result = await db.execute(select(func.count(ChatSession.id)))
        deleted_count = count_result.scalar() or 0
        
        # Delete all sessions (cascade will handle related records)
        await db.execute(delete(ChatSession))
        await db.commit()
        
        logger.info(f"Successfully deleted {deleted_count} chat session(s)")
        return DeleteAllSessionsResponse(
            message="All chat sessions deleted successfully",
            deleted_count=deleted_count
        )
    except Exception as e:
        logger.error(f"Error deleting all sessions: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting all sessions: {str(e)}")
