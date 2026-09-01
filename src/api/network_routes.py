"""Public network directory — no wallet required (D-044 / D-045).

Static registry + consumed BOOTSTRAP_NODES. Optional live probes (?live=1).
POST /announce lets an allowlisted clone/Replit be seen without a wallet/KEM.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.artcb.crypto_policy import NETWORK_ID
from src.artcb.p2p.public_url import public_register_url_ok
from src.artcb.p2p.seed_discovery import (
    DirectoryStore,
    public_directory_payload,
    skip_seed_discovery,
)

router = APIRouter(prefix="/api/v1/network", tags=["network"])


class AnnounceObserverRequest(BaseModel):
    node_public_url: str = Field(min_length=8)
    node_label: str = Field(default="", max_length=128)
    network_id: str = Field(default="")


@router.get("/nodes")
def list_infrastructure_nodes(
    request: Request,
    live: bool = Query(default=False, description="Outbound seed probe (short timeout; off by default so one hung peer cannot stall the worker)"),
) -> dict:
    data_dir = request.app.state.artcb.settings.data_dir
    want_live = bool(live) and not skip_seed_discovery()
    payload = public_directory_payload(live=want_live, data_dir=data_dir)
    return payload


@router.post("/announce")
def announce_observer(body: AnnounceObserverRequest, request: Request) -> dict:
    """Allowlisted observer (clone / Replit bootstrap) — no wallet, no KEM."""
    url = body.node_public_url.rstrip("/")
    ok, reason = public_register_url_ok(url)
    if not ok:
        raise HTTPException(status_code=400, detail=f"announce_url_rejected:{reason}")
    nid = (body.network_id or "").strip() or NETWORK_ID
    if nid != NETWORK_ID:
        raise HTTPException(status_code=400, detail=f"Réseau inconnu: {nid} — ce nœud est sur {NETWORK_ID}")
    store = DirectoryStore(request.app.state.artcb.settings.data_dir)
    entry = store.upsert(
        {
            "url": url,
            "label": body.node_label,
            "source": "announce",
            "network_id": nid,
        }
    )
    return {"registered": True, "observer": True, "entry": entry, "network_id": nid}
