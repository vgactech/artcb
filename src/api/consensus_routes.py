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
    view: int | None = Field(default=None, ge=0, le=10_000_000)


class CommitBody(BaseModel):
    work_id: str = Field(min_length=1, max_length=256)
    settlement_id: str = Field(min_length=8, max_length=128)
    epoch: int = Field(default=1, ge=1, le=10_000_000)
    view: int | None = Field(default=None, ge=0, le=10_000_000)


class ViewChangeBody(BaseModel):
    view: int = Field(ge=1, le=10_000_000)
    reason: str = Field(default="primary_unreachable", max_length=128)


class ReceiveViewChangeBody(BaseModel):
    view_change: dict


class NewViewBody(BaseModel):
    view: int = Field(ge=1, le=10_000_000)
    view_changes: list[dict]
    new_view: dict | None = None


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

    state = request.app.state.artcb
    data_dir = state.settings.data_dir
    store = EvidenceStore(data_dir)
    rows = store.list(limit=limit)
    summary = store.summary()
    sidecar = store.sidecar()
    authentic = False
    if sidecar:
        # Reuse tip-attest verifier on sha256 as "hash" stand-in via dedicated fields.
        from src.artcb.crypto.hybrid import verify_hybrid_and_or_window
        import base64

        sha = str(summary.get("sha256") or "")
        sig = str(sidecar.get("signature") or "")
        ed_b64 = str(sidecar.get("producer_ed25519_b64") or "")
        matches = sha and sha == str(sidecar.get("sha256") or "")
        if matches and sig and ed_b64:
            try:
                ed_pk = base64.b64decode(ed_b64, validate=False)
                pqc_b64 = str(sidecar.get("producer_pqc_b64") or "")
                pqc_pk = base64.b64decode(pqc_b64, validate=False) if pqc_b64 else None
                authentic = bool(
                    verify_hybrid_and_or_window(
                        message=sha.encode("utf-8"),
                        signature_value=sig,
                        ed25519_public_key=ed_pk,
                        pqc_public_key=pqc_pk,
                    )
                )
            except Exception:
                authentic = False
    return {
        "evidence": rows,
        "summary": summary,
        "sidecar": sidecar,
        "authenticated": authentic,
        "tampered": bool(summary.get("sha256") and sidecar.get("sha256") and not summary.get("current_matches_sidecar")),
        "not_block_append_bft": True,
        "scope": "active_byzantine_offer_evidence",
        "note": "259 = honest-offline. This list = active liar offers that were rejected.",
    }


@router.post("/byzantine/evidence/sign")
def byzantine_evidence_sign(request: Request) -> dict:
    """Sign the current evidence JSONL digest with this node's chain key.

    Sidecar only. Does not rewrite the book. signed_on_chain stays false until a memo.
    """
    from src.artcb.consensus.byzantine_evidence import EvidenceStore, EVIDENCE_SIGN_PROTOCOL
    from src.artcb.consensus.tip_attest import producer_key_b64, sign_message

    state = request.app.state.artcb
    store = EvidenceStore(state.settings.data_dir)
    summary = store.summary()
    sha = str(summary.get("sha256") or "")
    if not sha:
        raise HTTPException(status_code=404, detail="no_evidence_file")
    ed_b64, pqc_b64 = producer_key_b64(state.chain)
    sidecar = store.write_sidecar(
        {
            "sha256": sha,
            "bytes": summary.get("bytes"),
            "count": summary.get("count"),
            "signature": sign_message(state.chain, sha),
            "producer_ed25519_b64": ed_b64,
            "producer_pqc_b64": pqc_b64,
            "protocol": EVIDENCE_SIGN_PROTOCOL,
            "signed_on_chain": False,
        }
    )
    return {
        "ok": True,
        "sidecar": sidecar,
        "summary": store.summary(),
        "not_block_append_bft": True,
    }


@router.get("/tip-attest")
def consensus_tip_attest(request: Request) -> dict:
    """This node signs its current tip. Collect Q=3 externally. Not PBFT."""
    from src.artcb.consensus.tip_attest import attest_tip
    from src.artcb.release import release_identity

    state = request.app.state.artcb
    identity = release_identity()
    node_id = getattr(state.p2p_identity, "node_id", "") or ""
    return attest_tip(state.chain, git_sha=str(identity.get("git_sha") or ""), node_id=node_id)


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
    result = engine.prepare_local(body.work_id, body.settlement_id, view=body.view)
    payload = {
        "result": result,
        "node": engine.node_id,
        "view": int(getattr(getattr(engine, "pbft", None), "view", 0) or 0),
    }
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


def _pbft(request: Request):
    engine = _engine(request)
    store = getattr(engine, "pbft", None)
    if store is None:
        raise HTTPException(status_code=503, detail="pbft_view_unavailable")
    return store


@router.get("/pbft/view")
def pbft_view(request: Request) -> dict:
    return _pbft(request).snapshot()


@router.post("/pbft/view-change")
def pbft_view_change(body: ViewChangeBody, request: Request) -> dict:
    """This replica signs a VIEW-CHANGE. Process stays up. Does not wipe the book."""
    state = request.app.state.artcb
    store = _pbft(request)
    try:
        row = store.emit_view_change(
            state.chain,
            view=body.view,
            height=int(state.chain.height()),
            last_hash=str(state.chain.last_hash() or ""),
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, **row, "quorum": store.quorum_for(body.view)}


@router.post("/pbft/view-change/receive")
def pbft_view_change_receive(body: ReceiveViewChangeBody, request: Request) -> dict:
    store = _pbft(request)
    return store.accept_view_change(body.view_change)


@router.get("/pbft/view-changes")
def pbft_view_changes(request: Request, view: int) -> dict:
    store = _pbft(request)
    return store.quorum_for(int(view))


@router.post("/pbft/new-view")
def pbft_new_view(body: NewViewBody, request: Request) -> dict:
    """Install NEW-VIEW. If this replica is the new primary and new_view is omitted, it signs it."""
    state = request.app.state.artcb
    store = _pbft(request)
    changes = list(body.view_changes or [])
    if body.new_view:
        installed = store.install_new_view(body.new_view, changes)
        if not installed.get("ok"):
            raise HTTPException(status_code=409, detail=installed.get("reason") or "invalid_new_view")
        return {**installed, "new_view": body.new_view, "view_changes_count": len(changes)}
    try:
        emitted = store.emit_new_view(state.chain, view=body.view, view_changes=changes)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return emitted

