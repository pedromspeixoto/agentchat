AGENT_IMAGE ?= pedropeixoto6/agentchat-claude-sandbox
AGENT_TAG ?= $(shell git rev-parse --short HEAD)

.PHONY: setup infra infra-down migrate api web agent

setup:
	cd api && uv sync
	cd web && npm install

infra:
	docker compose up -d

infra-down:
	docker compose down

migrate:
	cd api && uv run alembic upgrade head

api:
	cd api && uv run uvicorn main:app --reload --port 8080

web:
	cd web && npm run dev

agent:
	docker buildx build --platform linux/amd64 -t $(AGENT_IMAGE):$(AGENT_TAG) ./agent --push
	sed -i.bak 's|image: $(AGENT_IMAGE):.*|image: $(AGENT_IMAGE):$(AGENT_TAG)|' agent/agent.yaml && rm -f agent/agent.yaml.bak
