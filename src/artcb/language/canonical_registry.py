"""ARTCB Canonical Language Registry — R485 — 2026-09-26.

Source de vérité unique pour toute déclaration de couverture linguistique.
Résout la divergence 14/16 langues (artcd_language_registry.json vs R471 vs concept_lexicon.py).

Règle : toute déclaration 'N langues supportées' doit appeler
    get_supported_isos()  ou  get_language_state(iso)
et NE PAS lire une constante locale.

LANGUAGE_REGISTRY_SHA : SHA-256 du fichier rules/LANGUAGE_REGISTRY_CANONICAL.json
    → toute mesure de couverture doit enregistrer ce SHA comme preuve.

CERTIFIED_100 = False — invariant absolu.
unique_human_proven = False — invariant absolu.
"""
from __future__ import annotations

MODULE_VERSION = "1.0.1"  # R485

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.language.canonical_registry")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CANONICAL_FILE = _REPO_ROOT / "rules" / "LANGUAGE_REGISTRY_CANONICAL.json"

# Invariants absolus
CERTIFIED_100 = False
UNIQUE_HUMAN_PROVEN = False


# ─── Structures ───────────────────────────────────────────────────────────────

@dataclass
class LanguageState:
    """État réel d'une langue dans le registre canonique ARTCB.

    Propriétés clés:
        iso              : code ISO 639-1 (ex: 'fr', 'ar')
        name             : nom anglais
        concept_lexicon_status : PARTIAL | NOT_STARTED | NOT_IN_REGISTRY
        r471_resolved    : nombre d'entrées résolues dans R471 (0 = aucune)
        r471_resolution_rate_pct : taux de résolution R471 (%)
        artcd_registry_status : état dans artcd_language_registry.json
        has_divergence   : True si concept_lexicon ≠ artcd_registry
        g10_target       : True si langue prioritaire G10
        tokenizer        : description du tokenizer disponible
        known_gaps       : lacunes documentées
    """
    iso: str
    name: str
    script: str
    direction: str
    concept_lexicon_status: str
    r471_entries: int
    r471_resolved: int
    r471_resolution_rate_pct: float
    artcd_registry_status: str
    has_divergence: bool
    g10_target: bool
    i18n_ui: str
    tokenizer: str
    known_gaps: str
    concept_lexicon_note: str = ""
    artcd_registry_note: str = ""
    divergence_note: str = ""


@dataclass
class CanonicalRegistrySummary:
    """Résumé du registre canonique."""
    registry_version: str
    registry_sha: str
    total_declared: int
    concept_lexicon_partial: int
    concept_lexicon_not_started: int
    r471_corpus_processed: int
    r471_total_entries: int
    r471_total_resolved: int
    r471_global_resolution_rate_pct: float
    r471_git_sha: str
    divergences_count: int
    certified_100: bool = False
    unique_human_proven: bool = False


# ─── Chargement ───────────────────────────────────────────────────────────────

