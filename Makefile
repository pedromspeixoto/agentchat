.PHONY: setup infra infra-down migrate api web

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
	cd api && uv run python run.py

web:
	cd web && npm run dev
