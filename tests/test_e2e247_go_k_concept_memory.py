"""Tests GO-K — ConceptID natif + mémoire binaire cross-session agent-agent.

Ces tests implémentent directement les 4 tests du rapport 238 :

  §28 — Test A→B sans langage humain
  §29 — Test de réutilisation cross-session
  §30 — Test de traduction interlangue (même concept FR/EN/ES → même ConceptID)
  §31 — Test raisonnement sans texte (graphe → ConceptID → raisonnement)

Plus :
  - ConceptID dérivé des symboles ARTCB (pas du texte) — §12 rapport 238
  - ExpressionID différent du ConceptID — §13
  - Stockage binaire .arcb exclusif — aucun JSONL, aucun JSON interne
  - Paquet agent-agent en binaire pur (encode_concept_packet / decode_concept_packet)
  - ConceptStore : persistance cross-session réelle (tmpdir simulant 2 sessions)
"""

from __future__ import annotations

import struct
import time
from pathlib import Path

import pytest

from artcb.ir.concept import (
    CONCEPT_PACKET_MAGIC,
    ConceptRecord,
    concept_id_from_node,
    decode_concept_packet,
    encode_concept_packet,
    expression_id,
)
from artcb.ir.encoder import IREncoder
from artcb.ir.models import IRNode
from artcb.memory.agent_channel import AgentChannel
from artcb.memory.concept_store import ConceptStore


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_store(tmp_path: Path, subdir: str = "store") -> ConceptStore:
    return ConceptStore(tmp_path / subdir)


def _make_channel(tmp_path: Path, agent_id: str, subdir: str | None = None) -> AgentChannel:
    store = _make_store(tmp_path, subdir or agent_id)
    return AgentChannel(agent_id=agent_id, store=store)


def _make_node(node_type: str = "F", sym: str = "D1", node_id: str = "n1") -> IRNode:
    return IRNode(
        id=node_id, t=node_type, sym=sym,
        txt="test concept", checksum="sha256:abc",
    )


# ── ConceptID — dérivé des symboles, pas du texte ─────────────────────────────

def test_concept_id_from_node_stable() -> None:
    """Le même nœud (même type + même symbole) produit toujours le même ConceptID."""
    node = _make_node("D", "D1", "n1")
    cid1 = concept_id_from_node(node)
    cid2 = concept_id_from_node(node)
    assert cid1 == cid2
    assert cid1.startswith("K")


def test_concept_id_not_text_hash() -> None:
    """Rapport 238 §12 : même symbole, texte différent → MÊME ConceptID."""
    n1 = IRNode(id="n1", t="F", sym="D1", txt="Le serveur vérifie la signature.", checksum="sha256:x")
    n2 = IRNode(id="n2", t="F", sym="D1", txt="The node must authenticate the block.", checksum="sha256:y")
    # Même type + même symbole = même concept sémantique
    assert concept_id_from_node(n1) == concept_id_from_node(n2)


def test_concept_id_different_symbol_differs() -> None:
    """Symboles différents → ConceptID différents."""
    n1 = _make_node("F", "D1")
    n2 = _make_node("F", "O1")
    assert concept_id_from_node(n1) != concept_id_from_node(n2)


def test_expression_id_different_from_concept_id() -> None:
    """Rapport 238 §13 : ExpressionID ≠ ConceptID."""
    node = _make_node("D", "D1")
    cid = concept_id_from_node(node)
    eid = expression_id("agent_a", node.id)
    assert cid != eid
    assert eid.startswith("E")
    assert cid.startswith("K")


def test_expression_id_differs_per_agent() -> None:
    """Deux agents ont des ExpressionID différents pour le même concept."""
    node = _make_node("D", "D1")
    eid_a = expression_id("agent_a", node.id, timestamp=1000.0)
    eid_b = expression_id("agent_b", node.id, timestamp=1000.0)
    assert eid_a != eid_b


# ── ConceptRecord binaire ─────────────────────────────────────────────────────

