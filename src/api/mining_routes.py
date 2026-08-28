"""Mining REST routes — pipeline apprentissage + raisonnement + PoL collectif."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.artcb.connectors.sources import DataSourceError
from src.artcb.mining.pipeline import MiningPipeline

logger = logging.getLogger("artcb.api.mining")
router = APIRouter(prefix="/api/v1/mining", tags=["mining"])


class MiningPipelineRequest(BaseModel):
    text: str | None = Field(default=None, min_length=1)
    connector_id: str | None = None
    session_id: str = "mining_session"
    use_llm: bool = False
    llm_provider: str | None = None
    actor_address: str | None = None
    wallet_name: str | None = None
    wallet_password: str | None = Field(default=None, description="Mot de passe du wallet")
    visibility: str = "private"
    group_id: str | None = None
    store_block: bool = True
    use_distributed_pool: bool = False
    encrypt_transport: bool = True
    auto_finalize: bool = False
    chunk_chars: int | None = Field(default=None, ge=100, le=8000)
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    batch_index: int = 0


class BulkMiningRequest(BaseModel):
    connector_id: str
    max_batches: int = Field(default=10, ge=1, le=1000)
    batch_size: int = Field(default=100, ge=1, le=1000)
    actor_address: str | None = None
    wallet_name: str | None = None
    wallet_password: str | None = None
    visibility: str = "private"
    group_id: str | None = None
    use_llm: bool = False
    llm_provider: str | None = None


def _state(request: Request):
    return request.app.state.artcb


def _pipeline(request: Request) -> MiningPipeline:
    state = _state(request)
    from src.artcb.wallet.manager import WalletManager

    pipe = MiningPipeline(
        dual=state.dual,
        chain=state.chain,
        wallet_manager=WalletManager(),
        connectors=state.connectors,
        groups=state.groups,
        timeline=state.timeline,
        register_graph=state.register_graph,
    )
    pipe.bind_identity(
        machine_registry=state.machine_registry,
        human_registry=state.human_registry,
        work_registry=state.work_registry,
    )
    return pipe


@router.post("/pipeline")
async def run_mining_pipeline(body: MiningPipelineRequest, request: Request) -> dict:
    """
    Pipeline unifié : source d'apprentissage → raisonnement (dual-agent) → minage PoL.

    Choix utilisateur :
    - ``use_distributed_pool=false`` (défaut) : calcul 100 % local
    - ``use_distributed_pool=true`` : pool distribué chiffré ML-KEM E2E (encrypt_transport obligatoire)
    """
    state = _state(request)

    if body.use_distributed_pool:
        if not body.text:
            raise HTTPException(status_code=422, detail="text required for distributed pool")
        from src.artcb.pool.discovery import build_peer_urls, discover_workers
        from src.artcb.pool.orchestrator import run_mining_with_options
        from src.artcb.pool.policy import PoolPolicyError, validate_pool_options
        from src.artcb.pool.service import PoolError

        try:
            validate_pool_options(
                use_distributed=body.use_distributed_pool,
                encrypt_transport=body.encrypt_transport,
                visibility=body.visibility,
                group_id=body.group_id,
                actor_address=body.actor_address,
                groups=state.groups,
            )
        except PoolPolicyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if state.pool is None:
            raise HTTPException(status_code=503, detail="Pool non initialisé")

        base_url = str(request.base_url).rstrip("/")
        workers = discover_workers(state, base_url)
        peer_urls = build_peer_urls(state, base_url, workers)
        addr, sign_fn = None, None
        if body.wallet_name:
            from src.artcb.wallet.manager import WalletManager
            try:
                wallet = WalletManager().load_wallet(name=body.wallet_name, user_password=body.wallet_password)
                addr, sign_fn = wallet.address, wallet.sign
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Wallet introuvable ou mot de passe incorrect: {body.wallet_name}") from exc
        actor = body.actor_address or addr

        chunk_chars = body.chunk_chars
        if chunk_chars is None and state.optimization is not None:
            chunk_chars = state.optimization.pool_chunk_chars
        if chunk_chars is None:
            from src.artcb.system.optimizer import default_pool_chunk_chars
            chunk_chars = default_pool_chunk_chars()

        try:
            return await asyncio.to_thread(
                run_mining_with_options,
                text=body.text,
                use_distributed_pool=True,
                encrypt_transport=body.encrypt_transport,
                visibility=body.visibility,
                group_id=body.group_id,
                actor_address=actor,
                wallet_name=body.wallet_name,
                groups=state.groups,
                pipeline=_pipeline(request),
                pool=state.pool,
                workers=workers,
                peer_urls=peer_urls,
                session_id=body.session_id,
                use_llm=body.use_llm,
                llm_provider=body.llm_provider,
                store_block=body.store_block,
                chunk_chars=chunk_chars,
                auto_dispatch=True,
                auto_process_local=True,
                auto_finalize=body.auto_finalize,
                contributor_address=actor,
                sign_fn=sign_fn,
            )
        except PoolError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    pipeline = _pipeline(request)
    try:
        if body.connector_id:
            result = await asyncio.to_thread(
                pipeline.run_from_connector,
                body.connector_id,
                limit=body.limit,
                offset=body.offset,
                batch_index=body.batch_index,
                session_id=body.session_id,
                use_llm=body.use_llm,
                llm_provider=body.llm_provider,
                actor_address=body.actor_address,
                wallet_name=body.wallet_name,
                visibility=body.visibility,
                group_id=body.group_id,
                store_block=body.store_block,
            )
        elif body.text:
            result = await asyncio.to_thread(
                pipeline.run_from_text,
                body.text,
                session_id=body.session_id,
                use_llm=body.use_llm,
                llm_provider=body.llm_provider,
                actor_address=body.actor_address,
                wallet_name=body.wallet_name,
                visibility=body.visibility,
                group_id=body.group_id,
                store_block=body.store_block,
            )
        else:
            raise HTTPException(status_code=422, detail="text or connector_id required")
    except (DataSourceError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "graph_id": result.graph_id,
        "node_count": result.node_count,
        "pol_score": result.pol_score,
        "block_index": result.block_index,
        "block_hash": result.block_hash,
        "block_reward": result.block_reward,
        "contributors": result.contributors,
        "phases": result.phases,
        "message": result.message,
    }


@router.post("/bulk")
def run_bulk_mining(body: BulkMiningRequest, request: Request) -> dict:
    """
  Minage par lots — banque / grosses bases : lit batch par batch, raisonne et mine chaque lot.
    """
    pipeline = _pipeline(request)
    results = []
    offset = 0
    for batch_i in range(body.max_batches):
        try:
            result = pipeline.run_from_connector(
                body.connector_id,
                limit=body.batch_size,
                offset=offset,
                batch_index=batch_i,
                use_llm=body.use_llm,
                llm_provider=body.llm_provider,
                actor_address=body.actor_address,
                wallet_name=body.wallet_name,
                visibility=body.visibility,
                group_id=body.group_id,
                store_block=True,
            )
        except DataSourceError as exc:
            if batch_i == 0:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            break

        row_count = result.phases.get("learning", {}).get("chars", 0)
        results.append({
            "batch": batch_i,
            "offset": offset,
            "graph_id": result.graph_id,
            "pol_score": result.pol_score,
            "block_index": result.block_index,
            "block_reward": result.block_reward,
            "chars": row_count,
        })

        if result.block_index is None:
            break

        offset += body.batch_size

        record = _state(request).connectors.get_connector(body.connector_id)
        if not record:
            break
        from src.artcb.connectors.sources import fetch_learning_text_batched

        probe = fetch_learning_text_batched(record, limit=1, offset=offset)
        if not probe.has_more and probe.row_count == 0:
            break

    return {
        "batches_processed": len(results),
        "results": results,
        "message": f"Minage bulk terminé — {len(results)} lots traités (apprentissage + raisonnement + blocs)",
    }


class ProtocolMineIn(BaseModel):
    graph_id: str = "g_protocol"
    graph_root: str
    pol_score: float = Field(0.8, ge=0, le=1)
    work_id: str
    machine_ids: list[str]
    job_id: str | None = None
    interval_seconds: float | None = 600
    n_partitions: int | None = None
    missing_preblock_ids: list[str] | None = None


@router.post("/protocol")
def mine_protocol(body: ProtocolMineIn, request: Request) -> dict:
    """One-shot H_adult → R(H) → HBP → P/W → OwnerDecay → Settlement → C hash v2."""
    engine = _state(request).protocol_engine
    if engine is None:
        raise HTTPException(status_code=503, detail="protocol engine not bound")
    from src.artcb.mining.protocol import ProtocolReject

    try:
        result = engine.execute_block(
            graph_id=body.graph_id,
            graph_root=body.graph_root,
            pol_score=body.pol_score,
            work_id=body.work_id,
            machine_ids=body.machine_ids,
            job_id=body.job_id,
            interval_seconds=body.interval_seconds,
            n_partitions=body.n_partitions,
            missing_preblock_ids=body.missing_preblock_ids,
        )
    except ProtocolReject as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)}) from exc
    return {
        "block_index": result.block_index,
        "block_hash": result.block_hash,
        "hash_version": result.hash_version,
        "h_adult": result.h_adult,
        "r_block_satoshi": result.r_block_satoshi,
        "hbp_rate": result.hbp_rate,
        "economic_root": result.economic_root,
        "total_paid_satoshi": result.total_paid_satoshi,
        "supply_satoshi": result.supply_satoshi,
        "conservation": result.total_paid_satoshi == result.r_block_satoshi,
        "by_address_satoshi": result.by_address_satoshi,
        "lines": result.lines,
        "phases": result.phases,
        "job_payment_distinct_from_r_block": True,
    }


@router.get("/protocol/status")
def protocol_status(request: Request) -> dict:
    engine = _state(request).protocol_engine
    chain = _state(request).chain
    from src.artcb.chain import ffi
    from src.artcb.tokenomics import MAX_SUPPLY_SATOSHI

    h_adult = engine.h_adult() if engine else 0
    supply = chain._issued_so_far_satoshi()
    return {
        "h_adult": h_adult,
        "h_adult_source": "HumanRegistry.verified_adult_count",
        "adult_age_years": 18,
        "supply_satoshi": supply,
        "max_supply_satoshi": MAX_SUPPLY_SATOSHI,
        "c_economic_root_abi": ffi.has_economic_root_abi(),
        "wired": engine is not None,
    }
