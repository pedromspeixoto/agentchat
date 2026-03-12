#!/usr/bin/env python3
"""Agent entry point - runs Claude Agent SDK and streams messages to stdout as JSON lines."""
import asyncio
import dataclasses
import json
import os
import shutil
import subprocess
import sys
import uuid
from typing import Any

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, tool as sdk_tool, create_sdk_mcp_server

ARTIFACT_FORMATS = {"txt", "md", "csv"}

# Queue for artifact events emitted by the in-process MCP tool.
# The tool cannot print directly to stdout (it would corrupt the MCP stdio transport),
# so it enqueues events here and the outer message loop emits them.
_artifact_queue: asyncio.Queue = asyncio.Queue()


def to_jsonable(obj):
    """Recursively serialize dataclasses and standard types to JSON-safe dicts."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        result = {"__type": type(obj).__name__}
        for f in dataclasses.fields(obj):
            result[f.name] = to_jsonable(getattr(obj, f.name))
        return result
    elif isinstance(obj, list):
        return [to_jsonable(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    return obj


def _read_file(name: str) -> str | None:
    workspace = os.environ.get("AGENT_WORKSPACE", os.getcwd())
    path = os.path.join(workspace, name)
    if os.path.isfile(path):
        return open(path, encoding="utf-8").read().strip()
    return None


def _build_system_prompt(base: str, history_json: str | None) -> str:
    """Always include conversation history as a system instruction."""
    if not history_json:
        return base
    try:
        history = json.loads(history_json)
        if not history:
            return base
        lines = [base, "", "Conversation history so far:"]
        for msg in history:
            role = msg.get("role", "user").capitalize()
            lines.append(f"{role}: {msg.get('content', '')}")
        return "\n".join(lines)
    except Exception:
        return base


@sdk_tool(
    "create_artifact",
    (
        "Write content to a file and register it as a downloadable artifact in the chat UI. "
        "Use this instead of the Write tool whenever the output is meant to be downloaded or "
        "presented to the user as a file (e.g. a report, a summary doc, a data export). "
        "Supported formats: txt (plain text), md (Markdown), csv (comma-separated data). "
        "The artifact will appear in the Artifacts panel automatically."
    ),
    {
        "filename": str,   # base name without path, e.g. 'report.md'
        "content": str,    # full UTF-8 text content to write
        "format": str,     # one of: txt, md, csv
    },
)
async def create_artifact(args: dict[str, Any]) -> dict[str, Any]:
    """Write a file to the workspace and enqueue an Artifact event for the outer loop to emit."""
    filename: str = args.get("filename", "output.txt")
    content: str = args.get("content", "")
    fmt: str = args.get("format", "txt").lower().lstrip(".")

    if fmt not in ARTIFACT_FORMATS:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error: unsupported format '{fmt}'. Allowed: {', '.join(sorted(ARTIFACT_FORMATS))}.",
                }
            ]
        }

    # Strip any path components to keep the file inside the workspace
    safe_name = os.path.basename(filename) or "output"
    base = safe_name.rsplit(".", 1)[0] if "." in safe_name else safe_name
    final_name = f"{base}.{fmt}"

    workspace = os.environ.get("AGENT_WORKSPACE", os.getcwd())
    file_path = os.path.join(workspace, final_name)
    encoded = content.encode("utf-8")

    try:
        with open(file_path, "wb") as fh:
            fh.write(encoded)
    except OSError as exc:
        return {
            "content": [{"type": "text", "text": f"Error writing file: {exc}"}]
        }

    # Enqueue the Artifact SSE event — the outer message loop picks it up and
    # prints it to stdout. We must not print directly here because this coroutine
    # runs inside the in-process MCP server whose transport uses stdio.
    await _artifact_queue.put({
        "__type": "Artifact",
        "id": str(uuid.uuid4()),
        "name": final_name,
        "kind": fmt,
        "size": len(encoded),
        "sandbox_path": f"/workspace/{final_name}",
    })

    return {
        "content": [
            {
                "type": "text",
                "text": f"Artifact created: {final_name} ({len(encoded)} bytes). It will appear in the artifacts panel.",
            }
        ]
    }


def _diagnose_claude() -> None:
    """Print claude binary location and version to stderr for debugging."""
    path = shutil.which("claude")
    print(f"[diag] claude binary: {path}", file=sys.stderr, flush=True)
    if path:
        result = subprocess.run([path, "--version"], capture_output=True, text=True)
        print(f"[diag] claude --version stdout: {result.stdout.strip()}", file=sys.stderr, flush=True)
        print(f"[diag] claude --version stderr: {result.stderr.strip()}", file=sys.stderr, flush=True)
        print(f"[diag] claude --version exit: {result.returncode}", file=sys.stderr, flush=True)


async def run():
    _diagnose_claude()
    has_direct = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_foundry = bool(os.environ.get("CLAUDE_CODE_USE_FOUNDRY")) and bool(os.environ.get("ANTHROPIC_FOUNDRY_API_KEY"))
    if not has_direct and not has_foundry:
        print(json.dumps({
            "__type": "error",
            "message": (
                "No Anthropic credentials found. "
                "Set ANTHROPIC_API_KEY for direct access, or "
                "CLAUDE_CODE_USE_FOUNDRY=1 + ANTHROPIC_FOUNDRY_API_KEY + ANTHROPIC_FOUNDRY_BASE_URL for Azure AI Foundry."
            ),
        }), flush=True)
        sys.exit(1)

    prompt = _read_file("prompt.txt")
    if not prompt:
        print(json.dumps({"__type": "error", "message": "No prompt provided"}), flush=True)
        sys.exit(1)

    history_json = _read_file("history.txt")
    sdk_session_id = os.environ.get("SDK_SESSION_ID") or None

    base_system_prompt = os.environ.get("SYSTEM_PROMPT", "You are a helpful assistant.")
    system_prompt = _build_system_prompt(base_system_prompt, history_json)

    artifact_server = create_sdk_mcp_server(
        name="artifact_tools",
        version="1.0.0",
        tools=[create_artifact],
    )

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        allowed_tools=[
            "Read", "Write", "Bash", "Glob", "Grep",
            "mcp__artifact_tools__create_artifact",
        ],
        permission_mode="acceptEdits",
        resume=sdk_session_id,
        include_partial_messages=True,
        mcp_servers={"artifact_tools": artifact_server},
        setting_sources=['project'], ## ["user", "project", "local"] to load all settings
    )

    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            async for message in client.receive_response():
                print(json.dumps(to_jsonable(message)), flush=True)
                # Drain any artifact events enqueued by the create_artifact tool
                while not _artifact_queue.empty():
                    event = _artifact_queue.get_nowait()
                    print(json.dumps(event), flush=True)
    except ExceptionGroup as eg:
        # Filter out transport cleanup errors that fire after streaming completes
        # (ProcessTransport is not ready for writing — SDK cleanup race condition)
        real_errors = [
            e for e in eg.exceptions
            if "ProcessTransport is not ready" not in str(e)
            and "CLIConnectionError" not in type(e).__name__
        ]
        if real_errors:
            raise ExceptionGroup(eg.message, real_errors) from eg
        # All sub-exceptions are transport cleanup noise — messages already streamed


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    asyncio.run(run())
