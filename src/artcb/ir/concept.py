"""ConceptID et ExpressionID — Langage IA natif ARTCB (GO-K / rapport 238).

Rapport 238 §13 :
  > "Un hash de texte n'est pas un identifiant sémantique."
  > "Il faut distinguer ConceptID (le concept) de ExpressionID (comment un agent l'a exprimé)."

Rapport 238 §23 :
  > "Agent A → ConceptID K8291 → Agent B"
  > "Si B connaît déjà K8291, il n'a plus besoin de recevoir toute la définition."

Rapport 238 §24 :
  > "Compact pour l'IA, vérifiable par le protocole."
  > ConceptID lié cryptographiquement à : DefinitionHash + Version + Symboles ARTCB.

Architecture :
  ExpressionID — identifie UNE manière d'exprimer un concept (peut varier entre agents/langues)
  ConceptID    — identifie LE concept sémantique stable (convergence de N expressions)

  "Le serveur doit vérifier la signature."  → ExpressionID E1 ─┐
  "Le nœud doit authentifier le bloc."      → ExpressionID E2 ─┼→ ConceptID K8392
  "Accept only after signature validation." → ExpressionID E3 ─┘

ConceptID dérivé depuis :
  - symboles ARTCB dominants du nœud (couches 1+2+3 de LANGAGE_SYMBOLES_ARTCB)
  - type sémantique (F/E/R/H/D/G/P/C)
  - relations (→ ⇒ ⊃ ⊥ ⊢ ≡)
  PAS du texte brut — PAS du hash de phrase.

Format binaire : les ConceptPacket entre agents utilisent struct pack (pas JSON).
"""

from __future__ import annotations

import hashlib
import struct
import time
from dataclasses import dataclass, field
from typing import Any

# ── Version du protocole ConceptID ────────────────────────────────────────────
CONCEPT_PROTOCOL_VERSION: int = 1

# Magic bytes pour un ConceptPacket binaire : ASCII "ACPT"
CONCEPT_PACKET_MAGIC = b"ACPT"
CONCEPT_PACKET_HEADER_SIZE = 12  # magic(4) + version(1) + n_concepts(2) + reserved(1) + payload_len(4)


# ── ConceptID ─────────────────────────────────────────────────────────────────

def _concept_id_from_symbols(
    node_type: str,
    primary_sym: str,
    relations: list[str],
) -> str:
    """Calcule un ConceptID stable depuis les symboles ARTCB — pas depuis le texte.

    Le même concept sémantique (même type + mêmes symboles + mêmes relations)
    produit toujours le même ConceptID, quelle que soit la langue d'expression.

    Args:
        node_type: Type sémantique F/E/R/H/D/G/P/C (grammar.NodeType)
        primary_sym: Symbole principal du nœud (ex: "O1α3", "D1", "M3")
        relations: Liste des relations sortantes (ex: ["→", "⊢"])

    Returns:
        ConceptID au format "K{16 hex chars}"
    """
    # Normalisation : ordre des relations déterministe
    rel_part = "|".join(sorted(set(relations)))
    raw = f"{node_type.upper()}:{primary_sym}:{rel_part}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"K{digest}"


def concept_id_from_node(node: Any) -> str:
    """Calcule le ConceptID d'un IRNode existant.

    Args:
        node: IRNode (duck typing — doit avoir .t, .sym, .id)

    Returns:
        ConceptID stable.
    """
    # Relations : non disponibles au niveau nœud seul — on utilise sym uniquement
    return _concept_id_from_symbols(
        node_type=str(node.t),
        primary_sym=str(node.sym),
        relations=[],
    )


def concept_id_from_graph_edge(
    node_type: str,
    primary_sym: str,
    outgoing_relations: list[str],
) -> str:
    """ConceptID enrichi avec les relations sortantes (contexte graphe complet)."""
    return _concept_id_from_symbols(node_type, primary_sym, outgoing_relations)


# ── ExpressionID ─────────────────────────────────────────────────────────────

def expression_id(agent_id: str, node_id: str, timestamp: float | None = None) -> str:
    """Identifiant unique d'une expression par un agent donné.

    ExpressionID identifie COMMENT un agent a exprimé un concept, pas LE concept.
    Deux agents peuvent avoir des ExpressionID différents pour le même ConceptID.

    Args:
        agent_id: Identifiant de l'agent (node_id, wallet address…)
        node_id: ID du nœud IRNode
        timestamp: Moment de l'expression (défaut: now)

    Returns:
        ExpressionID au format "E{16 hex chars}"
    """
    ts = timestamp if timestamp is not None else time.time()
    raw = f"{agent_id}:{node_id}:{ts:.3f}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"E{digest}"


# ── ConceptRecord ─────────────────────────────────────────────────────────────

