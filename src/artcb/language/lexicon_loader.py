"""R465 — ARTCB Lexicon Loader : chargement des dictionnaires complets dans LanguageRegistry.

Ce module charge les fichiers data/lexicons/{lang_id}_lexicon.json
(produits par scripts/artcb_r465_lexicon_build.py) dans le LanguageRegistry.

Architecture :
    data/lexicons/fr_lexicon.json  (kaikki.org/Wiktionary)
           ↓
    LexiconLoader.load(lang_id)
           ↓
    LanguageModule.entries : list[LexicalEntry]
           ↓
    coverage_state = IMPLEMENTED | UNIT_TESTED

Séparations R440/R441 maintenues :
    surface_form  ≠ lemma ≠ artcb_code ≠ ConceptID ≠ raisonnement

CERTIFIED_100=false — couverture = couverture Wiktionary de la langue.
"""
from __future__ import annotations

MODULE_VERSION = "1.0.1"  # R465 — lexicon loader

import json
import logging
from pathlib import Path
from typing import Optional

from src.artcb.language.registry import (
    CoverageState,
    LanguageModule,
    LanguageRegistry,
    LexicalEntry,
)

logger = logging.getLogger("artcb.language.lexicon_loader")

DEBUG_MODE = True  # mode DEBUG toujours actif (PROTOCOLE ARTCB)

# ── Constantes ────────────────────────────────────────────────────────────────

DEFAULT_LEXICON_DIR = Path("data/lexicons")
LEXICON_FILENAME_PATTERN = "{lang_id}_lexicon.json"


# ── LexiconLoader ─────────────────────────────────────────────────────────────

