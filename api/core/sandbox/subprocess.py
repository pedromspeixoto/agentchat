"""Local subprocess sandbox - runs agents with uv run.

Uses subprocess.Popen + threads instead of asyncio.create_subprocess_exec
so it works on Windows without requiring ProactorEventLoop.
"""
import asyncio
import json
import os
import subprocess
import threading
from pathlib import Path
from typing import AsyncIterator

from core.agents import AGENT_DIR
from core.logging import get_logger

logger = get_logger(__name__)


def _read_stdout_thread(
    proc: subprocess.Popen,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Read process stdout line-by-line and push parsed JSON dicts to queue."""
    try:
        for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                loop.call_soon_threadsafe(queue.put_nowait, json.loads(line))
            except json.JSONDecodeError:
                loop.call_soon_threadsafe(queue.put_nowait, {"__type": "raw", "content": line})
    except Exception as e:
        logger.error(f"Error reading agent stdout: {e}")
        loop.call_soon_threadsafe(queue.put_nowait, {"__type": "error", "message": str(e)})
    finally:
        loop.call_soon_threadsafe(queue.put_nowait, None)


def _drain_stderr_thread(
    proc: subprocess.Popen,
    stderr_lines: list[str],
) -> None:
    """Drain stderr to prevent pipe buffer blocking."""
    try:
        for raw_line in proc.stderr:
            text = raw_line.decode("utf-8", errors="replace").rstrip()
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
        files: list[tuple[str, bytes]] | None = None,
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

        # Write uploaded files and augment prompt
        if files:
            uploads_dir = workspace_dir / "uploads"
            uploads_dir.mkdir(exist_ok=True)
            file_lines = []
            for filename, content in files:
                dest = uploads_dir / filename
                dest.write_bytes(content)
                file_lines.append(f"- {dest} ({len(content)} bytes)")
            prompt = prompt + (
                "\n\nThe user uploaded the following files along with their message:\n"
                + "\n".join(file_lines)
                + "\n\nYou can read these files using the Read tool at the absolute paths shown above."
            )

        (workspace_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        if history:
            (workspace_dir / "history.txt").write_text(history, encoding="utf-8")
        resolved_env["AGENT_WORKSPACE"] = str(workspace_dir)
        #if sdk_session_id:
        #    resolved_env["SDK_SESSION_ID"] = sdk_session_id

        cmd = ["uv", "run", "python", "run_agent.py"]
        logger.info(f"Executing: {' '.join(cmd)} in {AGENT_DIR}")

        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(AGENT_DIR),
                env=resolved_env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            yield {"__type": "error", "message": f"Could not execute: {cmd}"}
            return

        queue: asyncio.Queue = asyncio.Queue()
        stderr_lines: list[str] = []
        loop = asyncio.get_running_loop()

        stdout_thread = threading.Thread(
            target=_read_stdout_thread, args=(process, queue, loop), daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_drain_stderr_thread, args=(process, stderr_lines), daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

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
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)

        if cancelled and process.poll() is None:
            # Close stdin so the agent gets EOF and can exit cleanly (avoids
            # CLIConnectionError "ProcessTransport is not ready for writing").
            if process.stdin:
                try:
                    process.stdin.close()
                except Exception:
                    pass
            try:
                process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait()
        else:
            process.wait()

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
