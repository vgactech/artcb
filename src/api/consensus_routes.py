"""Live BFT prepare/commit routes (DV-05). No bearer over remote HTTP."""

from __future__ import annotations

import json

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
    from src.artcb.consensus.replica_identity import official_consensus_node_id
    from src.artcb.node_registry import official_pbft_replica_ids

    official = official_consensus_node_id()
    node_id = official if official in official_pbft_replica_ids() else (getattr(state.p2p_identity, "node_id", "") or "")
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
        entered = _pbft_log(request).enter_view(int(installed.get("view") or body.view), changes)
        if not entered.get("ok"):
            raise HTTPException(status_code=409, detail=entered.get("reason") or "state_incomplete")
        return {**installed, "new_view": body.new_view, "view_changes_count": len(changes), "enter_view": entered}
    try:
        emitted = store.emit_new_view(state.chain, view=body.view, view_changes=changes)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    entered = _pbft_log(request).enter_view(
        int((emitted.get("new_view") or {}).get("view") or body.view), changes
    )
    if not entered.get("ok"):
        raise HTTPException(status_code=409, detail=entered.get("reason") or "state_incomplete")
    return {**emitted, "enter_view": entered}


def _pbft_log(request: Request):
    engine = _engine(request)
    store = getattr(engine, "pbft_log", None)
    if store is None:
        raise HTTPException(status_code=503, detail="pbft_finality_unavailable")
    return store


class PrePrepareBody(BaseModel):
    pre_prepare: dict


class PrepareMsgBody(BaseModel):
    prepare: dict | None = None
    view: int | None = None
    seq: int | None = None
    digest: str | None = None


class CommitMsgBody(BaseModel):
    commit: dict | None = None
    view: int | None = None
    seq: int | None = None
    digest: str | None = None


class ProposeBlockBody(BaseModel):
    graph_id: str = Field(default="pbft-265", max_length=256)
    graph_root: str = Field(default="265-finality", max_length=256)
    source: str = Field(default="pbft:propose", max_length=64)
    visibility: str = Field(default="public", max_length=16)


class ClientRequestBody(BaseModel):
    block: dict


class CertificateBody(BaseModel):
    certificate: dict
    block: dict | None = None


class ViewChange265Body(BaseModel):
    view: int = Field(ge=1)
    view_change: dict | None = None


class SelectPreparedBody(BaseModel):
    view_changes: list[dict]


class AnalyzeNewViewBody(BaseModel):
    view_changes: list[dict]


class BindPreparedBody(BaseModel):
    chosen: dict


@router.get("/replica-identity")
def consensus_replica_identity() -> dict:
    """Public NodeID ↔ key registry. Keys in a message are not the authority."""
    from src.artcb.consensus.replica_identity import public_registry_view

    return public_registry_view()


@router.get("/platform-attest")
def consensus_platform_attest() -> dict:
    """Best available platform proof (TPM / vTPM / cloud / observed). Never recast."""
    from src.artcb.consensus.platform_attest import collect_platform_attestation

    return collect_platform_attestation()


@router.get("/pbft/finality")
def pbft_finality_status(request: Request) -> dict:
    snap = _pbft_log(request).snapshot()
    from src.artcb.consensus.replica_identity import binding_enforced, official_consensus_node_id

    snap["identity_binding_enforced"] = binding_enforced()
    snap["official_replica_id"] = official_consensus_node_id()
    return snap


@router.get("/pbft/prepared")
def pbft_prepared(request: Request) -> dict:
    log = _pbft_log(request)
    return {"ok": True, "prepared": log.prepared_set(), "view": log.view}


@router.get("/pbft/certificate")
def pbft_certificate(request: Request, seq: int) -> dict:
    cert = _pbft_log(request).certificate(int(seq))
    if not cert:
        raise HTTPException(status_code=404, detail="no_certificate")
    return {"ok": True, "certificate": cert}


@router.post("/pbft/propose")
def pbft_propose(body: ProposeBlockBody, request: Request) -> dict:
    """Primary constructs a real chain block (dry_run) and signs PRE-PREPARE."""
    state = request.app.state.artcb
    log = _pbft_log(request)
    try:
        constructed = state.chain.append_block(
            graph_id=body.graph_id,
            graph_root=body.graph_root,
            pol_score=0.1,
            visibility=body.visibility,
            source=body.source,
            dry_run=True,
        )
        block = json.loads(constructed.to_json_line())
        pp = log.emit_preprepare(state.chain, block=block)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "pre_prepare": pp, "block": block, "digest": pp.get("digest")}


