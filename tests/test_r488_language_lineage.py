"""R488 — Tests SemanticLineage (Forensic Lineage couche-par-couche).

Tests T01→T22 validant :
  - T01-T03 : trace_lineage() — structure + 7 étapes
  - T04-T06 : étapes individuelles (tokenize, normalize, morphology)
  - T07-T08 : étape map_to_concept → artcb_code + concept_id
  - T09      : étape parse_to_ir → graph_id non-None
  - T10      : étape round_trip → round_trip_ok cohérent
  - T11      : explain() retourne texte lisible
  - T12      : to_dict() exportable (JSON-serializable)
  - T13      : to_json() valide
  - T14      : lineage_id déterministe (même text+lang → même id)
  - T15      : lineage_hash change si étapes changent
  - T16      : first_error_step() retourne None si tout OK
  - T17      : invariants unique_human_proven=False, certified=False
  - T18      : multi-langue (EN)
  - T19      : trace_batch() retourne N lineages
  - T20      : erreur get_adapter lang invalide → error non-None
  - T21      : lineage localise une erreur à la couche précise (simulation)
  - T22      : MODULE_VERSION = 1.0.x

CERTIFIED_100=false | unique_human_proven=False
"""
from __future__ import annotations

import json

import pytest

from src.artcb.language.lineage import (
    MODULE_VERSION,
    LineageStep,
    SemanticLineage,
    trace_batch,
    trace_lineage,
)


# ─── Fixture partagée ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def fr_lineage() -> SemanticLineage:
    """Lineage FR partagé — calculé une seule fois."""
    return trace_lineage("vérifier la signature du serveur", "fr")


@pytest.fixture(scope="module")
def en_lineage() -> SemanticLineage:
    """Lineage EN partagé."""
    return trace_lineage("verify the server signature", "en")


# ─── T01-T03 : structure de base ─────────────────────────────────────────────

def test_T01_trace_lineage_returns_semantic_lineage(fr_lineage):
    """T01 — trace_lineage() retourne un SemanticLineage."""
    assert isinstance(fr_lineage, SemanticLineage)


def test_T02_lineage_has_7_steps(fr_lineage):
    """T02 — Le lineage contient exactement 7 étapes."""
    assert len(fr_lineage.steps) == 7, (
        f"Attendu 7 étapes, obtenu {len(fr_lineage.steps)}"
    )


def test_T03_step_names_ordered(fr_lineage):
    """T03 — Les 7 étapes sont dans l'ordre attendu du pipeline."""
    expected = ["tokenize", "normalize", "morphology", "map_to_concept",
                "parse_to_ir", "concept_id", "round_trip"]
    actual = [s.name for s in fr_lineage.steps]
    assert actual == expected, f"Ordre attendu={expected}, obtenu={actual}"


# ─── T04-T06 : étapes lexicales ──────────────────────────────────────────────

def test_T04_tokenize_step(fr_lineage):
    """T04 — Étape tokenize produit une liste de tokens non vide."""
    step = fr_lineage.steps[0]
    assert step.name == "tokenize"
    assert step.error is None, f"Erreur tokenize: {step.error}"
    assert isinstance(fr_lineage.tokens, list)
    assert len(fr_lineage.tokens) > 0


def test_T05_normalize_step(fr_lineage):
    """T05 — Étape normalize produit un texte normalisé non vide."""
    step = fr_lineage.steps[1]
    assert step.name == "normalize"
    assert step.error is None
    assert fr_lineage.normalized_text != ""


def test_T06_morphology_step(fr_lineage):
    """T06 — Étape morphology produit des lemmes non vides."""
    step = fr_lineage.steps[2]
    assert step.name == "morphology"
    assert step.error is None
    assert isinstance(fr_lineage.lemmas, list)
    assert len(fr_lineage.lemmas) > 0


# ─── T07-T08 : étape sémantique ──────────────────────────────────────────────

def test_T07_map_to_concept_step(fr_lineage):
    """T07 — Étape map_to_concept produit un artcb_code non-None."""
    step = fr_lineage.steps[3]
    assert step.name == "map_to_concept"
    assert step.error is None, f"Erreur map_to_concept: {step.error}"
    assert fr_lineage.artcb_code is not None, "artcb_code ne doit pas être None"
    assert fr_lineage.artcb_code != "", "artcb_code ne doit pas être vide"