def test_concept_record_binary_roundtrip() -> None:
    """ConceptRecord sérialisé/désérialisé en binaire sans perte."""
    rec = ConceptRecord(
        concept_id="Kabc123def456789",
        symbol="α17",
        node_type="F",
        definition_hash="deadbeef" * 4,
        version=2,
        creator_agent="artcb1nodeXXX",
        expression_count=5,
    )
    binary = rec.to_binary()
    assert len(binary) == 128  # taille fixe
    recovered = ConceptRecord.from_binary(binary)
    assert recovered.concept_id == rec.concept_id
    assert recovered.symbol == rec.symbol
    assert recovered.node_type == rec.node_type
    assert recovered.version == rec.version
    assert recovered.expression_count == rec.expression_count


def test_concept_record_too_short_raises() -> None:
    with pytest.raises(ValueError, match="trop court"):
        ConceptRecord.from_binary(b"\x00" * 64)


# ── ConceptPacket — canal binaire agent-agent ─────────────────────────────────

def test_concept_packet_roundtrip() -> None:
    """Rapport 238 §23 : encode → decode → même ConceptID."""
    cids = ["Kabc1234567890ab", "Kdef1234567890cd", "K0001234567890ef"]
    packet = encode_concept_packet(cids)
    decoded = decode_concept_packet(packet)
    assert decoded == cids


def test_concept_packet_magic_present() -> None:
    """Le magic ACPT est en tête du paquet."""
    packet = encode_concept_packet(["Kabc1234567890ab"])
    assert packet[:4] == CONCEPT_PACKET_MAGIC


def test_concept_packet_bad_magic_raises() -> None:
    packet = encode_concept_packet(["Kabc1234567890ab"])
    bad = b"XXXX" + packet[4:]
    with pytest.raises(ValueError, match="Magic"):
        decode_concept_packet(bad)


def test_concept_packet_bad_version_raises() -> None:
    packet = bytearray(encode_concept_packet(["Kabc1234567890ab"]))
    packet[4] = 99
    with pytest.raises(ValueError, match="Version"):
        decode_concept_packet(bytes(packet))


def test_concept_packet_empty_list() -> None:
    packet = encode_concept_packet([])
    decoded = decode_concept_packet(packet)
    assert decoded == []


# ── ConceptStore — stockage binaire ──────────────────────────────────────────

def test_store_graph_creates_arcb_files(tmp_path: Path) -> None:
    """Rapport 238 : le stockage crée des fichiers .arcb, pas des .json ou .jsonl."""
    store = _make_store(tmp_path)
    encoder = IREncoder()
    graph = encoder.encode("Le nœud B doit vérifier la signature avant d'accepter.")
    store.store_graph(graph, agent_id="agent_test")

    arcb_files = list((tmp_path / "store" / "concepts").glob("*.arcb"))
    json_files  = list((tmp_path / "store" / "concepts").glob("*.json*"))
    assert len(arcb_files) >= 1, "Au moins un fichier .arcb doit être créé"
    assert len(json_files) == 0, "Aucun fichier JSON ne doit être créé"


def test_store_knows_concept_after_store(tmp_path: Path) -> None:
    """Rapport 238 §29 : après store_graph, knows_concept retourne True."""
    store = _make_store(tmp_path)
    encoder = IREncoder()
    graph = encoder.encode("Le protocole valide la preuve.")
    concept_ids = store.store_graph(graph, agent_id="agent_test")
    assert len(concept_ids) > 0
    for cid in concept_ids:
        assert store.knows_concept(cid), f"ConceptID {cid} devrait être connu"


def test_store_unknown_concept(tmp_path: Path) -> None:
    """Un ConceptID jamais vu → knows_concept retourne False."""
    store = _make_store(tmp_path)
    assert store.knows_concept("Kunknown_concept_id") is False


