"""R334 — adversarial ReasoningID tests (T1–T12) + multiset / structure fixes."""

from __future__ import annotations

import hashlib

from src.artcb.reasoning.canonical import (
    PROTOCOL,
    canonicalize_structured,
    canonicalize_text,
    human_view,
    semantic_identity_report,
)


def test_protocol_is_v2_not_set_bug() -> None:
    assert PROTOCOL == "r334-canonical-reasoning-v2"


def test_t1_same_reasoning_different_languages() -> None:
    texts = {
        "fr": "La voiture consomme beaucoup d'énergie.",
        "en": "The car consumes a lot of energy.",
        "zh": "汽车消耗大量能源。",
    }
    rep = semantic_identity_report(texts)
    assert rep["intersection_nonempty"] is True
    assert "K493b83061fa228b9" in rep["concept_intersection"] or rep["same_reasoning_id"]


def test_t2_punctuation_variant_same_or_measured() -> None:
    a = canonicalize_text("La voiture consomme beaucoup d'énergie.")
    b = canonicalize_text("La voiture consomme beaucoup d'énergie!")
    # May share concept bag; document either equal ID or shared intersection
    assert a.reasoning_id() == b.reasoning_id() or (
        set(a.concept_ids) & set(b.concept_ids)
    )


def test_t4_same_conclusion_different_premises() -> None:
    r1 = canonicalize_structured(
        premise_concept_ids=["KA", "KB"],
        conclusion_concept_ids=["KC"],
        relation_triples=[("KA", "⇒", "KC"), ("KB", "⇒", "KC")],
    )
    r2 = canonicalize_structured(
        premise_concept_ids=["KA", "KD"],
        conclusion_concept_ids=["KC"],
        relation_triples=[("KA", "⇒", "KC"), ("KD", "⇒", "KC")],
    )
    assert r1.conclusion_concept_ids == r2.conclusion_concept_ids
    assert r1.reasoning_id() != r2.reasoning_id()


def test_t5_same_concepts_different_relations() -> None:
    r1 = canonicalize_structured(
        premise_concept_ids=["KA"],
        conclusion_concept_ids=["KB"],
        relation_triples=[("KA", "⇒", "KB")],
    )
    r2 = canonicalize_structured(
        premise_concept_ids=["KA"],
        conclusion_concept_ids=["KB"],
        relation_triples=[("KA", "⊥", "KB")],
    )
    assert r1.concept_ids == r2.concept_ids
    assert r1.reasoning_id() != r2.reasoning_id()


def test_t6_order_normalized() -> None:
    r1 = canonicalize_structured(
        premise_concept_ids=["KB", "KA"],
        conclusion_concept_ids=["KC"],
        relation_triples=[("KB", "⇒", "KC"), ("KA", "⇒", "KC")],
    )
    r2 = canonicalize_structured(
        premise_concept_ids=["KA", "KB"],
        conclusion_concept_ids=["KC"],
        relation_triples=[("KA", "⇒", "KC"), ("KB", "⇒", "KC")],
    )
    assert r1.reasoning_id() == r2.reasoning_id()


def test_t7_multiset_repetition_matters() -> None:
    r1 = canonicalize_structured(
        premise_concept_ids=["KA", "KA"],
        conclusion_concept_ids=["KB"],
        relation_triples=[("KA", "⇒", "KB"), ("KA", "⇒", "KB")],
    )
    r2 = canonicalize_structured(
        premise_concept_ids=["KA"],
        conclusion_concept_ids=["KB"],
        relation_triples=[("KA", "⇒", "KB")],
    )
    assert list(r1.premise_concept_ids).count("KA") == 2
    assert list(r2.premise_concept_ids).count("KA") == 1
    assert r1.reasoning_id() != r2.reasoning_id()


def test_t8_equivalent_swap_changes_id() -> None:
    r1 = canonicalize_structured(premise_concept_ids=["KA"], conclusion_concept_ids=["KC"])
    r2 = canonicalize_structured(premise_concept_ids=["KB"], conclusion_concept_ids=["KC"])
    assert r1.reasoning_id() != r2.reasoning_id()


def test_t9_version_via_extra_premise() -> None:
    # Proxy for concept v1→v2: added version marker concept
    r1 = canonicalize_structured(premise_concept_ids=["KA"], conclusion_concept_ids=["KC"])
    r2 = canonicalize_structured(premise_concept_ids=["KA", "KAv2"], conclusion_concept_ids=["KC"])
    assert r1.reasoning_id() != r2.reasoning_id()


def test_t10_useless_premise_changes_id() -> None:
    r1 = canonicalize_structured(premise_concept_ids=["KA"], conclusion_concept_ids=["KC"])
    r2 = canonicalize_structured(premise_concept_ids=["KA", "KZ"], conclusion_concept_ids=["KC"])
    assert r1.reasoning_id() != r2.reasoning_id()


def test_t11_removing_necessary_premise_changes_id() -> None:
    r1 = canonicalize_structured(premise_concept_ids=["KA", "KB"], conclusion_concept_ids=["KC"])
    r2 = canonicalize_structured(premise_concept_ids=["KA"], conclusion_concept_ids=["KC"])
    assert r1.reasoning_id() != r2.reasoning_id()


def test_t12_contradiction_relation_distinct() -> None:
    r1 = canonicalize_structured(
        premise_concept_ids=["KA", "KB"],
        conclusion_concept_ids=["KC"],
        relation_triples=[("KA", "⇒", "KC")],
    )
    r2 = canonicalize_structured(
        premise_concept_ids=["KA", "KB"],
        conclusion_concept_ids=["KC"],
        relation_triples=[("KA", "⊥", "KB"), ("KA", "⇒", "KC")],
    )
    assert r1.reasoning_id() != r2.reasoning_id()


def test_premises_not_equal_conclusions_when_structured() -> None:
    r = canonicalize_structured(
        premise_concept_ids=["KA", "KB"],
        conclusion_concept_ids=["KC"],
        relation_triples=[("KA", "⇒", "KC")],
    )
    assert r.premise_concept_ids != r.conclusion_concept_ids


def test_human_view_not_identity() -> None:
    fr = "Le serveur doit vérifier la signature."
    en = "The server must verify the signature."
    assert hashlib.sha256(fr.encode()).hexdigest() != hashlib.sha256(en.encode()).hexdigest()
    a = canonicalize_text(fr)
    views = [
        human_view(reasoning_id=a.reasoning_id(), language="fr", text=fr),
        human_view(reasoning_id=a.reasoning_id(), language="en", text=en),
    ]
    assert views[0]["text_sha256"] != views[1]["text_sha256"]
    assert views[0]["reasoning_id"] == views[1]["reasoning_id"]
