"""R448 — Tests architecture modules linguistiques 14 langues.

Valide :
  - LanguageRegistry : 14 modules enregistrés
  - LexicalEntry : invariants dataclass
  - LanguageModule : coverage_pct, lookup
  - Registre officiel ARTCB_14_LANGUAGES.json
  - Honnêteté : coverage != 100%, CERTIFIED_100=false

PROTOCOLE ARTCB — mode DEBUG — jamais de stub — CERTIFIED_100=false.
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

REGISTRY_JSON = pathlib.Path("rules/ARTCB_14_LANGUAGES.json")


# ─── T01 — LexicalEntry invariants ───────────────────────────────────────────

class TestLexicalEntry:
    def test_t01_basic_creation(self) -> None:
        e = LexicalEntry(surface_form="voiture", lemma="voiture", artcb_code="C2", source="manual")
        assert e.surface_form == "voiture"
        assert e.artcb_code == "C2"
        assert e.confidence == 1.0

    def test_t02_confidence_bounds(self) -> None:
        e = LexicalEntry(surface_form="car", lemma="car", artcb_code="C2", confidence=0.9)
        assert 0.0 <= e.confidence <= 1.0

    def test_t03_invalid_confidence_raises(self) -> None:
        with pytest.raises(AssertionError):
            LexicalEntry(surface_form="car", lemma="car", artcb_code="C2", confidence=1.5)

    def test_t04_empty_artcb_code_raises(self) -> None:
        with pytest.raises(AssertionError):
            LexicalEntry(surface_form="car", lemma="car", artcb_code="")

    def test_t05_empty_surface_form_raises(self) -> None:
        with pytest.raises(AssertionError):
            LexicalEntry(surface_form="", lemma="voiture", artcb_code="C2")


# ─── T06 — LanguageModule ─────────────────────────────────────────────────────

class TestLanguageModule:
    def test_t06_empty_module(self) -> None:
        mod = LanguageModule(lang_id="fr", lang_name_en="French", script="Latin")
        assert mod.entry_count == 0
        assert mod.coverage_pct == 0.0
        assert mod.coverage_state == CoverageState.PARTIALLY_IMPLEMENTED

    def test_t07_add_and_lookup(self) -> None:
        mod = LanguageModule(lang_id="fr", lang_name_en="French", script="Latin")
        mod.add_entry(LexicalEntry(surface_form="voiture", lemma="voiture", artcb_code="C2"))
        assert mod.entry_count == 1
        found = mod.lookup("voiture")
        assert found is not None
        assert found.artcb_code == "C2"

    def test_t08_lookup_case_insensitive(self) -> None:
        mod = LanguageModule(lang_id="en", lang_name_en="English", script="Latin")
        mod.add_entry(LexicalEntry(surface_form="Car", lemma="car", artcb_code="C2"))
        assert mod.lookup("car") is not None
        assert mod.lookup("CAR") is not None

    def test_t09_lookup_miss_returns_none(self) -> None:
        mod = LanguageModule(lang_id="en", lang_name_en="English", script="Latin")
        assert mod.lookup("unknown_xyzfoo") is None

    def test_t10_coverage_pct_with_reference(self) -> None:
        mod = LanguageModule(lang_id="fr", lang_name_en="French", script="Latin",
                             entry_count_reference=100)
        for i in range(30):
            mod.add_entry(LexicalEntry(surface_form=f"word{i}", lemma=f"word{i}", artcb_code="C2"))
        assert mod.coverage_pct == 30.0

    def test_t11_coverage_pct_zero_if_no_reference(self) -> None:
        mod = LanguageModule(lang_id="fr", lang_name_en="French", script="Latin",
                             entry_count_reference=0)
        mod.add_entry(LexicalEntry(surface_form="test", lemma="test", artcb_code="V1"))
        assert mod.coverage_pct == 0.0

    def test_t12_summary_certified_false(self) -> None:
        mod = LanguageModule(lang_id="fr", lang_name_en="French", script="Latin")
        s = mod.summary()
        assert s["certified_100"] is False


# ─── T13 — LanguageRegistry ───────────────────────────────────────────────────

class TestLanguageRegistry:
    @pytest.fixture
    def reg(self) -> LanguageRegistry:
        return LanguageRegistry()

    def test_t13_14_languages_registered(self, reg: LanguageRegistry) -> None:
        # R465-ext : le registry est passé de 14 à 16 profils (+ la + pt-BR)
        all_ids = reg.all_lang_ids()
        assert len(all_ids) == 16, f"Registry doit avoir 16 profils (14 + la + pt-BR), trouvé {len(all_ids)}"
        # Les 14 initiaux doivent toujours être présents
        for lid in LanguageRegistry.INITIAL_14_LANG_IDS:
            assert lid in all_ids, f"{lid} absent du registry"

    def test_t14_all_initial_14_present(self, reg: LanguageRegistry) -> None:
        missing = reg.missing_from_initial_14()
        assert missing == [], f"Langues manquantes dans le registre: {missing}"

    def test_t15_each_lang_has_module(self, reg: LanguageRegistry) -> None:
        for lid in LanguageRegistry.INITIAL_14_LANG_IDS:
            mod = reg.get(lid)
            assert mod is not None, f"Module absent pour lang_id={lid!r}"
            assert mod.lang_id == lid

    def test_t16_no_lang_is_certified(self, reg: LanguageRegistry) -> None:
        """Honnêteté : aucune langue ne doit prétendre être CERTIFIED."""
        for lid in reg.all_lang_ids():
            mod = reg.get(lid)
            assert mod.coverage_state != CoverageState.CERTIFIED, (
                f"INTÉGRITÉ VIOLATION: {lid} déclaré CERTIFIED sans preuve"
            )

    def test_t17_global_coverage_zero_without_reference(self, reg: LanguageRegistry) -> None:
        """Aucune source de référence définie → coverage 0%."""
        pct = reg.global_coverage_pct()
        assert pct == 0.0, f"Coverage global devrait être 0.0 (pas de référence), got {pct}"

    def test_t18_lookup_all_empty_unknown(self, reg: LanguageRegistry) -> None:
        results = reg.lookup_all("xyzunknownword123")
        assert results == {}

    def test_t19_coverage_report_has_14_entries(self, reg: LanguageRegistry) -> None:
        # R465-ext : reg.coverage_report() retourne maintenant 16 profils (14 + la + pt-BR)
        report = reg.coverage_report()
        assert len(report) == 16, (
            f"coverage_report doit retourner 16 profils (14 + la + pt-BR), trouvé {len(report)}"
        )

    def test_t20_rtl_languages_known(self, reg: LanguageRegistry) -> None:
        """AR est RTL — vérifier que le script est bien enregistré."""
        ar = reg.get("ar")
        assert ar is not None
        assert ar.script == "Arabic"

    def test_t21_singleton_is_same_object(self) -> None:
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2


# ─── T22 — Registre JSON ARTCB_14_LANGUAGES.json ─────────────────────────────

class TestLanguagesJson:
    def test_t22_json_exists(self) -> None:
        assert REGISTRY_JSON.exists(), f"Registre JSON manquant: {REGISTRY_JSON}"

    def test_t23_json_valid(self) -> None:
        data = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
        assert "languages" in data, "Clé 'languages' manquante dans le JSON"
        assert "summary" in data

    def test_t24_json_has_14_languages(self) -> None:
        data = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
        assert len(data["languages"]) == 14

    def test_t25_json_lang_ids_match_registry(self) -> None:
        data = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
        json_ids = {l["lang_id"] for l in data["languages"]}
        reg_ids = set(LanguageRegistry.INITIAL_14_LANG_IDS)
        assert json_ids == reg_ids, f"Divergence IDs JSON vs registry: {json_ids ^ reg_ids}"

    def test_t26_json_certified_100_false(self) -> None:
        """Invariant : le JSON ne doit pas mentir sur la certification."""
        data = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
        # Note générale
        summary_note = data.get("summary", {}).get("note", "")
        assert "CERTIFIED_100=false" in summary_note or "false" in summary_note.lower(), (
            "INVARIANT VIOLATION: summary.note doit indiquer CERTIFIED_100=false"
        )

    def test_t27_json_no_lang_claims_100pct(self) -> None:
        """Aucune langue ne doit prétendre à 100% sans source de référence."""
        data = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
        for lang in data["languages"]:
            if lang.get("entry_count_reference", 0) == 0:
                # Sans référence, coverage_pct doit être 0
                assert lang.get("coverage_pct", 0) == 0.0, (
                    f"INTÉGRITÉ: {lang['lang_id']} annonce coverage_pct={lang['coverage_pct']} "
                    "sans entry_count_reference défini"
                )

    def test_t28_rtl_ar_flagged(self) -> None:
        data = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
        ar = next(l for l in data["languages"] if l["lang_id"] == "ar")
        assert ar["rtl"] is True

    def test_t29_all_langs_have_required_fields(self) -> None:
        required = ["lang_id", "script", "module_version", "coverage_state",
                    "entry_count_reference", "coverage_pct", "artcb_concepts_covered"]
        data = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
        for lang in data["languages"]:
            for f in required:
                assert f in lang, f"Champ '{f}' manquant pour {lang.get('lang_id')}"

    def test_t30_coverage_state_valid_values(self) -> None:
        valid = {s.value for s in CoverageState}
        data = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
        for lang in data["languages"]:
            state = lang.get("coverage_state", "")
            assert state in valid, f"{lang['lang_id']}: coverage_state={state!r} invalide"
