"""ARTCB Language Registry — 14 langues officielles initiales (R448).

Protocole ARTCB — mode DEBUG — jamais de stub — CERTIFIED_100=false.

Ce module définit :
  - LexicalEntry : entrée lexicale normalisée (lemme → ConceptID → code ARTCB)
  - LanguageModule : métadonnées + entrées d'une langue
  - LanguageRegistry : registre global des 14 langues

Architecture (R444/R441) :
  mot_surface_form
      ↓
  LexicalEntry (lemme normalisé)
      ↓
  ConceptID (hash déterministe ARTCB)
      ↓
  ArtcbCode (ex: V1, C2, S2, ...)
      ↓
  Symbole IR (ex: A1V1, O1C2...)

Séparations fondamentales (R440/R441) :
  LEXICON  ≠ ONTOLOGY ≠ KNOWLEDGE ≠ REASONING
  mot      ≠ sens     ≠ concept   ≠ symbole   ≠ raisonnement

Coverage states (R444 §44) :
  ABSENT | DOCUMENTED | PARTIALLY_IMPLEMENTED | IMPLEMENTED | UNIT_TESTED | CERTIFIED

CERTIFIED_100=false
"""
from __future__ import annotations
MODULE_VERSION = '1.0.2'  # R448 — language registry

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("artcb.language.registry")

# ─── Coverage states ──────────────────────────────────────────────────────────

class CoverageState(str, Enum):
    ABSENT = "ABSENT"
    DOCUMENTED = "DOCUMENTED"
    PARTIALLY_IMPLEMENTED = "PARTIALLY_IMPLEMENTED"
    IMPLEMENTED = "IMPLEMENTED"
    UNIT_TESTED = "UNIT_TESTED"
    INTEGRATION_TESTED = "INTEGRATION_TESTED"
    E2E_TESTED = "E2E_TESTED"
    LIVE_VERIFIED = "LIVE_VERIFIED"
    CERTIFIED = "CERTIFIED"


# ─── LexicalEntry ─────────────────────────────────────────────────────────────

@dataclass
class LexicalEntry:
    """Une entrée lexicale ARTCB : surface_form → lemma → artcb_code.

    Attributes:
        surface_form  : forme de surface (mot tel qu'écrit dans la langue)
        lemma         : forme canonique / racine normalisée
        artcb_code    : code ARTCB cible (ex: 'V1', 'C2', 'S2')
        sense_id      : identifiant du sens (pour la polysémie) — '' = sens unique
        confidence    : niveau de confiance 0.0→1.0
        source        : source lexicale (ex: 'wiktionary', 'manual', 'r430')
        note          : note libre (optionnel)
    """
    surface_form: str
    lemma: str
    artcb_code: str
    sense_id: str = ""
    confidence: float = 1.0
    source: str = "manual"
    note: str = ""

    def __post_init__(self) -> None:
        assert 0.0 <= self.confidence <= 1.0, f"confidence hors [0,1]: {self.confidence}"
        assert self.artcb_code, "artcb_code ne peut pas être vide"
        assert self.surface_form, "surface_form ne peut pas être vide"


# ─── LanguageModule ───────────────────────────────────────────────────────────

@dataclass
class LanguageModule:
    """Métadonnées et entrées lexicales d'une langue ARTCB.

    Chaque langue a son propre module : développé, testé et versionné
    indépendamment (R444 §3).

    Attributes:
        lang_id       : code ISO 639-1 (ex: 'fr', 'ar', 'zh')
        lang_name_en  : nom anglais de la langue
        script        : système d'écriture (ex: 'Latin', 'Arabic', 'CJK')
        module_version: version du module
        source_ref    : source lexicale de référence
        source_version: version de la source
        source_hash   : hash SHA-256 de la source ('' si non mesuré)
        entry_count_reference: nb d'entrées dans la source de référence (0=inconnu)
        entries       : liste des LexicalEntry de ce module
        coverage_state: état de couverture actuel
        notes         : notes de développement
    """
    lang_id: str
    lang_name_en: str
    script: str
    module_version: str = "0.1.0"
    source_ref: str = "manual_r448"
    source_version: str = ""
    source_hash: str = ""
    entry_count_reference: int = 0
    entries: list[LexicalEntry] = field(default_factory=list)
    coverage_state: CoverageState = CoverageState.PARTIALLY_IMPLEMENTED
    notes: str = ""

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @property
    def coverage_pct(self) -> float:
        """% des entrées de référence couvertes (0 si référence inconnue)."""
        if self.entry_count_reference == 0:
            return 0.0
        return round(100.0 * self.entry_count / self.entry_count_reference, 2)

    def lookup(self, surface_form: str) -> Optional[LexicalEntry]:
        """Cherche une entrée exacte par surface_form (casse-insensible)."""
        sf = surface_form.lower().strip()
        for e in self.entries:
            if e.surface_form.lower() == sf or e.lemma.lower() == sf:
                return e
        return None

    def add_entry(self, entry: LexicalEntry) -> None:
        self.entries.append(entry)

    def summary(self) -> dict:
        return {
            "lang_id": self.lang_id,
            "lang_name_en": self.lang_name_en,
            "script": self.script,
            "module_version": self.module_version,
            "source_ref": self.source_ref,
            "entry_count": self.entry_count,
            "entry_count_reference": self.entry_count_reference,
            "coverage_pct": self.coverage_pct,
            "coverage_state": self.coverage_state.value,
            "certified_100": False,
        }


