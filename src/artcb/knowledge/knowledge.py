"""KnowledgeRecord — Unité atomique de connaissance ARTCB (R434).

Un KnowledgeRecord identifie une connaissance produite par un agent.
Son KnowledgeID est stable, déterministe et cryptographiquement engagé sur :
  - l'identité canonique du raisonnement (ReasoningID ou hash IR)
  - le producteur (producer_id)
  - le timestamp de création

Types de connaissance (KnowledgeType) :
  - REASONING    : raisonnement (CanonicalReasoning → IR)
  - FACT         : fait observé ou extrait
  - HYPOTHESIS   : hypothèse non encore validée
  - PROOF        : preuve formelle ou informelle
  - COUNTER      : contre-preuve ou réfutation
  - COMPOSITION  : composition de plusieurs KnowledgeIDs
  - FAILURE      : échec documenté (utile pour la lignée)
  - CONDITION    : condition ou contrainte
  - DEPENDENCY   : dépendance entre connaissances

Invariants :
  - Un KnowledgeRecord ne peut PAS être modifié après création (frozen=True).
  - knowledge_id = "K" + sha256(canonical_payload)[:24]
  - knowledge_id est GLOBAL — deux agents produisant le même raisonnement
    sur les mêmes prémisses obtiennent le même KnowledgeID.
  - Un KnowledgeRecord avec status=INVALIDATED ne peut plus contribuer à PoL.
  - CERTIFIED_100=false

PROTOCOLE ARTCB — mode DEBUG actif.
"""

from __future__ import annotations
MODULE_VERSION = '1.0.1'  # R434 — Knowledge Layer

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class KnowledgeType(str, Enum):
    """Type sémantique d'une connaissance ARTCB."""
    REASONING    = "REASONING"
    FACT         = "FACT"
    HYPOTHESIS   = "HYPOTHESIS"
    PROOF        = "PROOF"
    COUNTER      = "COUNTER"
    COMPOSITION  = "COMPOSITION"
    FAILURE      = "FAILURE"
    CONDITION    = "CONDITION"
    DEPENDENCY   = "DEPENDENCY"


class KnowledgeStatus(str, Enum):
    """Cycle de vie d'un KnowledgeRecord."""
    ACTIVE       = "ACTIVE"       # Disponible pour usage et PoL
    SUPERSEDED   = "SUPERSEDED"   # Remplacé par une version plus récente
    INVALIDATED  = "INVALIDATED"  # Réfuté — ne contribue plus à PoL
    HYPOTHESIS   = "HYPOTHESIS"   # Non encore validé
    COMPOSED     = "COMPOSED"     # Issu d'une composition, pas d'un raisonnement direct


@dataclass(frozen=True)
class KnowledgeRecord:
    """Unité atomique de connaissance ARTCB — identité stable et cryptographiquement engagée.

    Champs clés :
      - knowledge_id  : identifiant stable "K" + sha256[:24]
      - reasoning_id  : ReasoningID d'origine (CanonicalReasoning.reasoning_id())
      - producer_id   : identifiant de l'agent ou du wallet producteur
      - knowledge_type: type sémantique (REASONING, FACT, PROOF, FAILURE, …)
      - status        : cycle de vie (ACTIVE, SUPERSEDED, INVALIDATED, …)
      - parent_ids    : KnowledgeIDs parents (pour composition et lignée)
      - content_hash  : sha256 du contenu sérialisé (validation d'intégrité)
      - created_at    : timestamp ISO UTC
      - metadata      : champs libres (language, source, confidence, …)
    """

    knowledge_id:    str
    reasoning_id:    str
    producer_id:     str
    knowledge_type:  KnowledgeType
    status:          KnowledgeStatus
    content_hash:    str
    created_at:      str
    parent_ids:      tuple[str, ...] = ()
    metadata:        dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge_id":   self.knowledge_id,
            "reasoning_id":   self.reasoning_id,
            "producer_id":    self.producer_id,
            "knowledge_type": self.knowledge_type.value,
            "status":         self.status.value,
            "content_hash":   self.content_hash,
            "created_at":     self.created_at,
            "parent_ids":     list(self.parent_ids),
            "metadata":       dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "KnowledgeRecord":
        return cls(
            knowledge_id=d["knowledge_id"],
            reasoning_id=d["reasoning_id"],
            producer_id=d["producer_id"],
            knowledge_type=KnowledgeType(d["knowledge_type"]),
            status=KnowledgeStatus(d["status"]),
            content_hash=d["content_hash"],
            created_at=d["created_at"],
            parent_ids=tuple(d.get("parent_ids", [])),
            metadata=dict(d.get("metadata", {})),
        )

    def is_usable(self) -> bool:
        """Retourne True si ce KnowledgeRecord peut contribuer à un UsageID et au PoL."""
        return self.status == KnowledgeStatus.ACTIVE

    def supersede(
        self,
        *,
        superseded_by: str,
    ) -> "KnowledgeRecord":
        """Retourne une copie marquée SUPERSEDED (frozen → nouvelle instance)."""
        return KnowledgeRecord(
            knowledge_id=self.knowledge_id,
            reasoning_id=self.reasoning_id,
            producer_id=self.producer_id,
            knowledge_type=self.knowledge_type,
            status=KnowledgeStatus.SUPERSEDED,
            content_hash=self.content_hash,
            created_at=self.created_at,
            parent_ids=self.parent_ids,
            metadata={**self.metadata, "superseded_by": superseded_by},
        )

    def invalidate(self, *, reason: str) -> "KnowledgeRecord":
        """Retourne une copie marquée INVALIDATED (frozen → nouvelle instance)."""
        return KnowledgeRecord(
            knowledge_id=self.knowledge_id,
            reasoning_id=self.reasoning_id,
            producer_id=self.producer_id,
            knowledge_type=self.knowledge_type,
            status=KnowledgeStatus.INVALIDATED,
            content_hash=self.content_hash,
            created_at=self.created_at,
            parent_ids=self.parent_ids,
            metadata={**self.metadata, "invalidation_reason": reason},
        )


