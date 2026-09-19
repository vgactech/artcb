"""TASK-006 — Creator-node / Primary failure policy (2026-09-18).

Définit le comportement du réseau ARTCB si aws-node-3 (PBFT primary, view=27)
est mort de façon permanente ou prolongée.

## Contexte

- Réseau : N=4 nœuds officiels, F=1, Q=3 (N4/N3/N2 + ovh-node-1 BLOQUÉ)
- PBFT primary actuel : aws-node-3 (view=27, ip=13.38.209.25)
- Situation : aws-node-3 offline depuis 2026-09-12, V-STALL-01 résolu par
  le watchdog (chain_height 1142→1198), PBFT ALIVE view=27

## Trois états de défaillance du primary

### ÉTAT 1 — PRIMARY_DEAD_TRANSIENT (mort temporaire < 24h)
    Comportement : attendre. Le watchdog (`public_tip_watchdog.py`) surveille
    et déclenche automatiquement un view-change si le tip stagne.
    Action opérateur : aucune.

### ÉTAT 2 — PRIMARY_DEAD_RECOVERABLE (mort prolongée 24h–7j)
    Comportement : view-change manuel vers le prochain primary candidat.
    `next_reachable_view()` saute les views dont le primary est injoignable.
    Action opérateur : POST /api/v1/consensus/pbft/view-change

### ÉTAT 3 — PRIMARY_DEAD_PERMANENT (mort définitive > 7j ou décision)
    Comportement : retrait du nœud du registre PBFT + élection d'un nouveau
    primary parmi les nœuds restants.
    → N passe de 4 à 3 (F=1, Q=2) — seuil de tolérance réduit.
    → OU remplacement physique du nœud (nouvelle VM + enrôlement PBFT).
    Action opérateur : décision explicite requise (TASK-006-PERMANENT-REMOVE).

## Garanties

- PBFT liveness : N=3, F=1, Q=2 reste tolérant à 1 panne Byzantine.
- block append : reste la plus longue chaîne publique valide (indépendant du PBFT).
- CERTIFIED_100=false : décision de retrait = action opérateur, pas automatique.
"""
from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.artcb.consensus.live_bft import n_f_q
from src.artcb.consensus.pbft_view import next_reachable_view, primary_of
from src.artcb.node_registry import official_pbft_replica_ids, official_pbft_n_f_q

logger = logging.getLogger("artcb.consensus.creator_node_policy")

# ─── Constantes ───────────────────────────────────────────────────────────────

# Seuils de détection d'état (modifiables par tests via paramètres)
_TRANSIENT_THRESHOLD_S  = 24 * 3600   # < 24h = transitoire
_RECOVERABLE_THRESHOLD_S = 7 * 86400  # < 7j  = récupérable
# > 7j sans retour = permanente (décision opérateur requise)

# Nœud actuellement bloqué par l'opérateur
_BLOCKED_NODES = frozenset({"ovh-node-1"})


# ─── Énumérations ─────────────────────────────────────────────────────────────

class PrimaryFailureState(str, Enum):
    """État de défaillance du PBFT primary."""
    ALIVE               = "ALIVE"                # primary répond
    DEAD_TRANSIENT      = "DEAD_TRANSIENT"       # mort < 24h
    DEAD_RECOVERABLE    = "DEAD_RECOVERABLE"     # mort 24h–7j → view-change
    DEAD_PERMANENT      = "DEAD_PERMANENT"       # mort > 7j → retrait possible


class NetworkResponseAction(str, Enum):
    """Action réseau recommandée."""
    WAIT                = "WAIT"                 # attendre — watchdog actif
    TRIGGER_VIEW_CHANGE = "TRIGGER_VIEW_CHANGE"  # view-change vers prochain primary
    OPERATOR_DECISION   = "OPERATOR_DECISION"    # décision opérateur requise
    REPLACE_NODE        = "REPLACE_NODE"         # remplacer le nœud physiquement


# ─── Structures ───────────────────────────────────────────────────────────────

