"""FastAPI application and process health endpoints."""

from fastapi import FastAPI

from clos.config import settings
from clos.logging import configure_logging

configure_logging(settings.log_level)
app = FastAPI(title="CLOS API", version="0.1.0")


@app.get("/health/live", tags=["health"])
async def live() -> dict[str, str]:
    """Report that the API process is responding."""
    return {"status": "live"}


@app.get("/health/ready", tags=["health"])
async def ready() -> dict[str, str]:
    """Report readiness; dependency probes are added with persistence phase."""
    return {"status": "ready"}

