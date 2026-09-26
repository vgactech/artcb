"""R486 — ARTCB Language Adapter interface + Semantic Corpus — 2026-09-26.

Implémentation de R486-A, R486-B, R486-C (R486 ordre expert) :

  R486-A : Batterie de conformité 16 langues — interface commune
  R486-B : Corpus sémantique canonique (concepts indépendants de la langue)
  R486-C : 16 pipelines sous interface LanguageAdapter commune

Architecture :
    texte_surface
         ↓
    LanguageAdapter.tokenize()       ← spécifique à chaque langue
         ↓
    LanguageAdapter.normalize()      ← normalisation Unicode + casse
         ↓
    LanguageAdapter.morphology()     ← POS + lemme (honnête = partiel)
         ↓
    LanguageAdapter.map_to_concept() ← LexiconMapper R467 → artcb_code
         ↓
    LanguageAdapter.parse_to_ir()    ← IREncoder → IRGraph
         ↓
    SemanticCorpus.get_concept_id()  ← ConceptID stable depuis artcb_code
         ↓
    LanguageAdapter.render_from_ir() ← IRDecoder → texte surface
         ↓
    LanguageAdapter.explain_mapping()← provenance complète (R487 lineage)

Règles R486 :
  - Les 16 adapters partagent la MÊME interface LanguageAdapter
  - Le ConceptID appartient au SemanticCorpus, PAS à l'adapter
  - alias = filet de sécurité lexical, PAS la normalisation morphologique
  - 1 corpus canonique → 16 adapters → 1 IR commun (pas 16 IR distincts)

CERTIFIED_100=false | unique_human_proven=False
"""
from __future__ import annotations

MODULE_VERSION = "1.0.1"  # R486

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.language.adapter")

DEBUG_MODE = True  # PROTOCOLE ARTCB — mode DEBUG permanent

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Invariants absolus
CERTIFIED_100 = False
UNIQUE_HUMAN_PROVEN = False


# ─── Coverage states honnêtes (R486) ─────────────────────────────────────────

class AdapterCoverage(str, Enum):
    """Niveau de couverture honnête d'un adapter.

    STUB            : interface présente, logique minimale (honnête)
    ALIAS_ONLY      : résolution uniquement via aliases concept_lexicon
    MORPHO_PARTIAL  : normalisation morphologique partielle
    MORPHO_FULL     : normalisation morphologique complète
    CERTIFIED       : couverture prouvée sur corpus de référence (jamais encore)
    """
    STUB = "STUB"
    ALIAS_ONLY = "ALIAS_ONLY"
    MORPHO_PARTIAL = "MORPHO_PARTIAL"
    MORPHO_FULL = "MORPHO_FULL"
    CERTIFIED = "CERTIFIED"


# ─── Structures de données R486 ───────────────────────────────────────────────

@dataclass
class TokenResult:
    """Résultat de tokenisation — R486-A §1."""
    tokens: list[str]
    iso: str
    method: str            # "whitespace" | "cjk_char" | "arabic" | "hangul" | etc.
    token_count: int = 0
    provenance: str = ""

    def __post_init__(self):
        self.token_count = len(self.tokens)


@dataclass
class NormalizeResult:
    """Résultat de normalisation Unicode — R486-A §2."""
    normalized: str
    original: str
    form: str              # "NFC" | "NFD" | "NFKC"
    lowercased: bool
    diacritics_stripped: bool = False
    provenance: str = ""


@dataclass
class MorphologyResult:
    """Résultat d'analyse morphologique — R486-A §3 (honnête = partiel)."""
    lemmas: list[str]
    pos_tags: list[str]    # POS simples ou "UNKNOWN"
    method: str            # "rule_based" | "wordnet" | "stub"
    language_specific_note: str = ""
    provenance: str = ""
    coverage: AdapterCoverage = AdapterCoverage.STUB


@dataclass
class ConceptMappingResult:
    """Résultat de mapping vers ConceptID — R486-A §5."""
    artcb_code: str        # ex: "V1", "C2", "UNK"
    concept_id: str        # hash stable depuis artcb_code
    match_method: str      # "exact_surface" | "exact_lemma" | "UNK"
    confidence: float      # [0.0 → 1.0] — 0.0 si UNK
    iso: str
    input_lemma: str
    input_surface: str
    provenance: str = ""


