"""FastAPI server for health checks, webhooks, and manual triggers."""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

from api.youtube_webhook import router as youtube_router
from config.settings import get_settings, setup_logging
from jobs.send_digest import send_digest
from jobs.run_pipeline import run_pipeline
from jobs.schedule_utils import schedule_description
from storage.db import Database

LOGGER = setup_logging("api.server")
app = FastAPI(title="Zero-Cost News Monitor", version="0.1.0")
app.include_router(youtube_router)


class RunPipelineRequest(BaseModel):
    """Optional body for manually triggering the pipeline."""

    force: bool = False
    scheduled: bool = False
    sources: list[str] = Field(default_factory=list)


class SendDigestRequest(BaseModel):
    """Optional body for manually triggering digest delivery."""

    force: bool = False
    scheduled: bool = False


@app.get("/health")
def health() -> dict[str, object]:
    """Return service and storage health details."""
    settings = get_settings()
    db = Database()
    return {
        "status": "ok",
        "schedule": schedule_description(),
        "timezone": settings.pipeline_schedule_timezone,
        "wecom_configured": bool(settings.wecom_webhook_url),
        "database": db.healthcheck(),
    }


@app.post("/run-pipeline")
def run_pipeline_endpoint(payload: RunPipelineRequest) -> dict[str, object]:
    """Manually trigger collection and scoring."""
    stats = run_pipeline(force=payload.force, only_sources=payload.sources, scheduled=payload.scheduled)
    return {"status": "ok", "stats": stats}


@app.post("/send-digest")
def send_digest_endpoint(payload: SendDigestRequest) -> dict[str, object]:
    """Manually trigger digest sending."""
    stats = send_digest(force=payload.force, scheduled=payload.scheduled)
    return {"status": "ok", "stats": stats}


def main() -> None:
    """Local development entry point."""
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
