"""R466 — ARTCB Lexicon Mapper : résolution artcb_code UNK → codes réels.

Pour chaque entrée lexicale (surface_form, lemma, pos) des 16 profils,
ce module cherche un mapping vers un code ARTCB connu (V1, C2, S2, …)
en consultant les tables ACTION_ALIASES, OBJECT_ALIASES, MODIFIER_ALIASES
de concept_lexicon.py.

Architecture :
    LexiconEntry (lemma, surface_form, pos, artcb_code="UNK")
           ↓
    LexiconMapper.resolve(entry) → artcb_code résolu ou "UNK"
           ↓
    LexiconEntry mise à jour (artcb_code = code résolu)

Règles de priorité (ordre décroissant) :
    1. Correspondance exacte sur surface_form (casse insensible)
    2. Correspondance exacte sur lemma (casse insensible)
    3. Correspondance préfixe sur lemma (clés ACTION_ALIASES triées longest-first)
    4. UNK conservé (honnête — pas de guess)

Tables consultées (dans l'ordre) :
    ACTION_ALIASES    → codes action (V1, O1, C1, K1, A1, M1, R1, D1, U1)
    OBJECT_ALIASES    → codes objet  (C2, S2, N1, E3, B1, M1, M2, M3, P1, P2, S1)
    MODIFIER_ALIASES  → codes modif  (QH, QL, MOD, NEG, PL)

CERTIFIED_100=false — seules les ~360 clés de concept_lexicon.py sont couvertes.
Pour les 21.5M entrées restantes, artcb_code="UNK" est la réponse honnête.
"""
from __future__ import annotations

MODULE_VERSION = "1.0.1"  # R466

import logging
from dataclasses import dataclass
from typing import Optional

from src.artcb.ir.concept_lexicon import (
    ACTION_ALIASES,
    ACTION_KEYS,
    MODIFIER_ALIASES,
    MODIFIER_KEYS,
    OBJECT_ALIASES,
    OBJECT_KEYS,
)

logger = logging.getLogger("artcb.language.lexicon_mapper")

DEBUG_MODE = True  # mode DEBUG toujours actif (PROTOCOLE ARTCB)

# ── Constante ──────────────────────────────────────────────────────────────────

UNRESOLVED_CODE = "UNK"

# Priorité de résolution : action > objet > modifieur (une seule catégorie par entrée)
_TABLES_PRIORITY: list[tuple[dict[str, str], list[str]]] = [
    (ACTION_ALIASES, ACTION_KEYS),
    (OBJECT_ALIASES, OBJECT_KEYS),
    (MODIFIER_ALIASES, MODIFIER_KEYS),
]


# ── Résultat de résolution ──────────────────────────────────────────────────────

@dataclass
class MappingResult:
    """Résultat de la résolution artcb_code pour une entrée lexicale.

    Attributes:
        surface_form    : forme de surface de l'entrée
        lemma           : lemme de l'entrée
        pos             : partie du discours (pos tag)
        artcb_code      : code ARTCB résolu ('V1', 'C2', …) ou 'UNK'
        resolved        : True si un code connu a été trouvé (pas UNK)
        match_method    : méthode de résolution utilisée
        matched_key     : clé de la table qui a matché (debug)
        table_name      : nom de la table source (ACTION/OBJECT/MODIFIER)
    """
    surface_form: str
    lemma: str
    pos: str
    artcb_code: str
    resolved: bool
    match_method: str  # "exact_surface" | "exact_lemma" | "prefix_lemma" | "unresolved"
    matched_key: Optional[str] = None
    table_name: Optional[str] = None


# ── Mapper ─────────────────────────────────────────────────────────────────────

