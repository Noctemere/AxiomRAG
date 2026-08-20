# AxiomRAG

Enterprise multimodal hybrid RAG and autonomous-agent platform.

## Current milestone

Phase 1 establishes the monorepo, typed service boundaries, local infrastructure, and health checks. Retrieval, ingestion, orchestration, and UI workflows are intentionally not implemented yet.

## Quick start

1. Install Python 3.12+, `uv`, Node.js 22+, and Docker Desktop.
2. Copy `.env.example` to `.env`.
3. Run `uv sync`.
4. Start dependencies with `docker compose -f infra/docker/docker-compose.yml up -d`.
5. Start the API with `uv run uvicorn apps.api.main:app --reload`.
6. Open `http://localhost:8000/docs`.

## Checks

```powershell
uv run ruff check .
uv run pyright
uv run pytest
npm --prefix apps/web run typecheck
```

See [docs/phase-1.md](docs/phase-1.md) for the file map and architecture notes.
