"""Pool calcul distribué E2E — routes REST ML-KEM."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.artcb.pool.discovery import build_peer_urls, discover_workers
from src.artcb.pool.orchestrator import run_mining_with_options
from src.artcb.pool.policy import PoolPolicyError, validate_pool_options
from src.artcb.pool.preferences import PoolPreferences, PoolPreferencesStore
from src.artcb.pool.service import PoolError

logger = logging.getLogger("artcb.api.pool")
router = APIRouter(prefix="/api/v1/pool", tags=["pool"])


class PoolWorkerSpec(BaseModel):
    node_id: str = Field(min_length=4)
    kem_public_hex: str = Field(min_length=32)
    base_url: str | None = None


class CreatePoolJobRequest(BaseModel):
    text: str = Field(min_length=1)
    visibility: str = "private"
    group_id: str | None = None
    workers: list[PoolWorkerSpec] = Field(default_factory=list)
    actor_address: str | None = None
    wallet_name: str | None = None
    wallet_password: str | None = Field(default=None, description="Mot de passe du wallet (requis si wallet_name fourni)")
    chunk_chars: int = Field(default=400, ge=100, le=8000)
    auto_dispatch: bool = True
    encrypt_transport: bool = True


class PoolRunRequest(BaseModel):
    """Cycle minage unifié — local OU pool distribué chiffré (choix utilisateur)."""

    text: str = Field(min_length=1)
    use_distributed_pool: bool = False
    encrypt_transport: bool = True
    visibility: str = "private"
    group_id: str | None = None
    actor_address: str | None = None
    wallet_name: str | None = None
    wallet_password: str | None = Field(default=None, description="Mot de passe du wallet (requis si wallet_name fourni)")
    session_id: str = "pool_run"
    use_llm: bool = False
    llm_provider: str | None = None
    store_block: bool = True
    chunk_chars: int = Field(default=400, ge=100, le=8000)
    auto_dispatch: bool = True
    auto_process_local: bool = True
    auto_finalize: bool = False


class PoolPreferencesRequest(BaseModel):
    use_distributed_pool: bool | None = None
    encrypt_transport: bool | None = None
    default_visibility: str | None = None
    default_group_id: str | None = None
    chunk_chars: int | None = Field(default=None, ge=100, le=8000)
    auto_dispatch: bool | None = None
    auto_process_incoming: bool | None = None
    auto_finalize: bool | None = None


class PoolResultRequest(BaseModel):
    chunk_id: str
    result_envelope: dict[str, str]


class FinalizePoolJobRequest(BaseModel):
    full_text: str = Field(min_length=1)


class ProcessIncomingRequest(BaseModel):
    wallet_name: str | None = None
    wallet_password: str | None = None
    contributor_address: str | None = None


def _state(request: Request):
    return request.app.state.artcb


def _pool(request: Request):
    pool = _state(request).pool
    if pool is None:
        raise HTTPException(status_code=503, detail="Pool non initialisé")
    return pool


def _prefs_store(request: Request) -> PoolPreferencesStore:
    return PoolPreferencesStore(_state(request).settings.data_dir)


def _owner_base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _discover_workers(request: Request) -> list[dict[str, str]]:
    return discover_workers(_state(request), _owner_base_url(request))


def _build_peer_urls(request: Request, workers: list[dict[str, str]] | None = None) -> dict[str, str]:
    return build_peer_urls(_state(request), _owner_base_url(request), workers)


def _wallet_sign(request: Request, wallet_name: str | None, wallet_password: str | None = None):
    if not wallet_name:
        return None, None
    from src.artcb.wallet.manager import WalletManager

    try:
        wallet = WalletManager().load_wallet(name=wallet_name, user_password=wallet_password)
    except (FileNotFoundError, Exception) as exc:
        raise HTTPException(status_code=400, detail=f"Wallet introuvable ou mot de passe incorrect: {wallet_name}") from exc
    return wallet.address, wallet.sign


def _validate_visibility_request(
    request: Request,
    *,
    visibility: str,
    group_id: str | None,
    actor_address: str | None,
    use_distributed: bool,
    encrypt_transport: bool,
) -> None:
    try:
        validate_pool_options(
            use_distributed=use_distributed,
            encrypt_transport=encrypt_transport,
            visibility=visibility,
            group_id=group_id,
            actor_address=actor_address,
            groups=_state(request).groups,
        )
    except PoolPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/status")
def pool_status(request: Request) -> dict[str, Any]:
    state = _state(request)
    pool = _pool(request)
    jobs = pool.list_jobs()
    incoming = pool.list_incoming()
    prefs = _prefs_store(request).load()
    return {
        "enabled": True,
        "crypto": "ML-KEM-768",
        "contexts": ["artcb-pool-chunk-v1", "artcb-pool-result-v1"],
        "node_id": state.p2p_identity.node_id,
        "kem_public_key_hex": state.p2p_identity.kem_public_key_hex,
        "job_count": len(jobs),
        "incoming_pending": len(incoming),
        "plaintext_on_network": False,
        "user_choices": {
            "use_distributed_pool": prefs.use_distributed_pool,
            "encrypt_transport": prefs.encrypt_transport,
            "default_visibility": prefs.default_visibility,
            "default_group_id": prefs.default_group_id,
        },
        "rule": "Calcul local par défaut — pool opt-in chiffré E2E obligatoire si distribué",
    }


@router.get("/preferences")
def get_pool_preferences(request: Request) -> dict:
    prefs = _prefs_store(request).load()
    return {"preferences": prefs.to_dict()}


@router.put("/preferences")
def update_pool_preferences(body: PoolPreferencesRequest, request: Request) -> dict:
    store = _prefs_store(request)
    prefs = store.load()
    data = body.model_dump(exclude_none=True)
    merged = PoolPreferences.from_dict({**prefs.to_dict(), **data})
    if merged.use_distributed_pool and not merged.encrypt_transport:
        raise HTTPException(
            status_code=400,
            detail="encrypt_transport doit rester true si use_distributed_pool est activé",
        )
    store.save(merged)
    return {"preferences": merged.to_dict(), "message": "Préférences pool enregistrées"}


@router.post("/run")
def run_pool_or_local_mining(body: PoolRunRequest, request: Request) -> dict:
    """Point d'entrée unifié : calcul local OU pool distribué chiffré selon choix utilisateur."""
    state = _state(request)
    _validate_visibility_request(
        request,
        visibility=body.visibility,
        group_id=body.group_id,
        actor_address=body.actor_address,
        use_distributed=body.use_distributed_pool,
        encrypt_transport=body.encrypt_transport,
    )
    from src.artcb.mining.pipeline import MiningPipeline
    from src.artcb.wallet.manager import WalletManager

    pipeline = MiningPipeline(
        dual=state.dual,
        chain=state.chain,
        wallet_manager=WalletManager(),
        connectors=state.connectors,
        groups=state.groups,
        timeline=state.timeline,
        register_graph=state.register_graph,
    )
    workers = _discover_workers(request) if body.use_distributed_pool else []
    peer_urls = _build_peer_urls(request, workers) if body.use_distributed_pool else {}
    addr, sign_fn = _wallet_sign(request, body.wallet_name, body.wallet_password)
    actor = body.actor_address or addr

    try:
        return run_mining_with_options(
            text=body.text,
            use_distributed_pool=body.use_distributed_pool,
            encrypt_transport=body.encrypt_transport,
            visibility=body.visibility,
            group_id=body.group_id,
            actor_address=actor,
            wallet_name=body.wallet_name,
            groups=state.groups,
            pipeline=pipeline,
            pool=_pool(request),
            workers=workers,
            peer_urls=peer_urls,
            session_id=body.session_id,
            use_llm=body.use_llm,
            llm_provider=body.llm_provider,
            store_block=body.store_block,
            chunk_chars=body.chunk_chars,
            auto_dispatch=body.auto_dispatch,
            auto_process_local=body.auto_process_local,
            auto_finalize=body.auto_finalize,
            contributor_address=actor,
            sign_fn=sign_fn,
        )
    except PoolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs")