class CanonicalLanguageRegistry:
    """Registre canonique des langues ARTCB.

    Charge rules/LANGUAGE_REGISTRY_CANONICAL.json et expose :
      - get_supported_isos()       → liste des ISO supportés
      - get_language_state(iso)    → LanguageState ou None
      - get_summary()              → CanonicalRegistrySummary
      - assert_registry_sha(sha)   → vérifie que le fichier n'a pas changé
      - get_divergences()          → langues avec divergence registry vs reality
      - get_by_lexicon_status(s)   → langues par statut
    """

    def __init__(self, registry_path: Path | None = None) -> None:
        self._path = registry_path or _CANONICAL_FILE
        self._data: dict[str, Any] = {}
        self._languages: dict[str, LanguageState] = {}
        self._sha: str = ""
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            logger.error("CanonicalLanguageRegistry: fichier absent — %s", self._path)
            return
        try:
            raw = self._path.read_bytes()
            self._sha = hashlib.sha256(raw).hexdigest()
            self._data = json.loads(raw.decode("utf-8"))
            for lang in self._data.get("languages", []):
                iso = lang.get("iso", "")
                if not iso:
                    continue
                divergence_raw = lang.get("divergence", "")
                has_div = bool(divergence_raw)
                state = LanguageState(
                    iso=iso,
                    name=lang.get("name", ""),
                    script=lang.get("script", ""),
                    direction=lang.get("direction", "ltr"),
                    concept_lexicon_status=lang.get("concept_lexicon_status", "UNKNOWN"),
                    r471_entries=lang.get("r471_entries", 0),
                    r471_resolved=lang.get("r471_resolved", 0),
                    r471_resolution_rate_pct=lang.get("r471_resolution_rate_pct", 0.0),
                    artcd_registry_status=lang.get("artcd_registry_status", "UNKNOWN"),
                    has_divergence=has_div,
                    g10_target=lang.get("g10_target", False),
                    i18n_ui=lang.get("i18n_ui", "NOT_DONE"),
                    tokenizer=lang.get("tokenizer", "UNKNOWN"),
                    known_gaps=lang.get("known_gaps", ""),
                    concept_lexicon_note=lang.get("concept_lexicon_note", ""),
                    artcd_registry_note=lang.get("artcd_registry_note", ""),
                    divergence_note=divergence_raw,
                )
                self._languages[iso] = state
            logger.debug(
                "CanonicalLanguageRegistry chargé: %d langues, sha=%s",
                len(self._languages), self._sha[:12]
            )
        except Exception as exc:
            logger.error("CanonicalLanguageRegistry._load: erreur — %s", exc)

    # ─── API publique ─────────────────────────────────────────────────────────

    def get_supported_isos(self) -> list[str]:
        """Liste des ISO supportés dans le registre canonique."""
        return sorted(self._languages.keys())

    def get_language_state(self, iso: str) -> LanguageState | None:
        """Retourne l'état d'une langue par son ISO 639-1.

        Args:
            iso: code ISO 639-1 (ex: 'fr', 'ar', 'pt-BR')

        Returns:
            LanguageState ou None si absent du registre.
        """
        return self._languages.get(iso)

    def get_summary(self) -> CanonicalRegistrySummary:
        """Résumé agrégé du registre."""
        meta = self._data.get("summary", {})
        return CanonicalRegistrySummary(
            registry_version=self._data.get("_meta", {}).get("version", "UNKNOWN"),
            registry_sha=self._sha,
            total_declared=meta.get("total_declared", len(self._languages)),
            concept_lexicon_partial=meta.get("concept_lexicon_partial", 0),
            concept_lexicon_not_started=meta.get("concept_lexicon_not_started", 0),
            r471_corpus_processed=meta.get("r471_corpus_processed", 0),
            r471_total_entries=meta.get("r471_total_entries", 0),
            r471_total_resolved=meta.get("r471_total_resolved", 0),
            r471_global_resolution_rate_pct=meta.get("r471_global_resolution_rate_pct", 0.0),
            r471_git_sha=meta.get("r471_git_sha", ""),
            divergences_count=len(self.get_divergences()),
            certified_100=False,
            unique_human_proven=False,
        )

    def assert_registry_sha(self, expected_sha: str) -> bool:
        """Vérifie que le SHA-256 du fichier correspond à expected_sha.

        Utilisation : toute mesure de couverture linguistique doit appeler
        cette méthode pour garantir qu'elle s'appuie sur la version attendue.

        Returns:
            True si le SHA correspond, False sinon.
        """
        return self._sha == expected_sha

    def get_registry_sha(self) -> str:
        """Retourne le SHA-256 du fichier registre (LANGUAGE_REGISTRY_SHA)."""
        return self._sha

    def get_divergences(self) -> list[LanguageState]:
        """Retourne les langues avec divergence registry vs reality."""
        return [lang for lang in self._languages.values() if lang.has_divergence]

    def get_by_lexicon_status(self, status: str) -> list[LanguageState]:
        """Retourne les langues par statut concept_lexicon.

        Args:
            status: 'PARTIAL' | 'NOT_STARTED' | 'NOT_IN_REGISTRY'
        """
        return [
            lang for lang in self._languages.values()
            if lang.concept_lexicon_status == status
        ]

    def get_g10_languages(self) -> list[LanguageState]:
        """Retourne les langues prioritaires G10."""
        return [lang for lang in self._languages.values() if lang.g10_target]

    def get_r471_resolution_table(self) -> list[dict[str, Any]]:
        """Tableau de résolution R471 par langue, trié par taux décroissant."""
        rows = [
            {
                "iso": lang.iso,
                "name": lang.name,
                "r471_entries": lang.r471_entries,
                "r471_resolved": lang.r471_resolved,
                "r471_resolution_rate_pct": lang.r471_resolution_rate_pct,
                "concept_lexicon_status": lang.concept_lexicon_status,
                "has_divergence": lang.has_divergence,
            }
            for lang in self._languages.values()
        ]
        return sorted(rows, key=lambda r: r["r471_resolution_rate_pct"], reverse=True)


# ─── Instance globale (singleton paresseux) ───────────────────────────────────

_registry_instance: CanonicalLanguageRegistry | None = None


def get_registry() -> CanonicalLanguageRegistry:
    """Retourne l'instance globale du registre canonique (singleton paresseux)."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = CanonicalLanguageRegistry()
    return _registry_instance


# ─── Fonctions de commodité ───────────────────────────────────────────────────

def get_supported_isos() -> list[str]:
    """Raccourci : liste des ISO supportés."""
    return get_registry().get_supported_isos()


def get_language_state(iso: str) -> LanguageState | None:
    """Raccourci : état d'une langue."""
    return get_registry().get_language_state(iso)


def get_language_registry_sha() -> str:
    """Raccourci : SHA-256 du registre canonique (LANGUAGE_REGISTRY_SHA)."""
    return get_registry().get_registry_sha()


# ─── CLI minimal ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import logging as _logging
    _logging.basicConfig(level=_logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

    reg = CanonicalLanguageRegistry()
    summary = reg.get_summary()
    print(f"[R485] Registre canonique ARTCB — v{summary.registry_version}")
    print(f"  SHA: {summary.registry_sha[:16]}...")
    print(f"  Langues: {summary.total_declared}")
    print(f"  R471 entries: {summary.r471_total_entries:,}")
    print(f"  R471 resolved: {summary.r471_total_resolved:,} ({summary.r471_global_resolution_rate_pct:.4f}%)")
    print(f"  Divergences: {summary.divergences_count}")
    print(f"  CERTIFIED_100: {summary.certified_100}")
    print()
    print("Langues avec divergences registry vs reality:")
    for lang in reg.get_divergences():
        print(f"  [{lang.iso}] {lang.name} — {lang.divergence_note}")
    print()
    print("Table résolution R471 (top 5):")
    for row in reg.get_r471_resolution_table()[:5]:
        print(f"  {row['iso']:6s} {row['r471_resolved']:5d}/{row['r471_entries']:>10,} = {row['r471_resolution_rate_pct']:.4f}%")
    sys.exit(0)