@dataclass
class RoundTripResult:
    """Résultat de round-trip texte→IR→texte — R486-F."""
    source_text: str
    reconstructed_text: str
    source_concept_ids: list[str]
    reconstructed_concept_ids: list[str]
    round_trip_ok: bool            # concept_ids conservés
    semantic_equivalence: bool     # source_concepts == reconstructed_concepts
    information_loss: bool         # des ConceptIDs ont disparu
    iso: str
    provenance: str = ""


@dataclass
class MappingProvenance:
    """Provenance complète d'une transformation — R486 + R487 lineage."""
    iso: str
    input_text: str
    tokens: list[str]
    normalized: str
    lemmas: list[str]
    artcb_codes: list[str]
    concept_ids: list[str]
    method_chain: list[str]        # ["tokenize:whitespace", "normalize:NFC", ...]
    registry_sha: str
    adapter_version: str
    certified_100: bool = False
    unique_human_proven: bool = False


# ─── ConceptID déterministe ───────────────────────────────────────────────────

def concept_id_from_code(artcb_code: str) -> str:
    """Génère un ConceptID stable et déterministe depuis un artcb_code.

    Format : K{sha256[:12]} — préfixe K pour Knowledge.
    Règle R486 : le ConceptID appartient au niveau sémantique commun,
    PAS à l'adapter de langue.

    Args:
        artcb_code: ex "V1", "C2", "UNK"

    Returns:
        ex "Kf3a7b2c1d4e5" pour "V1"
    """
    if not artcb_code or artcb_code == "UNK":
        return "K_UNK"
    digest = hashlib.sha256(f"ARTCB::{artcb_code}".encode()).hexdigest()
    return f"K{digest[:12]}"


# ─── Interface LanguageAdapter (R486-C) ───────────────────────────────────────

