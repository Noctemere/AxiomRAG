from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI

from apps.api.config import get_settings
from apps.api.container import ApplicationContainer
from apps.api.routes.admin import router as admin_router
from apps.api.routes.documents import router as documents_router
from apps.api.routes.query import QueryGraph, QueryStreamService
from apps.api.routes.query import router as query_router

settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Compose graph dependencies at startup and close clients on shutdown."""
    container = ApplicationContainer.create(settings)
    application.state.query_service = QueryStreamService(cast(QueryGraph, container.graph))
    try:
        yield
    finally:
        await container.close()


app = FastAPI(title="AxiomRAG API", version="0.1.0", lifespan=lifespan)
app.include_router(documents_router)
app.include_router(admin_router)
app.include_router(query_router)


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}
