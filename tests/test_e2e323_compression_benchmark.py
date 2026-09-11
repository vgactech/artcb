"""R323 — compression metric helpers smoke (no live network required for encode)."""

from __future__ import annotations

from pathlib import Path

from artcb.memory.agent_channel import AgentChannel
from artcb.memory.concept_store import ConceptStore


def test_short_phrase_packet_may_expand(tmp_path: Path) -> None:
    text = "La voiture consomme beaucoup d'énergie."
    ch = AgentChannel(agent_id="t", store=ConceptStore(tmp_path / "s"))
    r = ch.learn_from_text(text)
    # Document honesty: packet can be larger than short UTF-8
    assert len(r.packet) > 0
    assert len(r.concept_ids) >= 1


def test_eight_lang_unique_packet_beats_sum_utf8(tmp_path: Path) -> None:
    from artcb.ir.concept import encode_concept_packet

    corpus = {
        "fr": "La voiture consomme beaucoup d'énergie.",
        "en": "The car consumes a lot of energy.",
        "es": "El coche consume mucha energía.",
        "pt": "O carro consome muita energia.",
        "it": "L'auto consuma molta energia.",
        "ru": "Автомобиль потребляет много энергии.",
        "la": "Vehiculum multam energiam consumit.",
        "zh": "汽车消耗大量能源。",
    }
    ch = AgentChannel(agent_id="t", store=ConceptStore(tmp_path / "s"))
    ids: list[str] = []
    sum_utf8 = 0
    for t in corpus.values():
        sum_utf8 += len(t.encode())
        ids.extend(ch.learn_from_text(t).concept_ids)
    uniq = list(dict.fromkeys(ids))
    packet = encode_concept_packet(uniq)
    assert len(packet) < sum_utf8
    reduction = 100.0 * (1.0 - len(packet) / sum_utf8)
    assert reduction > 50.0