def test_store_expression_count_increments(tmp_path: Path) -> None:
    """Même concept soumis deux fois → expression_count augmente."""
    store = _make_store(tmp_path)
    encoder = IREncoder()
    text = "La blockchain mémorise les connaissances."
    graph1 = encoder.encode(text + " Version 1.")
    graph2 = encoder.encode(text + " Version 2.")

    ids1 = store.store_graph(graph1, agent_id="agent_a")
    ids2 = store.store_graph(graph2, agent_id="agent_b")

    common = set(ids1) & set(ids2)
    for cid in common:
        rec = store.get_concept_record(cid)
        assert rec is not None
        assert rec.expression_count >= 2


def test_store_index_persistent_across_instances(tmp_path: Path) -> None:
    """Rapport 238 §29 — cross-session : l'index persiste entre deux instances."""
    store1 = ConceptStore(tmp_path / "concepts_data")
    encoder = IREncoder()
    graph = encoder.encode("La signature PQC est vérifiée.")
    ids = store1.store_graph(graph, agent_id="session_1")
    del store1  # Simule la fin de session

    # Nouvelle instance — nouvelle "session"
    store2 = ConceptStore(tmp_path / "concepts_data")
    for cid in ids:
        assert store2.knows_concept(cid), f"Session 2 devrait connaître {cid}"


# ── §28 — Test A→B sans langage humain ───────────────────────────────────────

def test_agent_a_to_b_without_text(tmp_path: Path) -> None:
    """Rapport 238 §28 : Agent A encode du texte → envoie ConceptPacket binaire → B décode.

    B ne reçoit JAMAIS le texte source.
    B retrouve les graphes depuis son store binaire.
    """
    channel_a = _make_channel(tmp_path, "agent_a")
    channel_b = _make_channel(tmp_path, "agent_b")

    # Étape 1 : A et B apprennent le même concept (dans leurs stores séparés)
    text = "Le nœud vérifie la signature avant acceptation."
    channel_a.learn_from_text(text)
    channel_b.learn_from_text(text)  # B connaît déjà ce concept

    # Étape 2 : A encode une nouvelle pensée
    result_a = channel_a.learn_from_text("La preuve de connaissance est validée.")

    # Étape 3 : A envoie UNIQUEMENT le paquet binaire (pas de texte)
    packet = result_a.packet
    assert isinstance(packet, bytes)
    assert b"La preuve" not in packet  # Aucun texte dans le paquet

    # Étape 4 : B reçoit le paquet et retrouve les concepts
    recall_b = channel_b.receive_packet(packet)

    # Étape 5 : B a retrouvé les graphes en binaire
    assert recall_b.requested_concept_ids == result_a.concept_ids


def test_packet_contains_no_human_text(tmp_path: Path) -> None:
    """Le paquet ConceptPacket ne contient aucun texte lisible par un humain."""
    channel = _make_channel(tmp_path, "agent_test")
    result = channel.learn_from_text("Bonjour comment vas-tu en Python ?")
    packet = result.packet
    # Aucun mot français ne doit apparaître en clair dans le paquet
    assert b"Bonjour" not in packet
    assert b"comment" not in packet
    assert b"Python" not in packet


# ── §29 — Test de réutilisation cross-session ──────────────────────────────────

def test_reuse_cross_session_no_redefinition(tmp_path: Path) -> None:
    """Rapport 238 §29 : A apprend α17, B apprend α17. Plus tard : A→[K…]→B sans retransmettre la définition."""
    data_dir = tmp_path / "shared_store"

    # Session 1 : A et B apprennent le même texte
    store_a1 = ConceptStore(data_dir / "a")
    store_b1 = ConceptStore(data_dir / "b")
    encoder = IREncoder()

    text = "Le consensus BFT nécessite 2/3 validateurs."
    graph = encoder.encode(text)
    ids_a = store_a1.store_graph(graph, agent_id="session1_a")
    ids_b = store_b1.store_graph(graph, agent_id="session1_b")
    del store_a1, store_b1  # Fin de session 1

    # Session 2 (plus tard) : A envoie juste les ConceptID
    store_a2 = ConceptStore(data_dir / "a")
    store_b2 = ConceptStore(data_dir / "b")

    packet = encode_concept_packet(ids_a)
    decoded = decode_concept_packet(packet)

    # B retrouve les concepts sans redemander la définition
    for cid in decoded:
        assert store_b2.knows_concept(cid), (
            f"B devrait connaître {cid} depuis la session 1"
        )


