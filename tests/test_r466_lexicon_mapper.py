"""Tests R466 — LexiconMapper : résolution artcb_code UNK → codes réels.

Suite T01–T25 couvrant :
    - Résolution exacte surface_form (ACTION, OBJECT, MODIFIER)
    - Résolution exacte lemma (quand surface ≠ lemma)
    - Résolution préfixe lemma
    - Non-résolution honnête (UNK conservé)
    - Invariants de sécurité
    - resolve_batch() stats
    - get_mapper() singleton
    - Codes ARTCB retournés dans l'ensemble attendu
    - Edge cases (chaîne vide, casse, espaces)
    - Déterminisme (même entrée → même résultat)

CERTIFIED_100=false
"""
from __future__ import annotations

import pytest
import logging

from src.artcb.language.lexicon_mapper import (
    LexiconMapper,
    MapperStats,
    MappingResult,
    UNRESOLVED_CODE,
    get_mapper,
)

# ── Constantes de test ──────────────────────────────────────────────────────────

# Codes ARTCB légitimes (depuis concept_lexicon.py)
VALID_CODES = {
    "A1", "B1", "C1", "C2", "D1", "E3", "K1",
    "M1", "M2", "M3", "MOD", "N1", "NEG", "O1",
    "P1", "P2", "PL", "QH", "QL", "R1", "S1",
    "S2", "U1", "V1",
}

logger = logging.getLogger("tests.r466")


# ── Fixtures ────────────────────────────────────────────────────────────────────

@pytest.fixture
def mapper():
    return LexiconMapper()


# ── T01 : instanciation sans erreur ─────────────────────────────────────────────

def test_T01_instantiation():
    """T01 — LexiconMapper s'instancie sans exception."""
    m = LexiconMapper()
    assert m is not None


# ── T02 : résolution exacte surface_form ACTION ─────────────────────────────────

def test_T02_exact_surface_action(mapper):
    """T02 — 'vérifier' surface → code V1 (ACTION_ALIASES exact)."""
    result = mapper.resolve("vérifier", "vérifier", "verb")
    assert result.resolved is True
    assert result.artcb_code == "V1"
    assert result.match_method == "exact_surface"
    assert result.table_name == "ACTION"


# ── T03 : résolution exacte surface_form OBJECT ─────────────────────────────────

def test_T03_exact_surface_object(mapper):
    """T03 — 'server' surface → code N1 (OBJECT_ALIASES exact)."""
    result = mapper.resolve("server", "server", "noun")
    assert result.resolved is True
    assert result.artcb_code == "N1"
    assert result.match_method == "exact_surface"
    assert result.table_name == "OBJECT"


# ── T04 : résolution exacte surface_form MODIFIER ───────────────────────────────

def test_T04_exact_surface_modifier(mapper):
    """T04 — 'beaucoup' surface → code QH (MODIFIER_ALIASES exact)."""
    result = mapper.resolve("beaucoup", "beaucoup", "adv")
    assert result.resolved is True
    assert result.artcb_code == "QH"
    assert result.match_method == "exact_surface"
    assert result.table_name == "MODIFIER"


# ── T05 : résolution exacte lemma (surface différente) ──────────────────────────

def test_T05_exact_lemma_different_surface(mapper):
    """T05 — surface 'vérifions' (inexistant), lemma 'vérifier' → V1 via exact_lemma."""
    result = mapper.resolve("vérifions", "vérifier", "verb")
    assert result.resolved is True
    assert result.artcb_code == "V1"
    assert result.match_method == "exact_lemma"


# ── T06 : préfixe sur lemma ──────────────────────────────────────────────────────

def test_T06_prefix_lemma(mapper):
    """T06 — lemma 'vérification' préfixe 'vérifi' → V1 via prefix_lemma."""
    result = mapper.resolve("vérification", "vérification", "noun")
    assert result.resolved is True
    assert result.artcb_code == "V1"
    assert result.match_method == "prefix_lemma"


# ── T07 : non-résolution honnête ─────────────────────────────────────────────────

def test_T07_unresolved_unk(mapper):
    """T07 — lemme inconnu → artcb_code='UNK', resolved=False."""
    result = mapper.resolve("xyzqrst", "xyzqrst", "noun")
    assert result.resolved is False
    assert result.artcb_code == UNRESOLVED_CODE
    assert result.match_method == "unresolved"
    assert result.matched_key is None
    assert result.table_name is None


