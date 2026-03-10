"""Modal sandbox client for running agents in isolated containers."""
import asyncio
import json
import os
from typing import AsyncIterator

import modal

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEOUT = 10 * 60
DEFAULT_IDLE_TIMEOUT = 2 * 60


class ModalClient:
    """Client for managing Modal sandboxes."""

    def __init__(self):
        self.app = None
        self._initialized = False

    def _read_stdout_sync(self, process, queue: asyncio.Queue, loop):
        """Read process stdout in a thread and push dicts to queue."""
        try:
            for chunk in process.stdout:
                for line in chunk.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        asyncio.run_coroutine_threadsafe(queue.put(json.loads(line)), loop)
                    except json.JSONDecodeError:
                        asyncio.run_coroutine_threadsafe(
                            queue.put({"__type": "raw", "content": line}), loop
                        )
        except Exception as e:
            logger.error(f"Error streaming process output: {e}")
            asyncio.run_coroutine_threadsafe(
                queue.put({"__type": "error", "message": str(e)}), loop
            )
        finally:
            try:
                process.wait()
                if process.returncode and process.returncode != 0:
                    asyncio.run_coroutine_threadsafe(
                        queue.put({"__type": "exit", "returncode": process.returncode}), loop
                    )
            except Exception as e:
                logger.error(f"Error waiting for process: {e}")
            asyncio.run_coroutine_threadsafe(queue.put(None), loop)

    async def initialize(self) -> None:
        if self._initialized:
            return
        if settings.MODAL_TOKEN_ID and settings.MODAL_TOKEN_SECRET:
            os.environ["MODAL_TOKEN_ID"] = settings.MODAL_TOKEN_ID
            os.environ["MODAL_TOKEN_SECRET"] = settings.MODAL_TOKEN_SECRET
        self.app = await modal.App.lookup.aio("mobox-agents", create_if_missing=True)
        self._initialized = True
        logger.info("Modal client initialized")

    async def _get_or_create_sandbox(
        self,
        session_id: str,
        image_url: str,
        prompt: str,
        env_vars: dict[str, str],
        sdk_session_id: str | None,
        timeout: int,
        idle_timeout: int,
    ) -> modal.Sandbox:
        sandbox = None
        try:
            sandbox = await modal.Sandbox.from_name.aio("mobox-agents", session_id)
            exit_code = await sandbox.poll.aio()
            if exit_code is not None:
                logger.info(f"Sandbox {session_id} finished (exit={exit_code}), creating new")
                sandbox = None
        except Exception:
            logger.info(f"Sandbox {session_id} not found, creating new")

        if sandbox is None:
            env = {"PYTHONUNBUFFERED": "1"}
            if sdk_session_id:
                env["SDK_SESSION_ID"] = sdk_session_id

            secret = modal.Secret.from_dict({**env_vars, **env}) if (env_vars or env) else None
            sandbox = await modal.Sandbox.create.aio(
                name=session_id,
                app=self.app,
                image=modal.Image.from_registry(image_url),
                secrets=[secret] if secret else [],
                timeout=timeout,
                idle_timeout=idle_timeout,
                workdir="/workspace",
            )
            await sandbox.set_tags.aio({"session_id": session_id})
            logger.info(f"Created sandbox {sandbox.object_id} for session {session_id}")
        else:
            logger.info(f"Reusing sandbox {sandbox.object_id} for session {session_id}")

        prompt_file = await sandbox.open.aio("/workspace/prompt.txt", "w")
        await prompt_file.write.aio(prompt)
        await prompt_file.close.aio()

        return sandbox

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
        if command is None:
            command = ["python", "/app/run_agent.py"]

        await self.initialize()

        try:
            sandbox = await self._get_or_create_sandbox(
                session_id, image_url, prompt, env_vars, sdk_session_id,
                timeout, idle_timeout,
            )
            if history:
                hist_file = await sandbox.open.aio("/workspace/history.txt", "w")
                await hist_file.write.aio(history)
                await hist_file.close.aio()

            process = await sandbox.exec.aio(*command)
            queue: asyncio.Queue = asyncio.Queue()
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, self._read_stdout_sync, process, queue, loop)

            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event

        except Exception as e:
            logger.error(f"Agent execution error: {e}", exc_info=True)
            yield {"__type": "error", "message": str(e)}

    async def get_file(self, session_id: str, path: str) -> bytes:
        """Read a file from the Modal sandbox filesystem."""
        await self.initialize()
        try:
            sandbox = await modal.Sandbox.from_name.aio("mobox-agents", session_id)
            f = await sandbox.open.aio(path, "rb")
            data = await f.read.aio()
            await f.close.aio()
            return data if isinstance(data, bytes) else data.encode()
        except Exception as e:
            logger.error(f"Failed to read file from Modal sandbox: {e}", exc_info=True)
            raise
