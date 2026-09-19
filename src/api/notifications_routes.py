"""Notifications REST — Telegram uniquement."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.artcb.notifications.manager import NotificationError, NotificationManager

logger = logging.getLogger("artcb.api.notifications")
router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


class SaveChannelRequest(BaseModel):
    channel_type: Literal["telegram"]
    label: str = Field(min_length=1, max_length=128)
    secret: str = Field(min_length=8, description="Bot token Telegram")
    config: dict = Field(default_factory=dict)
    channel_id: str | None = None


class SendNotificationRequest(BaseModel):
    channel_id: str
    subject: str = "ARTCB"
    body: str = Field(min_length=1)


class BroadcastRequest(BaseModel):
    event: str = "artcb_event"
    subject: str = "ARTCB"
    body: str = Field(min_length=1)


def _state(request: Request):
    return request.app.state.artcb


def _notifications(request: Request) -> NotificationManager:
    return _state(request).notifications


@router.get("/channels")
def list_channels(request: Request) -> dict:
    channels = _notifications(request).list_channels()
    return {
        "channels": [c.public_dict() for c in channels],
        "count": len(channels),
        "supported": ["telegram"],
        "note": "Gmail retiré — intégration OAuth Google trop complexe pour release MVP",
        "storage": "local_encrypted",
    }


@router.post("/channels")
def save_channel(body: SaveChannelRequest, request: Request) -> dict:
    mgr = _notifications(request)
    try:
        channel = mgr.save_channel(
            channel_type=body.channel_type,
            label=body.label,
            secret=body.secret,
            config=body.config,
            channel_id=body.channel_id,
        )
        return {"channel": channel.public_dict(), "message": "Canal Telegram enregistré (local chiffré)"}
    except NotificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/channels/{channel_id}")
def delete_channel(channel_id: str, request: Request) -> dict:
    if not _notifications(request).delete_channel(channel_id):
        raise HTTPException(status_code=404, detail="Channel not found")
    return {"deleted": channel_id}


@router.post("/send")
def send_notification(body: SendNotificationRequest, request: Request) -> dict:
    mgr = _notifications(request)
    try:
        result = mgr.send(body.channel_id, subject=body.subject, body=body.body)
        return {"ok": True, **result}
    except NotificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/broadcast")
def broadcast(body: BroadcastRequest, request: Request) -> dict:
    results = _notifications(request).broadcast(
        event=body.event,
        subject=body.subject,
        body=body.body,
    )
    return {"results": results, "count": len(results)}
