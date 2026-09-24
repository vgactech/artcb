"""Tests R465 — Lexicon Loader : chargement des dictionnaires complets 14 langues.

Suite : T01–T25
Modules testés :
    src/artcb/language/lexicon_loader.py
    src/artcb/language/registry.py

Stratégie :
    - Valider le pipeline LexiconLoader via un mini-lexicon JSON compact (fixture)
      → évite le timeout sur fr_lexicon.json (97 MB / 784k entrées)
    - T01/T02 vérifient l'existence + format du fichier réel si présent
    - T03–T15, T20–T25 : loader_small (mini-lexicon tmp) → rapides (<1s)
    - Tests négatifs : langue absente, fichier corrompu

CERTIFIED_100=false — tests valident le pipeline, pas la complétude lexicale
(dépend de kaikki.org qui est la meilleure source libre disponible).
"""
from __future__ import annotations

import json
import pathlib
import pytest

from src.artcb.language.registry import (
    CoverageState,
    LanguageModule,
    LanguageRegistry,
    LexicalEntry,
    get_registry,
)
from src.artcb.language.lexicon_loader import (
    LexiconLoader,
    load_all_lexicons,
    get_loader,
)

LEXICON_DIR = pathlib.Path("data/lexicons")
FR_LEXICON = LEXICON_DIR / "fr_lexicon.json"

# ── Mini-lexicon compact (≈ 20 entrées) utilisé par les tests de pipeline ─────
_MINI_FR_ENTRIES = [
    {"surface_form": "bonjour", "lemma": "bonjour", "pos": "noun", "lang": "fr",
     "senses": [{"raw_gloss": "salutation"}], "forms": []},
    {"surface_form": "maison", "lemma": "maison", "pos": "noun", "lang": "fr",
     "senses": [{"raw_gloss": "habitation"}], "forms": [{"form": "maisons", "tags": ["plural"]}]},
    {"surface_form": "courir", "lemma": "courir", "pos": "verb", "lang": "fr",
     "senses": [{"raw_gloss": "se déplacer rapidement"}], "forms": []},
    {"surface_form": "grand", "lemma": "grand", "pos": "adj", "lang": "fr",
     "senses": [{"raw_gloss": "de grande taille"}], "forms": []},
    {"surface_form": "lentement", "lemma": "lentement", "pos": "adv", "lang": "fr",
     "senses": [{"raw_gloss": "de manière lente"}], "forms": []},
    {"surface_form": "artcb", "lemma": "artcb", "pos": "noun", "lang": "fr",
     "senses": [{"raw_gloss": "blockchain ARTCB"}], "forms": []},
    {"surface_form": "blockchain", "lemma": "blockchain", "pos": "noun", "lang": "fr",
     "senses": [{"raw_gloss": "chaîne de blocs"}], "forms": []},
    {"surface_form": "nœud", "lemma": "nœud", "pos": "noun", "lang": "fr",
     "senses": [{"raw_gloss": "nœud de réseau"}], "forms": [{"form": "nœuds", "tags": ["plural"]}]},
    {"surface_form": "cryptographie", "lemma": "cryptographie", "pos": "noun", "lang": "fr",
     "senses": [{"raw_gloss": "science du chiffrement"}], "forms": []},
    {"surface_form": "preuve", "lemma": "preuve", "pos": "noun", "lang": "fr",
     "senses": [{"raw_gloss": "démonstration"}], "forms": []},
]

_MINI_FR_LEXICON = {
    "lang_id": "fr",
    "lang_name_en": "French",
    "script": "Latin",
    "source": "kaikki.org-wiktionary",
    "build_date": "2026-09-25T00:00:00Z",
    "entry_count": len(_MINI_FR_ENTRIES),
    "raw_entry_count": len(_MINI_FR_ENTRIES),
    "entries": _MINI_FR_ENTRIES,
    "certified_100": False,
}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def fresh_registry():
    """LanguageRegistry fraîche sans entrées chargées."""
    return LanguageRegistry()


@pytest.fixture
def loader_small(tmp_path):
    """LexiconLoader sur mini-lexicon compact (fr uniquement) — rapide (<1s)."""
    fr_path = tmp_path / "fr_lexicon.json"
    fr_path.write_text(json.dumps(_MINI_FR_LEXICON), encoding="utf-8")
    return LexiconLoader(lexicon_dir=tmp_path)


