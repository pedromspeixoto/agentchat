"""Firecracker microVM sandbox client for running agents in isolated VMs."""
import json
from typing import AsyncIterator

import httpx

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEOUT = 10 * 60
DEFAULT_IDLE_TIMEOUT = 2 * 60


class FirecrackerClient:
    """Client for managing Firecracker microVM sandboxes via orchestrator API."""

    def __init__(self):
        self._client = httpx.AsyncClient(
            base_url=settings.FIRECRACKER_ORCHESTRATOR_URL,
            headers={"Authorization": f"Bearer {settings.FIRECRACKER_API_KEY}"},
            timeout=httpx.Timeout(30.0, read=660.0),
        )

    async def run_agent(
        self,
        session_id: str,
        image_url: str,
        prompt: str,
        env_vars: dict[str, str],
        command: list[str] | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        idle_timeout: int = DEFAULT_IDLE_TIMEOUT,
        sdk_session_id: str | None = None,
        history: str | None = None,
    ) -> AsyncIterator[dict]:
        vm_id: str | None = None
        try:
            # 1. Create VM
            create_resp = await self._client.post(
                "/vms",
                json={
                    "image_url": image_url,
                    "timeout": timeout,
                    "idle_timeout": idle_timeout,
                },
            )
            create_resp.raise_for_status()
            vm_id = create_resp.json()["vm_id"]
            logger.info(f"Created Firecracker VM {vm_id} for session {session_id}")

            # 2. Upload files
            files_dict: dict[str, str] = {"/workspace/prompt.txt": prompt}
            if history:
                files_dict["/workspace/history.txt"] = history

            upload_resp = await self._client.post(
                f"/vms/{vm_id}/files",
                json={"files": files_dict},
            )
            upload_resp.raise_for_status()

            # 3. Execute agent command with streaming
            exec_command = command or ["python", "/app/run_agent.py"]
            async with self._client.stream(
                "POST",
                f"/vms/{vm_id}/exec",
                json={
                    "command": exec_command,
                    "env_vars": env_vars,
                    "timeout": timeout,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[len("data: "):]
                    try:
                        yield json.loads(payload)
                    except json.JSONDecodeError:
                        yield {"__type": "raw", "content": payload}

        except Exception as e:
            logger.error(f"Firecracker agent execution error: {e}", exc_info=True)
            yield {"__type": "error", "message": str(e)}
        finally:
            if vm_id:
                try:
                    await self._client.delete(f"/vms/{vm_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete VM {vm_id}: {e}")

    async def get_file(self, session_id: str, path: str) -> bytes:
        """Read a file from the Firecracker VM filesystem."""
        resp = await self._client.get(
            f"/vms/{session_id}/files/read",
            params={"path": path},
        )
        resp.raise_for_status()
        return resp.content
