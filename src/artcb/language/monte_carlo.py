"""R489 — ARTCB Monte Carlo Linguistique — moteur de découverte de défauts.

Brique de développement du langage ARTCB (R486 ordre expert) :

  R489 : Monte Carlo linguistique — générateur automatique de cas difficiles
         intégré à la boucle Lineage → correction → test → non-régression.

Architecture (boucle fermée) :
    ┌──────────────────────────────────┐
    │  MonteCarloLinguistic            │
    │                                  │
    │  generate_variations()           │
    │    ↓ texte + variante            │
    │  trace_lineage() (R488)          │
    │    ↓ SemanticLineage             │
    │    ├── PASS → corpus_ok          │
    │    └── FAIL → MonteCarloFinding  │
    │              (couche + cause)    │
    └──────────────────────────────────┘

Générateurs de variations :
    1. CASE       : majuscules / minuscules / TOUT_CAPS / Titre
    2. WHITESPACE : espaces multiples, tabulations, zéro-espace
    3. NOISE      : fautes de frappe communes (transposition, suppression)
    4. SYNONYM    : variantes lexicales connues (depuis concept_lexicon.py)
    5. NEGATION   : phrases négatives (ne...pas, not, no, nicht, не...)
    6. WORD_ORDER : ordre alternatif des mots
    7. PUNCTUATION: virgules, points, tirets, guillemets
    8. TRUNCATION : mots tronqués (préfixes/suffixes)
    9. CONCAT     : concaténation de deux concepts (ambiguïté intentionnelle)
    10. UNICODE   : variantes Unicode (homoglyphes, combinaisons diacritiques)

Résultat :
    - MonteCarloFinding : cas échouant + couche d'erreur + lineage_id
    - Ces cas deviennent automatiquement des tests de non-régression
      (exportables en pytest via `export_regression_tests()`)

Propriétés :
    - Déterministe : seed fixe → mêmes cas générés → reproductible
    - Non-destructif : ne modifie pas les adapters
    - Honnête : un FAIL = défaut réel (pas un faux positif de test)
    - CERTIFIED_100=False | unique_human_proven=False

CERTIFIED_100=false | unique_human_proven=False
"""
from __future__ import annotations

MODULE_VERSION = "1.0.1"  # R489

import hashlib
import json
import logging
import random
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.language.monte_carlo")

DEBUG_MODE = True  # PROTOCOLE ARTCB — mode DEBUG permanent

# Invariants absolus
CERTIFIED_100 = False
UNIQUE_HUMAN_PROVEN = False

_REPO_ROOT = Path(__file__).resolve().parents[3]


# ─── Types de variations ──────────────────────────────────────────────────────

VARIATION_TYPES = [
    "case_upper",
    "case_lower",
    "case_title",
    "case_mixed",
    "whitespace_extra",
    "whitespace_tab",
    "noise_transpose",
    "noise_delete_char",
    "noise_duplicate_char",
    "synonym_variant",
    "negation",
    "word_order_reverse",
    "punctuation_add",
    "truncation_suffix",
    "truncation_prefix",
    "concat_two_concepts",
    "unicode_nfd",
    "unicode_ascii_only",
]


# ─── Résultat d'un cas Monte Carlo ───────────────────────────────────────────

@dataclass
class MonteCarloCase:
    """Un cas généré par le Monte Carlo linguistique.

    Peut être PASS (le concept est correctement résolu) ou FAIL (défaut détecté).
    """

    case_id: str                     # identifiant unique déterministe
    lang: str                        # code langue ISO 639-1
    original_text: str               # texte de référence
    variation_text: str              # texte après variation
    variation_type: str              # type de variation appliquée
    expected_artcb_code: str | None  # code attendu (depuis la référence)
    actual_artcb_code: str | None    # code obtenu sur la variation
    is_pass: bool                    # True si le concept est conservé
    lineage_id: str | None = None    # lineage_id du run sur variation_text
    first_error_step: str | None = None  # couche d'erreur si FAIL
    round_trip_ok: bool = False
    is_ok: bool = True               # lineage sans erreur interne
    duration_ms: float = 0.0

    # Invariants
    unique_human_proven: bool = False
    certified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "lang": self.lang,
            "original_text": self.original_text,
            "variation_text": self.variation_text,
            "variation_type": self.variation_type,
            "expected_artcb_code": self.expected_artcb_code,
            "actual_artcb_code": self.actual_artcb_code,
            "is_pass": self.is_pass,
            "lineage_id": self.lineage_id,
            "first_error_step": self.first_error_step,
            "round_trip_ok": self.round_trip_ok,
            "is_ok": self.is_ok,
            "duration_ms": round(self.duration_ms, 3),
            "unique_human_proven": self.unique_human_proven,
            "certified": self.certified,
        }


