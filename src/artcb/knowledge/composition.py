"""compose_knowledge — Composition de plusieurs KnowledgeIDs (R434).

La composition permet à un agent de combiner plusieurs connaissances existantes
pour en produire une nouvelle. Elle crée automatiquement :
  - un nouveau KnowledgeRecord de type COMPOSITION
  - les ProvenanceLinks reliant chaque parent au KnowledgeID composé
  - un UsageRecord pour chaque KnowledgeID parent

Propriété : un KnowledgeID de composition n'est usable() que si TOUS ses
parents sont ACTIVE (sinon le résultat est potentiellement compromis).

PROTOCOLE ARTCB — mode DEBUG actif.
"""

from __future__ import annotations
MODULE_VERSION = '1.0.1'  # R434 — Knowledge Layer

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.artcb.knowledge.knowledge import (
    KnowledgeRecord,
    KnowledgeStatus,
    KnowledgeType,
    create_knowledge,
)
from src.artcb.knowledge.provenance import ProvenanceChain, Transformation, make_link
from src.artcb.knowledge.usage import UsagePurpose, UsageRecord, record_usage


@dataclass
class CompositionResult:
    """Résultat d'une composition de KnowledgeIDs.

    Champs :
      - composed_record   : KnowledgeRecord de type COMPOSITION produit
      - provenance_chain  : ProvenanceChain reliant parents → composé
      - usage_records     : UsageRecord pour chaque parent utilisé
      - all_parents_active: True si tous les KnowledgeIDs parents étaient ACTIVE
      - composition_hash  : sha256 des parent_ids triés (identité de la composition)
    """

    composed_record:    KnowledgeRecord
    provenance_chain:   ProvenanceChain
    usage_records:      list[UsageRecord]
    all_parents_active: bool
    composition_hash:   str

    def to_dict(self) -> dict[str, Any]:
        return {
            "composed_record":    self.composed_record.to_dict(),
            "provenance_chain":   self.provenance_chain.to_dict(),
            "usage_records":      [u.to_dict() for u in self.usage_records],
            "all_parents_active": self.all_parents_active,
            "composition_hash":   self.composition_hash,
        }


def compose_knowledge(
    *,
    parent_records: list[KnowledgeRecord],
    producer_id: str,
    reasoning_id: str,
    content: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> CompositionResult:
    """Compose plusieurs KnowledgeRecords en un nouveau KnowledgeRecord.

    Paramètres :
      - parent_records : liste des KnowledgeRecords parents (≥ 2 recommandé).
      - producer_id    : agent/wallet qui effectue la composition.
      - reasoning_id   : ReasoningID du raisonnement de composition.
      - content        : dict optionnel représentant le résultat de la composition.
      - metadata       : champs libres.
      - created_at     : timestamp ISO UTC (automatique si None).

    Lève ValueError si parent_records est vide.

    Retourne un CompositionResult avec :
      - le nouveau KnowledgeRecord (type=COMPOSITION)
      - la ProvenanceChain complète
      - les UsageRecords pour chaque parent
      - all_parents_active indique si tous les parents étaient ACTIVE
    """
    if not parent_records:
        raise ValueError("compose_knowledge() requiert au moins un parent_record.")

    ts = created_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Calcul du composition_hash (identité de la combinaison)
    sorted_parent_ids = sorted(r.knowledge_id for r in parent_records)
    comp_raw = json.dumps(sorted_parent_ids, sort_keys=True, separators=(",", ":"))
    composition_hash = hashlib.sha256(comp_raw.encode("utf-8")).hexdigest()

    # Vérification que tous les parents sont ACTIVE
    all_parents_active = all(r.status == KnowledgeStatus.ACTIVE for r in parent_records)

    # Statut du composé : ACTIVE seulement si tous les parents le sont
    composed_status = KnowledgeStatus.ACTIVE if all_parents_active else KnowledgeStatus.HYPOTHESIS

    # Création du KnowledgeRecord composé
    composed_record = create_knowledge(
        reasoning_id=reasoning_id,
        producer_id=producer_id,
        knowledge_type=KnowledgeType.COMPOSITION,
        status=composed_status,
        content={
            "composition_hash": composition_hash,
            "parent_ids": sorted_parent_ids,
            **(content or {}),
        },
        parent_ids=sorted_parent_ids,
        metadata={
            "composition_hash": composition_hash,
            "all_parents_active": all_parents_active,
            **(metadata or {}),
        },
        created_at=ts,
    )

    # Construction de la ProvenanceChain
    chain = ProvenanceChain()
    for parent in parent_records:
        link = make_link(
            from_id=parent.knowledge_id,
            to_id=composed_record.knowledge_id,
            transformation=Transformation.COMPOSITION,
            actor_id=producer_id,
            created_at=ts,
        )
        chain.add_link(link)
    chain.seal()

    # UsageRecord pour chaque parent
    usage_records = [
        record_usage(
            knowledge_id=parent.knowledge_id,
            consumer_id=producer_id,
            purpose=UsagePurpose.COMPOSITION,
            result_knowledge_id=composed_record.knowledge_id,
            knowledge_status=parent.status.value,
            used_at=ts,
        )
        for parent in parent_records
    ]

    return CompositionResult(
        composed_record=composed_record,
        provenance_chain=chain,
        usage_records=usage_records,
        all_parents_active=all_parents_active,
        composition_hash=composition_hash,
    )