# ─── LanguageRegistry ─────────────────────────────────────────────────────────

class LanguageRegistry:
    """Registre des 14 langues officielles initiales ARTCB (R444/R448).

    Chaque langue est enregistrée avec :
      - ses métadonnées (ISO code, script, source, coverage)
      - ses entrées lexicales (LexicalEntry)
      - son état de couverture (CoverageState)

    Ce registre est la référence officielle pour :
      - mesurer la couverture lexicale (Test A — R444 §7)
      - détecter les mots manquants
      - router les surface_form → ConceptID dans l'encodeur IR

    HONEST LIMITS (R444/R445) :
      entry_count ≠ dictionnaire complet.
      coverage_state != CERTIFIED tant que entry_count_reference non défini
      et que les tests d'intégration ne sont pas PASS.
    """

    # Les 14 langues initiales (R465) — ordre alphabétique ISO
    INITIAL_14_LANG_IDS = ("ar", "de", "en", "es", "fr", "id", "it", "ja", "ko", "pl", "pt", "ru", "tr", "zh")

    # Extension R465-ext : +2 profils (Latin + Português Brasileiro)
    # Latin = profil indépendant (≠ italien), pt-BR = variante régionale distincte de pt
    EXTENDED_2_LANG_IDS = ("la", "pt-BR")

    # Référentiel complet 16 profils
    ALL_16_LANG_IDS = INITIAL_14_LANG_IDS + EXTENDED_2_LANG_IDS

    def __init__(self) -> None:
        self._modules: dict[str, LanguageModule] = {}
        self._register_initial_14()
        self._register_extended_2()

    def _register_initial_14(self) -> None:
        """Enregistre les 14 modules linguistiques initiaux avec état honnête."""
        initial = [
            # (lang_id, name_en, script, coverage_state, notes)
            ("fr", "French",     "Latin",   CoverageState.PARTIALLY_IMPLEMENTED,
             "R321/R430: FR couverte partiellement — phrases de production PASS, dictionnaire complet NON mesuré"),
            ("en", "English",    "Latin",   CoverageState.PARTIALLY_IMPLEMENTED,
             "R321/R430: EN couverte partiellement — phrases de production PASS"),
            ("es", "Spanish",    "Latin",   CoverageState.PARTIALLY_IMPLEMENTED,
             "R321/R430: ES couverte partiellement"),
            ("pt", "Portuguese", "Latin",   CoverageState.PARTIALLY_IMPLEMENTED,
             "R321: PT minimal — carro/servidor/assinatura présents. NOTE: pt = portugais neutre commun"),
            ("it", "Italian",    "Latin",   CoverageState.PARTIALLY_IMPLEMENTED,
             "R321: IT minimal — auto/blocco présents"),
            ("ru", "Russian",    "Cyrillic",CoverageState.PARTIALLY_IMPLEMENTED,
             "R321/R430: RU partial — автомобиль/сервер/подпись couverts"),
            ("zh", "Chinese",    "CJK",     CoverageState.PARTIALLY_IMPLEMENTED,
             "R321/R430: ZH partial — 汽车/服务器/签名 couverts"),
            ("ar", "Arabic",     "Arabic",  CoverageState.PARTIALLY_IMPLEMENTED,
             "R430: AR partial — 10 concepts de production PASS"),
            ("de", "German",     "Latin",   CoverageState.PARTIALLY_IMPLEMENTED,
             "R430: DE partial — umlauts tokenisés, 10 concepts PASS"),
            ("id", "Indonesian", "Latin",   CoverageState.PARTIALLY_IMPLEMENTED,
             "R430: ID partial — 10 concepts PASS"),
            ("ja", "Japanese",   "CJK+Kana",CoverageState.PARTIALLY_IMPLEMENTED,
             "R430: JA partial — Kanji/Katakana tokenisés, 10 concepts PASS"),
            ("ko", "Korean",     "Hangul",  CoverageState.PARTIALLY_IMPLEMENTED,
             "R430: KO partial — Hangul tokenisé, 10 concepts PASS"),
            ("pl", "Polish",     "Latin",   CoverageState.PARTIALLY_IMPLEMENTED,
             "R430: PL partial — diacritiques tokenisés, 10 concepts PASS"),
            ("tr", "Turkish",    "Latin",   CoverageState.PARTIALLY_IMPLEMENTED,
             "R430: TR partial — chars spéciaux tokenisés, 10 concepts PASS"),
        ]
        for lang_id, name_en, script, state, notes in initial:
            mod = LanguageModule(
                lang_id=lang_id,
                lang_name_en=name_en,
                script=script,
                module_version="0.1.0",
                source_ref="manual_r448",
                coverage_state=state,
                notes=notes,
            )
            self._modules[lang_id] = mod
        logger.debug("LanguageRegistry: %d modules initiaux enregistrés", len(self._modules))

    def _register_extended_2(self) -> None:
        """Enregistre les 2 profils étendus R465-ext : Latin (la) + Português Brasileiro (pt-BR)."""
        extended = [
            # Latin : profil indépendant (≠ it) — kaikki.org Latin 1.2 GB (DEPRECATED mais accessible)
            ("la", "Latin",                "Latin",  CoverageState.ABSENT,
             "R465-ext: Latin — profil distinct de IT. Source: kaikki.org/Latin (DEPRECATED). "
             "Pipeline: la_lexicon.json via artcb_r465_lexicon_build.py --lang la"),
            # Português Brasileiro : variante régionale distincte de pt
            # kaikki.org n'a pas de dump pt-BR séparé → source alternative requise
            # Source retenue : corpus open-source (voir LANG_CONFIG dans le script de build)
            ("pt-BR", "Portuguese (Brazil)", "Latin", CoverageState.ABSENT,
             "R465-ext: PT-BR — variante brésilienne distincte de pt (portugais européen neutre). "
             "Source: corpus open-source pt-BR (kaikki.org n'a pas de dump pt-BR séparé). "
             "Pipeline: pt-BR_lexicon.json via artcb_r465_lexicon_build.py --lang pt-BR"),
        ]
        for lang_id, name_en, script, state, notes in extended:
            mod = LanguageModule(
                lang_id=lang_id,
                lang_name_en=name_en,
                script=script,
                module_version="0.1.0",
                source_ref="r465_ext",
                coverage_state=state,
                notes=notes,
            )
            self._modules[lang_id] = mod
        logger.debug("LanguageRegistry: +2 profils étendus enregistrés (la, pt-BR)")

    def get(self, lang_id: str) -> Optional[LanguageModule]:
        return self._modules.get(lang_id)

    def all_lang_ids(self) -> list[str]:
        return list(self._modules.keys())

    def coverage_report(self) -> list[dict]:
        """Rapport de couverture pour toutes les langues."""
        return [mod.summary() for mod in self._modules.values()]

    def missing_from_initial_14(self) -> list[str]:
        """Langues de la liste 14 initiale non encore enregistrées."""
        return [lid for lid in self.INITIAL_14_LANG_IDS if lid not in self._modules]

    def missing_from_all_16(self) -> list[str]:
        """Profils de la liste 16 (14 + la + pt-BR) non encore enregistrés."""
        return [lid for lid in self.ALL_16_LANG_IDS if lid not in self._modules]

    def global_coverage_pct(self) -> float:
        """Moyenne des couvertures des langues ayant une référence définie."""
        with_ref = [m for m in self._modules.values() if m.entry_count_reference > 0]
        if not with_ref:
            return 0.0
        return round(sum(m.coverage_pct for m in with_ref) / len(with_ref), 2)

    def lookup_all(self, surface_form: str) -> dict[str, LexicalEntry]:
        """Cherche une surface_form dans tous les modules.

        Returns:
            dict lang_id → LexicalEntry (seulement les langues avec une correspondance)
        """
        results = {}
        for lang_id, mod in self._modules.items():
            entry = mod.lookup(surface_form)
            if entry is not None:
                results[lang_id] = entry
        return results


# ─── Singleton ────────────────────────────────────────────────────────────────

_registry: Optional[LanguageRegistry] = None


def get_registry() -> LanguageRegistry:
    """Retourne le singleton LanguageRegistry."""
    global _registry
    if _registry is None:
        _registry = LanguageRegistry()
    return _registry
