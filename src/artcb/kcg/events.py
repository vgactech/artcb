"""KCG — modèles d'événements (GO-F 2026-09-07).

Trois entités fondamentales :

  KnowledgeEntry  — une unité de connaissance publiée dans le KCG
  ConsultEvent    — CONSULT : accès à une connaissance (avant utilisation)
  UseEvent        — USE : utilisation effective + mesure de delta d'utilité

Format identifiant :
  KnowledgeID = "K_<graph_id_prefix>"
  UsageID     = "U_<hex16>"
  ConsultID   = "C_<hex16>"

Note : les fees (GO-G) seront référencés dans UseEvent.fee_pending
mais ne sont pas encore déclenchés (GO-F = enregistrement uniquement).
"""

from __future__ import annotations

import secrets
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import UTC, datetime
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _uid(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def knowledge_id(graph_id: str) -> str:
    """Dérive un KnowledgeID stable depuis un graph_id."""
    h = hashlib.sha256(graph_id.encode()).hexdigest()[:16]
    return f"K_{h}"


@dataclass
class KnowledgeEntry:
    """Unité de connaissance publiée dans le KCG.

    Créée lors du premier minage PoL d'un graphe IR.
    Liée au wallet du producteur.
    """
    knowledge_id: str           # K_<sha256prefix>
    graph_id: str               # identifiant graphe IR (source)
    producer_address: str       # wallet artcb1xxx du producteur
    pol_block_index: int        # bloc PoL qui certifie ce travail
    pol_score: float            # score PoL au moment de la publication
    created_at: str = field(default_factory=_now_iso)
    title: str = ""             # extrait du texte source (64 chars max)
    visibility: str = "public"  # public | private
    # Statistiques (mises à jour par KCGIndex)
    consult_count: int = 0
    use_count: int = 0
    total_delta_utility: float = 0.0
    reputation_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "KnowledgeEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ConsultEvent:
    """CONSULT — un agent/humain a découvert et demandé accès à K.

    Enregistré AVANT l'utilisation effective.
    GO-G ajoutera fee_amount ici et déclenchera le transfert wallet.
    """
    event_type: str = "CONSULT"
    consult_id: str = field(default_factory=lambda: _uid("C"))
    knowledge_id: str = ""          # K_ référencé
    graph_id: str = ""              # graphe source
    consultant_address: str = ""    # wallet artcb1xxx du consultant
    agent_id: str = ""              # agent (bob_agent_xxx ou "")
    session_id: str = ""
    timestamp: str = field(default_factory=_now_iso)
    # GO-G : fee_amount_satoshi sera non-nul quand le fee est activé
    fee_amount_satoshi: int = 0     # 0 = GO-F (pas encore de fee)
    fee_pending: bool = False       # True = GO-G activé

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ConsultEvent":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class UseEvent:
    """USE — utilisation effective + mesure de delta d'utilité.

    Enregistré après que le consultant a appliqué la connaissance
    et mesuré un résultat (delta_utility = résultat_après - résultat_avant).

    delta_utility > 0 → preuve d'utilité positive
    delta_utility = 0 → utilisation sans mesure (pas de preuve)
    delta_utility < 0 → utilisation contre-productive (rare)
    """
    event_type: str = "USE"
    usage_id: str = field(default_factory=lambda: _uid("U"))
    consult_id: str = ""            # ConsultEvent parent
    knowledge_id: str = ""          # K_ référencé
    graph_id: str = ""
    consumer_address: str = ""      # wallet artcb1xxx
    agent_id: str = ""
    session_id: str = ""
    timestamp: str = field(default_factory=_now_iso)
    # Mesure d'utilité (optionnelle — agent peut ne pas mesurer)
    score_before: float | None = None
    score_after: float | None = None
    delta_utility: float = 0.0      # score_after - score_before si mesurés
    utility_measured: bool = False  # True = delta calculé depuis scores réels
    # Référence au graphe dérivé (GO-G : K2 dérivé de K1)
    derived_graph_id: str = ""      # graph_id produit si K transformé → K2
    derived_knowledge_id: str = ""  # K_ du graphe dérivé

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "UseEvent":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