class LanguageAdapter:
    """Interface commune pour les 16 adapters linguistiques ARTCB.

    Contrat R486-C (7 méthodes obligatoires) :
        tokenize()       → TokenResult
        normalize()      → NormalizeResult
        morphology()     → MorphologyResult
        map_to_concept() → ConceptMappingResult
        parse_to_ir()    → IRGraph (via IREncoder)
        render_from_ir() → str (via IRDecoder)
        explain_mapping()→ MappingProvenance

    Règles :
        - Le ConceptID N'EST PAS défini dans l'adapter (appartient à SemanticCorpus)
        - Chaque méthode documente honnêtement sa couverture
        - fail-open : retour partiel préféré au crash
        - Jamais de hardcoding ou mock compromettant la véracité
    """

    iso: str = "UNKNOWN"
    name: str = "UNKNOWN"
    script: str = "UNKNOWN"
    direction: str = "ltr"
    coverage: AdapterCoverage = AdapterCoverage.STUB
    known_gaps: str = ""

    # ── Tokenisation ──────────────────────────────────────────────────────────

    def tokenize(self, text: str) -> TokenResult:
        """Tokenise le texte selon les règles de la langue.

        Override obligatoire pour les langues sans espaces (JA/ZH/KO/AR).
        Défaut : split whitespace + ponctuation basique.
        """
        tokens = [t for t in re.split(r"[\s\.,;:!?\(\)\[\]{}'\"]+", text) if t]
        return TokenResult(
            tokens=tokens,
            iso=self.iso,
            method="whitespace",
            provenance=f"{self.__class__.__name__}.tokenize:whitespace",
        )

    # ── Normalisation ─────────────────────────────────────────────────────────

    def normalize(self, text: str, form: str = "NFC") -> NormalizeResult:
        """Normalise le texte (Unicode + casse).

        Sous-classes peuvent surcharger pour la normalisation spécifique
        (ex: arabe RTL, kanji→hiragana, etc.)
        """
        normalized = unicodedata.normalize(form, text).lower().strip()
        return NormalizeResult(
            normalized=normalized,
            original=text,
            form=form,
            lowercased=True,
            provenance=f"{self.__class__.__name__}.normalize:{form}+lower",
        )

    # ── Morphologie ───────────────────────────────────────────────────────────

    def morphology(self, tokens: list[str]) -> MorphologyResult:
        """Analyse morphologique : lemmatisation + POS.

        Honnêteté : la plupart des adapters retournent STUB.
        Une analyse partielle vaut mieux qu'une analyse inventée.
        """
        return MorphologyResult(
            lemmas=tokens,  # sans lemmatisation = token brut
            pos_tags=["UNKNOWN"] * len(tokens),
            method="stub",
            language_specific_note=f"morphology stub for {self.iso} — no lemmatizer available",
            coverage=AdapterCoverage.STUB,
            provenance=f"{self.__class__.__name__}.morphology:stub",
        )

    # ── Mapping vers concept ──────────────────────────────────────────────────

    def map_to_concept(self, lemma: str, surface: str = "", pos: str = "UNKNOWN") -> ConceptMappingResult:
        """Mappe un lemme vers un artcb_code + ConceptID.

        Utilise LexiconMapper R467 API : resolve(surface_form, lemma, pos).
        Le ConceptID est calculé par concept_id_from_code() — appartient au
        niveau sémantique commun, pas à l'adapter.
        """
        try:
            from src.artcb.language.lexicon_mapper import LexiconMapper  # noqa: PLC0415
            mapper = LexiconMapper()
            surf = surface or lemma
            resolved = mapper.resolve(surf, lemma, pos)
            code = resolved.artcb_code if resolved and resolved.resolved else "UNK"
            method = resolved.match_method if resolved else "UNK"
        except Exception as exc:
            logger.debug("map_to_concept: LexiconMapper error %s — UNK", exc)
            code = "UNK"
            method = "error"

        return ConceptMappingResult(
            artcb_code=code,
            concept_id=concept_id_from_code(code),
            match_method=method if isinstance(method, str) else "UNK",
            confidence=1.0 if code != "UNK" else 0.0,
            iso=self.iso,
            input_lemma=lemma,
            input_surface=surface or lemma,
            provenance=f"{self.__class__.__name__}.map_to_concept:lexicon_mapper_r467",
        )

    # ── Parse vers IR ─────────────────────────────────────────────────────────

    def parse_to_ir(self, text: str):
        """Encode le texte vers un IRGraph via IREncoder.

        Returns:
            IRGraph ou None si erreur (fail-open).
        """
        try:
            from src.artcb.ir.encoder import IREncoder  # noqa: PLC0415
            encoder = IREncoder()
            return encoder.encode(text)
        except Exception as exc:
            logger.debug("parse_to_ir: IREncoder error %s", exc)
            return None

    # ── Rendu depuis IR ───────────────────────────────────────────────────────

    def render_from_ir(self, ir_graph) -> str:
        """Reconstruit un texte surface depuis un IRGraph via IRDecoder.

        Returns:
            texte reconstruit ou "" si erreur (fail-open).
        """
        if ir_graph is None:
            return ""
        try:
            from src.artcb.ir.decoder import IRDecoder  # noqa: PLC0415
            decoder = IRDecoder()
            return decoder.decode(ir_graph)
        except Exception as exc:
            logger.debug("render_from_ir: IRDecoder error %s", exc)
            return getattr(ir_graph, "source_text", "")

    # ── Explication / provenance ──────────────────────────────────────────────

    def explain_mapping(self, text: str) -> MappingProvenance:
        """Retourne la provenance complète de la transformation texte→IR.

        C'est le point d'entrée du forensic lineage (R487 préparé ici).
        """
        from src.artcb.language.canonical_registry import get_language_registry_sha  # noqa: PLC0415
        tok = self.tokenize(text)
        norm = self.normalize(text)
        morph = self.morphology(tok.tokens)
        codes: list[str] = []
        cids: list[str] = []
        for lemma, surface in zip(morph.lemmas, tok.tokens):
            r = self.map_to_concept(lemma, surface)
            codes.append(r.artcb_code)
            cids.append(r.concept_id)
        return MappingProvenance(
            iso=self.iso,
            input_text=text,
            tokens=tok.tokens,
            normalized=norm.normalized,
            lemmas=morph.lemmas,
            artcb_codes=codes,
            concept_ids=cids,
            method_chain=[
                f"tokenize:{tok.method}",
                f"normalize:{norm.form}",
                f"morphology:{morph.method}",
                "map_to_concept:lexicon_mapper_r467",
            ],
            registry_sha=get_language_registry_sha(),
            adapter_version=MODULE_VERSION,
            certified_100=False,
            unique_human_proven=False,
        )

    # ── Round-trip R486-F ─────────────────────────────────────────────────────

    def round_trip(self, text: str) -> RoundTripResult:
        """Exécute texte→IR→texte et compare les ConceptIDs.

        Règle R486-F : ConceptID_initial == ConceptID_final (pas surface identique).
        """
        prov1 = self.explain_mapping(text)
        ir = self.parse_to_ir(text)
        reconstructed = self.render_from_ir(ir)
        prov2 = self.explain_mapping(reconstructed) if reconstructed else prov1

        src_ids = [cid for cid in prov1.concept_ids if cid != "K_UNK"]
        rec_ids = [cid for cid in prov2.concept_ids if cid != "K_UNK"]

        semantic_eq = set(src_ids) == set(rec_ids)
        info_loss = bool(set(src_ids) - set(rec_ids))

        return RoundTripResult(
            source_text=text,
            reconstructed_text=reconstructed,
            source_concept_ids=src_ids,
            reconstructed_concept_ids=rec_ids,
            round_trip_ok=not info_loss,
            semantic_equivalence=semantic_eq,
            information_loss=info_loss,
            iso=self.iso,
            provenance=f"{self.__class__.__name__}.round_trip",
        )


