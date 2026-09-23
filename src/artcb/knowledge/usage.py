"""UsageRecord — Traçabilité de l'utilisation d'un KnowledgeID (R434).

Un UsageRecord est créé chaque fois qu'un KnowledgeID est utilisé par un agent
(composition, référence, dérivation, validation, PoL). Il constitue le maillon
entre la production de connaissance et la preuve d'utilité (PoL).

Modèle :
    KnowledgeID
         ↓
    UsageRecord  (UsageID, consumer_id, purpose, …)
         ↓
    Useful Work
         ↓
    PoL → Reward

Invariants :
  - usage_id = "U" + sha256(knowledge_id + consumer_id + purpose + used_at)[:24]
  - Un UsageRecord est frozen après création.
  - is_pol_eligible() retourne True uniquement si le KnowledgeRecord associé
    est ACTIVE et si le purpose est dans POL_ELIGIBLE_PURPOSES.
  - CERTIFIED_100=false

PROTOCOLE ARTCB — mode DEBUG actif.
"""

from __future__ import annotations
MODULE_VERSION = '1.0.1'  # R434 — Knowledge Layer

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class UsagePurpose(str, Enum):
    """Raison pour laquelle un KnowledgeID a été utilisé."""
    COMPOSITION    = "COMPOSITION"   # Combiné avec d'autres connaissances
    VALIDATION     = "VALIDATION"    # Utilisé pour valider un autre raisonnement
    DERIVATION     = "DERIVATION"    # Base d'un raisonnement dérivé
    REFERENCE      = "REFERENCE"     # Cité comme source
    CORRECTION     = "CORRECTION"    # Utilisé pour corriger une erreur
    POL_CLAIM      = "POL_CLAIM"     # Contribution directe à un PoL block
    RETRIEVAL      = "RETRIEVAL"     # Récupéré dans la base de connaissance
    COMPARISON     = "COMPARISON"    # Comparé à une autre connaissance
    CONTRADICTION  = "CONTRADICTION" # Utilisé pour réfuter


# Purposes éligibles à contribuer au PoL (subset strict)
POL_ELIGIBLE_PURPOSES: frozenset[UsagePurpose] = frozenset({
    UsagePurpose.COMPOSITION,
    UsagePurpose.VALIDATION,
    UsagePurpose.DERIVATION,
    UsagePurpose.POL_CLAIM,
})


@dataclass(frozen=True)
class UsageRecord:
    """Enregistrement d'une utilisation de KnowledgeID par un agent.

    Champs clés :
      - usage_id       : identifiant stable "U" + sha256[:24]
      - knowledge_id   : KnowledgeID utilisé
      - consumer_id    : identifiant de l'agent/wallet consommateur
      - purpose        : raison de l'utilisation (UsagePurpose)
      - used_at        : timestamp ISO UTC
      - result_knowledge_id : KnowledgeID produit grâce à cette utilisation (optionnel)
      - pol_eligible   : True si cette utilisation peut contribuer au PoL
      - metadata       : champs libres (job_id, work_id, confidence, …)
    """

    usage_id:             str
    knowledge_id:         str
    consumer_id:          str
    purpose:              UsagePurpose
    used_at:              str
    pol_eligible:         bool
    result_knowledge_id:  str | None = None
    metadata:             dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "usage_id":             self.usage_id,
            "knowledge_id":         self.knowledge_id,
            "consumer_id":          self.consumer_id,
            "purpose":              self.purpose.value,
            "used_at":              self.used_at,
            "pol_eligible":         self.pol_eligible,
            "result_knowledge_id":  self.result_knowledge_id,
            "metadata":             dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "UsageRecord":
        return cls(
            usage_id=d["usage_id"],
            knowledge_id=d["knowledge_id"],
            consumer_id=d["consumer_id"],
            purpose=UsagePurpose(d["purpose"]),
            used_at=d["used_at"],
            pol_eligible=bool(d["pol_eligible"]),
            result_knowledge_id=d.get("result_knowledge_id"),
            metadata=dict(d.get("metadata", {})),
        )


# ── Fonctions publiques ───────────────────────────────────────────────────────

def _compute_usage_id(
    *,
    knowledge_id: str,
    consumer_id: str,
    purpose: UsagePurpose,
    used_at: str,
) -> str:
    """Calcule un UsageID déterministe."""
    payload = json.dumps(
        {
            "knowledge_id": knowledge_id,
            "consumer_id": consumer_id,
            "purpose": purpose.value,
            "used_at": used_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return "U" + h[:24]


def record_usage(
    *,
    knowledge_id: str,
    consumer_id: str,
    purpose: UsagePurpose = UsagePurpose.REFERENCE,
    result_knowledge_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    used_at: str | None = None,
    knowledge_status: str = "ACTIVE",
) -> UsageRecord:
    """Crée un UsageRecord pour un KnowledgeID consommé.

    Paramètres :
      - knowledge_id         : KnowledgeID utilisé.
      - consumer_id          : identifiant de l'agent/wallet consommateur.
      - purpose              : raison de l'utilisation (REFERENCE par défaut).
      - result_knowledge_id  : KnowledgeID produit grâce à cette utilisation (optionnel).
      - metadata             : champs libres (job_id, work_id, confidence, …).
      - used_at              : timestamp ISO UTC (automatique si None).
      - knowledge_status     : état du KnowledgeRecord associé ("ACTIVE", "SUPERSEDED", …).
                               Seul ACTIVE → eligible PoL si purpose éligible.

    Retourne un UsageRecord frozen avec un UsageID stable.
    """
    ts = used_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    usage_id = _compute_usage_id(
        knowledge_id=knowledge_id,
        consumer_id=consumer_id,
        purpose=purpose,
        used_at=ts,
    )
    pol_eligible = (
        purpose in POL_ELIGIBLE_PURPOSES
        and knowledge_status == "ACTIVE"
    )
    return UsageRecord(
        usage_id=usage_id,
        knowledge_id=knowledge_id,
        consumer_id=consumer_id,
        purpose=purpose,
        used_at=ts,
        pol_eligible=pol_eligible,
        result_knowledge_id=result_knowledge_id,
        metadata=dict(metadata or {}),
    )