def list_pool_jobs(request: Request) -> dict:
    jobs = _pool(request).list_jobs()
    return {"jobs": [j.to_dict() for j in jobs], "count": len(jobs)}


@router.get("/jobs/{job_id}")
def get_pool_job(job_id: str, request: Request) -> dict:
    job = _pool(request).get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job introuvable")
    return {"job": job.to_dict()}


@router.post("/jobs")
def create_pool_job(body: CreatePoolJobRequest, request: Request) -> dict:
    _validate_visibility_request(
        request,
        visibility=body.visibility,
        group_id=body.group_id,
        actor_address=body.actor_address,
        use_distributed=True,
        encrypt_transport=body.encrypt_transport,
    )
    pool = _pool(request)
    workers = [w.model_dump() for w in body.workers] if body.workers else _discover_workers(request)
    if len(workers) < 1:
        raise HTTPException(status_code=400, detail="Aucun worker disponible")
    try:
        # PRE-FILTRE : récupérer anti_sybil depuis l'état de la chaîne
        state = request.app.state.artcb
        anti_sybil = getattr(getattr(state, "chain", None), "anti_sybil", None)
        job = pool.create_job(
            body.text,
            visibility=body.visibility,
            group_id=body.group_id,
            workers=workers,
            actor_address=body.actor_address,
            wallet_name=body.wallet_name,
            chunk_chars=body.chunk_chars,
            encrypt_transport=body.encrypt_transport,
            anti_sybil=anti_sybil,
            source="mining",
        )
    except PoolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    dispatch_results = None
    if body.auto_dispatch:
        peer_urls = _build_peer_urls(request, workers)
        dispatch_results = pool.dispatch_to_peers(job, peer_urls)

    return {
        "job": job.to_dict(),
        "workers": workers,
        "dispatch": dispatch_results,
        "encrypted_transport": body.encrypt_transport,
        "message": "Job pool créé — morceaux chiffrés ML-KEM E2E par worker",
    }


