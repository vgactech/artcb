"""Public network directory — no wallet required (D-044 / D-045).

Static registry + consumed BOOTSTRAP_NODES. Optional live probes (?live=1).
POST /announce lets an allowlisted clone/Replit be seen without a wallet/KEM.
"""

from __future__ import annotations

from typing import Any

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


@router.get("/nakamoto", summary="Coefficient de Nakamoto — diversité opérateur du réseau")
def nakamoto_coefficient(request: Request) -> dict[str, Any]:
    """Calcule le coefficient de Nakamoto du réseau ARTCB.

    Coefficient = nombre minimal d'entités indépendantes (opérateurs) qu'il faut
    compromettre pour contrôler plus de 50 % des nœuds PBFT.

    Méthode : regrouper les nœuds PBFT par (provider, doppler_project) comme proxy
    d'opérateur. BFT fault tolerance = f avec N=3f+1 → on contrôle si on a >N/3 nœuds.

    Note : avec 4 nœuds appartenant à 1 opérateur → coefficient=1 (honnête).
    L'objectif P2 (coefficient≥2) nécessite des nœuds indépendants tiers.
    """
    from src.artcb.node_registry import NODES, official_pbft_replica_ids
    from src.artcb.consensus.live_bft import n_f_q

    replicas = official_pbft_replica_ids()
    n, f, q = n_f_q(len(replicas))

    # Grouper par opérateur unique = (provider + racine du doppler_project)
    # Heuristique : même nic/compte → même compte cloud
    operator_map: dict[str, list[str]] = {}
    for nid in replicas:
        spec = NODES.get(nid)
        if spec is None:
            continue
        # Proxy opérateur = provider + doppler_project (un compte Doppler = un opérateur)
        op_key = f"{spec.provider}:{spec.doppler_project}"
        operator_map.setdefault(op_key, []).append(nid)

    # Coefficient = min nombre d'opérateurs pour atteindre >f nœuds (quorum Byzantine)
    # Trier par taille décroissante
    op_sizes = sorted([len(v) for v in operator_map.values()], reverse=True)
    cumul = 0
    nakamoto = 0
    threshold = f + 1  # contrôle BFT si >f nœuds compromis
    for sz in op_sizes:
        cumul += sz
        nakamoto += 1
        if cumul >= threshold:
            break

    goal_met = nakamoto >= 2  # objectif P2

    return {
        "nakamoto_coefficient": nakamoto,
        "goal_p2_met": goal_met,
        "goal_p2_target": 2,
        "n_replicas": n,
        "f_fault_tolerance": f,
        "threshold_to_control": threshold,
        "operators": {
            op: {"nodes": nodes, "count": len(nodes)}
            for op, nodes in operator_map.items()
        },
        "note": (
            "Coefficient=1 : 4 nœuds, 1 opérateur (vgactech). "
            "Atteindre ≥2 requiert des opérateurs tiers indépendants."
            if nakamoto < 2
            else f"Coefficient={nakamoto} — diversité opérateur suffisante."
        ),
        "certified_100_relevant": True,
        "ts_ns": __import__("time").time_ns(),
    }
