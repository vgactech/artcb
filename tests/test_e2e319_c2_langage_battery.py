"""R319 — C2 langage IA battery (local). CERTIFIED_100 remains false.

C2 (lexicon code) ≠ K3e7dc01… (ConceptID) ≠ C2-A…D (test ladder).
"""

from __future__ import annotations

from pathlib import Path

from artcb.ir.concept import concept_id_from_node, decode_concept_packet
from artcb.ir.concept_lexicon import object_codes
from artcb.ir.encoder import IREncoder
from artcb.memory.agent_channel import AgentChannel
from artcb.memory.concept_store import ConceptStore

VEHICLE_K = "K3e7dc01c5cf83cd8"


def test_c2_namespace_lexicon_code_vs_concept_id() -> None:
    assert object_codes("voiture") == ["C2"]
    g = IREncoder().encode("voiture")
    assert [concept_id_from_node(n) for n in g.nodes] == [VEHICLE_K]
    assert "C2" != VEHICLE_K


def test_c2_a_lexical_and_adversarial() -> None:
    ids = {w: concept_id_from_node(IREncoder().encode(w).nodes[0]) for w in ("voiture", "car", "coche")}
    assert len(set(ids.values())) == 1
    assert ids["voiture"] == VEHICLE_K
    assert VEHICLE_K not in [concept_id_from_node(n) for n in IREncoder().encode("avion").nodes]
    assert VEHICLE_K not in [concept_id_from_node(n) for n in IREncoder().encode("verificar").nodes]


def test_c2_a_automobile_synonym_gap_honest() -> None:
    """Synonym not in lexicon must not pretend to be vehicle ConceptID."""
    ids = [concept_id_from_node(n) for n in IREncoder().encode("automobile").nodes]
    assert VEHICLE_K not in ids


def test_c2_b_phrases_contain_vehicle_concept() -> None:
    phrases = (
        "La voiture consomme beaucoup.",
        "The car consumes a lot.",
        "El coche consume mucho.",
    )
    for p in phrases:
        ids = [concept_id_from_node(n) for n in IREncoder().encode(p).nodes]
        assert VEHICLE_K in ids, p


def test_c2_c_packet_reasoning_no_human_text(tmp_path: Path) -> None:
    ch = AgentChannel(agent_id="r", store=ConceptStore(tmp_path / "s"))
    r = ch.learn_from_text("Si la charge augmente, la consommation augmente.")
    assert b"charge" not in r.packet
    assert decode_concept_packet(r.packet) == r.concept_ids
    graphs = ch.store.recall_by_concept_ids(r.concept_ids)
    assert graphs


def test_c2_d_cold_b_missing_without_sync(tmp_path: Path) -> None:
    """Honest: packet alone does not inject A's .arcb into B."""
    a = AgentChannel(agent_id="a", store=ConceptStore(tmp_path / "a"))
    b = AgentChannel(agent_id="b", store=ConceptStore(tmp_path / "b"))
    learn = a.learn_from_text("Optimiser capacite sous charge IA.")
    cold = b.receive_packet(learn.packet)
    assert cold.missing_concept_ids or not cold.found_graphs


def test_c2_d_warm_prior_allows_recall(tmp_path: Path) -> None:
    text = "Optimiser capacite sous charge IA."
    a = AgentChannel(agent_id="a", store=ConceptStore(tmp_path / "a"))
    b = AgentChannel(agent_id="b", store=ConceptStore(tmp_path / "b"))
    learn = a.learn_from_text(text)
    b.learn_from_text(text)
    warm = b.receive_packet(learn.packet)
    assert warm.requested_concept_ids == learn.concept_ids
    assert not warm.missing_concept_ids
