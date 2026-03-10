"""Sandbox factory - returns the configured sandbox client."""
from enum import Enum
from typing import AsyncIterator, Protocol

from core.config import settings
from core.logging import get_logger
from core.sandbox.subprocess import SubprocessClient
from core.sandbox.modal import ModalClient
from core.sandbox.firecracker import FirecrackerClient

logger = get_logger(__name__)


class SandboxType(Enum):
    SUBPROCESS = "subprocess"
    MODAL = "modal"
    FIRECRACKER = "firecracker"


class SandboxClient(Protocol):
    """Protocol for sandbox implementations."""

    async def run_agent(
        self,
        session_id: str,
        image_url: str,
        prompt: str,
        env_vars: dict[str, str],
        command: list[str] | None = None,
        timeout: int = 600,
        idle_timeout: int = 120,
        sdk_session_id: str | None = None,
        history: str | None = None,
    ) -> AsyncIterator[dict]: ...

    async def get_file(self, session_id: str, path: str) -> bytes:
        """Read a file from the sandbox workspace. `path` may be absolute
        (e.g. /workspace/report.csv) or relative to the session workspace."""
        ...


def get_sandbox_client() -> SandboxClient:
    if settings.SANDBOX_BACKEND == SandboxType.MODAL.value:
        return ModalClient()
    if settings.SANDBOX_BACKEND == SandboxType.FIRECRACKER.value:
        return FirecrackerClient()
    return SubprocessClient()