@dataclass
class MonteCarloFinding:
    """Défaut détecté par le Monte Carlo (cas FAIL ou DEGRADED).

    Un finding = un nouveau cas de test de non-régression potentiel.
    Il est exportable en pytest via `export_regression_tests()`.
    """

    finding_id: str                  # SHA256 déterministe
    case: MonteCarloCase             # cas source
    severity: str                    # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    description: str                 # explication humaine
    recommendation: str              # action corrective suggérée
    adapter_version: str = ""
    timestamp_utc: float = field(default_factory=time.time)

    # Invariants
    unique_human_proven: bool = False
    certified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "severity": self.severity,
            "description": self.description,
            "recommendation": self.recommendation,
            "adapter_version": self.adapter_version,
            "timestamp_utc": self.timestamp_utc,
            "case": self.case.to_dict(),
            "unique_human_proven": self.unique_human_proven,
            "certified": self.certified,
        }


@dataclass
class MonteCarloRun:
    """Résultat complet d'un run Monte Carlo sur une langue.

    Contient tous les cas (PASS + FAIL) et les findings détectés.
    """

    run_id: str
    lang: str
    n_cases: int = 0
    n_pass: int = 0
    n_fail: int = 0
    n_error: int = 0                 # lineages avec erreur interne
    pass_rate: float = 0.0
    findings: list[MonteCarloFinding] = field(default_factory=list)
    cases: list[MonteCarloCase] = field(default_factory=list)
    duration_ms: float = 0.0
    adapter_version: str = ""

    # Invariants
    unique_human_proven: bool = False
    certified: bool = False

    def summary(self) -> str:
        return (
            f"MonteCarloRun [{self.lang}] run_id={self.run_id} "
            f"cases={self.n_cases} PASS={self.n_pass} FAIL={self.n_fail} "
            f"ERRORS={self.n_error} pass_rate={self.pass_rate:.1%} "
            f"findings={len(self.findings)} duration={self.duration_ms:.0f}ms"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "lang": self.lang,
            "n_cases": self.n_cases,
            "n_pass": self.n_pass,
            "n_fail": self.n_fail,
            "n_error": self.n_error,
            "pass_rate": round(self.pass_rate, 6),
            "adapter_version": self.adapter_version,
            "duration_ms": round(self.duration_ms, 3),
            "findings_count": len(self.findings),
            "findings": [f.to_dict() for f in self.findings],
            "cases_count": len(self.cases),
            "unique_human_proven": self.unique_human_proven,
            "certified": self.certified,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


# ─── Générateurs de variations ────────────────────────────────────────────────

def _apply_variation(text: str, variation_type: str, rng: random.Random) -> str:
    """Applique une variation à un texte source.

    Args:
        text: texte d'origine.
        variation_type: type de variation (VARIATION_TYPES).
        rng: générateur aléatoire déterministe.

    Returns:
        Texte transformé.
    """
    if variation_type == "case_upper":
        return text.upper()
    elif variation_type == "case_lower":
        return text.lower()
    elif variation_type == "case_title":
        return text.title()
    elif variation_type == "case_mixed":
        # Alternance majuscule/minuscule
        result = ""
        for i, c in enumerate(text):
            result += c.upper() if i % 2 == 0 else c.lower()
        return result
    elif variation_type == "whitespace_extra":
        words = text.split()
        return "  ".join(words)  # double espace
    elif variation_type == "whitespace_tab":
        words = text.split()
        return "\t".join(words)
    elif variation_type == "noise_transpose":
        # Transposer deux caractères adjacents au milieu d'un mot
        words = text.split()
        if not words:
            return text
        word = rng.choice(words)
        if len(word) < 3:
            return text
        idx = rng.randint(0, len(word) - 2)
        transposed = word[:idx] + word[idx + 1] + word[idx] + word[idx + 2:]
        return text.replace(word, transposed, 1)
    elif variation_type == "noise_delete_char":
        # Supprimer un caractère dans un mot
        words = text.split()
        if not words:
            return text
        word = rng.choice(words)
        if len(word) < 2:
            return text
        idx = rng.randint(0, len(word) - 1)
        deleted = word[:idx] + word[idx + 1:]
        return text.replace(word, deleted, 1)
    elif variation_type == "noise_duplicate_char":
        # Doubler un caractère
        words = text.split()
        if not words:
            return text
        word = rng.choice(words)
        if len(word) < 1:
            return text
        idx = rng.randint(0, len(word) - 1)
        duplicated = word[:idx] + word[idx] + word[idx:]
        return text.replace(word, duplicated, 1)
    elif variation_type == "synonym_variant":
        # Remplacement par un alias synonyme du concept_lexicon
        return _synonym_variant(text, rng)
    elif variation_type == "negation":
        # Ajouter une négation (langue-agnostique : "not " au début)
        return "not " + text
    elif variation_type == "word_order_reverse":
        # Inverser l'ordre des mots
        words = text.split()
        return " ".join(reversed(words))
    elif variation_type == "punctuation_add":
        # Ajouter virgule ou point final
        return text + rng.choice([",", ".", " ;", " !"])
    elif variation_type == "truncation_suffix":
        # Tronquer le dernier caractère d'un mot
        words = text.split()
        if not words:
            return text
        word = rng.choice(words)
        if len(word) > 2:
            truncated = word[:-1]
            return text.replace(word, truncated, 1)
        return text
    elif variation_type == "truncation_prefix":
        # Tronquer le premier caractère d'un mot
        words = text.split()
        if not words:
            return text
        word = rng.choice(words)
        if len(word) > 2:
            truncated = word[1:]
            return text.replace(word, truncated, 1)
        return text
    elif variation_type == "concat_two_concepts":
        # Concaténer avec un autre concept commun (ambiguïté intentionnelle)
        second = rng.choice(["block", "node", "wallet", "data", "hash"])
        return text + " " + second
    elif variation_type == "unicode_nfd":
        # Décomposition NFD (diacritiques séparés)
        return unicodedata.normalize("NFD", text)
    elif variation_type == "unicode_ascii_only":
        # Translittération approximative vers ASCII (strip diacritiques)
        nfd = unicodedata.normalize("NFD", text)
        return "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    else:
        return text  # variation inconnue → texte inchangé


def _synonym_variant(text: str, rng: random.Random) -> str:
    """Remplace un mot par un alias synonyme depuis le concept_lexicon.

    Cherche les aliases qui pourraient être des variantes du texte original
    et en sélectionne un aléatoirement.
    """
    try:
        from src.artcb.ir.concept_lexicon import (  # noqa: PLC0415
            ACTION_ALIASES, OBJECT_ALIASES, MODIFIER_ALIASES,
        )
    except ImportError:
        return text

    text_lower = text.lower()
    candidates: list[str] = []
    # Trouver les aliases qui matchent dans le texte actuel
    for alias_dict in [ACTION_ALIASES, OBJECT_ALIASES, MODIFIER_ALIASES]:
        for alias, code in alias_dict.items():
            if alias.lower() in text_lower and len(alias) > 2:
                # Chercher d'autres aliases pour le même code
                same_code_aliases = [k for k, v in alias_dict.items() if v == code and k != alias]
                candidates.extend(same_code_aliases[:3])

    if candidates:
        replacement = rng.choice(candidates)
        # Remplacer la première occurrence
        words = text.split()
        for i, word in enumerate(words):
            if word.lower() in {a.lower() for a in candidates}:
                words[i] = replacement
                return " ".join(words)

    return text  # pas de variante trouvée


# ─── Moteur principal Monte Carlo ─────────────────────────────────────────────

def _make_case_id(lang: str, original: str, variation_type: str, variation: str) -> str:
    """Génère un case_id déterministe."""
    payload = f"{lang}|{original}|{variation_type}|{variation}"
    return hashlib.sha256(payload.encode()).hexdigest()[:20]


def _make_finding_id(case_id: str, severity: str) -> str:
    """Génère un finding_id déterministe."""
    return hashlib.sha256(f"FINDING:{case_id}:{severity}".encode()).hexdigest()[:20]


def _classify_severity(
    expected_code: str | None,
    actual_code: str | None,
    has_lineage_error: bool,
) -> str:
    """Classifie la sévérité d'un défaut.

    CRITICAL : le code attendu ≠ None mais code obtenu = None ou totalement différent
    HIGH     : le code obtenu est UNK alors qu'un code valide était attendu
    MEDIUM   : erreur interne dans le lineage (couche défaillante)
    LOW      : variation bénigne (round_trip_ok=False mais code conservé)
    """
    if has_lineage_error:
        return "MEDIUM"
    if expected_code and expected_code != "UNK":
        if actual_code is None or actual_code == "UNK":
            return "HIGH"
        if actual_code != expected_code:
            return "CRITICAL"
    return "LOW"


def run_monte_carlo(
    lang: str,
    seed_texts: list[tuple[str, str | None]],
    *,
    variation_types: list[str] | None = None,
    seed: int = 0x41525443,  # "ARTC" déterministe
    max_cases: int | None = None,
    adapter=None,
    semantic_corpus=None,
) -> MonteCarloRun:
    """Lance un run Monte Carlo sur une langue.

    Pour chaque (texte_source, code_attendu) dans seed_texts, génère des
    variations et trace le lineage. Les cas FAIL deviennent des MonteCarloFinding.

    Args:
        lang: code langue ISO 639-1.
        seed_texts: liste de (texte, code_artcb_attendu_ou_None).
            Si code=None, le code de référence est calculé automatiquement
            en lançant trace_lineage(texte) sur le texte original.
        variation_types: liste des types de variations à appliquer.
            Par défaut : VARIATION_TYPES complet.
        seed: graine déterministe pour le générateur aléatoire.
        max_cases: limite le nombre de cas (None = tous).
        adapter: instance LanguageAdapter partagée (créée si None).
        semantic_corpus: instance SemanticCorpus partagée (créée si None).

    Returns:
        MonteCarloRun avec tous les cas et findings.
    """
    from src.artcb.language.adapter import SemanticCorpus, get_adapter  # noqa: PLC0415
    from src.artcb.language.lineage import trace_lineage  # noqa: PLC0415

    t_start = time.perf_counter()

    # Initialisation
    if adapter is None:
        adapter = get_adapter(lang)
    if adapter is None:
        logger.warning("run_monte_carlo: adapteur manquant pour lang=%r", lang)
        return MonteCarloRun(
            run_id=hashlib.sha256(f"MC:{lang}:{seed}".encode()).hexdigest()[:16],
            lang=lang,
        )

    if semantic_corpus is None:
        semantic_corpus = SemanticCorpus()

    variations_to_apply = variation_types if variation_types is not None else VARIATION_TYPES

    rng = random.Random(seed)

    # run_id déterministe
    run_id = hashlib.sha256(
        f"MC-RUN:{lang}:{seed}:{sorted(variations_to_apply)}:{[t for t, _ in seed_texts]}".encode()
    ).hexdigest()[:16]

    try:
        import src.artcb.language.adapter as _adm  # noqa: PLC0415
        adapter_version = getattr(_adm, "MODULE_VERSION", "?")
    except Exception:  # noqa: BLE001
        adapter_version = "?"

    run = MonteCarloRun(
        run_id=run_id,
        lang=lang,
        adapter_version=adapter_version,
    )

    all_cases: list[MonteCarloCase] = []
    all_findings: list[MonteCarloFinding] = []

    # ── Étape 1 : résoudre les codes de référence sur les textes originaux ────
    reference_codes: dict[str, str | None] = {}
    for orig_text, expected_code in seed_texts:
        if expected_code is not None:
            reference_codes[orig_text] = expected_code
        else:
            # Calcul automatique
            ref_lin = trace_lineage(orig_text, lang, adapter=adapter, semantic_corpus=semantic_corpus)
            reference_codes[orig_text] = ref_lin.artcb_code
            logger.debug(
                "run_monte_carlo [%s]: référence %r → code=%r",
                lang, orig_text[:30], ref_lin.artcb_code,
            )

    # ── Étape 2 : générer et évaluer les variations ───────────────────────────
    case_count = 0
    for orig_text, _ in seed_texts:
        expected_code = reference_codes[orig_text]

        for var_type in variations_to_apply:
            if max_cases is not None and case_count >= max_cases:
                break

            # Générer la variation
            varied_text = _apply_variation(orig_text, var_type, rng)

            # Skip si la variation est identique au texte original
            if varied_text == orig_text:
                continue

            # Tracer le lineage sur la variation
            t0 = time.perf_counter()
            lin = trace_lineage(varied_text, lang, adapter=adapter, semantic_corpus=semantic_corpus)
            duration = (time.perf_counter() - t0) * 1000

            # Calculer le case_id
            case_id = _make_case_id(lang, orig_text, var_type, varied_text)

            # Déterminer PASS/FAIL
            # PASS = le code obtenu correspond au code attendu (ou les deux sont UNK)
            is_pass = (lin.artcb_code == expected_code) or (
                lin.artcb_code == "UNK" and expected_code == "UNK"
            )

            err_step_name = None
            if lin.first_error_step() is not None:
                err_step_name = lin.first_error_step().name

            case = MonteCarloCase(
                case_id=case_id,
                lang=lang,
                original_text=orig_text,
                variation_text=varied_text,
                variation_type=var_type,
                expected_artcb_code=expected_code,
                actual_artcb_code=lin.artcb_code,
                is_pass=is_pass,
                lineage_id=lin.lineage_id,
                first_error_step=err_step_name,
                round_trip_ok=lin.round_trip_ok,
                is_ok=lin.is_ok(),
                duration_ms=duration,
            )

            all_cases.append(case)
            case_count += 1

            if not is_pass or err_step_name is not None:
                severity = _classify_severity(
                    expected_code,
                    lin.artcb_code,
                    err_step_name is not None,
                )
                description = (
                    f"Variation '{var_type}' sur texte {orig_text!r} → "
                    f"code attendu={expected_code!r}, obtenu={lin.artcb_code!r}"
                    + (f", erreur couche={err_step_name}" if err_step_name else "")
                )
                recommendation = _make_recommendation(var_type, err_step_name, lang)
                finding = MonteCarloFinding(
                    finding_id=_make_finding_id(case_id, severity),
                    case=case,
                    severity=severity,
                    description=description,
                    recommendation=recommendation,
                    adapter_version=adapter_version,
                )
                all_findings.append(finding)
                logger.debug(
                    "MC FAIL [%s] %s: %r → expected=%r actual=%r step=%s",
                    lang, var_type, orig_text[:25], expected_code, lin.artcb_code, err_step_name,
                )
        else:
            continue
        break

    # ── Étape 3 : statistiques ─────────────────────────────────────────────────
    run.cases = all_cases
    run.findings = all_findings
    run.n_cases = len(all_cases)
    run.n_pass = sum(1 for c in all_cases if c.is_pass)
    run.n_fail = sum(1 for c in all_cases if not c.is_pass)
    run.n_error = sum(1 for c in all_cases if not c.is_ok)
    run.pass_rate = run.n_pass / run.n_cases if run.n_cases > 0 else 0.0
    run.duration_ms = (time.perf_counter() - t_start) * 1000

    logger.info("MC RUN DONE: %s", run.summary())
    return run


def _make_recommendation(
    variation_type: str,
    error_step: str | None,
    lang: str,
) -> str:
    """Génère une recommandation corrective selon le type de variation et la couche d'erreur."""
    if error_step == "morphology":
        return (
            f"Améliorer le lemmatiseur pour {lang!r} — "
            f"la variation {variation_type!r} casse la couche morphologique."
        )
    elif error_step == "normalize":
        return (
            f"Vérifier la normalisation Unicode pour {lang!r} — "
            f"la variation {variation_type!r} produit une sortie inattendue."
        )
    elif error_step == "map_to_concept":
        return (
            f"Enrichir les aliases du concept_lexicon pour {lang!r} — "
            f"la variation {variation_type!r} n'est pas couverte."
        )
    elif error_step == "round_trip":
        return (
            f"Vérifier le round-trip pour {lang!r} — "
            f"la variation {variation_type!r} produit une perte sémantique."
        )
    elif "noise" in variation_type:
        return (
            f"Implémenter la correction orthographique pour {lang!r} — "
            f"les fautes de frappe ({variation_type!r}) ne sont pas tolérées."
        )
    elif "case" in variation_type:
        return (
            f"Vérifier la normalisation casse pour {lang!r} — "
            f"les variations de casse ({variation_type!r}) ne sont pas tolérées."
        )
    elif "unicode" in variation_type:
        return (
            f"Renforcer la normalisation Unicode pour {lang!r} — "
            f"les variantes Unicode ({variation_type!r}) ne sont pas couvertes."
        )
    else:
        return (
            f"Investiguer la variation {variation_type!r} pour {lang!r} — "
            f"le concept n'est pas conservé sous cette transformation."
        )


# ─── Export en cas de test de non-régression ─────────────────────────────────

def export_regression_cases(
    run: MonteCarloRun,
    *,
    only_fails: bool = True,
    min_severity: str = "MEDIUM",
) -> list[dict[str, Any]]:
    """Exporte les cas du run Monte Carlo comme tests de non-régression.

    Ces cas peuvent être intégrés dans la suite pytest pour empêcher
    les régressions futures.

    Args:
        run: MonteCarloRun complet.
        only_fails: si True, n'exporte que les cas FAIL.
        min_severity: sévérité minimale pour les findings (CRITICAL>HIGH>MEDIUM>LOW).

    Returns:
        Liste de dicts représentant les cas de non-régression.
        Format : {"case_id", "lang", "variation_text", "expected_artcb_code",
                  "actual_artcb_code", "variation_type", "severity", "finding_id"}
    """
    severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    min_sev_val = severity_order.get(min_severity, 2)

    regression_cases: list[dict[str, Any]] = []

    # Findings avec sévérité suffisante
    for finding in run.findings:
        if severity_order.get(finding.severity, 0) >= min_sev_val:
            regression_cases.append({
                "case_id": finding.case.case_id,
                "finding_id": finding.finding_id,
                "lang": finding.case.lang,
                "original_text": finding.case.original_text,
                "variation_text": finding.case.variation_text,
                "variation_type": finding.case.variation_type,
                "expected_artcb_code": finding.case.expected_artcb_code,
                "actual_artcb_code": finding.case.actual_artcb_code,
                "severity": finding.severity,
                "first_error_step": finding.case.first_error_step,
                "lineage_id": finding.case.lineage_id,
                "description": finding.description,
                "recommendation": finding.recommendation,
            })

    if not only_fails:
        # Ajouter aussi les cas PASS comme garde-fous
        for case in run.cases:
            if case.is_pass and not any(f.case.case_id == case.case_id for f in run.findings):
                regression_cases.append({
                    "case_id": case.case_id,
                    "finding_id": None,
                    "lang": case.lang,
                    "original_text": case.original_text,
                    "variation_text": case.variation_text,
                    "variation_type": case.variation_type,
                    "expected_artcb_code": case.expected_artcb_code,
                    "actual_artcb_code": case.actual_artcb_code,
                    "severity": "PASS",
                    "first_error_step": None,
                    "lineage_id": case.lineage_id,
                    "description": "Cas PASS — garde-fou de non-régression.",
                    "recommendation": "",
                })

    return regression_cases


def save_regression_cases(
    cases: list[dict[str, Any]],
    output_path: Path | str,
) -> Path:
    """Sauvegarde les cas de non-régression dans un fichier JSON.

    Args:
        cases: liste retournée par export_regression_cases().
        output_path: chemin du fichier JSON de sortie.

    Returns:
        Chemin du fichier écrit.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)
    logger.info("save_regression_cases: %d cas écrits dans %s", len(cases), path)
    return path
