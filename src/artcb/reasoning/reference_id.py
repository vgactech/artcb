"""ReferenceID — Identifiant canonique d'une référence ARTCB (R355, 2026-09-17).

Un ReferenceID identifie de façon non-ambiguë la CAUSE d'un raisonnement :
qu'est-ce qui a déclenché cette pensée, cette règle, cet événement ?

## Quatre types (rapport 370, section 9) :

  A. CODE   : référence à un fichier source (repo + commit + chemin + symbole)
  B. BLOCK  : référence à un bloc on-chain ARTCB (index + hash)
  C. RULE   : référence à une règle Cursor/Bob (nom + version + fichier)
  D. HUMAN  : référence à un identifiant humain ARTCB (human_id)

## Format canonique :

  refid:<type>:<sha256_16>

Exemple :
  refid:code:3f7a2b9c1e4d5f6a
  refid:block:a1b2c3d4e5f60001
  refid:rule:99f0deadbeef0123
  refid:human:ff00112233445566

HONNÊTETÉ : Ce module ne prétend pas que les références couvrent le CoT
interne du modèle. Elles couvrent ce qui est observable : fichiers modifiés,
blocs on-chain, règles lues, identités humaines invoquées.
CERTIFIED_100=false.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class RefType(str, Enum):
    CODE  = "code"   # Fichier / symbole dans le dépôt
    BLOCK = "block"  # Bloc on-chain ARTCB
    RULE  = "rule"   # Règle Cursor / Bob (.mdc / SKILL.md)
    HUMAN = "human"  # Identité humaine ARTCB (human_id)


@dataclass
class ReferenceID:
    """Identifiant canonique d'une référence ARTCB.

    Attributes:
        ref_type:    Type de référence (code/block/rule/human).
        payload:     Données spécifiques au type (dict).
        ref_id:      Hash canonique — calculé automatiquement.
        canonical:   Forme canonique lisible : refid:<type>:<sha256_16>
        created_at:  Horodatage nanoseconde de création.
    """
    ref_type: RefType
    payload: dict[str, Any]
    ref_id: str = field(default="", init=False)
    canonical: str = field(default="", init=False)
    created_at: int = field(default_factory=time.time_ns)

    def __post_init__(self) -> None:
        self.ref_id = self._compute_hash()
        self.canonical = f"refid:{self.ref_type.value}:{self.ref_id[:16]}"

    def _compute_hash(self) -> str:
        """Hash SHA-256 du type + payload trié."""
        blob = json.dumps(
            {"ref_type": self.ref_type.value, "payload": self.payload},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref_type": self.ref_type.value,
            "ref_id": self.ref_id,
            "canonical": self.canonical,
            "payload": self.payload,
            "created_at": self.created_at,
        }

    def __str__(self) -> str:
        return self.canonical

    def __repr__(self) -> str:
        return f"ReferenceID({self.canonical!r})"


# ─── Constructeurs spécialisés ────────────────────────────────────────────────


def ref_code(
    *,
    path: str,
    repository: str = "vgactech/artcb",
    commit: str = "",
    symbol: str = "",
    line_start: int | None = None,
    line_end: int | None = None,
    sha256: str = "",
) -> ReferenceID:
    """Crée un ReferenceID de type CODE.

    Args:
        path:        Chemin relatif du fichier dans le dépôt.
        repository:  Identifiant dépôt GitHub (ex: vgactech/artcb).
        commit:      SHA du commit (peut être vide si HEAD).
        symbol:      Nom du symbole (classe, fonction…).
        line_start:  Première ligne concernée.
        line_end:    Dernière ligne concernée.
        sha256:      Hash du contenu du fichier (optionnel).
    """
    return ReferenceID(
        ref_type=RefType.CODE,
        payload={
            "repository": repository,
            "commit": commit,
            "path": path,
            "symbol": symbol,
            "line_start": line_start,
            "line_end": line_end,
            "sha256": sha256,
        },
    )


def ref_block(
    *,
    block_index: int,
    block_hash: str,
    chain_id: str = "artcb-main",
    memo_type: str = "",
) -> ReferenceID:
    """Crée un ReferenceID de type BLOCK (référence à un bloc on-chain ARTCB)."""
    return ReferenceID(
        ref_type=RefType.BLOCK,
        payload={
            "chain_id": chain_id,
            "block_index": block_index,
            "block_hash": block_hash,
            "memo_type": memo_type,
        },
    )


def ref_rule(
    *,
    rule_name: str,
    rule_file: str = "",
    rule_version: str = "",
    rule_section: str = "",
) -> ReferenceID:
    """Crée un ReferenceID de type RULE (règle Cursor / Bob / ARTCB).

    Args:
        rule_name:    Nom canonique de la règle (ex: R350, artcb-live-node).
        rule_file:    Chemin du fichier contenant la règle.
        rule_version: Version ou date de la règle.
        rule_section: Section spécifique dans la règle.
    """
    return ReferenceID(
        ref_type=RefType.RULE,
        payload={
            "rule_name": rule_name,
            "rule_file": rule_file,
            "rule_version": rule_version,
            "rule_section": rule_section,
        },
    )


def ref_human(
    *,
    human_id: str,
    device_hint: str = "",
    wallet_address: str = "",
) -> ReferenceID:
    """Crée un ReferenceID de type HUMAN (identité biométrique ARTCB).

    unique_human_proven=false — CERTIFIED_100=false.
    """
    return ReferenceID(
        ref_type=RefType.HUMAN,
        payload={
            "human_id": human_id,
            "device_hint": device_hint,
            "wallet_address": wallet_address,
            "unique_human_proven": False,
            "certified_100": False,
        },
    )


def ref_from_dict(d: dict[str, Any]) -> ReferenceID:
    """Recrée un ReferenceID depuis son dict sérialisé."""
    ref_type = RefType(d["ref_type"])
    obj = ReferenceID(ref_type=ref_type, payload=d["payload"])
    # Vérification d'intégrité
    if obj.ref_id != d.get("ref_id", obj.ref_id):
        raise ValueError(
            f"ReferenceID integrity mismatch: stored={d.get('ref_id')!r} computed={obj.ref_id!r}"
        )
    return obj