# ── T08 : invariant — code retourné dans VALID_CODES ou UNK ─────────────────────

@pytest.mark.parametrize("surface,lemma,pos", [
    ("vérifier", "vérifier", "verb"),
    ("voiture", "voiture", "noun"),
    ("signature", "signature", "noun"),
    ("energy", "energy", "noun"),
    ("beaucoup", "beaucoup", "adv"),
    ("cannot", "cannot", "adv"),
    ("inconnu_xyz", "inconnu_xyz", "noun"),
])
def test_T08_code_in_valid_set_or_unk(mapper, surface, lemma, pos):
    """T08 — artcb_code est toujours dans VALID_CODES ou 'UNK'."""
    result = mapper.resolve(surface, lemma, pos)
    assert result.artcb_code in VALID_CODES or result.artcb_code == UNRESOLVED_CODE


# ── T09 : insensibilité à la casse surface ──────────────────────────────────────

def test_T09_case_insensitive_surface(mapper):
    """T09 — 'VÉRIFIER' → même résultat que 'vérifier'."""
    r1 = mapper.resolve("vérifier", "vérifier", "verb")
    r2 = mapper.resolve("VÉRIFIER", "VÉRIFIER", "verb")
    assert r1.artcb_code == r2.artcb_code
    assert r1.resolved == r2.resolved


# ── T10 : insensibilité à la casse lemma ────────────────────────────────────────

def test_T10_case_insensitive_lemma(mapper):
    """T10 — lemma 'Vérifier' (majuscule) → V1."""
    result = mapper.resolve("vérifions", "Vérifier", "verb")
    assert result.resolved is True
    assert result.artcb_code == "V1"


# ── T11 : déterminisme (même entrée → même résultat) ───────────────────────────

def test_T11_determinism(mapper):
    """T11 — deux appels identiques produisent le même résultat."""
    r1 = mapper.resolve("server", "server", "noun")
    r2 = mapper.resolve("server", "server", "noun")
    assert r1.artcb_code == r2.artcb_code
    assert r1.match_method == r2.match_method
    assert r1.matched_key == r2.matched_key


# ── T12 : resolve_batch sur liste vide ──────────────────────────────────────────

def test_T12_batch_empty(mapper):
    """T12 — resolve_batch([]) retourne liste vide et stats zéro."""
    updated, stats = mapper.resolve_batch([])
    assert updated == []
    assert stats.total == 0
    assert stats.resolved == 0
    assert stats.unresolved == 0
    assert stats.resolution_rate == 0.0


# ── T13 : resolve_batch stats cohérentes ────────────────────────────────────────

def test_T13_batch_stats(mapper):
    """T13 — resolve_batch retourne stats total=resolved+unresolved."""
    entries = [
        {"surface_form": "vérifier", "lemma": "vérifier", "pos": "verb", "artcb_code": ""},
        {"surface_form": "server", "lemma": "server", "pos": "noun", "artcb_code": ""},
        {"surface_form": "mot_inconnu_xyz", "lemma": "mot_inconnu_xyz", "pos": "noun", "artcb_code": ""},
    ]
    updated, stats = mapper.resolve_batch(entries)
    assert stats.total == 3
    assert stats.resolved == 2
    assert stats.unresolved == 1
    assert stats.total == stats.resolved + stats.unresolved


# ── T14 : resolve_batch met à jour artcb_code dans l'entrée ─────────────────────

def test_T14_batch_updates_artcb_code(mapper):
    """T14 — après resolve_batch, artcb_code est mis à jour dans les entrées."""
    entries = [
        {"surface_form": "vérifier", "lemma": "vérifier", "pos": "verb", "artcb_code": ""},
        {"surface_form": "mot_xyz", "lemma": "mot_xyz", "pos": "noun", "artcb_code": ""},
    ]
    updated, stats = mapper.resolve_batch(entries)
    assert updated[0]["artcb_code"] == "V1"
    assert updated[1]["artcb_code"] == "UNK"


# ── T15 : MapperStats.summary() retourne dict complet ───────────────────────────

def test_T15_stats_summary(mapper):
    """T15 — MapperStats.summary() contient les clés attendues."""
    stats = MapperStats(total=10, resolved=3, unresolved=7)
    stats.by_code = {"V1": 2, "N1": 1}
    stats.by_method = {"exact_surface": 3}
    s = stats.summary()
    assert "total" in s
    assert "resolved" in s
    assert "unresolved" in s
    assert "resolution_rate_pct" in s
    assert "by_code" in s
    assert "by_method" in s


