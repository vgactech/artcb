"""Live BFT prepare/commit routes (DV-05). No bearer over remote HTTP."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.artcb.economics.economic_snapshot import AlreadySettled

router = APIRouter(prefix="/api/v1/consensus", tags=["consensus"])


class PrepareBody(BaseModel):
    work_id: str = Field(min_length=1, max_length=256)
    settlement_id: str = Field(min_length=8, max_length=128)


class CommitBody(BaseModel):
    work_id: str = Field(min_length=1, max_length=256)
    settlement_id: str = Field(min_length=8, max_length=128)
    epoch: int = Field(default=1, ge=1, le=10_000_000)


class ProposeBody(BaseModel):
    work_id: str = Field(min_length=1, max_length=256)
    snapshot_digest: str = Field(min_length=8, max_length=128)
    epoch: int = Field(default=1, ge=1, le=10_000_000)
    forged_sid: str | None = None


def _engine(request: Request):
    engine = getattr(request.app.state.artcb, "live_bft", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="live_bft_unavailable")
    return engine


@router.get("/byzantine/evidence")
def byzantine_evidence(request: Request, limit: int = 100) -> dict:
    """Offers an honest node refused. Not a BFT certificate."""
    from src.artcb.consensus.byzantine_evidence import EvidenceStore

    data_dir = request.app.state.artcb.settings.data_dir
    store = EvidenceStore(data_dir)
    rows = store.list(limit=limit)
    return {
        "evidence": rows,
        "summary": store.summary(),
        "not_block_append_bft": True,
        "scope": "active_byzantine_offer_evidence",
        "note": "259 = honest-offline. This list = active liar offers that were rejected.",
    }


@router.get("/liveness")
def consensus_liveness(request: Request) -> dict:
    """Observe quorum / partition. Does not stop nodes. Does not steal produce."""
    from src.artcb.consensus.liveness import assess_liveness, probe_hosts
    from src.artcb.node_registry import OFFICIAL_COMPUTE_IPV4

    hosts = [f"http://{ip}:8000" for ip in OFFICIAL_COMPUTE_IPV4]
    pulses = probe_hosts(hosts, timeout=1.2)
    report = assess_liveness(include_self=False, peer_reachable=pulses)
    return report.to_dict()


@router.get("/status")
def consensus_status(request: Request) -> dict:
    state = request.app.state.artcb
    engine = _engine(request)
    identity = state.p2p_identity
    self_host = ""
    advertised = getattr(identity, "node_public_url", "") or ""
    if "://" in advertised:
        self_host = advertised.split("://", 1)[-1].split(":")[0].split("/")[0]
    return engine.status(state.p2p_peers.list_peers(), self_host=self_host)


@router.post("/prepare")
def consensus_prepare(body: PrepareBody, request: Request):
    engine = _engine(request)
    result = engine.prepare_local(body.work_id, body.settlement_id)
    payload = {"result": result, "node": engine.node_id}
    return JSONResponse(status_code=200 if result == "prepared" else 409, content=payload)


@router.post("/commit")
def consensus_commit(body: CommitBody, request: Request) -> dict:
    engine = _engine(request)
    try:
        return engine.commit_local(body.work_id, body.settlement_id, body.epoch)
    except AlreadySettled as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/propose")
def consensus_propose(body: ProposeBody, request: Request) -> dict:
    state = request.app.state.artcb
    engine = _engine(request)
    identity = state.p2p_identity
    self_host = ""
    advertised = getattr(identity, "node_public_url", "") or ""
    if "://" in advertised:
        self_host = advertised.split("://", 1)[-1].split(":")[0].split("/")[0]
    return engine.propose(
        work_id=body.work_id,
        snapshot_digest=body.snapshot_digest,
        peers=state.p2p_peers.list_peers(),
        self_host=self_host,
        epoch=body.epoch,
        forged_sid=body.forged_sid,
    )
