"""Tests R486 — Language Adapter + Semantic Corpus + Equivalence Matrix.

Couvre R486-A (batterie 16 langues), R486-B (corpus canonique),
R486-C (16 pipelines interface commune), R486-E (équivalence), R486-F (round-trip).

≥ 20 tests :
  - MODULE_VERSION + invariants
  - list_supported_isos() : 16 ISO
  - LanguageAdapter interface : tokenize/normalize/morphology/map_to_concept/parse_to_ir/render/explain
  - concept_id_from_code() : stabilité et déterminisme
  - SemanticCorpus : chargement, get_concept_id, summary
  - 16 adapters concrets : tokenize + map_to_concept
  - Probe triple FR/EN/ES : V1+S2+N1 convergent
  - ArabicAdapter : tashkeel stripped
  - TurkishAdapter : dotless-i
  - ChineseAdapter : char-by-char
  - JapaneseAdapter : CJK
  - KoreanAdapter : Hangul
  - RoundTrip FR : concept_ids conservés
  - Matrice équivalence FR/EN/ES → V1 commun
  - R486 règle : ConceptID stable entre adapters
  - Invariants CERTIFIED_100=False partout

ARTCB mode DEBUG — CERTIFIED_100=false
"""
from __future__ import annotations

import pytest
from pathlib import Path

from src.artcb.language.adapter import (
    MODULE_VERSION,
    CERTIFIED_100,
    UNIQUE_HUMAN_PROVEN,
    AdapterCoverage,
    TokenResult,
    NormalizeResult,
    MorphologyResult,
    ConceptMappingResult,
    RoundTripResult,
    MappingProvenance,
    EquivalenceCell,
    SemanticConcept,
    SemanticCorpus,
    LanguageAdapter,
    FrenchAdapter,
    EnglishAdapter,
    SpanishAdapter,
    PortugueseAdapter,
    RussianAdapter,
    ChineseAdapter,
    ArabicAdapter,
    GermanAdapter,
    JapaneseAdapter,
    KoreanAdapter,
    TurkishAdapter,
    LatinAdapter,
    get_adapter,
    get_all_adapters,
    list_supported_isos,
    concept_id_from_code,
    build_equivalence_matrix,
)


# ─── T01 — Module version + invariants ────────────────────────────────────────
def test_T01_module_invariants():
    """T01 : MODULE_VERSION semver + invariants absolus."""
    assert MODULE_VERSION
    assert len(MODULE_VERSION.split(".")) == 3
    assert CERTIFIED_100 is False
    assert UNIQUE_HUMAN_PROVEN is False


# ─── T02 — 16 adapters disponibles ────────────────────────────────────────────
def test_T02_sixteen_adapters():
    """T02 : list_supported_isos() retourne exactement 16 ISO."""
    isos = list_supported_isos()
    assert len(isos) == 16
    expected = {"fr", "en", "es", "pt", "pt-BR", "it", "ru", "zh",
                "ar", "de", "id", "ja", "ko", "pl", "tr", "la"}
    assert set(isos) == expected


# ─── T03 — get_adapter() ne retourne jamais None pour les 16 ISO ──────────────
def test_T03_all_adapters_present():
    """T03 : get_adapter() retourne un objet non-None pour chacun des 16 ISO."""
    for iso in list_supported_isos():
        adapter = get_adapter(iso)
        assert adapter is not None, f"Adapter manquant pour {iso}"
        assert isinstance(adapter, LanguageAdapter)
        assert adapter.iso == iso


# ─── T04 — concept_id_from_code() déterministe ───────────────────────────────
def test_T04_concept_id_deterministic():
    """T04 : concept_id_from_code() retourne toujours le même ID pour un même code."""
    cid_v1_a = concept_id_from_code("V1")
    cid_v1_b = concept_id_from_code("V1")
    assert cid_v1_a == cid_v1_b
    assert cid_v1_a.startswith("K")
    assert len(cid_v1_a) == 13  # K + 12 hex


# ─── T05 — concept_id_from_code() unicité ─────────────────────────────────────
def test_T05_concept_id_unique():
    """T05 : Deux artcb_codes différents → deux ConceptIDs différents."""
    codes = ["V1", "C2", "S2", "N1", "E3", "B1", "M1", "D1", "K1"]
    ids = [concept_id_from_code(c) for c in codes]
    assert len(set(ids)) == len(codes), "ConceptIDs non uniques"


# ─── T06 — concept_id_from_code() UNK → K_UNK ────────────────────────────────
def test_T06_concept_id_unk():
    """T06 : concept_id_from_code('UNK') = 'K_UNK' (constante réservée)."""
    assert concept_id_from_code("UNK") == "K_UNK"
    assert concept_id_from_code("") == "K_UNK"


