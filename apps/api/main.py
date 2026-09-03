from fastapi import FastAPI

from apps.api.config import get_settings
from apps.api.routes.documents import router as documents_router

settings = get_settings()
app = FastAPI(title="AxiomRAG API", version="0.1.0")
app.include_router(documents_router)


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}