# ── T16 : taux de résolution calculé correctement ───────────────────────────────

def test_T16_resolution_rate(mapper):
    """T16 — resolution_rate = resolved/total."""
    stats = MapperStats(total=100, resolved=25, unresolved=75)
    assert abs(stats.resolution_rate - 0.25) < 1e-9
    s = stats.summary()
    assert abs(s["resolution_rate_pct"] - 25.0) < 0.001


# ── T17 : get_mapper() retourne singleton ───────────────────────────────────────

def test_T17_singleton(mapper):
    """T17 — get_mapper() retourne le même objet à deux appels."""
    m1 = get_mapper()
    m2 = get_mapper()
    assert m1 is m2


# ── T18 : voiture → C2 (OBJECT multilingual) ────────────────────────────────────

def test_T18_vehicle_fr(mapper):
    """T18 — 'voiture' → C2 (véhicule FR, OBJECT_ALIASES)."""
    result = mapper.resolve("voiture", "voiture", "noun")
    assert result.resolved is True
    assert result.artcb_code == "C2"


# ── T19 : car → C2 (EN) ─────────────────────────────────────────────────────────

def test_T19_vehicle_en(mapper):
    """T19 — 'car' → C2 (véhicule EN)."""
    result = mapper.resolve("car", "car", "noun")
    assert result.resolved is True
    assert result.artcb_code == "C2"


# ── T20 : signature → S2 ────────────────────────────────────────────────────────

def test_T20_signature(mapper):
    """T20 — 'signature' → S2."""
    result = mapper.resolve("signature", "signature", "noun")
    assert result.resolved is True
    assert result.artcb_code == "S2"


# ── T21 : MappingResult contient tous les champs attendus ───────────────────────

def test_T21_result_fields(mapper):
    """T21 — MappingResult expose surface_form, lemma, pos, artcb_code, resolved, match_method."""
    result = mapper.resolve("server", "server", "noun")
    assert hasattr(result, "surface_form")
    assert hasattr(result, "lemma")
    assert hasattr(result, "pos")
    assert hasattr(result, "artcb_code")
    assert hasattr(result, "resolved")
    assert hasattr(result, "match_method")
    assert hasattr(result, "matched_key")
    assert hasattr(result, "table_name")


# ── T22 : edge case — surface_form vide ─────────────────────────────────────────

def test_T22_empty_surface(mapper):
    """T22 — surface_form vide → UNK sans exception."""
    result = mapper.resolve("", "", "noun")
    assert result.artcb_code == UNRESOLVED_CODE
    assert result.resolved is False


# ── T23 : edge case — surface avec espaces ──────────────────────────────────────

def test_T23_surface_with_spaces(mapper):
    """T23 — surface avec espaces → strip appliqué, pas de crash."""
    result = mapper.resolve("  vérifier  ", "  vérifier  ", "verb")
    assert result.resolved is True
    assert result.artcb_code == "V1"


# ── T24 : resolve_batch préserve les autres champs ──────────────────────────────

def test_T24_batch_preserves_other_fields(mapper):
    """T24 — resolve_batch préserve source, forms_count etc. des entrées."""
    entries = [
        {
            "surface_form": "vérifier",
            "lemma": "vérifier",
            "pos": "verb",
            "artcb_code": "",
            "source": "kaikki.org-wiktionary",
            "forms_count": 5,
        }
    ]
    updated, _ = mapper.resolve_batch(entries)
    assert updated[0]["source"] == "kaikki.org-wiktionary"
    assert updated[0]["forms_count"] == 5
    assert updated[0]["artcb_code"] == "V1"


# ── T25 : by_code stats comptent correctement ────────────────────────────────────

def test_T25_by_code_stats(mapper):
    """T25 — by_code comptabilise par code ARTCB."""
    entries = [
        {"surface_form": "vérifier", "lemma": "vérifier", "pos": "verb", "artcb_code": ""},
        {"surface_form": "verify", "lemma": "verify", "pos": "verb", "artcb_code": ""},
        {"surface_form": "server", "lemma": "server", "pos": "noun", "artcb_code": ""},
    ]
    _, stats = mapper.resolve_batch(entries)
    # V1 doit avoir au moins 1 (vérifier ou verify)
    assert "V1" in stats.by_code
    assert stats.by_code.get("V1", 0) >= 1
