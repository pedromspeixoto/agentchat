"""Pydantic schemas for chat artifacts."""
from pydantic import BaseModel


class ArtifactResponse(BaseModel):
    id: str
    chat_id: str
    name: str
    kind: str
    size: int | None = None
    url: str | None = None
    created_at: str
