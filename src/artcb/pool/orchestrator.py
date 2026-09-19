"""Orchestrateur pool — cycle complet local ou distribué chiffré."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
from collections.abc import Callable
from typing import Any

from src.artcb.pool.policy import PoolPolicyError, validate_pool_options
from src.artcb.pool.service import PoolError, PoolService

logger = logging.getLogger("artcb.pool.orchestrator")


def run_local_mining(
    pipeline,
    text: str,
    *,
    session_id: str,
    visibility: str,
    group_id: str | None,
    actor_address: str | None,
    wallet_name: str | None,
    use_llm: bool,
    llm_provider: str | None,
    store_block: bool,
) -> dict[str, Any]:
    result = pipeline.run_from_text(
        text,
        session_id=session_id,
        use_llm=use_llm,
        llm_provider=llm_provider,
        actor_address=actor_address,
        wallet_name=wallet_name,
        visibility=visibility,
        group_id=group_id,
        store_block=store_block,
    )
    return {
        "mode": "local",
        "encrypted_transport": False,
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


def run_distributed_pool(
    pool: PoolService,
    text: str,
    *,
    visibility: str,
    group_id: str | None,
    actor_address: str | None,
    wallet_name: str | None,
    workers: list[dict[str, str]],
    peer_urls: dict[str, str],
    chunk_chars: int,
    auto_dispatch: bool,
    auto_process_local: bool,
    auto_finalize: bool,
    contributor_address: str | None,
    sign_fn: Callable[[bytes], str] | None,
) -> dict[str, Any]:
    # PRE-FILTRE : récupérer anti_sybil depuis pool si disponible
    # Priorité : pré-filtrer les workers AVANT de créer le job
    anti_sybil = getattr(pool, "_anti_sybil", None)
    job = pool.create_job(
        text,
        visibility=visibility,
        group_id=group_id,
        workers=workers,
        actor_address=actor_address,
        wallet_name=wallet_name,
        chunk_chars=chunk_chars,
        encrypt_transport=True,
        anti_sybil=anti_sybil,
        source="mining",
    )
    dispatch_results = None
    if auto_dispatch:
        dispatch_results = pool.dispatch_to_peers(job, peer_urls)

    processed_local = None
    if auto_process_local and contributor_address:
        processed_local = pool.process_local_pending(
            contributor_address=contributor_address,
            sign_fn=sign_fn,
        )

    job = pool.get_job(job.job_id)
    if not job:
        raise PoolError("Job perdu après création")

    finalize_out = None
    if auto_finalize and job.status == "ready_finalize":
        finalize_out = pool.finalize_job(job.job_id, text)
        job = pool.get_job(job.job_id) or job

    return {
        "mode": "distributed_pool",
        "encrypted_transport": True,
        "job_id": job.job_id,
        "job_status": job.status,
        "visibility": visibility,
        "group_id": group_id,
        "chunk_count": len(job.chunks),
        "dispatch": dispatch_results,
        "processed_local": processed_local,
        "finalize": finalize_out,
        "graph_id": finalize_out.get("graph_id") if finalize_out else job.final_graph_id,
        "block_index": finalize_out.get("block_index") if finalize_out else job.block_index,
        "block_hash": finalize_out.get("block_hash") if finalize_out else None,
        "contributors": finalize_out.get("contributors") if finalize_out else None,
        "pol_score": finalize_out.get("pol_score") if finalize_out else None,
        "message": (
            "Pool distribué chiffré ML-KEM — raisonnement local par worker"
            if job.status != "completed"
            else "Pool distribué finalisé — bloc PoL gravé"
        ),
    }


def run_mining_with_options(
    *,
    text: str,
    use_distributed_pool: bool,
    encrypt_transport: bool,
    visibility: str,
    group_id: str | None,
    actor_address: str | None,
    wallet_name: str | None,
    groups,
    pipeline,
    pool: PoolService,
    workers: list[dict[str, str]],
    peer_urls: dict[str, str],
    session_id: str = "mining_session",
    use_llm: bool = False,
    llm_provider: str | None = None,
    store_block: bool = True,
    chunk_chars: int = 400,
    auto_dispatch: bool = True,
    auto_process_local: bool = True,
    auto_finalize: bool = False,
    contributor_address: str | None = None,
    sign_fn: Callable[[bytes], str] | None = None,
) -> dict[str, Any]:
    try:
        validate_pool_options(
            use_distributed=use_distributed_pool,
            encrypt_transport=encrypt_transport,
            visibility=visibility,
            group_id=group_id,
            actor_address=actor_address,
            groups=groups,
        )
    except PoolPolicyError as exc:
        raise PoolError(str(exc)) from exc

    if not use_distributed_pool:
        return run_local_mining(
            pipeline,
            text,
            session_id=session_id,
            visibility=visibility,
            group_id=group_id,
            actor_address=actor_address,
            wallet_name=wallet_name,
            use_llm=use_llm,
            llm_provider=llm_provider,
            store_block=store_block,
        )

    if not workers:
        raise PoolError("Aucun worker pool disponible — ajoutez un pair P2P ou utilisez calcul local")

    return run_distributed_pool(
        pool,
        text,
        visibility=visibility,
        group_id=group_id,
        actor_address=actor_address,
        wallet_name=wallet_name,
        workers=workers,
        peer_urls=peer_urls,
        chunk_chars=chunk_chars,
        auto_dispatch=auto_dispatch,
        auto_process_local=auto_process_local,
        auto_finalize=auto_finalize,
        contributor_address=contributor_address or actor_address,
        sign_fn=sign_fn,
    )
