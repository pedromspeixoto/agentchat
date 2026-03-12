FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python3.12

WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --no-editable

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable


FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/run_agent.py /app/
# Install skills as personal skills so Claude Code picks them up regardless of cwd
COPY --from=builder /app/.claude/skills/ /root/.claude/skills/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1