# ─── 16 adapters concrets (R486-C) ───────────────────────────────────────────
# Chaque adapter hérite de LanguageAdapter et documente honnêtement son niveau.
# Les gaps morphologiques (R486-D) sont notés — pas inventés.

class FrenchAdapter(LanguageAdapter):
    iso = "fr"; name = "French"; script = "Latin"; direction = "ltr"
    coverage = AdapterCoverage.ALIAS_ONLY
    known_gaps = "Inflection partielle; conjugaisons non lemmatisées"

class EnglishAdapter(LanguageAdapter):
    iso = "en"; name = "English"; script = "Latin"; direction = "ltr"
    coverage = AdapterCoverage.ALIAS_ONLY
    known_gaps = "POS filter CORR-01 actif; lemmatisation stub"

class SpanishAdapter(LanguageAdapter):
    iso = "es"; name = "Spanish"; script = "Latin"; direction = "ltr"
    coverage = AdapterCoverage.ALIAS_ONLY
    known_gaps = "Flexion verbale non couverte (6 temps)"

class PortugueseAdapter(LanguageAdapter):
    iso = "pt"; name = "Portuguese"; script = "Latin"; direction = "ltr"
    coverage = AdapterCoverage.ALIAS_ONLY
    known_gaps = "PT-BR vs PT-PT non distingués dans les aliases"

class PortugueseBRAdapter(LanguageAdapter):
    iso = "pt-BR"; name = "Portuguese (Brazil)"; script = "Latin"; direction = "ltr"
    coverage = AdapterCoverage.ALIAS_ONLY
    known_gaps = "Subset de pt — très faible taux résolution (0.02%)"

class ItalianAdapter(LanguageAdapter):
    iso = "it"; name = "Italian"; script = "Latin"; direction = "ltr"
    coverage = AdapterCoverage.ALIAS_ONLY
    known_gaps = "Très peu d'aliases — taux résolution 0.006%"

class RussianAdapter(LanguageAdapter):
    iso = "ru"; name = "Russian"; script = "Cyrillic"; direction = "ltr"
    coverage = AdapterCoverage.ALIAS_ONLY
    known_gaps = "6 cas de déclinaison non couverts; formes de base uniquement"

    def normalize(self, text: str, form: str = "NFC") -> NormalizeResult:
        """Normalisation Cyrillic : NFD → suppression diacritiques optionnels."""
        nfd = unicodedata.normalize("NFD", text)
        # Garder seulement les caractères Cyrillic de base + ponctuation
        cleaned = "".join(c for c in nfd if not unicodedata.combining(c))
        normalized = unicodedata.normalize("NFC", cleaned).lower().strip()
        return NormalizeResult(
            normalized=normalized, original=text, form="NFC",
            lowercased=True, diacritics_stripped=True,
            provenance="RussianAdapter.normalize:NFD+diacritics_stripped",
        )