# ── Fonctions publiques ───────────────────────────────────────────────────────

def _compute_knowledge_id(
    *,
    reasoning_id: str,
    producer_id: str,
    knowledge_type: KnowledgeType,
    parent_ids: tuple[str, ...],
    created_at: str,
) -> str:
    """Calcule un KnowledgeID déterministe et global.

    Deux agents produisant le même raisonnement avec les mêmes paramètres
    obtiennent le même KnowledgeID. Cela permet de détecter les doublons
    et de relier les contributions indépendantes.
    """
    payload = json.dumps(
        {
            "reasoning_id": reasoning_id,
            "producer_id": producer_id,
            "knowledge_type": knowledge_type.value,
            "parent_ids": sorted(parent_ids),
            "created_at": created_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return "K" + h[:24]


def _compute_content_hash(content: dict[str, Any]) -> str:
    """sha256 du contenu canonique (validation d'intégrité)."""
    raw = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_knowledge(
    *,
    reasoning_id: str,
    producer_id: str,
    knowledge_type: KnowledgeType = KnowledgeType.REASONING,
    status: KnowledgeStatus = KnowledgeStatus.ACTIVE,
    content: dict[str, Any] | None = None,
    parent_ids: list[str] | tuple[str, ...] = (),
    metadata: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> KnowledgeRecord:
    """Crée un KnowledgeRecord avec un KnowledgeID déterministe.

    Paramètres :
      - reasoning_id   : ReasoningID ou identifiant IR de la connaissance source.
      - producer_id    : identifiant de l'agent/wallet producteur.
      - knowledge_type : type sémantique (REASONING par défaut).
      - status         : ACTIVE par défaut.
      - content        : dict optionnel représentant le contenu (haché → content_hash).
      - parent_ids     : KnowledgeIDs parents (pour composition et lignée).
      - metadata       : champs libres (language, source, confidence, …).
      - created_at     : timestamp ISO UTC (automatique si None).

    Retourne un KnowledgeRecord frozen avec un KnowledgeID stable et global.
    """
    ts = created_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    pids = tuple(sorted(str(p) for p in parent_ids))
    content_hash = _compute_content_hash(content or {"reasoning_id": reasoning_id})
    knowledge_id = _compute_knowledge_id(
        reasoning_id=reasoning_id,
        producer_id=producer_id,
        knowledge_type=knowledge_type,
        parent_ids=pids,
        created_at=ts,
    )
    return KnowledgeRecord(
        knowledge_id=knowledge_id,
        reasoning_id=reasoning_id,
        producer_id=producer_id,
        knowledge_type=knowledge_type,
        status=status,
        content_hash=content_hash,
        created_at=ts,
        parent_ids=pids,
        metadata=dict(metadata or {}),
    )