class LexiconLoader:
    """Charge les dictionnaires complets (kaikki.org) dans un LanguageRegistry.

    Usage :
        registry = get_registry()
        loader = LexiconLoader()
        loader.load_all(registry)
        # Ou une seule langue :
        loader.load(registry, "fr")
    """

    def __init__(self, lexicon_dir: Path = DEFAULT_LEXICON_DIR) -> None:
        self.lexicon_dir = Path(lexicon_dir)
        if DEBUG_MODE:
            logger.debug("[R465][DEBUG] LexiconLoader initialisé — répertoire=%s", self.lexicon_dir)

    def lexicon_path(self, lang_id: str) -> Path:
        """Chemin du fichier lexique pour une langue."""
        return self.lexicon_dir / LEXICON_FILENAME_PATTERN.format(lang_id=lang_id)

    def is_available(self, lang_id: str) -> bool:
        """Retourne True si le fichier lexique de cette langue existe."""
        return self.lexicon_path(lang_id).is_file()

    def available_languages(self) -> list[str]:
        """Liste des langues pour lesquelles un fichier lexique est disponible."""
        if not self.lexicon_dir.is_dir():
            return []
        result = []
        for p in sorted(self.lexicon_dir.glob("*_lexicon.json")):
            lang_id = p.stem.replace("_lexicon", "")
            result.append(lang_id)
        return result

    def load(self, registry: LanguageRegistry, lang_id: str) -> int:
        """Charge le lexique complet d'une langue dans son module du registre.

        Args:
            registry : LanguageRegistry cible
            lang_id  : code ISO 639-1 de la langue (ex: 'fr')

        Returns:
            Nombre d'entrées chargées (0 si fichier absent ou erreur).
        """
        path = self.lexicon_path(lang_id)
        if not path.is_file():
            logger.warning("[R465] Lexique absent pour %s : %s", lang_id, path)
            return 0

        mod = registry.get(lang_id)
        if mod is None:
            logger.warning("[R465] Module %s non enregistré dans le registry", lang_id)
            return 0

        if DEBUG_MODE:
            logger.debug("[R465][DEBUG] Chargement lexique %s depuis %s", lang_id, path)

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("[R465] Erreur lecture JSON %s : %s", path, exc)
            return 0

        raw_entries = data.get("entries", [])
        source_ref = data.get("source", "kaikki.org-wiktionary")
        build_date = data.get("build_date", "")
        raw_count = data.get("raw_entry_count", 0)
        entry_count_file = data.get("entry_count", len(raw_entries))

        logger.info(
            "[R465] %s : chargement de %d entrées (brutes=%d, date=%s)",
            lang_id, len(raw_entries), raw_count, build_date,
        )

        loaded = 0
        errors = 0
        for raw in raw_entries:
            sf = raw.get("surface_form", "").strip()
            lemma = raw.get("lemma", sf).strip()
            pos = raw.get("pos", "unknown")
            artcb_code = raw.get("artcb_code", "")
            source = raw.get("source", source_ref)

            if not sf:
                continue

            # artcb_code vide → utiliser "UNK" pour les entrées non encore résolues
            # L'encodeur IR assignera le code réel lors de la résolution sémantique
            if not artcb_code:
                artcb_code = "UNK"

            try:
                entry = LexicalEntry(
                    surface_form=sf,
                    lemma=lemma if lemma else sf,
                    artcb_code=artcb_code,
                    sense_id=pos,
                    confidence=1.0,
                    source=source,
                    note=f"R465 kaikki.org pos={pos}",
                )
                mod.add_entry(entry)
                loaded += 1
            except AssertionError as exc:
                if DEBUG_MODE:
                    logger.debug("[R465][DEBUG] Entrée rejetée (%s) : %s", sf, exc)
                errors += 1
                continue

        # Mettre à jour les métadonnées du module
        mod.source_ref = source_ref
        mod.source_version = build_date
        mod.entry_count_reference = entry_count_file
        mod.module_version = f"1.0.0-R465-{build_date[:10]}" if build_date else "1.0.0-R465"
        mod.notes = (
            f"R465 — lexique complet chargé depuis kaikki.org/Wiktionary. "
            f"Entrées chargées : {loaded}. Erreurs : {errors}. "
            f"CERTIFIED_100=false."
        )

        # Mise à jour du CoverageState selon la couverture mesurée
        if loaded > 0:
            if errors == 0:
                mod.coverage_state = CoverageState.IMPLEMENTED
            else:
                mod.coverage_state = CoverageState.PARTIALLY_IMPLEMENTED
        else:
            mod.coverage_state = CoverageState.ABSENT

        if DEBUG_MODE:
            logger.debug(
                "[R465][DEBUG] %s chargé : %d entrées, %d erreurs, coverage=%s",
                lang_id, loaded, errors, mod.coverage_state.value,
            )

        logger.info(
            "[R465] %s ✓ — %d entrées chargées (%d erreurs) — coverage=%s",
            lang_id, loaded, errors, mod.coverage_state.value,
        )
        return loaded

    def load_all(self, registry: LanguageRegistry) -> dict[str, int]:
        """Charge les lexiques de toutes les langues disponibles.

        Returns:
            dict lang_id → nb_entrées_chargées
        """
        available = self.available_languages()
        if DEBUG_MODE:
            logger.debug(
                "[R465][DEBUG] load_all : %d lexiques disponibles : %s",
                len(available), available,
            )

        results: dict[str, int] = {}
        total = 0
        for lang_id in available:
            count = self.load(registry, lang_id)
            results[lang_id] = count
            total += count

        logger.info(
            "[R465] load_all terminé : %d langues, %d entrées totales",
            len(results), total,
        )
        return results

    def coverage_report(self, registry: LanguageRegistry) -> list[dict]:
        """Rapport de couverture détaillé après chargement."""
        report = []
        for lang_id in LanguageRegistry.INITIAL_14_LANG_IDS:
            mod = registry.get(lang_id)
            available = self.is_available(lang_id)
            if mod:
                report.append({
                    "lang_id": lang_id,
                    "lang_name_en": mod.lang_name_en,
                    "lexicon_file_available": available,
                    "entry_count": mod.entry_count,
                    "entry_count_reference": mod.entry_count_reference,
                    "coverage_pct": mod.coverage_pct,
                    "coverage_state": mod.coverage_state.value,
                    "source_ref": mod.source_ref,
                    "module_version": mod.module_version,
                    "certified_100": False,
                })
            else:
                report.append({
                    "lang_id": lang_id,
                    "lexicon_file_available": available,
                    "entry_count": 0,
                    "coverage_state": "NOT_REGISTERED",
                    "certified_100": False,
                })
        return report


# ── Singleton loader ───────────────────────────────────────────────────────────

_loader: Optional[LexiconLoader] = None


def get_loader(lexicon_dir: Path = DEFAULT_LEXICON_DIR) -> LexiconLoader:
    """Retourne le singleton LexiconLoader."""
    global _loader
    if _loader is None:
        _loader = LexiconLoader(lexicon_dir=lexicon_dir)
    return _loader


def load_all_lexicons(
    registry: LanguageRegistry,
    lexicon_dir: Path = DEFAULT_LEXICON_DIR,
) -> dict[str, int]:
    """Raccourci : charge tous les lexiques disponibles dans le registry.

    Usage depuis registry.py ou main.py :
        from src.artcb.language.lexicon_loader import load_all_lexicons
        load_all_lexicons(get_registry())
    """
    loader = get_loader(lexicon_dir)
    return loader.load_all(registry)