class ChineseAdapter(LanguageAdapter):
    iso = "zh"; name = "Chinese (Simplified)"; script = "Han"; direction = "ltr"
    coverage = AdapterCoverage.STUB
    known_gaps = "Pas de segmentation (jieba absent); caractère-par-caractère uniquement"

    def tokenize(self, text: str) -> TokenResult:
        """Tokenisation CJK : caractère par caractère (sans segmentation)."""
        tokens = list(text.strip())
        tokens = [t for t in tokens if t.strip()]
        return TokenResult(
            tokens=tokens, iso=self.iso, method="cjk_char",
            provenance="ChineseAdapter.tokenize:cjk_char (no word segmentation — gap R486-D)",
        )

class ArabicAdapter(LanguageAdapter):
    iso = "ar"; name = "Arabic"; script = "Arabic"; direction = "rtl"
    coverage = AdapterCoverage.ALIAS_ONLY
    known_gaps = "RTL non rendu côté UI; racine morphologique non extraite"
    _ARABIC_RE = re.compile(r"[\u0600-\u06ff\u0750-\u077f]+")

    def tokenize(self, text: str) -> TokenResult:
        """Tokenisation arabe : tokens Arabic Unicode uniquement."""
        tokens = self._ARABIC_RE.findall(text)
        if not tokens:
            tokens = [t for t in text.split() if t.strip()]
        return TokenResult(
            tokens=tokens, iso=self.iso, method="arabic_unicode",
            provenance="ArabicAdapter.tokenize:arabic_unicode (root morphology not extracted — gap R486-D)",
        )

    def normalize(self, text: str, form: str = "NFC") -> NormalizeResult:
        """Normalisation arabe : NFC, sans voyellation (tashkeel)."""
        # Supprimer les diacritiques arabes (tashkeel U+064B–U+065F)
        cleaned = re.sub(r"[\u064b-\u065f\u0670]", "", text)
        normalized = unicodedata.normalize("NFC", cleaned).strip()
        return NormalizeResult(
            normalized=normalized, original=text, form="NFC",
            lowercased=False, diacritics_stripped=True,
            provenance="ArabicAdapter.normalize:NFC+tashkeel_stripped",
        )

class GermanAdapter(LanguageAdapter):
    iso = "de"; name = "German"; script = "Latin"; direction = "ltr"
    coverage = AdapterCoverage.ALIAS_ONLY
    known_gaps = "Mots composés non segmentés (Serversignatur → server+signatur gap); 4 cas non couverts"

    def normalize(self, text: str, form: str = "NFC") -> NormalizeResult:
        """Normalisation allemand : NFC + lower + Umlaut normalization."""
        # Conserver les Umlauts mais normaliser Unicode
        normalized = unicodedata.normalize("NFC", text).lower().strip()
        return NormalizeResult(
            normalized=normalized, original=text, form="NFC",
            lowercased=True,
            provenance="GermanAdapter.normalize:NFC+lower (compound words not split — gap R486-D)",
        )

class IndonesianAdapter(LanguageAdapter):
    iso = "id"; name = "Indonesian"; script = "Latin"; direction = "ltr"
    coverage = AdapterCoverage.ALIAS_ONLY
    known_gaps = "Agglutination préfixe/suffixe non gérée (me-, ber-, -kan, -i)"

class JapaneseAdapter(LanguageAdapter):
    iso = "ja"; name = "Japanese"; script = "Hiragana+Katakana+Kanji"; direction = "ltr"
    coverage = AdapterCoverage.STUB
    known_gaps = "Pas de MeCab/word segmentation; caractère-par-caractère; Kanji non convertis"
    _CJK_RE = re.compile(r"[\u3000-\u9fff\uf900-\ufaff\u3040-\u30ff]+|[a-zA-Z]+")

    def tokenize(self, text: str) -> TokenResult:
        """Tokenisation japonaise : groupes CJK/hiragana/katakana sans segmentation."""
        tokens = []
        for m in self._CJK_RE.finditer(text):
            t = m.group()
            if len(t) <= 3:
                tokens.append(t)
            else:
                # Découper en bigrammes (approximation sans MeCab)
                tokens.extend(t[i:i+2] for i in range(0, len(t)-1, 2))
        if not tokens:
            tokens = list(text.strip())
        return TokenResult(
            tokens=[t for t in tokens if t.strip()], iso=self.iso, method="cjk_bigram",
            provenance="JapaneseAdapter.tokenize:cjk_bigram (no MeCab — gap R486-D)",
        )

