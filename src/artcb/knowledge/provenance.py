"""ProvenanceChain — Lignée cryptographique des KnowledgeIDs (R434).

La provenance permet de répondre à :
  - Qui a produit cette connaissance ?
  - À partir de quelles connaissances antérieures ?
  - Quelle transformation a produit cette version ?
  - La lignée est-elle intègre (non altérée) ?

Modèle :
    KnowledgeID_A  (producer_A)
          │
    ProvenanceLink (A → B, transformation="DERIVATION")
          │
    KnowledgeID_B  (producer_B)
          │
    ProvenanceLink (B → C, transformation="COMPOSITION")
          │
    KnowledgeID_C

ProvenanceChain = liste ordonnée de ProvenanceLinks + hash de chaîne (R433-style).

Invariants :
  - link_id = "PL" + sha256(from_id + to_id + transformation + ts)[:20]
  - chain_hash = sha256(concat des link_ids en ordre)
  - La chaîne est append-only — ProvenanceChain est frozen après seal().
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


class Transformation(str, Enum):
    """Type de transformation entre deux KnowledgeIDs dans une lignée."""
    DERIVATION     = "DERIVATION"     # B est dérivé de A
    COMPOSITION    = "COMPOSITION"    # C est la composition de A+B
    CORRECTION     = "CORRECTION"     # B corrige A
    VALIDATION     = "VALIDATION"     # B valide A
    REFUTATION     = "REFUTATION"     # B réfute A
    SPECIALISATION = "SPECIALISATION" # B est une spécialisation de A
    GENERALISATION = "GENERALISATION" # B est une généralisation de A
    TRANSLATION    = "TRANSLATION"    # B est A dans une autre langue/représentation


@dataclass(frozen=True)
class ProvenanceLink:
    """Lien de provenance entre deux KnowledgeIDs.

    Champs :
      - link_id        : identifiant stable "PL" + sha256[:20]
      - from_id        : KnowledgeID source
      - to_id          : KnowledgeID cible (produit)
      - transformation : type de transformation (Transformation)
      - actor_id       : agent qui a effectué la transformation
      - created_at     : timestamp ISO UTC
      - metadata       : champs libres
    """

    link_id:        str
    from_id:        str
    to_id:          str
    transformation: Transformation
    actor_id:       str
    created_at:     str
    metadata:       dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "link_id":        self.link_id,
            "from_id":        self.from_id,
            "to_id":          self.to_id,
            "transformation": self.transformation.value,
            "actor_id":       self.actor_id,
            "created_at":     self.created_at,
            "metadata":       dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProvenanceLink":
        return cls(
            link_id=d["link_id"],
            from_id=d["from_id"],
            to_id=d["to_id"],
            transformation=Transformation(d["transformation"]),
            actor_id=d["actor_id"],
            created_at=d["created_at"],
            metadata=dict(d.get("metadata", {})),
        )


def _compute_link_id(
    *,
    from_id: str,
    to_id: str,
    transformation: Transformation,
    actor_id: str,
    created_at: str,
) -> str:
    payload = json.dumps(
        {
            "from_id": from_id,
            "to_id": to_id,
            "transformation": transformation.value,
            "actor_id": actor_id,
            "created_at": created_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return "PL" + h[:20]


def make_link(
    *,
    from_id: str,
    to_id: str,
    transformation: Transformation,
    actor_id: str,
    metadata: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> ProvenanceLink:
    """Crée un ProvenanceLink entre deux KnowledgeIDs."""
    ts = created_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    link_id = _compute_link_id(
        from_id=from_id,
        to_id=to_id,
        transformation=transformation,
        actor_id=actor_id,
        created_at=ts,
    )
    return ProvenanceLink(
        link_id=link_id,
        from_id=from_id,
        to_id=to_id,
        transformation=transformation,
        actor_id=actor_id,
        created_at=ts,
        metadata=dict(metadata or {}),
    )


@dataclass
class ProvenanceChain:
    """Lignée ordonnée de ProvenanceLinks avec intégrité cryptographique.

    La chaîne est append-only : add_link() ajoute un maillon et recalcule
    le chain_hash. seal() gèle la chaîne (frozen=True interne).

    chain_hash = sha256(link_id[0] || link_id[1] || … || link_id[n])
    Toute altération ou réordonnancement d'un maillon invalide le chain_hash.
    """

    links: list[ProvenanceLink] = field(default_factory=list)
    _sealed: bool = field(default=False, compare=False, repr=False)

    def add_link(self, link: ProvenanceLink) -> None:
        """Ajoute un maillon. Lève RuntimeError si la chaîne est scellée."""
        if self._sealed:
            raise RuntimeError("ProvenanceChain est scellée — impossible d'ajouter un lien.")
        self.links.append(link)

    def chain_hash(self) -> str:
        """sha256 de la concaténation ordonnée des link_ids."""
        concat = "".join(lk.link_id for lk in self.links)
        return hashlib.sha256(concat.encode("utf-8")).hexdigest()

    def seal(self) -> "ProvenanceChain":
        """Scelle la chaîne (aucun ajout ultérieur possible). Retourne self."""
        self._sealed = True
        return self

    @property
    def is_sealed(self) -> bool:
        return self._sealed

    def verify(self) -> bool:
        """Vérifie que la chaîne est cohérente (chaque to_id est le from_id du suivant).

        Retourne True si la lignée est continue, False si un saut est détecté.
        Pour une chaîne vide ou à 1 maillon, retourne toujours True.
        """
        if len(self.links) < 2:
            return True
        for i in range(len(self.links) - 1):
            if self.links[i].to_id != self.links[i + 1].from_id:
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "links": [lk.to_dict() for lk in self.links],
            "chain_hash": self.chain_hash(),
            "sealed": self._sealed,
            "length": len(self.links),
            "continuous": self.verify(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProvenanceChain":
        chain = cls(links=[ProvenanceLink.from_dict(lk) for lk in d.get("links", [])])
        if d.get("sealed"):
            chain._sealed = True
        return chain

    def ancestors(self, knowledge_id: str) -> list[str]:
        """Retourne la liste des KnowledgeIDs ancêtres de knowledge_id dans la chaîne."""
        ancestors: list[str] = []
        target = knowledge_id
        for lk in reversed(self.links):
            if lk.to_id == target:
                ancestors.append(lk.from_id)
                target = lk.from_id
        return ancestors
