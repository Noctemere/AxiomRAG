.PHONY: install lint typecheck test dev infra-up infra-down

install:
	uv sync

lint:
	uv run ruff check .

typecheck:
	uv run pyright

test:
	uv run pytest

dev:
	uv run uvicorn apps.api.main:app --reload

infra-up:
	docker compose -f infra/docker/docker-compose.yml up -d

infra-down:
	docker compose -f infra/docker/docker-compose.yml down