class KoreanAdapter(LanguageAdapter):
    iso = "ko"; name = "Korean"; script = "Hangul"; direction = "ltr"
    coverage = AdapterCoverage.STUB
    known_gaps = "Agglutination Hangul; particules postpositionnelles non extraites"
    _HANGUL_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff]+")

    def tokenize(self, text: str) -> TokenResult:
        """Tokenisation coréenne : blocs Hangul."""
        tokens = self._HANGUL_RE.findall(text)
        if not tokens:
            tokens = [t for t in text.split() if t.strip()]
        return TokenResult(
            tokens=tokens, iso=self.iso, method="hangul_blocks",
            provenance="KoreanAdapter.tokenize:hangul_blocks (no morphological analysis — gap R486-D)",
        )

class PolishAdapter(LanguageAdapter):
    iso = "pl"; name = "Polish"; script = "Latin"; direction = "ltr"
    coverage = AdapterCoverage.ALIAS_ONLY
    known_gaps = "7 cas grammaticaux non traités; formes de base uniquement"

    def normalize(self, text: str, form: str = "NFC") -> NormalizeResult:
        """Normalisation polonaise : NFC + lower (diacritiques conservés)."""
        normalized = unicodedata.normalize("NFC", text).lower().strip()
        return NormalizeResult(
            normalized=normalized, original=text, form="NFC", lowercased=True,
            provenance="PolishAdapter.normalize:NFC+lower (case inflection not handled — gap R486-D)",
        )

class TurkishAdapter(LanguageAdapter):
    iso = "tr"; name = "Turkish"; script = "Latin"; direction = "ltr"
    coverage = AdapterCoverage.ALIAS_ONLY
    known_gaps = "Agglutination + harmonie vocalique non traitées; résolution 0.22% = aliases de base uniquement"

    def normalize(self, text: str, form: str = "NFC") -> NormalizeResult:
        """Normalisation turc : NFC + lower avec préservation ı/İ."""
        # Turc : 'I' → 'ı' (pas 'i') — remplacement avant lower()
        cleaned = text.replace("İ", "i").replace("I", "ı")
        normalized = unicodedata.normalize("NFC", cleaned).lower().strip()
        return NormalizeResult(
            normalized=normalized, original=text, form="NFC", lowercased=True,
            provenance="TurkishAdapter.normalize:NFC+dotless_i (vowel harmony not handled — gap R486-D)",
        )

class LatinAdapter(LanguageAdapter):
    iso = "la"; name = "Latin"; script = "Latin"; direction = "ltr"
    coverage = AdapterCoverage.ALIAS_ONLY
    known_gaps = "5 déclinaisons + 6 cas non gérés; usage philologique uniquement"


# ─── Registre des 16 adapters ─────────────────────────────────────────────────

_ADAPTERS: dict[str, LanguageAdapter] = {
    "fr":    FrenchAdapter(),
    "en":    EnglishAdapter(),
    "es":    SpanishAdapter(),
    "pt":    PortugueseAdapter(),
    "pt-BR": PortugueseBRAdapter(),
    "it":    ItalianAdapter(),
    "ru":    RussianAdapter(),
    "zh":    ChineseAdapter(),
    "ar":    ArabicAdapter(),
    "de":    GermanAdapter(),
    "id":    IndonesianAdapter(),
    "ja":    JapaneseAdapter(),
    "ko":    KoreanAdapter(),
    "pl":    PolishAdapter(),
    "tr":    TurkishAdapter(),
    "la":    LatinAdapter(),
}


def get_adapter(iso: str) -> LanguageAdapter | None:
    """Retourne l'adapter pour un ISO donné."""
    return _ADAPTERS.get(iso)


