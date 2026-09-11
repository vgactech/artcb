"""Canal agent-agent natif ARTCB — GO-K / rapport 238 §28.

Test fonctionnel central (rapport 238 §28+§29) :

  Test A→B sans langage humain :
    Étape 1 : Agent A reçoit texte humain → encode → IRGraph
    Étape 2 : A extrait ConceptID → encode_concept_packet (binaire pur)
    Étape 3 : A transmet UNIQUEMENT le paquet binaire à B
    Étape 4 : B décode les ConceptID → recall depuis son ConceptStore
    Étape 5 : B peut raisonner sur les concepts SANS avoir reçu le texte

  Test de réutilisation (§29) :
    A apprend concept X → ConceptID K8291
    B mémorise aussi K8291
    3 sessions plus tard : A envoie juste [K8291]
    B répond avec le graphe complet depuis son store binaire — sans traduction

Ce module implémente le canal de communication.
Le stockage est dans ConceptStore (concept_store.py).
Les ConceptPackets sont définis dans concept.py.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from src.artcb.ir.concept import (
    ConceptRecord,
    concept_id_from_node,
    decode_concept_packet,
    encode_concept_packet,
    expression_id,
)
from src.artcb.ir.encoder import IREncoder
from src.artcb.ir.models import IRGraph
from src.artcb.memory.concept_store import ConceptStore

logger = logging.getLogger("artcb.memory.agent_channel")


# ── Résultats ─────────────────────────────────────────────────────────────────

@dataclass
class LearnResult:
    """Résultat d'un apprentissage : graphe → concepts binaires."""
    graph_id: str
    concept_ids: list[str]
    new_concepts: int
    known_concepts: int
    packet: bytes            # ConceptPacket binaire prêt à transmettre
    agent_id: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        """Vue humaine uniquement."""
        return {
            "graph_id": self.graph_id,
            "concept_ids": self.concept_ids,
            "new_concepts": self.new_concepts,
            "known_concepts": self.known_concepts,
            "packet_size_bytes": len(self.packet),
            "agent_id": self.agent_id,
        }


@dataclass
class RecallResult:
    """Résultat d'un rappel cross-session par ConceptID."""
    requested_concept_ids: list[str]
    found_graphs: list[IRGraph]
    missing_concept_ids: list[str]
    agent_id: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        """Vue humaine uniquement."""
        return {
            "requested": len(self.requested_concept_ids),
            "found_graphs": len(self.found_graphs),
            "missing": self.missing_concept_ids,
            "agent_id": self.agent_id,
        }


# ── AgentChannel ─────────────────────────────────────────────────────────────