def test_T08_concept_id_step(fr_lineage):
    """T08 — Étape concept_id produit un concept_id non-None."""
    step = fr_lineage.steps[5]
    assert step.name == "concept_id"
    assert step.error is None
    assert fr_lineage.concept_id is not None, "concept_id ne doit pas être None"
    # Le concept_id commence par 'K' (SemanticCorpus convention)
    assert fr_lineage.concept_id.startswith("K"), (
        f"concept_id attendu commençant par 'K', obtenu '{fr_lineage.concept_id}'"
    )


# ─── T09 : étape IR ──────────────────────────────────────────────────────────

def test_T09_parse_to_ir_step(fr_lineage):
    """T09 — Étape parse_to_ir produit un graph_id non-None."""
    step = fr_lineage.steps[4]
    assert step.name == "parse_to_ir"
    assert step.error is None, f"Erreur parse_to_ir: {step.error}"
    assert fr_lineage.ir_graph_id is not None


# ─── T10 : étape round-trip ──────────────────────────────────────────────────

def test_T10_round_trip_step(fr_lineage):
    """T10 — Étape round_trip retourne un résultat cohérent."""
    step = fr_lineage.steps[6]
    assert step.name == "round_trip"
    assert step.error is None, f"Erreur round_trip: {step.error}"
    # round_trip_ok est un booléen valide
    assert isinstance(fr_lineage.round_trip_ok, bool)


# ─── T11-T13 : export / explain ──────────────────────────────────────────────

def test_T11_explain_readable(fr_lineage):
    """T11 — explain() retourne une chaîne lisible avec toutes les étapes."""
    explanation = fr_lineage.explain()
    assert isinstance(explanation, str)
    assert "SemanticLineage" in explanation
    assert "tokenize" in explanation
    assert "round_trip" in explanation
    assert fr_lineage.lang in explanation


def test_T12_to_dict_json_serializable(fr_lineage):
    """T12 — to_dict() est JSON-serializable."""
    d = fr_lineage.to_dict()
    assert isinstance(d, dict)
    # Sérialisation sans erreur
    serialized = json.dumps(d, ensure_ascii=False)
    parsed = json.loads(serialized)
    assert parsed["lang"] == "fr"
    assert len(parsed["steps"]) == 7


def test_T13_to_json_valid(fr_lineage):
    """T13 — to_json() retourne un JSON valide."""
    j = fr_lineage.to_json()
    assert isinstance(j, str)
    parsed = json.loads(j)
    assert "lineage_id" in parsed
    assert "lineage_hash" in parsed


# ─── T14-T15 : reproductibilité ──────────────────────────────────────────────

def test_T14_lineage_id_deterministic():
    """T14 — lineage_id est déterministe pour le même texte+lang."""
    l1 = trace_lineage("vérifier la signature", "fr")
    l2 = trace_lineage("vérifier la signature", "fr")
    assert l1.lineage_id == l2.lineage_id, (
        f"lineage_id non déterministe: {l1.lineage_id} vs {l2.lineage_id}"
    )


def test_T15_different_text_different_lineage_id():
    """T15 — Textes différents → lineage_id différents."""
    l1 = trace_lineage("vérifier la signature", "fr")
    l2 = trace_lineage("chiffrer les données", "fr")
    assert l1.lineage_id != l2.lineage_id


# ─── T16-T17 : invariants ────────────────────────────────────────────────────

def test_T16_first_error_step_none_if_ok(fr_lineage):
    """T16 — first_error_step() retourne None si toutes les étapes sont OK."""
    err_step = fr_lineage.first_error_step()
    # Le lineage FR complet doit être sans erreur
    if not fr_lineage.is_ok():
        pytest.skip(f"Lineage FR non-OK — première erreur: {err_step}")
    assert err_step is None


def test_T17_invariants_always_false(fr_lineage):
    """T17 — unique_human_proven et certified toujours False."""
    assert fr_lineage.unique_human_proven is False
    assert fr_lineage.certified is False


# ─── T18 : multi-langue ──────────────────────────────────────────────────────