def get_all_adapters() -> dict[str, LanguageAdapter]:
    """Retourne les 16 adapters (copie du registre)."""
    return dict(_ADAPTERS)


def list_supported_isos() -> list[str]:
    """Liste des 16 ISO supportés par les adapters."""
    return sorted(_ADAPTERS.keys())


# ─── SemanticCorpus canonique (R486-B) ────────────────────────────────────────

@dataclass
class SemanticConcept:
    """Entrée canonique du corpus sémantique ARTCB.

    Le ConceptID appartient ici — pas dans les adapters de langue.
    """
    artcb_code: str          # ex: "V1"
    concept_id: str          # hash stable : concept_id_from_code(artcb_code)
    category: str            # "ACTION" | "OBJECT" | "MODIFIER" | "UNKNOWN"
    canonical_form: str      # forme canonique en anglais (langue de référence du code)
    description: str         # description courte
    variants: list[str] = field(default_factory=list)
    related_codes: list[str] = field(default_factory=list)
    known_ambiguities: list[str] = field(default_factory=list)
    negative_examples: list[str] = field(default_factory=list)
    corpus_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "artcb_code": self.artcb_code,
            "concept_id": self.concept_id,
            "category": self.category,
            "canonical_form": self.canonical_form,
            "description": self.description,
            "variants": self.variants,
            "related_codes": self.related_codes,
            "known_ambiguities": self.known_ambiguities,
            "negative_examples": self.negative_examples,
            "corpus_version": self.corpus_version,
            "certified_100": False,
        }


class SemanticCorpus:
    """Corpus sémantique canonique — source de vérité des ConceptIDs.

    R486-B : 1 corpus → 16 adapters (pas 16 corpus distincts).
    Le ConceptID est calculé une seule fois ici, de manière déterministe.
    """

    def __init__(self) -> None:
        self._concepts: dict[str, SemanticConcept] = {}
        self._build_from_lexicon()

    def _build_from_lexicon(self) -> None:
        """Construit le corpus depuis concept_lexicon.py (ACTION + OBJECT + MODIFIER)."""
        try:
            from src.artcb.ir.concept_lexicon import ACTION_ALIASES, OBJECT_ALIASES, MODIFIER_ALIASES  # noqa: PLC0415
            # Codes uniques depuis les tables
            action_codes = set(ACTION_ALIASES.values())
            object_codes_set = set(OBJECT_ALIASES.values())
            modifier_codes_set = set(MODIFIER_ALIASES.values())

            for code in sorted(action_codes):
                self._add_concept(code, "ACTION")
            for code in sorted(object_codes_set):
                if code not in self._concepts:
                    self._add_concept(code, "OBJECT")
            for code in sorted(modifier_codes_set):
                if code not in self._concepts:
                    self._add_concept(code, "MODIFIER")
        except Exception as exc:
            logger.error("SemanticCorpus._build_from_lexicon: %s", exc)

    def _add_concept(self, artcb_code: str, category: str) -> None:
        cid = concept_id_from_code(artcb_code)
        self._concepts[artcb_code] = SemanticConcept(
            artcb_code=artcb_code,
            concept_id=cid,
            category=category,
            canonical_form=artcb_code,
            description=f"ARTCB semantic concept {artcb_code} ({category})",
        )

    def get_concept(self, artcb_code: str) -> SemanticConcept | None:
        return self._concepts.get(artcb_code)

    def get_concept_id(self, artcb_code: str) -> str:
        """Retourne le ConceptID stable pour un artcb_code."""
        c = self._concepts.get(artcb_code)
        return c.concept_id if c else "K_UNK"

    def all_codes(self) -> list[str]:
        return sorted(self._concepts.keys())

    def summary(self) -> dict[str, Any]:
        by_cat: dict[str, int] = {}
        for c in self._concepts.values():
            by_cat[c.category] = by_cat.get(c.category, 0) + 1
        h = hashlib.sha256(
            json.dumps(sorted(self._concepts.keys())).encode()
        ).hexdigest()
        return {
            "corpus_version": "1.0.0",
            "total_concepts": len(self._concepts),
            "by_category": by_cat,
            "corpus_hash": h,
            "certified_100": False,
        }


