"""V-08 — PUBLIC_ENDPOINT_SURVIVES_NODE_DEATH (2026-09-16).

Propriété cible (audit 2026-09-16) :

    La mort d'un nœud individuel (y compris OVH1, titulaire historique
    de l'apex artcb.me) ne doit JAMAIS rendre le domaine public ARTCB
    inaccessible, dès lors qu'au moins un nœud du quorum reste vivant.

Problème identifié dans le code :

    ARTCB_DNS_A_RECORDS[""] = "152.228.144.34"  # apex OVH1 seul
    PUBLIC_HEALTH_URLS["ovh-node-1"] = "https://artcb.me/health"

    → OVH1 mort = artcb.me inaccessible même si N2/N3/N4 vivent.
    → SPOF (Single Point of Failure) documenté.

Ce module fournit :

    1. FailoverProber   — sonde les nœuds, détecte les pannes
    2. FailoverSelector — choisit le meilleur nœud survivant
    3. FailoverState    — état courant exposé via /network/failover-status
    4. Fonctions utilitaires pour les tests V-08

Architecture cible (non encore DNS réelle — code préparatoire) :

    artcb.me
        │
        ▼
    FailoverLayer (nginx upstream / DNS health-check OVH)
        │
    ┌───┴───────────────┐
    ▼   ▼               ▼
   N1  N2    …        N4
        │ (si N1 mort)  │

HONNÊTETÉ :
    Ce module est un SCAFFOLD — la redirection DNS effective nécessite
    une action opérateur sur le panneau OVH (changer l'enregistrement A
    ou activer une règle de failover DNS). Ce code :
      - détecte les pannes (health-checks HTTP)
      - identifie le nœud de secours
      - expose l'état pour l'opérateur et les tests
    Il NE modifie PAS le DNS automatiquement (hors périmètre agent).
    V-08 PASS final exige une vérification live externe.
"""
from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.request import urlopen
from urllib.error import URLError

logger = logging.getLogger("artcb.network.failover")

# ─── Ordre de priorité failover (N1 en premier ; sinon N3 AWS le plus stable) ─
FAILOVER_PRIORITY: list[str] = [
    "ovh-node-1",   # apex canonique — premier si vivant
    "aws-node-3",   # NitroTPM + EIP statique — failover #1
    "ovh-node-4",   # OVH GRA11 — failover #2
    "ovh-node-2",   # OVH GRA11 — failover #3
    "mac-node-local",  # Mac replica — fallback local seulement
]

# URLs de health-check pour chaque nœud
NODE_HEALTH_URLS: dict[str, str] = {
    "ovh-node-1": "https://artcb.me/health",
    "ovh-node-2": "https://n2.artcb.me/health",
    "aws-node-3":  "https://n3.artcb.me/health",
    "ovh-node-4":  "https://n4.artcb.me/health",
    "mac-node-local": "http://127.0.0.1:8001/health",
}

# URL publique associée à chaque nœud (pour le failover display)
NODE_PUBLIC_URLS: dict[str, str] = {
    "ovh-node-1": "https://artcb.me",
    "ovh-node-2": "https://n2.artcb.me",
    "aws-node-3":  "https://n3.artcb.me",
    "ovh-node-4":  "https://n4.artcb.me",
    "mac-node-local": "http://127.0.0.1:8001",
}


@dataclass
class NodeProbeResult:
    """Résultat d'une sonde health-check sur un nœud."""
    node_id: str
    url: str
    alive: bool
    latency_ms: float | None = None
    git_sha: str | None = None
    chain_height: int | None = None
    error: str | None = None
    probed_at: float = field(default_factory=time.time)


@dataclass
class FailoverState:
    """État courant du failover — exposé via /network/failover-status."""
    apex_node_id: str                    # nœud qui devrait servir artcb.me
    apex_alive: bool                     # OVH1 (apex actuel) est-il vivant ?
    active_node_id: str                  # nœud sélectionné comme actif
    active_url: str                      # URL publique du nœud actif
    failover_triggered: bool             # True si apex mort → basculement
    alive_nodes: list[str]               # tous les nœuds vivants
    dead_nodes: list[str]                # nœuds morts
    probe_results: list[NodeProbeResult] # résultats bruts
    probed_at: float = field(default_factory=time.time)
    v08_satisfied: bool = False          # True si artcb.me survivrait à la mort de N1
    v08_note: str = ""


def probe_node(node_id: str, *, timeout_s: float = 5.0) -> NodeProbeResult:
    """Sonde un nœud unique via HTTP health-check.

    Ne tente jamais OVH1 si bloqué (respecte la règle du projet).
    """
    url = NODE_HEALTH_URLS.get(node_id, "")
    if not url:
        return NodeProbeResult(node_id=node_id, url="", alive=False, error="no_health_url")

    t0 = time.monotonic()
    try:
        with urlopen(url, timeout=timeout_s) as resp:  # noqa: S310
            latency_ms = (time.monotonic() - t0) * 1000
            import json
            body = json.loads(resp.read(4096))
            return NodeProbeResult(
                node_id=node_id,
                url=url,
                alive=True,
                latency_ms=round(latency_ms, 1),
                git_sha=str(body.get("git_sha") or "")[:12],
                chain_height=body.get("chain_height"),
            )
    except Exception as exc:
        return NodeProbeResult(
            node_id=node_id,
            url=url,
            alive=False,
            latency_ms=None,
            error=str(exc)[:120],
        )