# ─── T07 — SemanticCorpus chargé depuis concept_lexicon ──────────────────────
def test_T07_semantic_corpus_loaded():
    """T07 : SemanticCorpus contient au moins 20 concepts depuis concept_lexicon."""
    corpus = SemanticCorpus()
    s = corpus.summary()
    assert s["total_concepts"] >= 20
    assert s["certified_100"] is False
    assert len(s["corpus_hash"]) == 64  # SHA-256


# ─── T08 — SemanticCorpus : ConceptID stable pour V1/S2/N1 ──────────────────
def test_T08_corpus_concept_ids_stable():
    """T08 : ConceptID de V1/S2/N1 depuis SemanticCorpus == concept_id_from_code()."""
    corpus = SemanticCorpus()
    for code in ["V1", "S2", "N1", "C2", "E3"]:
        from_corpus = corpus.get_concept_id(code)
        from_func = concept_id_from_code(code)
        assert from_corpus == from_func, f"{code}: corpus={from_corpus} != func={from_func}"


# ─── T09 — Probe triple FR : vérifier → V1, signature → S2, serveur → N1 ──────
def test_T09_probe_triple_fr():
    """T09 : 'vérifier la signature du serveur' → V1/S2/N1 en FR."""
    fr = get_adapter("fr")
    prov = fr.explain_mapping("vérifier la signature du serveur")
    assert "V1" in prov.artcb_codes, f"V1 attendu, codes: {prov.artcb_codes}"
    assert "S2" in prov.artcb_codes, f"S2 attendu, codes: {prov.artcb_codes}"
    assert "N1" in prov.artcb_codes, f"N1 attendu, codes: {prov.artcb_codes}"


# ─── T10 — Probe triple EN : verify → V1, signature → S2 ─────────────────────
def test_T10_probe_triple_en():
    """T10 : 'verify the server signature' → V1/S2 en EN."""
    en = get_adapter("en")
    prov = en.explain_mapping("verify the server signature")
    assert "V1" in prov.artcb_codes
    assert "S2" in prov.artcb_codes


# ─── T11 — Probe triple ES : verificar → V1 ──────────────────────────────────
def test_T11_probe_triple_es():
    """T11 : 'verificar la firma del servidor' → V1 en ES."""
    es = get_adapter("es")
    prov = es.explain_mapping("verificar la firma del servidor")
    assert "V1" in prov.artcb_codes


# ─── T12 — Même ConceptID V1 pour FR/EN/ES (convergence sémantique) ──────────
def test_T12_cross_language_v1_convergence():
    """T12 : vérifier/verify/verificar → même ConceptID K45438c1fb97f (V1)."""
    v1_cid = concept_id_from_code("V1")
    for iso, phrase in [("fr", "vérifier"), ("en", "verify"), ("es", "verificar")]:
        adapter = get_adapter(iso)
        result = adapter.map_to_concept(phrase, phrase)
        assert result.concept_id == v1_cid, (
            f"[{iso}] '{phrase}' → {result.concept_id}, attendu {v1_cid}"
        )


# ─── T13 — ArabicAdapter : tashkeel strippé ──────────────────────────────────
def test_T13_arabic_tashkeel_stripped():
    """T13 : ArabicAdapter.normalize() supprime les diacritiques arabes (tashkeel)."""
    ar = get_adapter("ar")
    # Texte avec tashkeel U+064E (fatha)
    text_with_tashkeel = "التَّحَقُّق"
    result = ar.normalize(text_with_tashkeel)
    assert "\u064e" not in result.normalized  # fatha supprimée
    assert result.diacritics_stripped is True


# ─── T14 — TurkishAdapter : dotless-i ────────────────────────────────────────
def test_T14_turkish_dotless_i():
    """T14 : TurkishAdapter.normalize() gère 'İ' → 'i' (pas la règle latine)."""
    tr = get_adapter("tr")
    result = tr.normalize("İmzalamak")
    assert "i" in result.normalized
    assert "İ" not in result.normalized


# ─── T15 — ChineseAdapter : tokenisation char-by-char ────────────────────────
def test_T15_chinese_tokenize_char():
    """T15 : ChineseAdapter.tokenize() retourne des tokens individuels (pas de segmentation)."""
    zh = get_adapter("zh")
    result = zh.tokenize("验证服务器")
    assert result.method == "cjk_char"
    assert len(result.tokens) == len("验证服务器")


# ─── T16 — JapaneseAdapter : bigrammes CJK ───────────────────────────────────
def test_T16_japanese_tokenize_bigram():
    """T16 : JapaneseAdapter.tokenize() retourne des bigrammes CJK."""
    ja = get_adapter("ja")
    result = ja.tokenize("サーバー署名を検証")
    assert result.method == "cjk_bigram"
    assert len(result.tokens) > 0