@router.post("/jobs/{job_id}/dispatch")
def dispatch_pool_job(job_id: str, request: Request) -> dict:
    pool = _pool(request)
    job = pool.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job introuvable")
    peer_urls = _build_peer_urls(request)
    results = pool.dispatch_to_peers(job, peer_urls)
    return {"job_id": job_id, "results": results, "encrypted": True}


@router.post("/incoming")
def receive_pool_chunk(payload: dict, request: Request) -> dict:
    """Worker reçoit un morceau chiffré (jamais en clair)."""
    try:
        return _pool(request).receive_incoming_chunk(payload)
    except PoolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/incoming")
def list_pool_incoming(request: Request) -> dict:
    items = _pool(request).list_incoming()
    return {"incoming": items, "count": len(items)}


@router.post("/incoming/{chunk_id}/process")
def process_pool_chunk(chunk_id: str, body: ProcessIncomingRequest, request: Request) -> dict:
    pool = _pool(request)
    addr, sign_fn = _wallet_sign(request, body.wallet_name, body.wallet_password)
    contributor = body.contributor_address or addr
    if not contributor:
        raise HTTPException(status_code=400, detail="contributor_address ou wallet_name requis")
    try:
        return pool.process_incoming_chunk(chunk_id, contributor_address=contributor, sign_fn=sign_fn)
    except PoolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/incoming/process-all")
def process_all_incoming(body: ProcessIncomingRequest, request: Request) -> dict:
    pool = _pool(request)
    addr, sign_fn = _wallet_sign(request, body.wallet_name, body.wallet_password)
    contributor = body.contributor_address or addr
    if not contributor:
        raise HTTPException(status_code=400, detail="contributor_address ou wallet_name requis")
    results = pool.process_local_pending(contributor_address=contributor, sign_fn=sign_fn)
    return {"processed": results, "count": len(results)}


@router.post("/jobs/{job_id}/results")
def receive_pool_result(job_id: str, body: PoolResultRequest, request: Request) -> dict:
    try:
        return _pool(request).receive_result(job_id, body.chunk_id, body.result_envelope)
    except PoolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/finalize")
def finalize_pool_job(job_id: str, body: FinalizePoolJobRequest, request: Request) -> dict:
    try:
        return _pool(request).finalize_job(job_id, body.full_text)
    except PoolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