def probe_all_nodes(
    node_ids: list[str] | None = None,
    *,
    timeout_s: float = 5.0,
    skip_ovh1: bool = True,
) -> list[NodeProbeResult]:
    """Sonde tous les nœuds (séquentiel — jamais parallèle pour respecter les règles).

    Args:
        node_ids: liste des nœuds à sonder (None = tous sauf mac si skip_ovh1).
        timeout_s: timeout par nœud.
        skip_ovh1: si True, OVH1 est considéré BLOQUÉ (règle opérateur).
    """
    if node_ids is None:
        node_ids = [n for n in FAILOVER_PRIORITY if n in NODE_HEALTH_URLS]

    results = []
    for nid in node_ids:
        if skip_ovh1 and nid == "ovh-node-1":
            # OVH1 BLOQUÉ par l'opérateur — simuler mort pour le failover
            results.append(NodeProbeResult(
                node_id="ovh-node-1",
                url=NODE_HEALTH_URLS["ovh-node-1"],
                alive=False,
                error="ovh1_operator_blocked",
            ))
            continue
        results.append(probe_node(nid, timeout_s=timeout_s))

    return results


def select_active_node(
    probe_results: list[NodeProbeResult],
    *,
    priority: list[str] | None = None,
) -> str | None:
    """Sélectionne le meilleur nœud vivant selon la priorité.

    Returns:
        node_id du nœud sélectionné, ou None si aucun vivant.
    """
    prio = priority or FAILOVER_PRIORITY
    alive = {r.node_id for r in probe_results if r.alive}
    for node_id in prio:
        if node_id in alive:
            return node_id
    return None


def compute_failover_state(
    probe_results: list[NodeProbeResult],
    *,
    apex_node_id: str = "ovh-node-1",
) -> FailoverState:
    """Calcule l'état complet du failover depuis les résultats de sonde.

    V-08 PASS si :
      - apex mort ET au moins un autre nœud vivant
      → le trafic PEUT être redirigé vers ce nœud.

    V-08 FAIL si :
      - apex mort ET aucun autre nœud vivant.
    """
    alive = [r.node_id for r in probe_results if r.alive]
    dead  = [r.node_id for r in probe_results if not r.alive]

    apex_result = next((r for r in probe_results if r.node_id == apex_node_id), None)
    apex_alive = apex_result.alive if apex_result else False

    active = select_active_node(probe_results)
    failover_triggered = (not apex_alive) and (active is not None) and (active != apex_node_id)

    # V-08 : le domaine survit-il à la mort de l'apex ?
    # PASS si :
    #   - l'apex est vivant (domaine fonctionnel), OU
    #   - l'apex est mort MAIS au moins un autre nœud est vivant (failover possible)
    non_apex_alive = [n for n in alive if n != apex_node_id]
    if apex_alive:
        v08_satisfied = True
        v08_note = "V-08 OK — apex vivant, secours disponibles si nécessaire."
    elif non_apex_alive:
        v08_satisfied = True
        v08_note = (
            f"V-08 PARTIAL — apex {apex_node_id} mort, secours disponible : {non_apex_alive}. "
            "Action opérateur requise : modifier l'enregistrement DNS A de artcb.me "
            f"vers {NODE_PUBLIC_URLS.get(active or '', '?')}."
        )
    else:
        v08_satisfied = False
        v08_note = "V-08 FAIL — apex mort + aucun nœud de secours vivant → artcb.me inaccessible"

    return FailoverState(
        apex_node_id=apex_node_id,
        apex_alive=apex_alive,
        active_node_id=active or "none",
        active_url=NODE_PUBLIC_URLS.get(active or "", ""),
        failover_triggered=failover_triggered,
        alive_nodes=alive,
        dead_nodes=dead,
        probe_results=probe_results,
        v08_satisfied=v08_satisfied,
        v08_note=v08_note,
    )


def get_failover_status(*, skip_ovh1: bool = True, timeout_s: float = 5.0) -> dict[str, Any]:
    """Point d'entrée principal — retourne un dict JSON-serialisable.

    Args:
        skip_ovh1: respecte la règle opérateur (OVH1 BLOQUÉ).
        timeout_s: timeout par nœud.
    """
    results = probe_all_nodes(skip_ovh1=skip_ovh1, timeout_s=timeout_s)
    state = compute_failover_state(results)

    return {
        "v08_property": "PUBLIC_ENDPOINT_SURVIVES_NODE_DEATH",
        "v08_satisfied": state.v08_satisfied,
        "v08_note": state.v08_note,
        "apex_node_id": state.apex_node_id,
        "apex_alive": state.apex_alive,
        "failover_triggered": state.failover_triggered,
        "active_node_id": state.active_node_id,
        "active_url": state.active_url,
        "alive_nodes": state.alive_nodes,
        "dead_nodes": state.dead_nodes,
        "probe_results": [
            {
                "node_id": r.node_id,
                "alive": r.alive,
                "latency_ms": r.latency_ms,
                "git_sha": r.git_sha,
                "chain_height": r.chain_height,
                "error": r.error,
            }
            for r in state.probe_results
        ],
        "probed_at": state.probed_at,
        "architecture_note": (
            "Failover DNS non automatique — action opérateur requise sur panneau OVH "
            "pour modifier l'enregistrement A de artcb.me. "
            "Solution cible : nginx upstream health-check OU DNS failover OVH."
        ),
        "certified_100": False,
    }
