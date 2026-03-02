"""Local subprocess sandbox - runs agents with uv run."""
import asyncio
import json
import os
from pathlib import Path
from typing import AsyncIterator

from core.agents import AGENT_DIR
from core.logging import get_logger

logger = get_logger(__name__)


async def _read_stdout(process, queue: asyncio.Queue) -> None:
    """Read process stdout and push parsed JSON dicts to queue."""
    try:
        if process.stdout:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                line = line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    await queue.put(json.loads(line))
                except json.JSONDecodeError:
                    await queue.put({"__type": "raw", "content": line})
    except Exception as e:
        logger.error(f"Error reading agent stdout: {e}")
        await queue.put({"__type": "error", "message": str(e)})
    finally:
        await queue.put(None)


async def _drain_stderr(process, stderr_lines: list[str]) -> None:
    """Drain stderr to prevent pipe buffer blocking."""
    try:
        if process.stderr:
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    stderr_lines.append(text)
                    logger.info("Agent stderr: %s", text)
    except Exception as e:
        logger.debug("Stopped draining agent stderr: %s", e)


class SubprocessClient:
    """Runs agents locally with uv run (no Modal/Docker)."""

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
    ) -> AsyncIterator[dict]:
        resolved_env = os.environ.copy()
        # Don't inherit API's venv so uv run in agent/ uses agent's .venv (avoids uv warning)
        resolved_env.pop("VIRTUAL_ENV", None)
        resolved_env.pop("VIRTUAL_ENV_PROMPT", None)
        # Prevent SDK 0.1.44+ "nested Claude Code session" check from blocking the agent
        resolved_env.pop("CLAUDECODE", None)
        resolved_env.pop("CLAUDE_CODE_ENTRYPOINT", None)
        resolved_env.update(env_vars)

        workspace_dir = AGENT_DIR / "workspace" / session_id
        workspace_dir.mkdir(parents=True, exist_ok=True)
        (workspace_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        if history:
            (workspace_dir / "history.txt").write_text(history, encoding="utf-8")
        resolved_env["AGENT_WORKSPACE"] = str(workspace_dir)
        if sdk_session_id:
            resolved_env["SDK_SESSION_ID"] = sdk_session_id

        cmd = ["uv", "run", "python", "run_agent.py"]
        logger.info(f"Executing: {' '.join(cmd)} in {AGENT_DIR}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(AGENT_DIR),
                env=resolved_env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            yield {"__type": "error", "message": f"Could not execute: {cmd}"}
            return

        queue: asyncio.Queue = asyncio.Queue()
        stderr_lines: list[str] = []
        read_task = asyncio.create_task(_read_stdout(process, queue))
        stderr_task = asyncio.create_task(_drain_stderr(process, stderr_lines))

        cancelled = False
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        except asyncio.CancelledError:
            cancelled = True
        finally:
            read_task.cancel()
            stderr_task.cancel()
            for t in (read_task, stderr_task):
                try:
                    await t
                except asyncio.CancelledError:
                    pass

        if cancelled and process.returncode is None:
            # Close stdin so the agent gets EOF and can exit cleanly (avoids
            # CLIConnectionError "ProcessTransport is not ready for writing").
            if process.stdin:
                try:
                    process.stdin.close()
                except Exception:
                    pass
            try:
                await asyncio.wait_for(process.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                process.terminate()
        await process.wait()

        if process.returncode and process.returncode != 0 and not cancelled:
            stderr_text = "\n".join(stderr_lines).strip()
            error_msg = f"Agent exited with code {process.returncode}"
            if stderr_text:
                error_msg += f": {stderr_text}"
            logger.error("Agent subprocess failed: %s", error_msg)
            yield {"__type": "error", "message": error_msg}
        elif process.returncode and process.returncode != 0 and cancelled:
            logger.debug("Agent subprocess exited with code %s after cancel", process.returncode)

    async def get_file(self, session_id: str, path: str) -> bytes:
        """Read a file from the local session workspace."""
        workspace_dir = AGENT_DIR / "workspace" / session_id
        if path.startswith("/workspace/"):
            local_path = workspace_dir / path[len("/workspace/"):]
        elif not os.path.isabs(path):
            local_path = workspace_dir / path
        else:
            local_path = Path(path)
        return await asyncio.to_thread(local_path.read_bytes)