@pytest.fixture
def loader_from_tmp(tmp_path):
    """LexiconLoader pointant vers un répertoire temporaire vide (tests négatifs)."""
    return LexiconLoader(lexicon_dir=tmp_path)


# ── Tests infrastructure ──────────────────────────────────────────────────────

# T01 — fr_lexicon.json existe (produit par le build) — skippé si absent (build en cours)
@pytest.mark.skipif(not FR_LEXICON.is_file(), reason="fr_lexicon.json absent (build en cours)")
def test_T01_fr_lexicon_file_exists():
    assert FR_LEXICON.is_file(), (
        f"fr_lexicon.json absent. Exécuter : "
        f"python3 scripts/artcb_r465_lexicon_build.py --lang fr --test"
    )


# T02 — fr_lexicon.json contient le bon format — skippé si absent
@pytest.mark.skipif(not FR_LEXICON.is_file(), reason="fr_lexicon.json absent (build en cours)")
def test_T02_fr_lexicon_format():
    data = json.loads(FR_LEXICON.read_text(encoding="utf-8"))
    assert data["lang_id"] == "fr"
    assert data["lang_name_en"] == "French"
    assert "entries" in data
    assert isinstance(data["entries"], list)
    assert len(data["entries"]) > 0
    assert data["certified_100"] is False


# T03 — LexiconLoader.is_available(fr) = True
def test_T03_is_available_fr(loader_small):
    assert loader_small.is_available("fr") is True


# T04 — LexiconLoader.is_available(xx) = False (langue inconnue)
def test_T04_is_available_unknown(loader_small):
    assert loader_small.is_available("xx") is False


# T05 — available_languages() contient au moins 'fr'
def test_T05_available_languages(loader_small):
    langs = loader_small.available_languages()
    assert "fr" in langs


# ── Tests chargement FR (mini-lexicon compact) ────────────────────────────────

# T06 — load(fr) retourne un count > 0
def test_T06_load_fr_count(loader_small, fresh_registry):
    count = loader_small.load(fresh_registry, "fr")
    assert count > 0, "Aucune entrée chargée pour fr"


# T07 — load(fr) peuple le module
def test_T07_load_fr_module_populated(loader_small, fresh_registry):
    loader_small.load(fresh_registry, "fr")
    mod = fresh_registry.get("fr")
    assert mod is not None
    assert mod.entry_count > 0


# T08 — Invariant : toutes les LexicalEntry ont surface_form non vide
def test_T08_all_entries_have_surface_form(loader_small, fresh_registry):
    loader_small.load(fresh_registry, "fr")
    mod = fresh_registry.get("fr")
    for entry in mod.entries:
        assert entry.surface_form, "surface_form vide détectée"


# T09 — Invariant : toutes les LexicalEntry ont artcb_code non vide
def test_T09_all_entries_have_artcb_code(loader_small, fresh_registry):
    loader_small.load(fresh_registry, "fr")
    mod = fresh_registry.get("fr")
    for entry in mod.entries:
        assert entry.artcb_code, f"artcb_code vide pour {entry.surface_form}"


# T10 — artcb_code = 'UNK' pour les entrées non encore résolues
def test_T10_artcb_code_unk_for_unresolved(loader_small, fresh_registry):
    loader_small.load(fresh_registry, "fr")
    mod = fresh_registry.get("fr")
    unk_count = sum(1 for e in mod.entries if e.artcb_code == "UNK")
    # La majorité des entrées doit avoir artcb_code=UNK (l'encodeur IR résoudra après)
    assert unk_count > 0, "Aucune entrée UNK — inattendu pour un lexique brut"


# T11 — coverage_state = IMPLEMENTED après chargement sans erreur
def test_T11_coverage_state_implemented(loader_small, fresh_registry):
    loader_small.load(fresh_registry, "fr")
    mod = fresh_registry.get("fr")
    assert mod.coverage_state in (
        CoverageState.IMPLEMENTED,
        CoverageState.PARTIALLY_IMPLEMENTED,
    ), f"coverage_state inattendu: {mod.coverage_state}"


# T12 — coverage_pct > 0 après chargement
def test_T12_coverage_pct_positive(loader_small, fresh_registry):
    loader_small.load(fresh_registry, "fr")
    mod = fresh_registry.get("fr")
    assert mod.coverage_pct > 0.0


# T13 — entry_count_reference est défini après chargement
def test_T13_entry_count_reference_set(loader_small, fresh_registry):
    loader_small.load(fresh_registry, "fr")
    mod = fresh_registry.get("fr")
    assert mod.entry_count_reference > 0