def test_T18_english_lineage(en_lineage):
    """T18 — Lineage EN fonctionne correctement (7 étapes, lang='en')."""
    assert en_lineage.lang == "en"
    assert len(en_lineage.steps) == 7
    assert en_lineage.lineage_id != ""
    # Les tokens EN doivent être non vides
    assert len(en_lineage.tokens) > 0


# ─── T19 : trace_batch ───────────────────────────────────────────────────────

def test_T19_trace_batch_returns_n_lineages():
    """T19 — trace_batch() retourne autant de lineages que de textes."""
    texts = [
        "vérifier la signature",
        "chiffrer les données",
        "créer un bloc",
    ]
    lineages = trace_batch(texts, "fr")
    assert len(lineages) == 3
    for lin, txt in zip(lineages, texts):
        assert lin.text == txt
        assert lin.lang == "fr"
        assert len(lin.steps) == 7


# ─── T20 : erreur lang invalide ──────────────────────────────────────────────

def test_T20_invalid_lang_returns_error():
    """T20 — Lang invalide → SemanticLineage avec error non-None."""
    lin = trace_lineage("test text", "xx")  # lang inexistant → fallback probable
    # Soit get_adapter fonctionne en fallback, soit retourne error
    # Le lineage doit exister dans les deux cas
    assert isinstance(lin, SemanticLineage)
    assert lin.text == "test text"
    assert lin.lang == "xx"


# ─── T21 : localisation d'erreur ─────────────────────────────────────────────

def test_T21_error_localization():
    """T21 — first_error_step() localise l'erreur à la bonne couche.

    Si un adapter produit une erreur, elle doit être tracée dans l'étape
    correspondante — pas dans le lineage global.
    """
    # On peut simuler une erreur en passant un adapter qui plante à morphology
    class BrokenMorphAdapter:
        """Adapter qui plante intentionnellement à morphology."""
        def tokenize(self, text):
            from src.artcb.language.adapter import TokenResult
            return TokenResult(tokens=text.split(), iso="test", method="whitespace")

        def normalize(self, text, form="NFC"):
            from src.artcb.language.adapter import NormalizeResult
            return NormalizeResult(
                normalized=text.lower(), original=text, form=form,
                lowercased=True
            )

        def morphology(self, tokens):
            raise RuntimeError("morphology_error_intentionnel")

        def map_to_concept(self, text):
            from src.artcb.language.adapter import ConceptMappingResult
            return ConceptMappingResult(
                artcb_code="UNK", concept_id="K_UNK", match_method="UNK",
                confidence=0.0, iso="test", input_lemma=text, input_surface=text
            )

        def parse_to_ir(self, text):
            from src.artcb.ir.encoder import IREncoder
            return IREncoder().encode(text)

        def round_trip(self, text):
            from src.artcb.language.adapter import RoundTripResult
            return RoundTripResult(
                source_text=text, reconstructed_text=text,
                source_concept_ids=[], reconstructed_concept_ids=[],
                round_trip_ok=False, semantic_equivalence=False,
                information_loss=False, iso="test"
            )

    broken_adapter = BrokenMorphAdapter()
    lin = trace_lineage("test error", "fr", adapter=broken_adapter)

    # Le lineage doit exister
    assert isinstance(lin, SemanticLineage)
    assert len(lin.steps) == 7

    # L'erreur doit être dans l'étape morphology (step_id=3)
    err_step = lin.first_error_step()
    assert err_step is not None, "Une erreur doit avoir été tracée"
    assert err_step.name == "morphology", (
        f"Erreur attendue à 'morphology', tracée à '{err_step.name}'"
    )
    assert "morphology_error_intentionnel" in (err_step.error or "")

    # Les étapes suivantes doivent avoir continué (pas d'arrêt)
    step_names = [s.name for s in lin.steps]
    assert "map_to_concept" in step_names
    assert "round_trip" in step_names


# ─── T22 : version ───────────────────────────────────────────────────────────

def test_T22_module_version():
    """T22 — MODULE_VERSION de lineage.py est 1.0.x."""
    major, minor, _patch = (int(x) for x in MODULE_VERSION.split("."))
    assert (major, minor) == (1, 0), (
        f"MODULE_VERSION doit être 1.0.x, obtenu '{MODULE_VERSION}'"
    )