# ── §30 — Test traduction interlangue ─────────────────────────────────────────

def test_same_concept_different_languages_same_concept_id() -> None:
    """Rapport 238 §30 : FR/EN/ES sur le même concept sémantique → même symbole → même ConceptID."""
    # Les trois phrases expriment le même concept : "VÉRIFICATION SIGNATURE"
    # Si l'IR leur assigne le même type + même symbole → même ConceptID
    n_fr = IRNode(id="n1", t="D", sym="V1", txt="Le serveur vérifie la signature.", checksum="sha256:fr")
    n_en = IRNode(id="n2", t="D", sym="V1", txt="The server verifies the signature.", checksum="sha256:en")
    n_es = IRNode(id="n3", t="D", sym="V1", txt="El servidor verifica la firma.", checksum="sha256:es")

    cid_fr = concept_id_from_node(n_fr)
    cid_en = concept_id_from_node(n_en)
    cid_es = concept_id_from_node(n_es)

    # Même type (D) + même symbole (V1) → même ConceptID (indépendant de la langue)
    assert cid_fr == cid_en == cid_es, (
        "Rapport 238 §30 : même concept sémantique → même ConceptID quelle que soit la langue"
    )


# ── §31 — Raisonnement sans texte ────────────────────────────────────────────

def test_reasoning_via_concept_ids_only(tmp_path: Path) -> None:
    """Rapport 238 §31 : K1 + K2 ⇒ K3 — raisonnement sur ConceptID sans texte."""
    store = _make_store(tmp_path)
    encoder = IREncoder()

    # Apprendre 3 concepts distincts
    g1 = encoder.encode("La blockchain ARTCB est sécurisée par PoL.")
    g2 = encoder.encode("Le PoL valide la connaissance.")
    g3 = encoder.encode("La connaissance validée est récompensée.")

    ids1 = store.store_graph(g1, agent_id="agent")
    ids2 = store.store_graph(g2, agent_id="agent")
    ids3 = store.store_graph(g3, agent_id="agent")

    all_ids = ids1 + ids2 + ids3

    # Raisonnement : chercher si on connaît tous les concepts nécessaires au raisonnement
    # sans accéder au texte source
    known = [cid for cid in all_ids if store.knows_concept(cid)]
    assert len(known) == len(all_ids), "Tous les concepts du raisonnement doivent être connus"

    # Rappel des graphes par ConceptID uniquement — aucun texte transmis
    graphs = store.recall_by_concept_ids(all_ids)
    assert len(graphs) > 0

    # Vérification : les graphes retrouvés ne nécessitent PAS de re-consultation du texte
    # → les ConceptID suffisent pour identifier les blocs de connaissance
    for graph in graphs:
        for node in graph.nodes:
            assert concept_id_from_node(node) in all_ids


# ── Vocabulaire + stats ───────────────────────────────────────────────────────

def test_vocabulary_size_grows(tmp_path: Path) -> None:
    """Le vocabulaire de l'agent grandit à chaque apprentissage."""
    channel = _make_channel(tmp_path, "agent_vocab")
    assert channel.vocabulary_size() == 0
    channel.learn_from_text("Premier concept.")
    assert channel.vocabulary_size() > 0
    size1 = channel.vocabulary_size()
    channel.learn_from_text("Deuxième concept totalement différent.")
    assert channel.vocabulary_size() >= size1


def test_stats_returns_human_view(tmp_path: Path) -> None:
    """stats() retourne un dict lisible pour l'API humaine."""
    store = _make_store(tmp_path)
    encoder = IREncoder()
    store.store_graph(encoder.encode("Test stats."), agent_id="agent")
    s = store.stats()
    assert "concept_count" in s
    assert "store_version" in s
    assert s["concept_count"] > 0