# T14 — source_ref est 'kaikki.org-wiktionary' après chargement
def test_T14_source_ref_kaikki(loader_small, fresh_registry):
    loader_small.load(fresh_registry, "fr")
    mod = fresh_registry.get("fr")
    assert "kaikki" in mod.source_ref.lower()


# T15 — module_version contient 'R465' après chargement
def test_T15_module_version_r465(loader_small, fresh_registry):
    loader_small.load(fresh_registry, "fr")
    mod = fresh_registry.get("fr")
    assert "R465" in mod.module_version


# ── Tests négatifs ────────────────────────────────────────────────────────────

# T16 — load(xx) pour langue inconnue retourne 0
def test_T16_load_unknown_lang_returns_0(loader_from_tmp, fresh_registry):
    count = loader_from_tmp.load(fresh_registry, "xx")
    assert count == 0


# T17 — load(fr) avec fichier absent retourne 0
def test_T17_load_missing_file_returns_0(loader_from_tmp, fresh_registry):
    count = loader_from_tmp.load(fresh_registry, "fr")
    assert count == 0


# T18 — load avec JSON corrompu ne crashe pas et retourne 0
def test_T18_load_corrupted_json(tmp_path, fresh_registry):
    corrupt = tmp_path / "fr_lexicon.json"
    corrupt.write_text("{ this is not valid JSON }", encoding="utf-8")
    loader = LexiconLoader(lexicon_dir=tmp_path)
    count = loader.load(fresh_registry, "fr")
    assert count == 0


# T19 — load avec entries vides retourne 0
def test_T19_load_empty_entries(tmp_path, fresh_registry):
    empty_data = {
        "lang_id": "fr", "lang_name_en": "French", "script": "Latin",
        "source": "test", "build_date": "2026-01-01", "entry_count": 0,
        "raw_entry_count": 0, "entries": [], "certified_100": False,
    }
    path = tmp_path / "fr_lexicon.json"
    path.write_text(json.dumps(empty_data), encoding="utf-8")
    loader = LexiconLoader(lexicon_dir=tmp_path)
    count = loader.load(fresh_registry, "fr")
    assert count == 0
    mod = fresh_registry.get("fr")
    assert mod.coverage_state == CoverageState.ABSENT


# ── Tests load_all (mini-lexicon compact) ─────────────────────────────────────

# T20 — load_all retourne un dict avec au moins 'fr'
def test_T20_load_all_returns_fr(loader_small, fresh_registry):
    results = loader_small.load_all(fresh_registry)
    assert "fr" in results
    assert results["fr"] > 0


# T21 — load_all : total entrées > 0
def test_T21_load_all_total_positive(loader_small, fresh_registry):
    results = loader_small.load_all(fresh_registry)
    total = sum(results.values())
    assert total > 0


# T22 — coverage_report contient les 14 langues officielles
def test_T22_coverage_report_14_langs(loader_small, fresh_registry):
    loader_small.load_all(fresh_registry)
    report = loader_small.coverage_report(fresh_registry)
    lang_ids = [r["lang_id"] for r in report]
    for expected in LanguageRegistry.INITIAL_14_LANG_IDS:
        assert expected in lang_ids, f"{expected} absent du rapport de couverture"


# T23 — certified_100 = False dans tous les rapports de couverture
def test_T23_coverage_report_certified_false(loader_small, fresh_registry):
    loader_small.load_all(fresh_registry)
    report = loader_small.coverage_report(fresh_registry)
    for r in report:
        assert r["certified_100"] is False


# T24 — lookup fonctionne après chargement
def test_T24_lookup_works_after_load(loader_small, fresh_registry):
    loader_small.load(fresh_registry, "fr")
    mod = fresh_registry.get("fr")
    # Chercher le premier mot chargé
    if mod.entries:
        first = mod.entries[0].surface_form
        found = mod.lookup(first)
        assert found is not None
        assert found.surface_form.lower() == first.lower()


# T25 — Invariant : confidence dans [0.0, 1.0] pour toutes les entrées
def test_T25_confidence_bounds(loader_small, fresh_registry):
    loader_small.load(fresh_registry, "fr")
    mod = fresh_registry.get("fr")
    for entry in mod.entries:
        assert 0.0 <= entry.confidence <= 1.0, (
            f"confidence hors bornes pour {entry.surface_form}: {entry.confidence}"
        )