class LexiconMapper:
    """Résout artcb_code pour les entrées lexicales des 16 profils ARTCB.

    Usage :
        mapper = LexiconMapper()
        result = mapper.resolve("vérifier", "vérifier", "verb")
        # → MappingResult(artcb_code="V1", resolved=True, match_method="exact_surface")

    Le mapper est stateless et thread-safe (tables en lecture seule).
    """

    def __init__(self) -> None:
        if DEBUG_MODE:
            logger.debug(
                "[R466][DEBUG] LexiconMapper initialisé — %d clés action, %d clés objet, %d clés modif",
                len(ACTION_ALIASES),
                len(OBJECT_ALIASES),
                len(MODIFIER_ALIASES),
            )

    # ── API publique ────────────────────────────────────────────────────────────

    def resolve(
        self,
        surface_form: str,
        lemma: str,
        pos: str,
    ) -> MappingResult:
        """Résout le code ARTCB pour une entrée lexicale (surface_form, lemma, pos).

        Ordre de priorité :
            1. surface_form exact (casse insensible)
            2. lemma exact (casse insensible)
            3. préfixe sur lemma (longest-first depuis concept_lexicon._sorted_keys)
            4. UNK (honnête)

        Args:
            surface_form : mot tel qu'écrit dans le texte ('vérifier', 'cars', …)
            lemma        : forme canonique ('vérifier', 'car', …)
            pos          : catégorie grammaticale ('verb', 'noun', 'adv', …)

        Returns:
            MappingResult avec artcb_code résolu ou 'UNK'
        """
        sf_lower = surface_form.lower().strip()
        lm_lower = lemma.lower().strip()

        # 1. Correspondance exacte sur surface_form
        for table, _keys, name in self._tables_with_names():
            if sf_lower in table:
                code = table[sf_lower]
                if DEBUG_MODE:
                    logger.debug(
                        "[R466][DEBUG] EXACT_SURFACE surface=%r → code=%s (table=%s)",
                        surface_form, code, name,
                    )
                return MappingResult(
                    surface_form=surface_form,
                    lemma=lemma,
                    pos=pos,
                    artcb_code=code,
                    resolved=True,
                    match_method="exact_surface",
                    matched_key=sf_lower,
                    table_name=name,
                )

        # 2. Correspondance exacte sur lemma
        if sf_lower != lm_lower:
            for table, _keys, name in self._tables_with_names():
                if lm_lower in table:
                    code = table[lm_lower]
                    if DEBUG_MODE:
                        logger.debug(
                            "[R466][DEBUG] EXACT_LEMMA lemma=%r → code=%s (table=%s)",
                            lemma, code, name,
                        )
                    return MappingResult(
                        surface_form=surface_form,
                        lemma=lemma,
                        pos=pos,
                        artcb_code=code,
                        resolved=True,
                        match_method="exact_lemma",
                        matched_key=lm_lower,
                        table_name=name,
                    )

        # 3. Préfixe sur lemma (longest-first)
        for table, keys, name in self._tables_with_names():
            for key in keys:
                if lm_lower.startswith(key):
                    code = table[key]
                    if DEBUG_MODE:
                        logger.debug(
                            "[R466][DEBUG] PREFIX_LEMMA lemma=%r key=%r → code=%s (table=%s)",
                            lemma, key, code, name,
                        )
                    return MappingResult(
                        surface_form=surface_form,
                        lemma=lemma,
                        pos=pos,
                        artcb_code=code,
                        resolved=True,
                        match_method="prefix_lemma",
                        matched_key=key,
                        table_name=name,
                    )

        # 4. Non résolu — UNK honnête
        if DEBUG_MODE:
            logger.debug(
                "[R466][DEBUG] UNRESOLVED surface=%r lemma=%r pos=%r",
                surface_form, lemma, pos,
            )
        return MappingResult(
            surface_form=surface_form,
            lemma=lemma,
            pos=pos,
            artcb_code=UNRESOLVED_CODE,
            resolved=False,
            match_method="unresolved",
            matched_key=None,
            table_name=None,
        )

    def resolve_batch(
        self,
        entries: list[dict],
    ) -> tuple[list[dict], "MapperStats"]:
        """Résout artcb_code pour une liste d'entrées lexicales brutes (format lexicon JSON).

        Optimisé pour les grands volumes (21.5M entrées) :
        - Lookups dict O(1) uniquement (exact surface puis exact lemma)
        - Pas de recherche préfixe en mode batch : trop coûteuse (O(N×K))
          et source de faux positifs sur lemmes courts ('can', 'car', etc.)
        - Le matching préfixe reste disponible via resolve() unitaire (encodage phrase)
        - Logging DEBUG uniquement en résumé global, pas par entrée

        Args:
            entries : liste de dicts avec clés 'surface_form', 'lemma', 'pos', 'artcb_code', …

        Returns:
            tuple (entries_mises_à_jour, stats)
        """
        stats = MapperStats()
        updated: list[dict] = []

        # Index combiné clé→code — O(1) lookups — priorité ACTION > OBJECT > MODIFIER
        combined: dict[str, str] = {}
        for k, v in MODIFIER_ALIASES.items():
            combined[k] = v
        for k, v in OBJECT_ALIASES.items():
            combined[k] = v
        for k, v in ACTION_ALIASES.items():
            combined[k] = v  # ACTION prioritaire (écrase si doublon)

        for entry in entries:
            sf = entry.get("surface_form", "")
            lm = entry.get("lemma", "") or sf
            sf_l = sf.lower().strip()
            lm_l = lm.lower().strip()

            code = UNRESOLVED_CODE
            method = "unresolved"

            # 1. Exact surface O(1)
            hit = combined.get(sf_l)
            if hit is not None:
                code = hit
                method = "exact_surface"
            # 2. Exact lemma O(1) — seulement si surface ≠ lemma
            elif sf_l != lm_l:
                hit = combined.get(lm_l)
                if hit is not None:
                    code = hit
                    method = "exact_lemma"

            entry_copy = dict(entry)
            entry_copy["artcb_code"] = code

            stats.total += 1
            if code != UNRESOLVED_CODE:
                stats.resolved += 1
                stats.by_code[code] = stats.by_code.get(code, 0) + 1
                stats.by_method[method] = stats.by_method.get(method, 0) + 1
            else:
                stats.unresolved += 1

            updated.append(entry_copy)

        if DEBUG_MODE:
            logger.debug(
                "[R466][DEBUG] resolve_batch terminé — total=%d résolu=%d UNK=%d (%.4f%%)",
                stats.total, stats.resolved, stats.unresolved,
                (stats.resolved / stats.total * 100) if stats.total else 0.0,
            )

        return updated, stats

    # ── Helpers internes ────────────────────────────────────────────────────────

    @staticmethod
    def _tables_with_names() -> list[tuple[dict[str, str], list[str], str]]:
        return [
            (ACTION_ALIASES, ACTION_KEYS, "ACTION"),
            (OBJECT_ALIASES, OBJECT_KEYS, "OBJECT"),
            (MODIFIER_ALIASES, MODIFIER_KEYS, "MODIFIER"),
        ]


