"""Chat API routes - streams Claude Agent SDK events via SSE."""
import json
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.sse import EventSourceResponse, format_sse_event
from starlette.background import BackgroundTask
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.database import get_db, AsyncSessionLocal
from core.agents import load_agent_config, get_agent_env_vars
from core.sandbox import get_sandbox_client
from core.logging import get_logger
from models.chat import CHAT_TITLE_PLACEHOLDER, ChatSession, ChatMessage, ChatEvent, ChatUsage, ChatArtifact
from core.storage import upload_artifact
from routes.schemas.chat import ChatRequest

router = APIRouter()
logger = get_logger(__name__)


# Local mirrors of the SDK types — the API server processes raw dicts from the
# sandbox subprocess and never imports claude_agent_sdk directly.

@dataclass
class _TextBlock:
    text: str

@dataclass
class _ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]

_ContentBlock = _TextBlock | _ToolUseBlock

@dataclass
class _AssistantMessage:
    content: list[_ContentBlock]
    model: str
    parent_tool_use_id: str | None = None
    error: str | None = None

@dataclass
class _ResultMessage:
    subtype: str
    duration_ms: int
    duration_api_ms: int
    is_error: bool
    num_turns: int
    session_id: str
    total_cost_usd: float | None = None
    usage: dict[str, Any] | None = None
    result: str | None = None


class _ArtifactMsg(TypedDict):
    __type: str
    id: str
    name: str
    kind: str
    size: NotRequired[int | None]
    sandbox_path: NotRequired[str | None]


def _extract_text(content: list[_ContentBlock]) -> str:
    return "".join(b.text for b in content if isinstance(b, _TextBlock))


def _parse_content_block(b: dict[str, Any]) -> _ContentBlock | None:
    t = b.get("__type")
    if t == "TextBlock":
        return _TextBlock(text=b["text"])
    if t == "ToolUseBlock":
        return _ToolUseBlock(id=b["id"], name=b["name"], input=b.get("input", {}))
    return None


def _parse_message(msg: dict[str, Any]) -> _AssistantMessage | _ResultMessage | None:
    t = msg.get("__type")
    if t == "AssistantMessage":
        content = [b for raw in msg.get("content", []) if (b := _parse_content_block(raw)) is not None]
        return _AssistantMessage(
            content=content,
            model=msg.get("model", ""),
            parent_tool_use_id=msg.get("parent_tool_use_id"),
            error=msg.get("error"),
        )
    if t == "ResultMessage":
        return _ResultMessage(
            subtype=msg.get("subtype", ""),
            duration_ms=msg.get("duration_ms", 0),
            duration_api_ms=msg.get("duration_api_ms", 0),
            is_error=msg.get("is_error", False),
            num_turns=msg.get("num_turns", 0),
            session_id=msg.get("session_id", ""),
            total_cost_usd=msg.get("total_cost_usd"),
            usage=msg.get("usage"),
            result=msg.get("result"),
        )
    return None


