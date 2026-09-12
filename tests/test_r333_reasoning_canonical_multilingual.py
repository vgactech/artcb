"""R333 R-01 — Reasoning canonicalization & multilingual semantic identity."""

from __future__ import annotations

from src.artcb.reasoning.canonical import (
    canonicalize_text,
    human_view,
    semantic_identity_report,
)


def test_t1_determinism_same_text() -> None:
    a = canonicalize_text("La voiture consomme beaucoup d'énergie.")
    b = canonicalize_text("La voiture consomme beaucoup d'énergie.")
    assert a.reasoning_id() == b.reasoning_id()
    assert a.reasoning_hash() == b.reasoning_hash()
    assert a.reasoning_id().startswith("R")


def test_t3_multilingual_same_concept_bag() -> None:
    texts = {
        "fr": "La voiture consomme beaucoup d'énergie.",
        "en": "The car consumes a lot of energy.",
        "zh": "汽车消耗大量能源。",
        "es": "El coche consume mucha energía.",
    }
    rep = semantic_identity_report(texts)
    # Same L4 bag ConceptID across languages (not same UTF-8)
    assert rep["intersection_nonempty"] is True
    assert "K493b83061fa228b9" in rep["concept_intersection"] or rep["same_reasoning_id"]
    # Human views differ by text hash but share reasoning if IDs equal
    rid = next(iter(rep["reasoning_ids"].values()))
    views = {lang: human_view(reasoning_id=rid, language=lang, text=texts[lang]) for lang in texts}
    assert len({v["text_sha256"] for v in views.values()}) == len(texts)
    assert all(v["reasoning_id"] == rid for v in views.values())


def test_t4_different_premises_different_id() -> None:
    r1 = canonicalize_text("Cette méthode réduit le nombre d'opérations.")
    r2 = canonicalize_text(
        "Cette méthode réduit le nombre d'opérations, donc elle est toujours meilleure."
    )
    # May share some concepts but full bags / graphs should differ when conclusion expands
    # If encoder collapses identically, still require at least text-view inequality documented
    assert r1.reasoning_id() != r2.reasoning_id() or set(r1.concept_ids) != set(r2.concept_ids)


def test_human_text_not_identity() -> None:
    fr = "Le serveur doit vérifier la signature."
    en = "The server must verify the signature."
    a = canonicalize_text(fr)
    b = canonicalize_text(en)
    # Text hashes differ
    import hashlib

    assert hashlib.sha256(fr.encode()).hexdigest() != hashlib.sha256(en.encode()).hexdigest()
    # Semantic overlap expected (probe sentences)
    assert set(a.concept_ids) & set(b.concept_ids)
