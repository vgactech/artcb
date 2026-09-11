"""ConceptStore — Mémoire cross-session en binaire natif ARTCB (GO-K / rapport 238).

Rapport 238 §29 — Test de réutilisation :
  "A apprend α17 = Concept X. B apprend le même concept.
   Trois jours plus tard : A → α17. B doit comprendre directement sans demander
   'Que signifie α17 ?'"

Rapport 238 §35 :
  Le stockage DOIT permettre :
  - ConceptID persistant cross-session
  - Récupération par ConceptID uniquement (pas par texte)
  - Format binaire .arcb (jamais JSONL, jamais JSON pour le canal IA)

Architecture :
  data/concepts/
    index.bin        — index binaire compact (ConceptRecord × N)
    {concept_id}.arcb — graphe IR complet en binaire GO-I pour chaque concept
    manifest.bin     — métadonnées du store (version, count, last_updated)

Le canal humain (API REST) peut exposer du JSON — mais le stockage interne
est toujours binaire. Aucun JSONL, aucun texte source dans l'index.
"""

from __future__ import annotations

import hashlib
import logging
import struct
import time
from pathlib import Path
from typing import Any

from src.artcb.ir.binary import graph_from_bytes, graph_to_bytes
from src.artcb.ir.concept import (
    ConceptRecord,
    concept_id_from_node,
    expression_id,
)
from src.artcb.ir.models import IRGraph

logger = logging.getLogger("artcb.memory.concept_store")

# ── Constantes ────────────────────────────────────────────────────────────────

STORE_VERSION: int = 1
MANIFEST_MAGIC = b"ACMS"   # ARTCB Concept Memory Store
MANIFEST_SIZE = 24          # magic(4) + version(2) + count(4) + last_updated(8) + reserved(6)
INDEX_RECORD_SIZE = 128     # taille d'un ConceptRecord binaire


class ConceptStoreError(Exception):
    """Erreur du ConceptStore."""


# ── ConceptStore ──────────────────────────────────────────────────────────────