class AgentChannel:
    """Canal de communication sémantique agent-agent.

    Rapport 238 §21 :
    "Homme → interface → AGENT → LANGAGE IA NATIF ARTCB → AGENT → interface → Homme"

    Le langage humain est l'interface, pas le format interne.

    Usage typique :
        channel_a = AgentChannel(agent_id="node_a", store=store_a)
        channel_b = AgentChannel(agent_id="node_b", store=store_b)

        # Agent A apprend depuis du texte (interface humaine → une seule fois)
        result = channel_a.learn_from_text("Le nœud vérifie la signature.")

        # A transmet UNIQUEMENT le paquet binaire à B
        packet = result.packet  # bytes — pas de texte

        # Agent B décode et retrouve les concepts depuis son store
        recall = channel_b.receive_packet(packet)

        # B peut raisonner directement sur les graphes
        for graph in recall.found_graphs:
            # graphe complet disponible en binaire — aucune conversion
            ...
    """

    def __init__(
        self,
        *,
        agent_id: str,
        store: ConceptStore,
        encoder: IREncoder | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.store = store
        self._encoder = encoder or IREncoder()
        # R320 — nombre de graphes récupérés du réseau au dernier receive_packet
        self.last_resolved_from_network = 0

    def learn_from_text(self, text: str) -> LearnResult:
        """Point d'entrée humain → binaire ARTCB.

        Le texte humain entre UNE SEULE FOIS ici.
        Tout ce qui sort est en ConceptID + binaire.

        Args:
            text: Texte humain (FR/EN/autre — indifférent).

        Returns:
            LearnResult avec ConceptID + paquet binaire transmissible.
        """
        graph = self._encoder.encode(text)

        # Compter les concepts nouveaux vs connus avant le stockage
        known_before = sum(
            1 for node in graph.nodes
            if self.store.knows_concept(concept_id_from_node(node))
        )

        concept_ids = self.store.store_graph(graph, agent_id=self.agent_id)

        new_count = len(concept_ids) - known_before
        packet = encode_concept_packet(concept_ids)

        logger.info(
            "Agent %s : appris %d concepts (%d nouveaux) depuis texte len=%d",
            self.agent_id, len(concept_ids), new_count, len(text),
        )
        return LearnResult(
            graph_id=graph.graph_id,
            concept_ids=concept_ids,
            new_concepts=new_count,
            known_concepts=known_before,
            packet=packet,
            agent_id=self.agent_id,
        )

    def export_bundle(self, concept_ids: list[str]) -> bytes:
        """R320 — bundle binaire ``ACBN`` transportant les graphes ``.arcb``.

        Le ConceptPacket (``ACPT``) ne transporte que des identifiants ; ce bundle
        transporte la définition binaire elle-même, donc un agent froid peut
        comprendre sans jamais recevoir de texte humain.
        """
        from src.artcb.memory.concept_sync import export_bundle

        return export_bundle(self.store, concept_ids)

    def ingest_bundle(self, data: bytes) -> dict:
        """R320 — ingère un bundle ``ACBN`` reçu du réseau dans le store local."""
        from src.artcb.memory.concept_sync import import_bundle

        return import_bundle(self.store, data, agent_id=self.agent_id)

    def receive_packet(self, packet: bytes, resolver: Any = None) -> RecallResult:
        """Réception d'un ConceptPacket depuis un autre agent.

        Rapport 238 §29 : "B doit comprendre directement sans demander
        'Que signifie α17 ?'"

        B cherche les ConceptID dans son store binaire.
        Si un concept est inconnu → il est listé dans missing_concept_ids.

        Args:
            packet: Bytes reçus (ConceptPacket binaire).

        Returns:
            RecallResult avec les graphes trouvés en binaire.
        """
        concept_ids = decode_concept_packet(packet)
        graphs = self.store.recall_by_concept_ids(concept_ids)
        found_ids = set()
        for graph in graphs:
            for node in graph.nodes:
                found_ids.add(concept_id_from_node(node))
        missing = [cid for cid in concept_ids if cid not in found_ids]

        # R320 (2026-09-11T21:30:00Z) — résolution réseau des concepts manquants.
        # `resolver(missing) -> bytes | None` va chercher le bundle .arcb sur ARTCB.
        # Sans ce maillon, C2-D « cold B » était structurellement impossible.
        resolved_from_network = 0
        if missing and resolver is not None:
            try:
                bundle = resolver(list(missing))
            except Exception as exc:  # noqa: BLE001 — un réseau indisponible n'est pas un crash
                logger.warning("resolver réseau en échec : %s", type(exc).__name__)
                bundle = None
            if bundle:
                report = self.ingest_bundle(bundle)
                resolved_from_network = int(report.get("graphs", 0))
                graphs = self.store.recall_by_concept_ids(concept_ids)
                found_ids = set()
                for graph in graphs:
                    for node in graph.nodes:
                        found_ids.add(concept_id_from_node(node))
                missing = [cid for cid in concept_ids if cid not in found_ids]
        self.last_resolved_from_network = resolved_from_network

        logger.info(
            "Agent %s : reçu paquet %d concepts → %d graphes trouvés, %d manquants",
            self.agent_id, len(concept_ids), len(graphs), len(missing),
        )
        return RecallResult(
            requested_concept_ids=concept_ids,
            found_graphs=graphs,
            missing_concept_ids=missing,
            agent_id=self.agent_id,
        )

    def send_packet(self, concept_ids: list[str]) -> bytes:
        """Encode une liste de ConceptID en paquet binaire pour transmission.

        Args:
            concept_ids: ConceptID à envoyer.

        Returns:
            Bytes prêts à transmettre (aucun texte inclus).
        """
        return encode_concept_packet(concept_ids)

    def knows(self, concept_id: str) -> bool:
        """Rapport 238 §29 : l'agent connaît-il ce concept ?"""
        return self.store.knows_concept(concept_id)

    def vocabulary_size(self) -> int:
        """Nombre de concepts que cet agent a mémorisés."""
        return self.store.concept_count()