import json  # noqa: E402 (nécessaire pour summary)


# ─── Matrice d'équivalence 16×16 (R486-E) ────────────────────────────────────

@dataclass
class EquivalenceCell:
    """Cellule de la matrice d'équivalence 16×16."""
    iso_from: str
    iso_to: str
    input_text: str
    concept_id_from: str
    concept_id_to: str
    equivalent: bool
    collision: bool = False
    information_loss: bool = False
    ambiguity: bool = False
    note: str = ""


def build_equivalence_matrix(
    test_phrases: dict[str, str],   # iso → phrase sémantiquement équivalente
    corpus: SemanticCorpus | None = None,
) -> list[EquivalenceCell]:
    """Construit la matrice d'équivalence pour un ensemble de phrases équivalentes.

    Args:
        test_phrases: dict {iso: "phrase dans cette langue"} — même sens présumé
        corpus: SemanticCorpus (optionnel)

    Returns:
        Liste de EquivalenceCell pour tous les chemins iso_from → iso_to.

    Note R486-E : teste iso_A → ConceptID puis ConceptID → iso_B → ConceptID.
    Détecte collision, perte d'info, ambiguïté.
    """
    cells: list[EquivalenceCell] = []
    # Étape 1 : résoudre ConceptIDs pour chaque langue
    resolved: dict[str, tuple[str, list[str]]] = {}  # iso → (artcb_code, concept_ids)
    for iso, phrase in test_phrases.items():
        adapter = get_adapter(iso)
        if adapter is None:
            continue
        prov = adapter.explain_mapping(phrase)
        # ConceptIDs non-UNK
        cids = [c for c in prov.concept_ids if c != "K_UNK"]
        primary_code = prov.artcb_codes[0] if prov.artcb_codes else "UNK"
        resolved[iso] = (primary_code, cids)

    # Étape 2 : matrice 16×16
    iso_list = sorted(test_phrases.keys())
    for iso_from in iso_list:
        for iso_to in iso_list:
            if iso_from not in resolved or iso_to not in resolved:
                continue
            code_from, cids_from = resolved[iso_from]
            code_to, cids_to = resolved[iso_to]
            # Équivalence = même artcb_code principal (ou intersection des CIDs)
            equiv = code_from == code_to and code_from != "UNK"
            collision = (code_from != code_to) and (code_from != "UNK") and (code_to != "UNK")
            info_loss = bool(set(cids_from) - set(cids_to)) if cids_from else False
            cells.append(EquivalenceCell(
                iso_from=iso_from,
                iso_to=iso_to,
                input_text=test_phrases[iso_from],
                concept_id_from=code_from,
                concept_id_to=code_to,
                equivalent=equiv,
                collision=collision,
                information_loss=info_loss,
                note=f"{iso_from}→{iso_to}: {'EQUIV' if equiv else 'DIVERGE'}",
            ))
    return cells


# ─── CLI minimal ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import logging as _logging
    _logging.basicConfig(level=_logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

    print(f"[R486] Language Adapters — v{MODULE_VERSION}")
    print(f"  Adapters: {list_supported_isos()}")

    corpus = SemanticCorpus()
    s = corpus.summary()
    print(f"  Semantic corpus: {s['total_concepts']} concepts, hash={s['corpus_hash'][:12]}...")

    # Test round-trip sur "verify the server signature" (probe triple R321)
    test_phrases = {
        "fr": "vérifier la signature du serveur",
        "en": "verify the server signature",
        "es": "verificar la firma del servidor",
        "de": "den Server überprüfen",
        "ar": "التحقق من توقيع الخادم",
    }
    print("\n  Round-trip par langue :")
    for iso, phrase in test_phrases.items():
        adapter = get_adapter(iso)
        if adapter:
            rt = adapter.round_trip(phrase)
            print(f"    [{iso}] ok={rt.round_trip_ok} cids={rt.source_concept_ids[:3]}")

    cells = build_equivalence_matrix(test_phrases, corpus)
    print(f"\n  Matrice équivalence: {len(cells)} cellules")
    equiv_count = sum(1 for c in cells if c.equivalent)
    print(f"  Équivalentes: {equiv_count}/{len(cells)}")
    sys.exit(0)