@router.post("/pbft/client-request")
def pbft_client_request(body: ClientRequestBody, request: Request) -> dict:
    """Non-primary submits a constructed block. Primary wraps it in PRE-PREPARE."""
    from src.artcb.consensus.pbft_view import primary_of

    state = request.app.state.artcb
    log = _pbft_log(request)
    block = body.block if isinstance(body.block, dict) else {}
    view = int(log.view)
    if log.replica_id != primary_of(view):
        raise HTTPException(status_code=409, detail="not_primary")
    try:
        idx = int(block.get("index", -1))
    except (TypeError, ValueError):
        idx = -1
    if idx != int(state.chain.height()) or str(block.get("prev_hash") or "") != str(state.chain.last_hash() or ""):
        raise HTTPException(status_code=409, detail="not_extending")
    if str(block.get("visibility") or "") != "public":
        raise HTTPException(status_code=409, detail="not_public")
    try:
        pp = log.emit_preprepare(state.chain, block=block)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "pre_prepare": pp, "block": block, "digest": pp.get("digest")}


@router.post("/pbft/pre-prepare")
def pbft_pre_prepare(body: PrePrepareBody, request: Request) -> dict:
    log = _pbft_log(request)
    accepted = log.accept_preprepare(body.pre_prepare)
    if not accepted.get("ok"):
        raise HTTPException(status_code=409, detail=accepted.get("reason") or "invalid_preprepare")
    return accepted


@router.post("/pbft/prepare")
def pbft_prepare(body: PrepareMsgBody, request: Request) -> dict:
    state = request.app.state.artcb
    log = _pbft_log(request)
    if body.prepare:
        accepted = log.accept_prepare(body.prepare)
        if not accepted.get("ok") and accepted.get("reason") in (
            "invalid_replica_key_binding",
            "invalid_replica_pqc_binding",
            "unregistered_replica_key",
            "replica_key_revoked",
            "replica_key_expired",
            "replica_key_not_yet_valid",
            "replica_pqc_downgrade",
            "unknown_replica_id",
        ):
            raise HTTPException(status_code=409, detail=accepted.get("reason"))
        return accepted
    try:
        row = log.emit_prepare(state.chain, view=int(body.view), seq=int(body.seq), digest=str(body.digest))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "prepare": row}


@router.post("/pbft/commit")
def pbft_commit_msg(body: CommitMsgBody, request: Request) -> dict:
    state = request.app.state.artcb
    log = _pbft_log(request)
    if body.commit:
        return log.accept_commit(body.commit)
    try:
        emitted = log.emit_commit(state.chain, view=int(body.view), seq=int(body.seq), digest=str(body.digest))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, **emitted}


@router.post("/pbft/certificate")
def pbft_install_certificate(body: CertificateBody, request: Request) -> dict:
    state = request.app.state.artcb
    log = _pbft_log(request)
    installed = log.install_certificate(body.certificate)
    if not installed.get("ok"):
        raise HTTPException(status_code=409, detail=installed.get("reason") or "invalid_certificate")
    wrote = False
    if body.block:
        wrote = state.chain.write_certified_block(body.block, body.certificate)
    return {**installed, "wrote": wrote}


@router.post("/pbft/view-change-265")
def pbft_view_change_265(body: ViewChange265Body, request: Request) -> dict:
    state = request.app.state.artcb
    log = _pbft_log(request)
    if body.view_change:
        stored = log.remember_view_change_265(body.view_change)
        return {"ok": stored, "reason": None if stored else "invalid_view_change_265"}
    try:
        row = log.emit_view_change_265(state.chain, view=body.view)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "view_change": row}


@router.post("/pbft/analyze-new-view")
def pbft_analyze_new_view(body: AnalyzeNewViewBody, request: Request) -> dict:
    """Read-only NEW-VIEW certificate analysis. Does not bind or enter_view."""
    log = _pbft_log(request)
    analysis = log.analyze_new_view_certificate(body.view_changes)
    return {
        "ok": True,
        "analysis": analysis,
        "selected_is_none": analysis.get("selected") is None,
        "bound": False,
        "note": "analyze only — no bind_prepared, no enter_view",
    }


@router.post("/pbft/select-prepared")
def pbft_select_prepared(body: SelectPreparedBody, request: Request) -> dict:
    from src.artcb.consensus.pbft_finality import verify_prepared_certificate

    log = _pbft_log(request)
    analysis = log.analyze_new_view_certificate(body.view_changes)
    chosen = analysis.get("selected") if isinstance(analysis.get("selected"), dict) else None
    bound = log.bind_prepared_constraint(chosen) if chosen else {"ok": False, "reason": "no_prepared"}
    return {
        "ok": chosen is not None and bool(bound.get("ok")),
        "chosen": chosen,
        "proof": bool(chosen) and verify_prepared_certificate(chosen),
        "bound": bound,
        "analysis": analysis,
    }


@router.post("/pbft/bind-prepared")
def pbft_bind_prepared(body: BindPreparedBody, request: Request) -> dict:
    log = _pbft_log(request)
    installed = log.bind_prepared_constraint(body.chosen)
    if not installed.get("ok"):
        raise HTTPException(status_code=409, detail=installed.get("reason") or "bind_failed")
    return installed