@dataclass
class ConceptRecord:
    """Association entre un ConceptID et ses métadonnées sémantiques.

    Rapport 238 §24 : "compact pour l'IA, vérifiable par le protocole"
    - concept_id : identifiant sémantique stable
    - definition_hash : hash du binaire ARTCB canonique (vérifié par le protocole)
    - symbol : symbole ARTCB compact (α17, D1, O1M3…)
    - node_type : type sémantique (F/E/R/H/D/G/P/C)
    - version : version du concept (évolution sans casser l'ancien)
    - creator_agent : agent qui a proposé ce concept
    - created_at : timestamp de création
    - expression_count : nombre d'agents qui ont exprimé ce concept
    """
    concept_id: str
    symbol: str
    node_type: str
    definition_hash: str = ""
    version: int = 1
    creator_agent: str = "unknown"
    created_at: float = field(default_factory=time.time)
    expression_count: int = 1

    def to_binary(self) -> bytes:
        """Sérialise en binaire compact (pas JSON).

        Format :
          concept_id(32 bytes ASCII padded)
          symbol(16 bytes UTF-8 padded)
          node_type(2 bytes)
          version(2 bytes uint16)
          expression_count(4 bytes uint32)
          created_at(8 bytes double)
          definition_hash(32 bytes hex)
          creator_agent(32 bytes padded)
        """
        cid  = self.concept_id.encode("ascii").ljust(32, b"\x00")[:32]
        sym  = self.symbol.encode("utf-8").ljust(16, b"\x00")[:16]
        nt   = self.node_type.encode("ascii").ljust(2, b"\x00")[:2]
        ver  = struct.pack(">H", self.version)
        cnt  = struct.pack(">I", self.expression_count)
        ts   = struct.pack(">d", self.created_at)
        dhash = self.definition_hash.encode("ascii").ljust(32, b"\x00")[:32]
        agent = self.creator_agent.encode("utf-8").ljust(32, b"\x00")[:32]
        return cid + sym + nt + ver + cnt + ts + dhash + agent

    @classmethod
    def from_binary(cls, data: bytes) -> ConceptRecord:
        """Désérialise depuis le format binaire compact."""
        if len(data) < 128:
            raise ValueError(f"ConceptRecord trop court : {len(data)} bytes (min 128)")
        concept_id     = data[0:32].rstrip(b"\x00").decode("ascii")
        symbol         = data[32:48].rstrip(b"\x00").decode("utf-8")
        node_type      = data[48:50].rstrip(b"\x00").decode("ascii")
        version        = struct.unpack(">H", data[50:52])[0]
        expression_count = struct.unpack(">I", data[52:56])[0]
        created_at     = struct.unpack(">d", data[56:64])[0]
        definition_hash = data[64:96].rstrip(b"\x00").decode("ascii")
        creator_agent  = data[96:128].rstrip(b"\x00").decode("utf-8")
        return cls(
            concept_id=concept_id,
            symbol=symbol,
            node_type=node_type,
            definition_hash=definition_hash,
            version=version,
            creator_agent=creator_agent,
            created_at=created_at,
            expression_count=expression_count,
        )

    def to_dict(self) -> dict[str, Any]:
        """Vue lisible pour l'interface humaine uniquement."""
        return {
            "concept_id": self.concept_id,
            "symbol": self.symbol,
            "node_type": self.node_type,
            "definition_hash": self.definition_hash,
            "version": self.version,
            "creator_agent": self.creator_agent,
            "created_at": self.created_at,
            "expression_count": self.expression_count,
        }


# ── ConceptPacket — canal agent-agent ─────────────────────────────────────────

def encode_concept_packet(concept_ids: list[str]) -> bytes:
    """Encode une liste de ConceptID en paquet binaire pour transmission agent-agent.

    Rapport 238 §23 : "Agent A → ConceptID K8291 → Agent B"
    Agent A envoie UNIQUEMENT les ConceptID — pas le texte, pas le JSON.

    Format :
      ACPT(4) + version(1) + n_concepts(2) + reserved(1) + payload_len(4)
      + [concept_id(32 bytes) × n_concepts]

    Args:
        concept_ids: Liste de ConceptID au format "K{hex}"

    Returns:
        Bytes prêts à être transmis sur le canal P2P.
    """
    n = len(concept_ids)
    payload = b"".join(
        cid.encode("ascii").ljust(32, b"\x00")[:32]
        for cid in concept_ids
    )
    header = (
        CONCEPT_PACKET_MAGIC
        + struct.pack("B", CONCEPT_PROTOCOL_VERSION)
        + struct.pack(">H", n)
        + b"\x00"                          # reserved
        + struct.pack(">I", len(payload))
    )
    return header + payload


def decode_concept_packet(data: bytes) -> list[str]:
    """Décode un paquet binaire ConceptID.

    Args:
        data: Bytes reçus sur le canal P2P.

    Returns:
        Liste de ConceptID.

    Raises:
        ValueError: Si magic ou version invalides, ou payload tronqué.
    """
    if len(data) < CONCEPT_PACKET_HEADER_SIZE:
        raise ValueError(f"Paquet trop court : {len(data)} bytes")

    magic = data[:4]
    if magic != CONCEPT_PACKET_MAGIC:
        raise ValueError(f"Magic invalide : {magic!r}")

    version = struct.unpack("B", data[4:5])[0]
    if version != CONCEPT_PROTOCOL_VERSION:
        raise ValueError(f"Version inconnue : {version}")

    n_concepts = struct.unpack(">H", data[5:7])[0]
    payload_len = struct.unpack(">I", data[8:12])[0]
    payload = data[CONCEPT_PACKET_HEADER_SIZE: CONCEPT_PACKET_HEADER_SIZE + payload_len]

    if len(payload) != payload_len:
        raise ValueError(f"Payload tronqué : {len(payload)} bytes (attendu {payload_len})")

    expected_payload_size = n_concepts * 32
    if len(payload) < expected_payload_size:
        raise ValueError(f"Payload insuffisant pour {n_concepts} concepts")

    result = []
    for i in range(n_concepts):
        chunk = payload[i * 32: (i + 1) * 32]
        cid = chunk.rstrip(b"\x00").decode("ascii")
        result.append(cid)
    return result
