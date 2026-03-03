# Building AgentChat: A Production-Grade AI Chat Application with Sandboxed Agent Execution

> A deep-dive into building a streaming, multi-session chat application powered by the Claude Agent SDK — with Modal cloud containers and subprocess sandboxes for safe, isolated agent execution.

---

## Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [The Stack](#the-stack)
4. [Frontend: React + SSE Streaming](#frontend-react--sse-streaming)
5. [The API Layer: FastAPI + PostgreSQL](#the-api-layer-fastapi--postgresql)
6. [The Sandbox: Isolated Agent Execution](#the-sandbox-isolated-agent-execution)
   - [Why Sandboxing Matters](#why-sandboxing-matters)
   - [The Sandbox Abstraction](#the-sandbox-abstraction)
   - [Subprocess Backend (Local Dev)](#subprocess-backend-local-dev)
   - [Modal Backend (Production)](#modal-backend-production)
   - [The Agent Inside the Sandbox](#the-agent-inside-the-sandbox)
   - [Message Flow: Sandbox to Browser](#message-flow-sandbox-to-browser)
   - [Artifact Handling](#artifact-handling)
   - [Security Considerations & Open Items](#security-considerations--open-items)
7. [Session Management & History](#session-management--history)
8. [Artifact Storage with MinIO](#artifact-storage-with-minio)
9. [Running the System](#running-the-system)
10. [What's Next](#whats-next)

---

## Overview

AgentChat is a full-stack AI chat application built around the **Claude Agent SDK**. Unlike typical chatbot wrappers, AgentChat runs the AI agent inside an **isolated execution sandbox** — either a local subprocess or a Modal cloud container — so the agent can safely execute code, create files, and use tools without touching the host environment.

The result is a system that feels like a polished chat UI but is actually orchestrating a distributed, containerized AI agent under the hood.

```
  You type a message in the browser
          │
          ▼
  React frontend sends it over HTTP
          │
          ▼
  FastAPI picks it up and spins up (or resumes)
  an isolated sandbox for this session
          │
          ▼
  Claude Agent SDK runs inside the sandbox,
  executes tools, writes files, thinks out loud
          │
          ▼
  Results stream back as Server-Sent Events
          │
          ▼
  Browser renders messages and artifacts in real time
```

---

## System Architecture

Here's the full system at a glance:

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser                                  │
│                                                                 │
│  ┌─────────────┐   ┌──────────────────┐   ┌─────────────────┐  │
│  │   Sidebar   │   │    Chat Area     │   │ Artifacts Panel │  │
│  │  (sessions) │   │ (messages + SSE) │   │  (files/docs)   │  │
│  └─────────────┘   └──────────────────┘   └─────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │  HTTP REST + Server-Sent Events
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   FastAPI  (port 8080)                          │
│                                                                 │
│  POST /api/v1/chat/                ← streaming SSE endpoint     │
│  GET|DELETE /api/v1/sessions/      ← session management         │
│  GET /api/v1/sessions/{id}/messages                             │
│  GET /api/v1/sessions/{id}/artifacts                            │
│  GET /health  |  GET /ready                                     │
└────────┬──────────────────┬──────────────────┬──────────────────┘
         │                  │                  │
         ▼                  ▼                  ▼
┌──────────────┐   ┌────────────────┐   ┌────────────────────────┐
│  PostgreSQL  │   │     MinIO      │   │       Sandbox          │
│              │   │  (S3-compat.)  │   │                        │
│  sessions    │   │               │   │  ┌──────────────────┐   │
│  messages    │   │  artifacts/   │   │  │   Subprocess     │   │
│  artifacts   │   │  {session}/   │   │  │  (local / dev)   │   │
│  usage stats │   │  {file}       │   │  └────────┬─────────┘   │
└──────────────┘   └────────────────┘   │           │             │
                                        │  ┌────────┴─────────┐   │
                                        │  │  Modal Container │   │
                                        │  │   (production)   │   │
                                        │  └────────┬─────────┘   │
                                        └───────────┼─────────────┘
                                                    │
                                                    ▼
                                        ┌───────────────────────┐
                                        │   Claude Agent SDK    │
                                        │                       │
                                        │  Tools: Read, Write,  │
                                        │  Bash, Glob, Grep,    │
                                        │  create_artifact      │
                                        │                       │
                                        │  ← Anthropic API      │
                                        └───────────────────────┘
```

---

## The Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend | React + Vite + TypeScript | Fast dev experience, native SSE support |
| API | FastAPI (Python) | Async-first, excellent SSE support |
| Agent | Claude Agent SDK | Official SDK with tool use, resumption, streaming |
| Sandbox (dev) | Python subprocess | Zero infrastructure, instant feedback loop |
| Sandbox (prod) | Modal cloud containers | Isolated, scalable, GPU-capable if needed |
| Database | PostgreSQL + SQLAlchemy | Reliable session/message persistence |
| Artifact storage | MinIO (S3-compatible) | Self-hosted object store with presigned URLs |
| Config | Pydantic Settings | Type-safe environment config |
| Migrations | Alembic | Schema versioning |

---

## Frontend: React + SSE Streaming

The frontend is a single-page React app. What makes it interesting is how it handles **concurrent streams** across multiple sessions.

### Multi-Session Streaming

When you fire off a message and then switch to a different conversation, the original stream keeps running in the background. The frontend tracks this with an `AbortController` map keyed by session ID:

```
User sends message in Session A
    │
    ├── Stream starts for Session A
    │   AbortController stored: streamsRef["session-A"] = controller
    │
User clicks Session B
    │
    ├── Session A stream continues silently in background
    │   Session B messages load normally
    │   Sidebar shows "Responding…" badge on Session A
    │
Session A stream completes
    │
    ├── streamsRef["session-A"] deleted
    │   DB save happens via BackgroundTask
    │
User clicks back to Session A
    │
    └── useEffect reloads messages from DB
        Messages appear fully hydrated
```

### SSE Event Protocol

The API uses Server-Sent Events for streaming. Each event has a `type` and a JSON `data` payload:

```
event: session_start
data: {"session_id": "abc123", "is_new": true}

event: StreamEvent
data: {"delta": {"type": "text_delta", "text": "Here is"}}

event: StreamEvent
data: {"delta": {"type": "text_delta", "text": " your analysis..."}}

event: AssistantMessage
data: {"content": [{"type": "text", "text": "Here is your analysis..."}]}

event: Artifact
data: {"id": "...", "name": "report.csv", "kind": "csv", "url": "https://..."}

event: done
data: {}
```

The frontend parses these line-by-line, assembling streaming deltas into visible text in real time, and routing artifact events to the side panel.

### Landing Page to Chat Transition

```
┌──────────────────────────────┐     User clicks "Start"
│                              │     ──────────────────▶
│        AgentChat             │
│                              │     ┌──────────────────────────┐
│   [Claude Agent SDK badge]   │     │  Chat Area               │
│                              │     │                          │
│   A powerful interface...    │     │  [empty, ready to type]  │
│                              │     │                          │
│   [ Start a conversation ]   │     │  ┌──────────────────┐   │
│                              │     │  │ Ask anything…    │   │
│   ┌────────┐ ┌──────────┐   │     │  └──────────────────┘   │
│   │ SDK    │ │ Sandbox  │   │     └──────────────────────────┘
│   └────────┘ └──────────┘   │
└──────────────────────────────┘
```

---

## The API Layer: FastAPI + PostgreSQL

### Chat Endpoint

The most important route is `POST /api/v1/chat/`. It is responsible for:

1. Creating or retrieving a session
2. Saving the user message
3. Resolving the sandbox client (subprocess or Modal)
4. Loading the agent config (`agent/agent.yaml`)
5. Building the conversation history and passing it to the sandbox
6. Streaming agent output back as SSE
7. Saving assistant messages, tool calls, usage stats, and artifacts in a `BackgroundTask` after the stream closes

```
POST /api/v1/chat/
      │
      ├─ 1. Upsert session in PostgreSQL
      ├─ 2. Save user message to DB
      ├─ 3. Load agent.yaml → image, env_vars whitelist, timeouts
      ├─ 4. Build history from previous messages
      ├─ 5. get_sandbox_client() → SubprocessClient | ModalClient
      │
      └─ 6. EventSourceResponse (SSE)
              │
              └─ async for msg in sandbox.run_agent(...):
                      │
                      ├─ StreamEvent → yield text delta SSE
                      ├─ AssistantMessage → yield SSE + queue for DB save
                      ├─ Artifact → get_file() → upload to MinIO → yield SSE
                      ├─ ResultMessage → capture sdk_session_id, usage stats
                      └─ error → yield error SSE
              │
              └─ BackgroundTask: save messages, events, usage, artifacts to DB
```

### Database Schema

```
ChatSession
├── id (UUID, PK)
├── title (str, nullable)
├── sdk_session_id (str, nullable)  ← Claude SDK session for resumption
├── created_at
└── updated_at

ChatMessage
├── id (UUID, PK)
├── chat_id (FK → ChatSession)
├── role ('user' | 'assistant')
├── content (text)
├── message_metadata (JSON)
└── created_at

ChatEvent
├── id (UUID, PK)
├── chat_id (FK → ChatSession)
├── message_id (FK → ChatMessage, nullable)
├── event_type ('tool_call' | 'tool_result' | 'thinking' | 'error' | 'status')
├── event_name (str, nullable)
├── event_data (JSON)
└── created_at

ChatUsage
├── id (UUID, PK)
├── chat_id (FK → ChatSession)
├── input_tokens, output_tokens, total_tokens
├── cost_usd
└── created_at

ChatArtifact
├── id (UUID, PK)
├── chat_id (FK → ChatSession)
├── name (filename)
├── kind ('csv' | 'pdf' | 'json' | 'txt' | 'xlsx' | 'other')
├── size (bytes, nullable)
├── url (presigned MinIO URL, nullable)
└── created_at
```

All relationships cascade on delete — removing a session removes everything attached to it.

---

## The Sandbox: Isolated Agent Execution

This is the most critical and interesting part of AgentChat. The sandbox layer is what separates this from a simple API wrapper — it gives the agent a real, isolated environment to execute code, read and write files, and use tools without touching the host system.

### Why Sandboxing Matters

When you give an AI agent tools like `Bash`, `Write`, and `Read`, you need to think carefully about where those tools run. Without sandboxing:

- The agent runs code directly on your server
- A malicious or buggy prompt can affect the host filesystem
- Multiple sessions can interfere with each other
- There's no resource isolation (CPU, memory, disk)
- You can't control what network calls the agent makes

AgentChat solves this by running the agent **inside an isolated environment** — either a local subprocess with a scoped workspace directory, or a cloud container on Modal.

### The Sandbox Abstraction

Both backends implement the same `SandboxClient` protocol, making them interchangeable at runtime:

```
SandboxClient (Protocol)
│
├── run_agent(
│     session_id: str,
│     image_url: str,
│     prompt: str,
│     env_vars: dict[str, str],
│     command: list[str] | None,
│     timeout: int,
│     idle_timeout: int,
│     sdk_session_id: str | None,
│     history: str | None,
│   ) -> AsyncIterator[dict]
│
└── get_file(session_id: str, path: str) -> bytes

         ┌──────────────────────────┐
         │                          │
         ▼                          ▼
SubprocessClient               ModalClient
(SANDBOX_BACKEND=subprocess)   (SANDBOX_BACKEND=modal)
```

The factory is a single function:

```python
def get_sandbox_client() -> SandboxClient:
    if settings.SANDBOX_BACKEND == "modal":
        return ModalClient()
    return SubprocessClient()
```

Swapping backends is a one-line environment variable change.

---

### Subprocess Backend (Local Dev)

The subprocess backend is designed for **local development** — zero infrastructure, instant iteration.

```
FastAPI Route
     │
     │  sandbox.run_agent(session_id, prompt, ...)
     ▼
SubprocessClient
     │
     ├─ 1. Create workspace:  agent/workspace/{session_id}/
     ├─ 2. Write:             workspace/prompt.txt
     ├─ 3. Write:             workspace/history.txt  (if resuming)
     │
     ├─ 4. Build env vars:
     │      Copy OS environment
     │      Remove: VIRTUAL_ENV, CLAUDE_CODE* (avoid nested venv/SDK conflicts)
     │      Add:    AGENT_WORKSPACE, ANTHROPIC_API_KEY, SDK_SESSION_ID, ...
     │
     ├─ 5. Spawn:  asyncio.create_subprocess_exec(
     │               "uv", "run", "python", "run_agent.py",
     │               cwd="agent/",
     │               env=env,
     │               stdout=PIPE, stderr=PIPE
     │             )
     │
     ├─ 6. Stream stdout line-by-line:
     │      async for line in process.stdout:
     │          msg = json.loads(line)
     │          yield msg
     │
     ├─ 7. Drain stderr in parallel (prevents pipe buffer deadlock)
     │
     └─ 8. Graceful shutdown:
            Close stdin → wait 3s → terminate if still running


get_file(session_id, path):
     └─ Read from:  agent/workspace/{session_id}/{path}
```

**Key implementation details:**

- `VIRTUAL_ENV` is stripped to prevent the subprocess from inheriting the outer virtual environment (which would confuse `uv run`)
- `CLAUDE_CODE*` env vars are stripped so the Claude Agent SDK doesn't detect a nested Claude Code session and apply different behavior
- Stderr is drained concurrently with stdout to avoid blocking the pipe buffer — a subtle but critical detail for long-running agents
- The workspace directory is scoped per `session_id`, so sessions are fully isolated from each other on disk

---

### Modal Backend (Production)

The Modal backend runs the agent inside a **real cloud container**, providing true isolation, scalability, and reproducibility.

```
FastAPI Route
     │
     │  sandbox.run_agent(session_id, prompt, ...)
     ▼
ModalClient
     │
     ├─ 1. Check for existing sandbox:
     │      modal.Sandbox.list(tags={"session_id": session_id})
     │
     ├─ 2a. If exists and running:
     │       sandbox = existing sandbox
     │
     ├─ 2b. If not exists (or exited):
     │       sandbox = modal.Sandbox.create(
     │         image=modal.Image.from_registry(image_url),
     │         secrets=[modal.Secret.from_dict(env_vars)],
     │         timeout=600,
     │         cloud="aws",
     │         tags={"session_id": session_id}
     │       )
     │
     ├─ 3. Write files to container:
     │      sandbox.open("/workspace/prompt.txt", "w").write(prompt)
     │      sandbox.open("/workspace/history.txt", "w").write(history)
     │
     ├─ 4. Execute agent:
     │      process = await sandbox.exec(*command)
     │        command = ["python", "/app/run_agent.py"]
     │
     ├─ 5. Stream stdout in thread executor:
     │      async for line in stdout_lines:
     │          msg = json.loads(line)
     │          yield msg
     │
     └─ 6. Cleanup:
            Sandbox idles for idle_timeout then terminates automatically


get_file(session_id, path):
     └─ sandbox.open(f"/workspace/{path}", "rb").read()
```

**Container lifecycle per session:**

```
Session Start
     │
     ▼
┌─────────────────────────────────────┐
│  Modal Sandbox (tagged: session_id) │
│                                     │
│  Image: pedropeixoto6/              │
│         agentchat-claude-sandbox    │
│         :{git-sha}                  │  ← immutable, pinned to git SHA
│                                     │
│  /workspace/                        │
│    prompt.txt                       │
│    history.txt                      │
│    [agent-generated files...]       │
│                                     │
│  ENV: ANTHROPIC_API_KEY=...         │
│       AGENT_WORKSPACE=/workspace    │
│       TAVILY_API_KEY=...            │
└──────────────┬──────────────────────┘
               │
               │  idle_timeout (2 min) expires
               ▼
         Sandbox exits
         (auto-cleanup by Modal)
```

**Why pin images to git SHA?**

The agent image is built with `make agent`, which tags it as `{image}:{short-git-sha}`. This means every deployment is immutable and traceable — you always know exactly what code ran in production for any given session.

```bash
# Builds, pushes, and updates agent/agent.yaml in one shot
make agent

# Result: agent/agent.yaml updated to point at:
# pedropeixoto6/agentchat-claude-sandbox:96efe3a
```

---

### The Agent Inside the Sandbox

Regardless of which sandbox backend is used, the agent always runs the same code: `agent/run_agent.py` with the Claude Agent SDK.

```
agent/run_agent.py starts
     │
     ├─ Read AGENT_WORKSPACE from env
     ├─ Read prompt.txt from workspace
     ├─ Read history.txt from workspace (if exists)
     ├─ Read SDK_SESSION_ID from env (if resuming)
     │
     ├─ Build MCP server with custom tool:
     │      @sdk_tool("create_artifact")
     │      async def create_artifact(args):
     │          # Write file to workspace
     │          # Queue Artifact event
     │
     ├─ Configure agent:
     │      ClaudeAgentOptions(
     │        system_prompt="...",
     │        allowed_tools=["Read", "Write", "Bash", "Glob", "Grep",
     │                       "mcp__artifact_tools__create_artifact"],
     │        permission_mode="acceptEdits",
     │        resume=sdk_session_id,
     │        include_partial_messages=True,
     │        mcp_servers={"artifact_tools": artifact_server},
     │      )
     │
     └─ Run agent loop:
          async for message in agent.run(prompt):
               │
               ├─ Check artifact_queue for pending artifacts
               │   If any: print Artifact event JSON to stdout
               │
               └─ print(json.dumps(to_jsonable(message)), flush=True)
                    └─ Serialized to: {"__type": "AssistantMessage", ...}
```

**Message serialization** is key — all SDK types are converted to JSON with a `__type` discriminator field, which the API layer uses to route them correctly.

**Why queue artifacts instead of printing them inline?**

The agent uses an MCP (Model Context Protocol) server for the `create_artifact` tool. MCP communication happens over stdio, so the agent can't freely print to stdout during tool execution without corrupting the MCP protocol stream. Instead, artifacts are queued and emitted by the outer message loop between turns.

---

### Message Flow: Sandbox to Browser

Here's the complete path a single streaming message takes, from agent to pixel:

```
Claude Agent SDK (inside sandbox)
     │
     │  AssistantMessage with streaming text
     │
     ▼
run_agent.py
     │
     │  print(json.dumps(to_jsonable(message)), flush=True)
     │
     ▼
Sandbox stdout (pipe or Modal exec stream)
     │
     │  {"__type": "StreamEvent", "delta": {"type": "text_delta", "text": "Hello"}}
     │
     ▼
SubprocessClient / ModalClient
     │
     │  async for line in stdout:
     │      msg = json.loads(line)
     │      yield msg
     │
     ▼
FastAPI chat route
     │
     │  async for msg in sandbox.run_agent(...):
     │      event_type = msg.get("__type", "")
     │      data = json.dumps(msg)
     │      yield f"event: {event_type}\ndata: {data}\n\n"
     │
     ▼
EventSourceResponse (SSE)
     │
     │  HTTP/1.1 200 OK
     │  Content-Type: text/event-stream
     │
     │  event: StreamEvent
     │  data: {"delta": {"type": "text_delta", "text": "Hello"}}
     │
     ▼
Browser EventSource
     │
     │  onmessage → parse event type → route to callback
     │      StreamEvent → setStreamingText(prev + delta)
     │
     ▼
React state update → re-render → text appears on screen
```

---

### Artifact Handling

Artifacts are files the agent produces — CSVs, PDFs, JSON exports, analysis reports. They require a more complex flow because they need to leave the sandbox and be stored durably.

```
Agent calls create_artifact("report.csv", content, "csv")
     │
     ├─ Tool writes file to:  /workspace/report.csv
     └─ Enqueues:  {"type": "Artifact", "sandbox_path": "report.csv", "name": "report.csv"}

     ▼

Agent loop emits Artifact event to stdout
     │
     │  {"__type": "Artifact", "sandbox_path": "report.csv", "name": "report.csv", ...}
     │
     ▼

FastAPI chat route intercepts Artifact event
     │
     ├─ sandbox.get_file(session_id, "report.csv")
     │       └─ Reads bytes from workspace (subprocess) or container (Modal)
     │
     ├─ upload_artifact(session_id, artifact_id, "report.csv", file_bytes)
     │       └─ Uploads to MinIO:
     │              bucket: agentchat-artifacts
     │              key:    artifacts/{session_id}/{artifact_id}/report.csv
     │              Returns: presigned URL (valid 7 days)
     │
     ├─ Save ChatArtifact to PostgreSQL
     │
     └─ Forward SSE to browser (with MinIO URL, without sandbox_path):
            event: Artifact
            data: {"name": "report.csv", "kind": "csv", "url": "https://minio/..."}

     ▼

Browser receives Artifact event
     │
     ├─ Adds to artifacts list → ArtifactsPanel opens
     └─ Inline artifact card appears in chat with download link
```

**Artifact type detection** happens by file extension, mapped to one of: `csv`, `pdf`, `json`, `txt`, `xlsx`, `other`. Each type gets a distinct color and icon in the UI.

---

### Security Considerations & Open Items

#### What's Protected Today

**Environment variable whitelisting** is enforced via `agent.yaml`:

```yaml
env_vars:
  - ANTHROPIC_API_KEY
  - TAVILY_API_KEY
```

Only variables explicitly listed here are passed to the sandbox. Everything else — database credentials, MinIO secrets, internal service tokens — never enters the container. The API code enforces this whitelist strictly before calling `sandbox.run_agent()`.

**Session isolation** is enforced at the workspace level. Each session gets its own directory (`workspace/{session_id}/`) and its own Modal sandbox (tagged with `session_id`), so sessions cannot read each other's files.

**Tool whitelisting** in `run_agent.py` restricts what the agent can do — only `Read`, `Write`, `Bash`, `Glob`, `Grep`, and `create_artifact` are available. No network tools, no arbitrary imports.

#### ⚠️ Open Item: Outbound Network & Secret Exfiltration via Container Proxy

> **This is a known gap that needs to be addressed before running untrusted workloads.**

Currently, the agent running inside the sandbox has unrestricted outbound network access. This means a sufficiently adversarial prompt could instruct the agent to exfiltrate data — including any secrets that were legitimately injected (like `ANTHROPIC_API_KEY`) — via outbound HTTP calls.

**The fix: a container-level egress proxy.**

The plan is to place a transparent proxy between the sandbox container and the internet that:

1. **Blocks all outbound traffic by default**
2. **Whitelists only approved destinations** (e.g., `api.anthropic.com`, specific tool endpoints)
3. **Strips or rewrites Authorization headers** on non-whitelisted destinations to prevent secret injection
4. **Logs all outbound requests** for auditability

```
Sandbox Container
     │
     │  All outbound traffic
     ▼
┌─────────────────────────────┐
│      Egress Proxy           │   ← TO BE IMPLEMENTED
│                             │
│  Rules:                     │
│  ALLOW  api.anthropic.com   │
│  ALLOW  api.tavily.com      │
│  BLOCK  *                   │
│                             │
│  Strip: Authorization       │
│         on blocked routes   │
└──────────────┬──────────────┘
               │  Approved traffic only
               ▼
          The Internet
```

For Modal, this could be implemented using Modal's network controls or a sidecar proxy. For the subprocess backend, OS-level network namespacing or a local proxy (e.g., mitmproxy in transparent mode) would achieve the same.

**Until this is in place, AgentChat should only be used with trusted prompts and trusted users.**

---

## Session Management & History

AgentChat supports true multi-turn conversations across sessions. The Claude Agent SDK has native session resumption — when you return to a conversation, the agent picks up exactly where it left off.

```
First message in Session A
     │
     ▼
Agent runs, SDK creates internal session
     │
ResultMessage received:
     └─ sdk_session_id: "sdk-session-abc"

API saves sdk_session_id to ChatSession in DB

─────────────────────────────────────────

Second message in Session A
     │
     ▼
API loads ChatSession → reads sdk_session_id: "sdk-session-abc"
     │
     ▼
sandbox.run_agent(sdk_session_id="sdk-session-abc", ...)
     │
     ▼
Agent resumes conversation with full context intact
```

**History fallback:** For the Modal backend, there's a known issue where passing `SDK_SESSION_ID` directly can cause problems with sandbox initialization. As a workaround, the API serializes conversation history to a `history.txt` file in the workspace, which the agent reads and injects into its system prompt context. This preserves conversational continuity even when native SDK session resumption isn't available.

---

## Artifact Storage with MinIO

Artifacts produced by the agent are stored in MinIO, an S3-compatible object store. This decouples artifact lifetime from sandbox lifetime — the sandbox can terminate, but artifacts remain accessible indefinitely.

```
MinIO Bucket: agentchat-artifacts
│
└── artifacts/
    ├── {session-id-1}/
    │   ├── {artifact-id-1}/
    │   │   └── report.csv
    │   └── {artifact-id-2}/
    │       └── analysis.pdf
    └── {session-id-2}/
        └── {artifact-id-3}/
            └── data.json
```

Presigned URLs are generated at upload time (valid for 7 days) and stored in the `ChatArtifact` table. The frontend uses these URLs directly for downloads — no API proxy needed.

In production, MinIO can be replaced with any S3-compatible service (AWS S3, GCS with interop, Cloudflare R2) by changing endpoint configuration.

---

## Running the System

### Local Development

```bash
# 1. Install dependencies (api + web)
make setup

# 2. Start PostgreSQL and MinIO
make infra

# 3. Run DB migrations
make migrate

# 4. Copy and configure environment
cp api/.env.example api/.env
# Set ANTHROPIC_API_KEY, leave SANDBOX_BACKEND=subprocess

# 5. Start API
make api        # → http://localhost:8080

# 6. Start frontend (new terminal)
make web        # → http://localhost:5173
```

### Production (with Modal)

```bash
# 1. Build and push agent Docker image
make agent
# → Builds for linux/amd64, pushes to registry
# → Updates agent/agent.yaml with new image tag
# → Commit agent.yaml alongside code changes

# 2. Configure environment
# Set SANDBOX_BACKEND=modal
# Set MODAL_TOKEN_ID and MODAL_TOKEN_SECRET

# 3. Deploy API (your preferred platform)
# API picks up Modal config automatically
```

### Infrastructure Topology

```
Local Dev                          Production
─────────────────────────          ─────────────────────────────────
localhost:5173  (Vite)             CDN / static hosting (React build)
localhost:8080  (FastAPI)          Cloud Run / ECS / Fly.io (FastAPI)
localhost:5432  (PostgreSQL)       Managed PostgreSQL (RDS, Supabase)
localhost:9000  (MinIO)            S3 / R2 / GCS
Subprocess sandbox                 Modal cloud containers
```

---

## What's Next

AgentChat is a solid foundation. Here's what's on the roadmap:

### Security (High Priority)
- **Container egress proxy** — Block secret exfiltration from sandboxes (see [open item above](#-open-item-outbound-network--secret-exfiltration-via-container-proxy))
- **Rate limiting** — Per-user token and request limits
- **Authentication** — User accounts and session ownership

### Agent Capabilities
- **More tools** — Web search, code execution with output capture, image generation
- **Multi-agent** — Orchestrate multiple specialized agents per session
- **Streaming tool results** — Show tool call inputs/outputs inline as they happen

### Infrastructure
- **Horizontal API scaling** — Stateless API with external stream coordination
- **Artifact versioning** — Keep history of artifact revisions per session
- **Webhook support** — Notify external systems when agents complete tasks

### UX
- **Markdown rendering** — Render agent responses as formatted markdown
- **Code syntax highlighting** — Better display of code blocks
- **Artifact previews** — In-browser CSV viewer, PDF previewer

---

*Built with the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk) and [Modal](https://modal.com).*