@dataclass
class PrimaryFailureReport:
    """Rapport d'état de défaillance du primary PBFT.

    Produit par `assess_primary_failure()`.
    Ne déclenche aucune action automatique — informationnel uniquement.
    L'opérateur décide des actions basées sur ce rapport.
    """
    primary_node_id: str
    failure_state: PrimaryFailureState
    recommended_action: NetworkResponseAction
    downtime_seconds: float

    # Vue actuelle et prochain candidat
    current_view: int
    next_view_plan: dict[str, Any]

    # État du quorum après retrait hypothétique du primary
    quorum_after_removal: dict[str, Any]

    # Nœuds restants (excluant le primary mort et les bloqués)
    surviving_nodes: list[str]

    # Horodatage
    assessed_at: float = field(default_factory=time.time)

    # Honnêteté
    certified_100: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_node_id": self.primary_node_id,
            "failure_state": self.failure_state.value,
            "recommended_action": self.recommended_action.value,
            "downtime_seconds": round(self.downtime_seconds, 1),
            "current_view": self.current_view,
            "next_view_plan": self.next_view_plan,
            "quorum_after_removal": self.quorum_after_removal,
            "surviving_nodes": self.surviving_nodes,
            "assessed_at": self.assessed_at,
            "certified_100": self.certified_100,
            "note": self.note,
        }


@dataclass
class NodeRemovalPlan:
    """Plan de retrait d'un nœud PBFT (décision opérateur uniquement).

    Ce dataclass est INFORMATIF. L'exécution réelle du retrait exige :
      1. La décision explicite de l'opérateur
      2. Une modification du registre NODES dans node_registry.py
         (pbft_replica=False sur le nœud retiré)
      3. Un redémarrage de l'application sur tous les nœuds restants
      4. Une vérification que Q nœuds restants forment un quorum valide

    ARTCB n'effectue JAMAIS un retrait automatique.
    CERTIFIED_100=false.
    """
    node_to_remove: str
    reason: str
    current_n: int
    current_f: int | None
    current_q: int
    new_n: int
    new_f: int | None
    new_q: int
    quorum_maintained: bool       # True si new_n ≥ 3 (Q ≥ 2)
    requires_replacement: bool    # True si new_n < 4 (tolérance réduite)
    action_steps: list[str]
    certified_100: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_to_remove": self.node_to_remove,
            "reason": self.reason,
            "current_n_f_q": [self.current_n, self.current_f, self.current_q],
            "new_n_f_q": [self.new_n, self.new_f, self.new_q],
            "quorum_maintained": self.quorum_maintained,
            "requires_replacement": self.requires_replacement,
            "action_steps": self.action_steps,
            "certified_100": self.certified_100,
            "note": (
                "Retrait MANUEL uniquement — opérateur doit mettre pbft_replica=False "
                "dans node_registry.py puis redémarrer tous les nœuds."
            ),
        }


# ─── Fonctions principales ─────────────────────────────────────────────────────

def classify_failure_state(
    downtime_seconds: float,
    *,
    transient_threshold: float = _TRANSIENT_THRESHOLD_S,
    recoverable_threshold: float = _RECOVERABLE_THRESHOLD_S,
) -> tuple[PrimaryFailureState, NetworkResponseAction]:
    """Classifie l'état de défaillance selon la durée d'indisponibilité.

    Args:
        downtime_seconds: durée de l'indisponibilité confirmée en secondes.
        transient_threshold: seuil au-delà duquel c'est "récupérable" (défaut 24h).
        recoverable_threshold: seuil au-delà duquel c'est "permanent" (défaut 7j).

    Returns:
        (PrimaryFailureState, NetworkResponseAction)
    """
    if downtime_seconds <= 0:
        return PrimaryFailureState.ALIVE, NetworkResponseAction.WAIT
    if downtime_seconds < transient_threshold:
        return PrimaryFailureState.DEAD_TRANSIENT, NetworkResponseAction.WAIT
    if downtime_seconds < recoverable_threshold:
        return PrimaryFailureState.DEAD_RECOVERABLE, NetworkResponseAction.TRIGGER_VIEW_CHANGE
    return PrimaryFailureState.DEAD_PERMANENT, NetworkResponseAction.OPERATOR_DECISION