async def _get_or_create_session(
    db: AsyncSession,
    session_id: str | None,
    prompt: str,
) -> tuple[ChatSession, bool]:
    if session_id:
        result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
        session = result.scalar_one_or_none()
        if session:
            if session.title == CHAT_TITLE_PLACEHOLDER:
                session.title = prompt[:50] + ("..." if len(prompt) > 50 else "")
                await db.commit()
            return session, False

    new_id = session_id or str(uuid.uuid4())
    session = ChatSession(
        id=new_id,
        title=prompt[:50] + ("..." if len(prompt) > 50 else ""),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    logger.info(f"Created session {new_id}")
    return session, True


@router.post("/")
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Execute agent and forward Claude SDK events via SSE."""

    agent_config = load_agent_config()
    if not agent_config.image:
        raise HTTPException(status_code=400, detail="Agent has no image configured")

    session, is_new = await _get_or_create_session(db, request.session_id, request.prompt)
    session_id = str(session.id)
    sdk_session_id = session.sdk_session_id

    # Fetch conversation history from DB (before saving the new user message)
    history_json: str | None = None
    if not is_new:
        msgs_result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.chat_id == session_id)
            .order_by(ChatMessage.created_at.asc())
        )
        history_msgs = msgs_result.scalars().all()
        if history_msgs:
            history_json = json.dumps([
                {"role": m.role, "content": m.content} for m in history_msgs
            ])

    # Save user message immediately
    db.add(ChatMessage(
        id=str(uuid.uuid4()),
        chat_id=session_id,
        role="user",
        content=request.prompt,
    ))
    session.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()

    env_vars = get_agent_env_vars(agent_config)
    if not env_vars:
        raise HTTPException(status_code=500, detail="Service temporarily unavailable")

    # Collected during streaming, saved in background after SSE closes
    stream_state = {
        "assistant_text": "",
        "sdk_session_id": sdk_session_id,
        "cost_usd": 0.0,
        "usage": {},
        "tool_events": [],
    }

    async def save_to_db():
        try:
            async with AsyncSessionLocal() as save_db:
                text = stream_state["assistant_text"]
                if text:
                    save_db.add(ChatMessage(
                        id=str(uuid.uuid4()),
                        chat_id=session_id,
                        role="assistant",
                        content=text,
                    ))

                for evt in stream_state["tool_events"]:
                    save_db.add(evt)

                u = stream_state["usage"]
                inp = int(u.get("input_tokens", 0))
                out = int(u.get("output_tokens", 0))
                if inp + out > 0 or stream_state["cost_usd"] > 0:
                    save_db.add(ChatUsage(
                        id=str(uuid.uuid4()),
                        chat_id=session_id,
                        input_tokens=inp,
                        output_tokens=out,
                        total_tokens=inp + out,
                        cost_usd=stream_state["cost_usd"],
                    ))

                new_sdk_id = stream_state["sdk_session_id"]
                if new_sdk_id and new_sdk_id != sdk_session_id:
                    result = await save_db.execute(
                        select(ChatSession).where(ChatSession.id == session_id)
                    )
                    sess = result.scalar_one_or_none()
                    if sess:
                        sess.sdk_session_id = new_sdk_id
                        logger.info(f"Updated SDK session ID → {new_sdk_id}")

                await save_db.commit()
                logger.info(f"Saved DB records for session {session_id}")
        except Exception as e:
            logger.error(f"Failed to save to DB: {e}", exc_info=True)

    async def generate():
        # First event: let the FE know the session_id (critical for new sessions)
        yield format_sse_event(
            data_str=json.dumps({"session_id": session_id, "is_new": is_new}),
            event="session_start",
        )

        sandbox = get_sandbox_client()
        try:
            async for msg in sandbox.run_agent(
                session_id=session_id,
                image_url=agent_config.image,
                prompt=request.prompt,
                env_vars=env_vars,
                command=agent_config.command,
                timeout=agent_config.timeout,
                idle_timeout=agent_config.idle_timeout,
                sdk_session_id=sdk_session_id,
                history=history_json,
            ):
                msg_type = msg.get("__type", "")
                parsed = _parse_message(msg)

                # Collect assistant text and tool events for DB
                if isinstance(parsed, _AssistantMessage):
                    stream_state["assistant_text"] += _extract_text(parsed.content)
                    for block in parsed.content:
                        if isinstance(block, _ToolUseBlock):
                            # Fetch original raw dict (preserves __type + full structure for DB)
                            raw_block = next(
                                (b for b in msg.get("content", []) if b.get("id") == block.id),
                                {},
                            )
                            stream_state["tool_events"].append(ChatEvent(
                                id=str(uuid.uuid4()),
                                chat_id=session_id,
                                event_type="tool_use",
                                event_name=block.name,
                                event_data=raw_block,
                            ))

                # Extract cost, SDK session ID, and usage from result
                elif isinstance(parsed, _ResultMessage):
                    stream_state["sdk_session_id"] = parsed.session_id or stream_state["sdk_session_id"]
                    stream_state["cost_usd"] = float(parsed.total_cost_usd or 0.0)
                    stream_state["usage"] = parsed.usage or {}

                # Handle artifacts: copy from sandbox → MinIO → DB, then forward with URL
                elif msg_type == "Artifact":
                    artifact: _ArtifactMsg = msg  # type: ignore[assignment]
                    artifact_id = artifact.get("id") or str(uuid.uuid4())
                    name = artifact.get("name", "artifact")
                    kind = artifact.get("kind", "other")
                    size = artifact.get("size")
                    sandbox_path = artifact.get("sandbox_path")
                    artifact_url: str | None = None

                    if sandbox_path:
                        try:
                            file_bytes = await sandbox.get_file(session_id, sandbox_path)
                            size = size or len(file_bytes)
                            _, artifact_url = await upload_artifact(session_id, artifact_id, name, file_bytes)
                        except Exception as art_err:
                            logger.error(f"Failed to copy artifact from sandbox: {art_err}", exc_info=True)

                    # Save artifact to DB immediately so it's available on reload
                    try:
                        async with AsyncSessionLocal() as art_db:
                            art_db.add(ChatArtifact(
                                id=artifact_id,
                                chat_id=session_id,
                                name=name,
                                kind=kind,
                                size=size,
                                url=artifact_url,
                            ))
                            await art_db.commit()
                    except Exception as db_err:
                        logger.error(f"Failed to save artifact to DB: {db_err}", exc_info=True)

                    # Forward event with resolved URL (omit raw sandbox_path)
                    msg = {k: v for k, v in msg.items() if k != "sandbox_path"}
                    msg["id"] = artifact_id
                    msg["url"] = artifact_url
                    msg["size"] = size

                yield format_sse_event(data_str=json.dumps(msg), event=msg_type or "message")

        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield format_sse_event(
                data_str=json.dumps({"__type": "error", "message": str(e)}),
                event="error",
            )

    return EventSourceResponse(generate(), background=BackgroundTask(save_to_db))
