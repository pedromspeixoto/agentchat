# agentchat

Chat application with Claude Agent SDK for intelligence, session management and sandbox orchestration (Modal or Subprocess) using FastAPI, and a React (powered by Vite) frontend.

![Demo](assets/demo.gif)

## Architecture

```
  Browser
    │
    │  HTTP / SSE
    ▼
┌──────────────────────────────────────────────────────────┐
│                   React + Vite (port 5173)               │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐   │
│  │   Sidebar   │  │   ChatArea   │  │ ArtifactsPanel │   │
│  │  (sessions) │  │  (messages)  │  │   (files)      │   │
│  └─────────────┘  └──────────────┘  └────────────────┘   │
└────────────────────────┬─────────────────────────────────┘
                         │ REST + SSE
                         ▼
┌──────────────────────────────────────────────────────────┐
│                  FastAPI (port 8080)                     │
│                                                          │
│  POST /api/v1/chat/          ← streaming (SSE)           │
│  GET/POST/DELETE /api/v1/sessions/                       │
│  GET /api/v1/sessions/{id}/messages                      │
│  GET /api/v1/sessions/{id}/artifacts                     │
│  GET /health                                             │
└──────┬───────────────────────┬───────────────────────────┘
       │                       │
       ▼                       ▼
┌─────────────┐      ┌─────────────────────────────────────┐
│  PostgreSQL │      │            Sandbox                  │
│  (sessions, │      │                                     │
│   messages, │      │  ┌──────────────┐  ┌────────────┐   │
│  artifacts) │      │  │  Subprocess  │  │   Modal    │   │
└─────────────┘      │  └──────┬───────┘  └───────┬────┘   │
                     │         └────────┬─────────┘        │
                     └──────────────────┼──────────────────┘
                                        │
                                        ▼
                             ┌──────────────────────┐
                             │  Claude Agent SDK    │
                             │  (agent/agent.yaml)  │
                             │                      │
                             │  ← Anthropic API     │
                             └──────────────────────┘
                                        │
                                        ▼
                             ┌──────────────────────┐
                             │    MinIO / S3        │
                             │  (artifact storage)  │
                             └──────────────────────┘
```

## Structure

- **api/** — FastAPI backend (Python, PostgreSQL, MiniO, SSE chat, sessions)
- **web/** — React + Vite + TypeScript frontend
- **agent/** — Agent configuration and tooling (Claude Agent SDK)

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (for PostgreSQL)
- [uv](https://docs.astral.sh/uv/) (Python)
- [Node.js](https://nodejs.org/) (for the web app)

## Setup

```bash
# Install dependencies
make setup

# Start PostgreSQL
make infra
```

## Running

```bash
# API
make api

# Web (in another terminal)
make web
```

- **API:** [http://localhost:8080](http://localhost:8080)
- **Web:** [http://localhost:5173](http://localhost:5173) (or the port Vite prints)

## Environment

- Copy `api/.env.example` to `api/.env` and set your database and API keys as needed.
- The API expects PostgreSQL (default in `docker-compose.yaml`: user/pass/db `agentchat`, port `5432`).

## Commands


| Command           | Description               |
| ----------------- | ------------------------- |
| `make setup`      | Install API and web deps  |
| `make infra`      | Start Docker (PostgreSQL) |
| `make infra-down` | Stop Docker services      |
| `make migrate`    | Run DB migrations         |
| `make api`        | Run FastAPI (port 8080)   |
| `make web`        | Run Vite dev server       |


