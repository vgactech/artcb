"""ConceptBundle — transport réseau du ConceptStore (R320, 2026-09-11T21:30:00Z).

Problème mesuré en R319 (C2-D = PARTIAL) :
  L'agent A apprend un texte, en dérive des ConceptID et envoie un ConceptPacket
  binaire (``ACPT``) à l'agent B. Le paquet ne transporte QUE des identifiants.
  Si le store de B ne contient pas déjà le blob ``.arcb`` correspondant, B ne peut
  rien reconstruire : ``missing_concept_ids`` non vide → « cold B » échoue.
  R319 contournait le trou avec un ``shutil.copytree`` sur disque local — ce n'est
  pas une preuve réseau.

R320 ajoute le maillon manquant : un **ConceptBundle** binaire natif, qui transporte
les graphes ``.arcb`` eux-mêmes, et peut donc voyager sur le réseau ARTCB.

Format binaire ``ACBN`` (aucun JSON, aucun texte humain dans l'en-tête) ::

    magic(4)="ACBN" | version(2) | graph_count(4)
    puis graph_count × :
        graph_id_len(2) | graph_id(utf-8) | blob_len(4) | blob(.arcb ARCB)

Le blob est exactement l'octet-pour-octet du fichier ``{graph_id}.arcb`` produit
par ``ConceptStore``. L'import chez B redonne donc le même ``definition_hash``
et les mêmes ConceptID — la dérivation est déterministe.
"""

from __future__ import annotations

import hashlib
import logging
import struct
from typing import TYPE_CHECKING

from src.artcb.ir.binary import graph_from_bytes

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.artcb.memory.concept_store import ConceptStore

logger = logging.getLogger("artcb.memory.concept_sync")

BUNDLE_MAGIC = b"ACBN"  # ARTCB Concept Bundle Network
BUNDLE_VERSION = 1
BUNDLE_HEADER_SIZE = 10  # magic(4) + version(2) + count(4)


class ConceptBundleError(Exception):
    """Bundle binaire illisible ou incohérent."""


def encode_concept_bundle(graphs: list[tuple[str, bytes]]) -> bytes:
    """Sérialise une liste ``(graph_id, blob .arcb)`` en bundle binaire.

    Args:
        graphs: paires ``(graph_id, bytes)`` — le blob est le ``.arcb`` brut.

    Returns:
        Bundle binaire ``ACBN``.
    """
    out = bytearray()
    out += BUNDLE_MAGIC
    out += struct.pack(">H", BUNDLE_VERSION)
    out += struct.pack(">I", len(graphs))
    for graph_id, blob in graphs:
        gid = graph_id.encode("utf-8")
        if len(gid) > 65535:
            raise ConceptBundleError("graph_id trop long")
        out += struct.pack(">H", len(gid))
        out += gid
        out += struct.pack(">I", len(blob))
        out += blob
    return bytes(out)


def decode_concept_bundle(data: bytes) -> list[tuple[str, bytes]]:
    """Désérialise un bundle binaire ``ACBN``."""
    if len(data) < BUNDLE_HEADER_SIZE:
        raise ConceptBundleError("bundle trop court")
    if data[:4] != BUNDLE_MAGIC:
        raise ConceptBundleError(f"magic invalide : {data[:4]!r} (attendu {BUNDLE_MAGIC!r})")
    version = struct.unpack(">H", data[4:6])[0]
    if version != BUNDLE_VERSION:
        raise ConceptBundleError(f"version bundle non supportée : {version}")
    count = struct.unpack(">I", data[6:10])[0]
    offset = BUNDLE_HEADER_SIZE
    graphs: list[tuple[str, bytes]] = []
    for _ in range(count):
        if offset + 2 > len(data):
            raise ConceptBundleError("bundle tronqué (graph_id_len)")
        gid_len = struct.unpack(">H", data[offset:offset + 2])[0]
        offset += 2
        if offset + gid_len + 4 > len(data):
            raise ConceptBundleError("bundle tronqué (graph_id)")
        graph_id = data[offset:offset + gid_len].decode("utf-8")
        offset += gid_len
        blob_len = struct.unpack(">I", data[offset:offset + 4])[0]
        offset += 4
        if offset + blob_len > len(data):
            raise ConceptBundleError("bundle tronqué (blob)")
        blob = data[offset:offset + blob_len]
        offset += blob_len
        graphs.append((graph_id, blob))
    return graphs


def bundle_sha256(data: bytes) -> str:
    """Ancre on-chain du bundle : sha256 du binaire transporté."""
    return hashlib.sha256(data).hexdigest()


def export_bundle(store: ConceptStore, concept_ids: list[str]) -> bytes:
    """Construit le bundle binaire qui couvre ``concept_ids``.

    Chaque ConceptID demandé est résolu vers le ou les graphes ``.arcb`` du store
    qui le contiennent. Un graphe n'est jamais dupliqué dans le bundle.
    """
    seen: set[str] = set()
    graphs: list[tuple[str, bytes]] = []
    for graph_id, blob in store.iter_graph_blobs_for(concept_ids):
        if graph_id in seen:
            continue
        seen.add(graph_id)
        graphs.append((graph_id, blob))
    return encode_concept_bundle(graphs)


def import_bundle(store: ConceptStore, data: bytes, *, agent_id: str = "network") -> dict:
    """Ingère un bundle binaire dans un ConceptStore local.

    Returns:
        ``{"graphs": n, "concept_ids": [...], "bundle_sha256": "…"}``
    """
    graphs = decode_concept_bundle(data)
    ingested: list[str] = []
    for graph_id, blob in graphs:
        graph = graph_from_bytes(blob)
        if graph.graph_id != graph_id:
            logger.warning(
                "bundle graph_id=%s ≠ graph.graph_id=%s — on garde celui du graphe",
                graph_id, graph.graph_id,
            )
        ingested.extend(store.store_graph(graph, agent_id=agent_id))
    return {
        "graphs": len(graphs),
        "concept_ids": sorted(set(ingested)),
        "bundle_sha256": bundle_sha256(data),
        "bundle_bytes": len(data),
    }
