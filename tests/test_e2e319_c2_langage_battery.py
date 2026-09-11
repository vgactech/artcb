"""R319/R321 — C2 langage IA battery (local). CERTIFIED_100 remains false.

C2 (lexicon code) ≠ K3e7dc01… (ConceptID) ≠ C2-A…E (test ladder).
R321: FR EN ES PT IT RU LA ZH + automobile synonym closed.
"""

from __future__ import annotations

from pathlib import Path

from artcb.ir.concept import concept_id_from_node, decode_concept_packet
from artcb.ir.concept_lexicon import object_codes
from artcb.ir.encoder import IREncoder
from artcb.memory.agent_channel import AgentChannel
from artcb.memory.concept_store import ConceptStore

VEHICLE_K = "K3e7dc01c5cf83cd8"
L4_K = "Ke410ef3b8d2bddd5"

VEHICLE_WORDS = {
    "fr": "voiture",
    "en": "car",
    "es": "coche",
    "pt": "carro",
    "it": "auto",
    "ru": "автомобиль",
    "la": "vehiculum",
    "zh": "汽车",
}

L4_PHRASES = {
    "fr": "La voiture consomme beaucoup d'énergie.",
    "en": "The car consumes a lot of energy.",
    "es": "El coche consume mucha energía.",
    "pt": "O carro consome muita energia.",
    "it": "L'auto consuma molta energia.",
    "ru": "Автомобиль потребляет много энергии.",
    "la": "Vehiculum multam energiam consumit.",
    "zh": "汽车消耗大量能源。",
}


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


def test_c2_a_eight_lang_vehicle_same_concept_id() -> None:
    ids = {
        lang: concept_id_from_node(IREncoder().encode(word).nodes[0])
        for lang, word in VEHICLE_WORDS.items()
    }
    assert set(ids.values()) == {VEHICLE_K}


def test_c2_a_automobile_synonym_converges_r321() -> None:
    """R321 closed the R319 automobile synonym GAP."""
    ids = [concept_id_from_node(n) for n in IREncoder().encode("automobile").nodes]
    assert VEHICLE_K in ids
    assert "C2" not in object_codes("autonomie")


def test_c2_b_l4_phrases_eight_lang_same_bag() -> None:
    ids_map = {
        lang: [concept_id_from_node(n) for n in IREncoder().encode(p).nodes]
        for lang, p in L4_PHRASES.items()
    }
    for lang, ids in ids_map.items():
        assert L4_K in ids, lang
    assert len({ids[0] for ids in ids_map.values()}) == 1


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


def test_c2_e_cross_lang_agents_same_concept(tmp_path: Path) -> None:
    """C2-E: A(FR) / B(ZH) / C(RU) learn surface forms → same ConceptID."""
    a = AgentChannel(agent_id="a_fr", store=ConceptStore(tmp_path / "a"))
    b = AgentChannel(agent_id="b_zh", store=ConceptStore(tmp_path / "b"))
    c = AgentChannel(agent_id="c_ru", store=ConceptStore(tmp_path / "c"))
    ra = a.learn_from_text("voiture")
    rb = b.learn_from_text("汽车")
    rc = c.learn_from_text("автомобиль")
    assert set(ra.concept_ids) == set(rb.concept_ids) == set(rc.concept_ids) == {VEHICLE_K}