class ConceptStore:
    """Mémoire sémantique cross-session en binaire ARTCB natif.

    Toutes les écritures/lectures internes passent par le format binaire .arcb.
    Aucun JSON, aucun JSONL, aucun texte source dans les chemins IA-IA.

    Seul to_dict() / from_dict() sur ConceptRecord est fourni pour l'API humaine.
    """

    def __init__(self, data_dir: Path) -> None:
        self._root = Path(data_dir) / "concepts"
        self._root.mkdir(parents=True, exist_ok=True)
        self._index_path = self._root / "index.bin"
        self._manifest_path = self._root / "manifest.bin"
        self._index: dict[str, ConceptRecord] = {}
        self._load_index()

    # ── Persistance manifest ──────────────────────────────────────────────────

    def _write_manifest(self) -> None:
        ts = time.time()
        data = (
            MANIFEST_MAGIC
            + struct.pack(">H", STORE_VERSION)
            + struct.pack(">I", len(self._index))
            + struct.pack(">d", ts)
            + b"\x00" * 6   # reserved
        )
        self._manifest_path.write_bytes(data)

    def _read_manifest(self) -> dict[str, Any] | None:
        if not self._manifest_path.exists():
            return None
        data = self._manifest_path.read_bytes()
        if len(data) < MANIFEST_SIZE or data[:4] != MANIFEST_MAGIC:
            return None
        version = struct.unpack(">H", data[4:6])[0]
        count = struct.unpack(">I", data[6:10])[0]
        last_updated = struct.unpack(">d", data[10:18])[0]
        return {"version": version, "count": count, "last_updated": last_updated}

    # ── Persistance index ─────────────────────────────────────────────────────

    def _load_index(self) -> None:
        """Charge l'index binaire depuis disque."""
        if not self._index_path.exists():
            self._index = {}
            return
        data = self._index_path.read_bytes()
        n = len(data) // INDEX_RECORD_SIZE
        loaded = 0
        for i in range(n):
            chunk = data[i * INDEX_RECORD_SIZE: (i + 1) * INDEX_RECORD_SIZE]
            try:
                record = ConceptRecord.from_binary(chunk)
                self._index[record.concept_id] = record
                loaded += 1
            except Exception as exc:
                logger.warning("Index record %d corrompu : %s", i, exc)
        logger.debug("ConceptStore chargé : %d concepts", loaded)

    def _save_index(self) -> None:
        """Écrit l'index binaire sur disque (append-safe via réécriture complète)."""
        records = sorted(self._index.values(), key=lambda r: r.concept_id)
        data = b"".join(r.to_binary() for r in records)
        self._index_path.write_bytes(data)
        self._write_manifest()
        logger.debug("ConceptStore sauvegardé : %d concepts", len(records))

    # ── Stockage graphe binaire ───────────────────────────────────────────────

    def _graph_path(self, concept_id: str) -> Path:
        """Chemin du fichier .arcb pour un concept."""
        return self._root / f"{concept_id}.arcb"

    def _write_graph(self, concept_id: str, graph: IRGraph) -> str:
        """Écrit un graphe en binaire .arcb. Retourne le hash du contenu."""
        binary = graph_to_bytes(graph)
        path = self._graph_path(concept_id)
        path.write_bytes(binary)
        content_hash = hashlib.sha256(binary).hexdigest()
        logger.debug(
            "Graphe écrit %s → %s (%d bytes, hash=%s…)",
            concept_id, path.name, len(binary), content_hash[:12],
        )
        return content_hash

    def _read_graph(self, concept_id: str) -> IRGraph | None:
        """Lit un graphe depuis le binaire .arcb. Retourne None si absent."""
        path = self._graph_path(concept_id)
        if not path.exists():
            return None
        binary = path.read_bytes()
        return graph_from_bytes(binary)

    # ── API IA-native ─────────────────────────────────────────────────────────

    def store_graph(
        self,
        graph: IRGraph,
        *,
        agent_id: str = "unknown",
    ) -> list[str]:
        """Enregistre tous les concepts d'un graphe IR en binaire.

        Un concept = un nœud IRNode avec son ConceptID.
        Le graphe complet est stocké en .arcb pour chaque ConceptID dominant.

        Args:
            graph: Graphe IR encodé.
            agent_id: Identifiant de l'agent qui soumet ce graphe.

        Returns:
            Liste des ConceptID enregistrés ou mis à jour.
        """
        concept_ids: list[str] = []
        definition_hash = self._write_graph(graph.graph_id, graph)

        for node in graph.nodes:
            cid = concept_id_from_node(node)
            if cid in self._index:
                # Concept déjà connu → incrémenter expression_count
                self._index[cid].expression_count += 1
                logger.debug("Concept %s déjà connu, expressions=%d", cid, self._index[cid].expression_count)
            else:
                # Nouveau concept
                record = ConceptRecord(
                    concept_id=cid,
                    symbol=str(node.sym),
                    node_type=str(node.t),
                    definition_hash=definition_hash,
                    version=1,
                    creator_agent=agent_id,
                )
                self._index[cid] = record
                logger.debug("Nouveau concept : %s sym=%s type=%s", cid, node.sym, node.t)
            concept_ids.append(cid)

        self._save_index()
        return concept_ids

    def recall_by_concept_ids(self, concept_ids: list[str]) -> list[IRGraph]:
        """Récupère les graphes binaires associés à une liste de ConceptID.

        Rapport 238 §29 : "B doit comprendre directement sans demander
        'Que signifie α17 ?'"

        Args:
            concept_ids: Liste de ConceptID à retrouver.

        Returns:
            Liste des IRGraph trouvés (les ConceptID inconnus sont ignorés).
        """
        results: list[IRGraph] = []
        seen_graph_ids: set[str] = set()

        for cid in concept_ids:
            record = self._index.get(cid)
            if record is None:
                logger.debug("ConceptID %s inconnu dans ce store", cid)
                continue

            # Retrouver le graphe par graph_id associé au concept
            # On cherche dans tous les .arcb du store le graphe qui contient ce concept
            for arcb_path in self._root.glob("*.arcb"):
                graph_id = arcb_path.stem
                if graph_id in seen_graph_ids:
                    continue
                try:
                    graph = graph_from_bytes(arcb_path.read_bytes())
                    if any(concept_id_from_node(n) == cid for n in graph.nodes):
                        results.append(graph)
                        seen_graph_ids.add(graph_id)
                        break
                except Exception:
                    continue

        logger.debug(
            "recall_by_concept_ids : demandé=%d trouvé=%d graphes",
            len(concept_ids), len(results),
        )
        return results

    def knows_concept(self, concept_id: str) -> bool:
        """Rapport 238 §29 : 'B connaît-il α17 ?'"""
        return concept_id in self._index

    def get_concept_record(self, concept_id: str) -> ConceptRecord | None:
        """Retourne les métadonnées binaires d'un concept."""
        return self._index.get(concept_id)

    def all_concept_ids(self) -> list[str]:
        """Retourne tous les ConceptID connus (vocabulaire de l'agent)."""
        return list(self._index.keys())

    def concept_count(self) -> int:
        return len(self._index)

    # ── R320 (2026-09-11T21:30:00Z) — transport réseau des blobs .arcb ───────
    # Ajout, rien de supprimé : R319 ne savait pas sortir les octets du store,
    # donc un agent B « froid » ne pouvait jamais résoudre un ConceptID reçu.

    def iter_graph_blobs_for(self, concept_ids: list[str]) -> list[tuple[str, bytes]]:
        """Retourne les blobs binaires ``.arcb`` couvrant ces ConceptID.

        Un blob est renvoyé tel quel (octet pour octet) : c'est ce qui circule
        sur le réseau ARTCB, jamais du texte humain.
        """
        wanted = {cid for cid in concept_ids if cid in self._index}
        out: list[tuple[str, bytes]] = []
        if not wanted:
            return out
        for arcb_path in sorted(self._root.glob("*.arcb")):
            try:
                binary = arcb_path.read_bytes()
                graph = graph_from_bytes(binary)
            except Exception:  # noqa: BLE001 — un blob corrompu ne bloque pas l'export
                continue
            node_cids = {concept_id_from_node(n) for n in graph.nodes}
            if node_cids & wanted:
                out.append((graph.graph_id, binary))
        return out

    def all_graph_blobs(self) -> list[tuple[str, bytes]]:
        """Tous les blobs binaires du store (export complet)."""
        out: list[tuple[str, bytes]] = []
        for arcb_path in sorted(self._root.glob("*.arcb")):
            try:
                out.append((arcb_path.stem, arcb_path.read_bytes()))
            except Exception:  # noqa: BLE001
                continue
        return out

    def ingest_graph_bytes(self, blob: bytes, *, agent_id: str = "network") -> list[str]:
        """Ingère un blob ``.arcb`` reçu du réseau. Retourne les ConceptID appris."""
        graph = graph_from_bytes(blob)
        return self.store_graph(graph, agent_id=agent_id)

    def stats(self) -> dict[str, Any]:
        """Vue humaine uniquement — le stockage interne reste binaire."""
        manifest = self._read_manifest()
        return {
            "concept_count": len(self._index),
            "store_version": STORE_VERSION,
            "store_path": str(self._root),
            "manifest": manifest,
            "top_concepts": [
                r.to_dict()
                for r in sorted(
                    self._index.values(),
                    key=lambda x: x.expression_count,
                    reverse=True,
                )[:10]
            ],
        }
