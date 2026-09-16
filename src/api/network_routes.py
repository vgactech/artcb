"""Public network directory — no wallet required (D-044 / D-045).

Static registry + consumed BOOTSTRAP_NODES. Optional live probes (?live=1).
POST /announce lets an allowlisted clone/Replit be seen without a wallet/KEM.

V-08 (2026-09-16) : ajout de GET /failover-status
    Expose l'état du failover SPOF artcb.me → nœuds de secours.
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


# ─── V-08 : failover-status ───────────────────────────────────────────────────

@router.get(
    "/failover-status",
    summary="V-08 — État failover SPOF artcb.me",
    tags=["network", "v08"],
)
def failover_status(
    skip_ovh1: bool = Query(
        default=True,
        description=(
            "Si True (défaut), OVH1 est traité comme bloqué "
            "(règle opérateur). Passer False pour forcer un probe OVH1 réel."
        ),
    ),
    timeout_s: float = Query(
        default=3.0,
        ge=0.5,
        le=15.0,
        description="Timeout HTTP par nœud en secondes.",
    ),
) -> dict[str, Any]:
    """Retourne l'état de failover du réseau ARTCB (propriété V-08).

    **V-08 — PUBLIC_ENDPOINT_SURVIVES_NODE_DEATH**

    Vérifie que la mort d'OVH1 (apex `artcb.me`) ne rend pas le service
    inaccessible, dès lors qu'au moins un nœud de secours (N2/N3/N4) est vivant.

    Champs clés :
    - `v08_satisfied` : True si un nœud non-apex est vivant
    - `failover_triggered` : True si l'apex est mort ET un secours est sélectionné
    - `active_node_id` / `active_url` : nœud actif recommandé
    - `v08_note` : message opérateur (action DNS si nécessaire)

    **Note architecturale** : la redirection DNS effective reste une action
    opérateur manuelle (panneau OVH). Ce endpoint expose l'état et le diagnostic ;
    il ne modifie pas le DNS automatiquement.
    """
    from src.artcb.network.failover import get_failover_status

    return get_failover_status(skip_ovh1=skip_ovh1, timeout_s=timeout_s)