# ── Statistiques de mapping ─────────────────────────────────────────────────────

@dataclass
class MapperStats:
    """Statistiques de résolution après resolve_batch().

    Attributes:
        total       : nombre total d'entrées traitées
        resolved    : nombre d'entrées avec code résolu (≠ UNK)
        unresolved  : nombre d'entrées encore UNK
        by_code     : répartition par code ARTCB (ex: {'V1': 142, 'C2': 89, …})
        by_method   : répartition par méthode de résolution
    """
    total: int = 0
    resolved: int = 0
    unresolved: int = 0
    by_code: dict[str, int] = None  # type: ignore[assignment]
    by_method: dict[str, int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.by_code is None:
            self.by_code = {}
        if self.by_method is None:
            self.by_method = {}

    @property
    def resolution_rate(self) -> float:
        """Taux de résolution [0.0, 1.0]."""
        if self.total == 0:
            return 0.0
        return self.resolved / self.total

    def summary(self) -> dict:
        return {
            "total": self.total,
            "resolved": self.resolved,
            "unresolved": self.unresolved,
            "resolution_rate_pct": round(self.resolution_rate * 100, 4),
            "by_code": dict(sorted(self.by_code.items(), key=lambda x: -x[1])),
            "by_method": dict(sorted(self.by_method.items(), key=lambda x: -x[1])),
        }


# ── Singleton ───────────────────────────────────────────────────────────────────

_mapper: Optional[LexiconMapper] = None


def get_mapper() -> LexiconMapper:
    """Retourne le singleton LexiconMapper (stateless, partageable)."""
    global _mapper
    if _mapper is None:
        _mapper = LexiconMapper()
    return _mapper