# ─── T17 — KoreanAdapter : blocs Hangul ──────────────────────────────────────
def test_T17_korean_tokenize_hangul():
    """T17 : KoreanAdapter.tokenize() retourne des blocs Hangul."""
    ko = get_adapter("ko")
    result = ko.tokenize("서버 서명을 검증")
    assert result.method == "hangul_blocks"
    assert len(result.tokens) >= 1


# ─── T18 — Round-trip FR : ConceptIDs conservés ──────────────────────────────
def test_T18_round_trip_fr():
    """T18 : Round-trip 'vérifier la signature du serveur' conserve V1/S2/N1."""
    fr = get_adapter("fr")
    rt = fr.round_trip("vérifier la signature du serveur")
    assert isinstance(rt, RoundTripResult)
    assert rt.iso == "fr"
    assert rt.round_trip_ok is True  # aucun concept perdu
    # V1/S2/N1 présents dans les source_concept_ids
    v1_cid = concept_id_from_code("V1")
    assert v1_cid in rt.source_concept_ids


# ─── T19 — Matrice équivalence FR/EN/ES → V1 commun ─────────────────────────
def test_T19_equivalence_matrix_fr_en_es():
    """T19 : La matrice FR/EN/ES sur 'vérifier/verify/verificar' → équivalence V1."""
    phrases = {
        "fr": "vérifier la signature du serveur",
        "en": "verify the server signature",
        "es": "verificar la firma del servidor",
    }
    cells = build_equivalence_matrix(phrases)
    assert len(cells) == 9  # 3×3

    # Toutes les cellules devraient être équivalentes (V1 primaire)
    equiv_cells = [c for c in cells if c.equivalent]
    assert len(equiv_cells) == 9, f"Attendu 9 équivalences, obtenu {len(equiv_cells)}"


# ─── T20 — MappingProvenance : provenance complète ────────────────────────────
def test_T20_mapping_provenance_complete():
    """T20 : explain_mapping() retourne une provenance complète non vide."""
    fr = get_adapter("fr")
    prov = fr.explain_mapping("vérifier la signature")
    assert isinstance(prov, MappingProvenance)
    assert prov.iso == "fr"
    assert len(prov.tokens) > 0
    assert len(prov.artcb_codes) > 0
    assert len(prov.concept_ids) > 0
    assert len(prov.method_chain) == 4
    assert len(prov.registry_sha) == 64  # SHA-256 du registre
    assert prov.certified_100 is False
    assert prov.unique_human_proven is False


# ─── T21 — Interface commune : les 16 adapters implémentent tokenize/normalize ─
def test_T21_all_adapters_common_interface():
    """T21 : Les 16 adapters implémentent tous tokenize() et normalize()."""
    for iso in list_supported_isos():
        adapter = get_adapter(iso)
        # tokenize
        tok = adapter.tokenize("hello world test")
        assert isinstance(tok, TokenResult)
        assert tok.iso == iso
        # normalize
        norm = adapter.normalize("Hello World")
        assert isinstance(norm, NormalizeResult)
        assert norm.normalized  # non vide


# ─── T22 — SemanticCorpus : all_codes() cohérent avec summary ────────────────
def test_T22_corpus_all_codes_coherent():
    """T22 : len(corpus.all_codes()) == summary['total_concepts']."""
    corpus = SemanticCorpus()
    assert len(corpus.all_codes()) == corpus.summary()["total_concepts"]
    # V1/S2/N1/C2 présents
    codes = corpus.all_codes()
    for expected in ["V1", "S2", "N1", "C2"]:
        assert expected in codes, f"{expected} absent du corpus"


# ─── T23 — R486 règle : ConceptID identique entre adapters pour V1 ───────────
def test_T23_concept_id_cross_adapter_stable():
    """T23 : Le ConceptID V1 est identique quelque soit l'adapter qui le calcule.

    Règle R486-C : le ConceptID appartient au niveau sémantique commun,
    pas à l'adapter. Les 16 adapters doivent retourner le même concept_id pour V1.
    """
    v1_expected = concept_id_from_code("V1")
    # Mots qui mappent V1 dans différentes langues
    v1_words = [
        ("fr", "vérifier"), ("en", "verify"), ("es", "verificar"),
        ("pt", "verificar"), ("de", "prüfen"),
    ]
    for iso, word in v1_words:
        adapter = get_adapter(iso)
        result = adapter.map_to_concept(word, word)
        if result.artcb_code == "V1":
            assert result.concept_id == v1_expected, (
                f"[{iso}] '{word}' → concept_id={result.concept_id}, attendu {v1_expected}"
            )