def compute_quorum_after_removal(
    node_to_remove: str,
    *,
    all_replicas: tuple[str, ...] | None = None,
    blocked: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Calcule le quorum si `node_to_remove` est retiré du registre PBFT.

    Args:
        node_to_remove: nœud à retirer hypothétiquement.
        all_replicas: liste complète des replicas (None = live depuis node_registry).
        blocked: nœuds bloqués opérateur (None = _BLOCKED_NODES).

    Returns:
        dict avec new_n, new_f, new_q, quorum_maintained, effective_replicas.
    """
    if all_replicas is None:
        all_replicas = official_pbft_replica_ids()
    blocked_set = blocked if blocked is not None else _BLOCKED_NODES

    # Replicas effectifs = tous sauf celui à retirer et les bloqués
    effective = [
        nid for nid in all_replicas
        if nid != node_to_remove and nid not in blocked_set
    ]
    new_n = len(effective)
    new_n_real, new_f, new_q = n_f_q(new_n)

    return {
        "removed_node": node_to_remove,
        "blocked_nodes": list(blocked_set),
        "effective_replicas": effective,
        "new_n": new_n,
        "new_f": new_f,
        "new_q": new_q,
        "quorum_maintained": new_n >= 3,  # Q=2 minimum viable
        "note": (
            f"N={new_n}, F={new_f}, Q={new_q} après retrait de {node_to_remove}. "
            + ("Quorum maintenu." if new_n >= 3 else "QUORUM PERDU — remplacement obligatoire.")
        ),
    }


def assess_primary_failure(
    *,
    primary_node_id: str = "aws-node-3",
    downtime_seconds: float,
    current_view: int = 27,
    transient_threshold: float = _TRANSIENT_THRESHOLD_S,
    recoverable_threshold: float = _RECOVERABLE_THRESHOLD_S,
) -> PrimaryFailureReport:
    """Évalue l'état de défaillance du primary PBFT et produit un rapport.

    Fonction principale TASK-006 — pure, sans effet de bord.

    Args:
        primary_node_id: identifiant du nœud primary défaillant.
        downtime_seconds: durée confirmée d'indisponibilité.
        current_view: vue PBFT courante.
        transient_threshold: seuil transitoire (défaut 24h).
        recoverable_threshold: seuil permanent (défaut 7j).

    Returns:
        PrimaryFailureReport avec état, action recommandée, plan de view-change
        et impact quorum.
    """
    failure_state, recommended_action = classify_failure_state(
        downtime_seconds,
        transient_threshold=transient_threshold,
        recoverable_threshold=recoverable_threshold,
    )

    # Plan de view-change vers le prochain primary joignable
    next_view = next_reachable_view(current_view)

    # Impact quorum si retrait
    quorum_after = compute_quorum_after_removal(primary_node_id)

    # Nœuds survivants (hors primary mort et hors bloqués)
    all_replicas = official_pbft_replica_ids()
    surviving = [
        nid for nid in all_replicas
        if nid != primary_node_id and nid not in _BLOCKED_NODES
    ]

    # Note explicative
    notes = {
        PrimaryFailureState.ALIVE: (
            "Primary joignable — aucune action requise."
        ),
        PrimaryFailureState.DEAD_TRANSIENT: (
            f"Primary {primary_node_id} injoignable depuis {downtime_seconds/3600:.1f}h. "
            "Watchdog actif — attendre un retour ou le view-change automatique."
        ),
        PrimaryFailureState.DEAD_RECOVERABLE: (
            f"Primary {primary_node_id} injoignable depuis {downtime_seconds/3600:.1f}h. "
            "View-change recommandé : POST /api/v1/consensus/pbft/view-change. "
            f"Prochain primary : {next_view.get('primary', 'inconnu')} (view {next_view.get('target_view', '?')})."
        ),
        PrimaryFailureState.DEAD_PERMANENT: (
            f"Primary {primary_node_id} injoignable depuis {downtime_seconds/86400:.1f}j. "
            "Décision opérateur requise : retirer le nœud du registre PBFT OU remplacer la VM. "
            f"Sans remplacement : N→{quorum_after['new_n']}, "
            f"F={quorum_after['new_f']}, Q={quorum_after['new_q']}. "
            + quorum_after['note']
        ),
    }

    logger.info(
        "assess_primary_failure: primary=%s downtime=%.0fs state=%s action=%s",
        primary_node_id, downtime_seconds, failure_state.value, recommended_action.value,
    )

    return PrimaryFailureReport(
        primary_node_id=primary_node_id,
        failure_state=failure_state,
        recommended_action=recommended_action,
        downtime_seconds=downtime_seconds,
        current_view=current_view,
        next_view_plan=next_view,
        quorum_after_removal=quorum_after,
        surviving_nodes=surviving,
        note=notes[failure_state],
    )


def build_node_removal_plan(
    node_to_remove: str,
    *,
    reason: str = "permanent_failure",
    all_replicas: tuple[str, ...] | None = None,
    blocked: frozenset[str] | None = None,
) -> NodeRemovalPlan:
    """Construit le plan de retrait d'un nœud PBFT.

    INFORMATIF UNIQUEMENT — n'exécute aucune modification.
    L'opérateur doit valider et exécuter les `action_steps` manuellement.

    Args:
        node_to_remove: nœud à retirer.
        reason: raison du retrait (pour traçabilité).
        all_replicas: liste complète (None = live).
        blocked: nœuds bloqués (None = _BLOCKED_NODES).

    Returns:
        NodeRemovalPlan avec étapes à suivre.
    """
    if all_replicas is None:
        all_replicas = official_pbft_replica_ids()
    blocked_set = blocked if blocked is not None else _BLOCKED_NODES

    current_n = len(all_replicas)
    _, current_f, current_q = n_f_q(current_n)

    quorum_after = compute_quorum_after_removal(
        node_to_remove, all_replicas=all_replicas, blocked=blocked_set
    )
    new_n = quorum_after["new_n"]
    _, new_f, new_q = n_f_q(new_n)
    quorum_maintained = new_n >= 3

    action_steps = [
        f"1. Confirmer que {node_to_remove} est définitivement mort "
        f"(raison : {reason}).",
        f"2. Dans src/artcb/node_registry.py : mettre pbft_replica=False "
        f"sur NodeSpec(node_id='{node_to_remove}').",
        "3. Committer le changement + pusher sur main.",
        "4. Redémarrer l'application sur tous les nœuds survivants "
        "(follow-main ou déploiement manuel).",
        f"5. Vérifier via GET /api/v1/consensus/pbft/status que N={new_n}, "
        f"Q={new_q} et qu'un nouveau primary est élu.",
        "6. Si quorum_maintained=False (N<3) : déployer un nouveau nœud "
        "AVANT de retirer l'ancien.",
        "7. Mettre à jour .artcb/task_ledger.yaml : TASK-006 → DONE.",
    ]

    if not quorum_maintained:
        action_steps.insert(0,
            "⚠️ QUORUM INSUFFISANT après retrait — déployer une VM de remplacement "
            "et l'enrôler dans PBFT (pbft_replica=True) AVANT de procéder."
        )

    return NodeRemovalPlan(
        node_to_remove=node_to_remove,
        reason=reason,
        current_n=current_n,
        current_f=current_f,
        current_q=current_q,
        new_n=new_n,
        new_f=new_f,
        new_q=new_q,
        quorum_maintained=quorum_maintained,
        requires_replacement=not quorum_maintained or new_n < 4,
    action_steps=action_steps,
    )
