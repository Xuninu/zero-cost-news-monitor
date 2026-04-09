"""YouTube webhook verification and ingestion endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from config.settings import get_settings, load_yaml_config, setup_logging
from ingest.youtube_ingest import parse_youtube_webhook
from jobs.run_pipeline import process_raw_items
from storage.db import Database

LOGGER = setup_logging("api.youtube_webhook")
router = APIRouter(prefix="/youtube", tags=["youtube"])


@router.get("/webhook", response_class=PlainTextResponse)
async def verify_youtube_webhook(
    mode: str = Query("", alias="hub.mode"),
    challenge: str = Query("", alias="hub.challenge"),
    verify_token: str = Query("", alias="hub.verify_token"),
) -> str:
    """Respond to the YouTube subscription verification challenge."""
    settings = get_settings()
    if mode not in {"subscribe", "unsubscribe"}:
        raise HTTPException(status_code=400, detail="Invalid hub.mode value.")
    if settings.youtube_verify_token and verify_token != settings.youtube_verify_token:
        raise HTTPException(status_code=403, detail="Invalid verify token.")
    return challenge


@router.post("/webhook")
async def receive_youtube_webhook(request: Request) -> dict[str, object]:
    """Receive a YouTube video publish notification and process it immediately."""
    try:
        payload = await request.body()
        raw_items = parse_youtube_webhook(payload, load_yaml_config("sources.yaml"))
        stats = process_raw_items(raw_items, db=Database(), send_urgent=True)
        return {"status": "ok", "processed": stats}
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("YouTube webhook processing failed.")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
