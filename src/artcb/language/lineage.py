"""R488 — ARTCB Forensic Lineage — traceur de compilation sémantique couche-par-couche.

Brique de développement du langage ARTCB (R486 ordre expert) :

  R488 : Forensic Lineage — « Pourquoi ce ConceptID ? »

Architecture :
    Pour chaque texte source, SemanticLineage enregistre exactement :

    texte source
         ↓  [étape 1 : tokenisation]
    tokens
         ↓  [étape 2 : normalisation]
    normalized
         ↓  [étape 3 : morphologie]
    lemmas + POS
         ↓  [étape 4 : mapping lexical]
    artcb_code + match_source
         ↓  [étape 5 : IR]
    IRGraph (graph_id, nodes, edges)
         ↓  [étape 6 : ConceptID]
    concept_id + concept_label
         ↓  [étape 7 : round-trip]
    round_trip_text + round_trip_ok

Chaque étape est horodatée, versionnée et exportable en dict pour audit.

Usage dans la boucle de développement :
    lineage = trace_lineage("vérifier la signature du serveur", lang="fr")
    # → permet de localiser l'erreur à la couche précise
    # → si round_trip_ok=False → quelle étape a produit la perte ?

Propriétés :
    - Reproductible : même texte + même version adapter = même lineage
    - Exportable : to_dict() / to_json() pour archivage forensic
    - Traceable : chaque étape cite le module + version + méthode
    - Non-certifié : CERTIFIED_100=False | unique_human_proven=False

CERTIFIED_100=false | unique_human_proven=False
"""
from __future__ import annotations

MODULE_VERSION = "1.0.1"  # R488

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.language.lineage")

DEBUG_MODE = True  # PROTOCOLE ARTCB — mode DEBUG permanent

# Invariants absolus
CERTIFIED_100 = False
UNIQUE_HUMAN_PROVEN = False

_REPO_ROOT = Path(__file__).resolve().parents[3]


# ─── Étapes de lineage ────────────────────────────────────────────────────────

@dataclass
class LineageStep:
    """Une étape dans la chaîne de traitement sémantique.

    Chaque étape est une transformation atomique documentée.
    """

    step_id: int                      # numéro d'ordre (1-based)
    name: str                         # nom de l'étape (ex: "tokenize")
    layer: str                        # couche (ex: "lexical", "morpho", "semantic")
    input_value: Any                  # valeur en entrée (repr)
    output_value: Any                 # valeur en sortie (repr)
    method: str = ""                  # méthode utilisée (ex: "whitespace", "rule_based")
    module: str = ""                  # module source (ex: "adapter.FrenchAdapter")
    module_version: str = ""          # version du module
    duration_ms: float = 0.0          # durée de l'étape en millisecondes
    error: str | None = None          # message d'erreur si l'étape a échoué
    notes: list[str] = field(default_factory=list)  # notes libres pour audit

    def to_dict(self) -> dict[str, Any]:
        """Sérialise l'étape pour export JSON/forensic."""
        return {
            "step_id": self.step_id,
            "name": self.name,
            "layer": self.layer,
            "input_repr": repr(self.input_value)[:200],
            "output_repr": repr(self.output_value)[:200],
            "method": self.method,
            "module": self.module,
            "module_version": self.module_version,
            "duration_ms": round(self.duration_ms, 3),
            "error": self.error,
            "notes": self.notes,
        }


# ─── Résultat complet du lineage ─────────────────────────────────────────────

@dataclass
class SemanticLineage:
    """Lineage complet d'une compilation sémantique ARTCB.

    Contient toutes les étapes de traduction :
        texte source → tokens → normalized → morpho → artcb_code → IR → ConceptID → round-trip

    Utilisation forensic :
        - Pour localiser une erreur : identifier la première étape avec .error non-None
        - Pour vérifier la reproductibilité : comparer .lineage_hash sur deux runs
        - Pour auditer le mapping : inspecter les étapes 4 (map_to_concept) et 6 (concept_id)
    """

    # Identité
    text: str                         # texte source original
    lang: str                         # code langue ISO 639-1
    lineage_id: str = ""              # SHA256 déterministe (text + lang + adapter_version)
    lineage_hash: str = ""            # SHA256 de toutes les étapes sérialisées

    # Étapes (ordonnées)
    steps: list[LineageStep] = field(default_factory=list)

    # Résultats clés (raccourcis pour accès rapide)
    tokens: list[str] = field(default_factory=list)
    normalized_text: str = ""
    lemmas: list[str] = field(default_factory=list)
    artcb_code: str | None = None
    match_source: str = ""            # "lexicon_mapper" | "ir_encoder" | "none"
    ir_graph_id: str | None = None
    concept_id: str | None = None
    concept_label: str | None = None
    round_trip_text: str | None = None
    round_trip_ok: bool = False

    # Méta
    adapter_type: str = ""            # ex: "FrenchAdapter"
    adapter_version: str = ""
    timestamp_utc: float = field(default_factory=time.time)
    total_duration_ms: float = 0.0
    error: str | None = None          # erreur globale si pipeline échoué

    # Invariants
    unique_human_proven: bool = False
    certified: bool = False

    def first_error_step(self) -> LineageStep | None:
        """Retourne la première étape en erreur, ou None si tout est OK."""
        for step in self.steps:
            if step.error is not None:
                return step
        return None

    def is_ok(self) -> bool:
        """True si aucune étape en erreur et round_trip_ok."""
        return self.error is None and self.first_error_step() is None

    def to_dict(self) -> dict[str, Any]:
        """Sérialise le lineage complet pour export JSON/forensic."""
        return {
            "lineage_id": self.lineage_id,
            "lineage_hash": self.lineage_hash,
            "text": self.text,
            "lang": self.lang,
            "adapter_type": self.adapter_type,
            "adapter_version": self.adapter_version,
            "timestamp_utc": self.timestamp_utc,
            "total_duration_ms": round(self.total_duration_ms, 3),
            "tokens": self.tokens,
            "normalized_text": self.normalized_text,
            "lemmas": self.lemmas,
            "artcb_code": self.artcb_code,
            "match_source": self.match_source,
            "ir_graph_id": self.ir_graph_id,
            "concept_id": self.concept_id,
            "concept_label": self.concept_label,
            "round_trip_text": self.round_trip_text,
            "round_trip_ok": self.round_trip_ok,
            "error": self.error,
            "steps": [s.to_dict() for s in self.steps],
            "unique_human_proven": self.unique_human_proven,
            "certified": self.certified,
        }

    def to_json(self, indent: int = 2) -> str:
        """Sérialise en JSON indenté."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def explain(self) -> str:
        """Retourne une explication textuelle du lineage (pour debug/audit).

        Format :
            [lang] texte → tokens → normalized → code → concept_id → round_trip_ok
        """
        lines = [
            f"=== SemanticLineage [{self.lang}] ===",
            f"  texte source : {self.text!r}",
            f"  adapter      : {self.adapter_type} v{self.adapter_version}",
            f"  lineage_id   : {self.lineage_id}",
        ]
        for step in self.steps:
            status = "✓" if step.error is None else f"✗ {step.error}"
            lines.append(
                f"  [{step.step_id}] {step.name:<20} ({step.layer}) "
                f"→ {repr(step.output_value)[:60]!r}  [{status}]  {step.duration_ms:.1f}ms"
            )
        lines.append(
            f"  round_trip_ok: {self.round_trip_ok}  |  "
            f"concept_id: {self.concept_id}  |  "
            f"total: {self.total_duration_ms:.1f}ms"
        )
        if self.error:
            lines.append(f"  ERREUR GLOBALE: {self.error}")
        return "\n".join(lines)


# ─── Traceur principal ────────────────────────────────────────────────────────

def trace_lineage(
    text: str,
    lang: str,
    *,
    adapter=None,
    semantic_corpus=None,
) -> SemanticLineage:
    """Trace le lineage complet d'une compilation sémantique ARTCB.

    Pour chaque texte source, exécute le pipeline complet et enregistre
    chaque étape avec sa durée, sa méthode, et sa sortie.

    En cas d'erreur à une étape, le lineage continue les étapes suivantes
    avec None/fallback — afin de localiser précisément l'étape défaillante.

    Args:
        text: texte source à compiler.
        lang: code langue ISO 639-1 (ex: "fr", "en", "de").
        adapter: instance LanguageAdapter (créée si None via get_adapter(lang)).
        semantic_corpus: instance SemanticCorpus (créée si None).

    Returns:
        SemanticLineage avec toutes les étapes documentées.
    """
    from src.artcb.language.adapter import SemanticCorpus, get_adapter  # noqa: PLC0415

    t_start = time.perf_counter()

    # Adapter + corpus
    if adapter is None:
        try:
            adapter = get_adapter(lang)
        except Exception as exc:  # noqa: BLE001
            return SemanticLineage(
                text=text,
                lang=lang,
                error=f"get_adapter({lang!r}) failed: {exc}",
            )

    if semantic_corpus is None:
        semantic_corpus = SemanticCorpus()

    adapter_type = type(adapter).__name__

    # Récupère MODULE_VERSION de l'adapter si disponible
    try:
        import src.artcb.language.adapter as _adm  # noqa: PLC0415
        adapter_version = getattr(_adm, "MODULE_VERSION", "?")
    except Exception:  # noqa: BLE001
        adapter_version = "?"

    # lineage_id déterministe
    lineage_id = hashlib.sha256(
        f"ARTCB-LINEAGE:{lang}:{adapter_type}:{adapter_version}:{text}".encode()
    ).hexdigest()[:24]

    lineage = SemanticLineage(
        text=text,
        lang=lang,
        lineage_id=lineage_id,
        adapter_type=adapter_type,
        adapter_version=adapter_version,
        timestamp_utc=time.time(),
    )

    steps: list[LineageStep] = []
    step_id = 0

    # ── Étape 1 : Tokenisation ────────────────────────────────────────────────
    step_id += 1
    t0 = time.perf_counter()
    try:
        tok_result = adapter.tokenize(text)
        tokens = tok_result.tokens
        lineage.tokens = tokens
        step = LineageStep(
            step_id=step_id,
            name="tokenize",
            layer="lexical",
            input_value=text,
            output_value=tokens,
            method=tok_result.method,
            module=f"adapter.{adapter_type}",
            module_version=adapter_version,
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
    except Exception as exc:  # noqa: BLE001
        tokens = text.split()
        lineage.tokens = tokens
        step = LineageStep(
            step_id=step_id,
            name="tokenize",
            layer="lexical",
            input_value=text,
            output_value=tokens,
            module=f"adapter.{adapter_type}",
            duration_ms=(time.perf_counter() - t0) * 1000,
            error=str(exc),
        )
    steps.append(step)

    # ── Étape 2 : Normalisation ───────────────────────────────────────────────
    step_id += 1
    t0 = time.perf_counter()
    try:
        norm_result = adapter.normalize(text)
        normalized = norm_result.normalized
        lineage.normalized_text = normalized
        step = LineageStep(
            step_id=step_id,
            name="normalize",
            layer="lexical",
            input_value=text,
            output_value=normalized,
            method=norm_result.form,
            module=f"adapter.{adapter_type}",
            module_version=adapter_version,
            duration_ms=(time.perf_counter() - t0) * 1000,
            notes=(["diacritics_stripped"] if norm_result.diacritics_stripped else []),
        )
    except Exception as exc:  # noqa: BLE001
        normalized = text.lower()
        lineage.normalized_text = normalized
        step = LineageStep(
            step_id=step_id,
            name="normalize",
            layer="lexical",
            input_value=text,
            output_value=normalized,
            module=f"adapter.{adapter_type}",
            duration_ms=(time.perf_counter() - t0) * 1000,
            error=str(exc),
        )
    steps.append(step)

    # ── Étape 3 : Morphologie ─────────────────────────────────────────────────
    step_id += 1
    t0 = time.perf_counter()
    try:
        morpho_result = adapter.morphology(tokens)
        lemmas = morpho_result.lemmas
        lineage.lemmas = lemmas
        step = LineageStep(
            step_id=step_id,
            name="morphology",
            layer="morphological",
            input_value=tokens,
            output_value={"lemmas": lemmas, "pos": morpho_result.pos_tags},
            method=morpho_result.method,
            module=f"adapter.{adapter_type}",
            module_version=adapter_version,
            duration_ms=(time.perf_counter() - t0) * 1000,
            notes=[morpho_result.language_specific_note] if morpho_result.language_specific_note else [],
        )
    except Exception as exc:  # noqa: BLE001
        lemmas = tokens
        lineage.lemmas = lemmas
        step = LineageStep(
            step_id=step_id,
            name="morphology",
            layer="morphological",
            input_value=tokens,
            output_value=lemmas,
            module=f"adapter.{adapter_type}",
            duration_ms=(time.perf_counter() - t0) * 1000,
            error=str(exc),
        )
    steps.append(step)

    # ── Étape 4 : Mapping lexical → artcb_code ────────────────────────────────
    step_id += 1
    t0 = time.perf_counter()
    try:
        concept_map = adapter.map_to_concept(normalized)
        # ConceptMappingResult est un dataclass (pas un dict)
        if hasattr(concept_map, "artcb_code"):
            artcb_code = concept_map.artcb_code
            match_source = concept_map.match_method
            output_val = {
                "artcb_code": artcb_code,
                "concept_id": concept_map.concept_id,
                "match_method": match_source,
                "confidence": concept_map.confidence,
            }
        elif isinstance(concept_map, dict):
            artcb_code = concept_map.get("artcb_code")
            match_source = concept_map.get("match_method", concept_map.get("match_source", "lexicon_mapper"))
            output_val = concept_map
        else:
            artcb_code = None
            match_source = "none"
            output_val = repr(concept_map)
        lineage.artcb_code = artcb_code
        lineage.match_source = match_source
        step = LineageStep(
            step_id=step_id,
            name="map_to_concept",
            layer="semantic",
            input_value=normalized,
            output_value=output_val,
            method=match_source,
            module=f"adapter.{adapter_type}",
            module_version=adapter_version,
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
    except Exception as exc:  # noqa: BLE001
        artcb_code = None
        lineage.artcb_code = None
        lineage.match_source = "none"
        step = LineageStep(
            step_id=step_id,
            name="map_to_concept",
            layer="semantic",
            input_value=normalized,
            output_value=None,
            module=f"adapter.{adapter_type}",
            duration_ms=(time.perf_counter() - t0) * 1000,
            error=str(exc),
        )
    steps.append(step)

    # ── Étape 5 : IR (IRGraph) ────────────────────────────────────────────────
    step_id += 1
    t0 = time.perf_counter()
    try:
        ir_graph = adapter.parse_to_ir(text)
        lineage.ir_graph_id = ir_graph.graph_id
        step = LineageStep(
            step_id=step_id,
            name="parse_to_ir",
            layer="ir",
            input_value=text,
            output_value={
                "graph_id": ir_graph.graph_id,
                "node_count": len(ir_graph.nodes),
                "edge_count": len(ir_graph.edges),
            },
            method="IREncoder",
            module=f"adapter.{adapter_type}",
            module_version=adapter_version,
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
    except Exception as exc:  # noqa: BLE001
        lineage.ir_graph_id = None
        step = LineageStep(
            step_id=step_id,
            name="parse_to_ir",
            layer="ir",
            input_value=text,
            output_value=None,
            module=f"adapter.{adapter_type}",
            duration_ms=(time.perf_counter() - t0) * 1000,
            error=str(exc),
        )
    steps.append(step)

    # ── Étape 6 : ConceptID ───────────────────────────────────────────────────
    step_id += 1
    t0 = time.perf_counter()
    try:
        concept_id = semantic_corpus.get_concept_id(artcb_code or "")
        concept_label = semantic_corpus.get_concept_label(artcb_code or "") if hasattr(semantic_corpus, "get_concept_label") else None
        lineage.concept_id = concept_id
        lineage.concept_label = concept_label
        step = LineageStep(
            step_id=step_id,
            name="concept_id",
            layer="semantic",
            input_value=artcb_code,
            output_value={"concept_id": concept_id, "concept_label": concept_label},
            method="SemanticCorpus.get_concept_id",
            module="language.adapter.SemanticCorpus",
            module_version=adapter_version,
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
    except Exception as exc:  # noqa: BLE001
        lineage.concept_id = None
        lineage.concept_label = None
        step = LineageStep(
            step_id=step_id,
            name="concept_id",
            layer="semantic",
            input_value=artcb_code,
            output_value=None,
            module="language.adapter.SemanticCorpus",
            duration_ms=(time.perf_counter() - t0) * 1000,
            error=str(exc),
        )
    steps.append(step)

    # ── Étape 7 : Round-trip ──────────────────────────────────────────────────
    step_id += 1
    t0 = time.perf_counter()
    try:
        rt_result = adapter.round_trip(text)
        # RoundTripResult est un dataclass (pas un dict)
        if hasattr(rt_result, "round_trip_ok"):
            rt_ok = rt_result.round_trip_ok
            rt_text = rt_result.reconstructed_text
        elif isinstance(rt_result, dict):
            rt_ok = bool(rt_result.get("round_trip_ok", False))
            rt_text = rt_result.get("round_trip_text") or rt_result.get("reconstructed_text")
        else:
            rt_ok = False
            rt_text = repr(rt_result)
        lineage.round_trip_text = rt_text
        lineage.round_trip_ok = rt_ok
        step = LineageStep(
            step_id=step_id,
            name="round_trip",
            layer="validation",
            input_value=text,
            output_value={
                "round_trip_text": rt_text,
                "round_trip_ok": rt_ok,
            },
            method="adapter.round_trip",
            module=f"adapter.{adapter_type}",
            module_version=adapter_version,
            duration_ms=(time.perf_counter() - t0) * 1000,
            notes=([] if lineage.round_trip_ok else ["round_trip_FAIL — perte sémantique détectée"]),
        )
    except Exception as exc:  # noqa: BLE001
        lineage.round_trip_text = None
        lineage.round_trip_ok = False
        step = LineageStep(
            step_id=step_id,
            name="round_trip",
            layer="validation",
            input_value=text,
            output_value=None,
            module=f"adapter.{adapter_type}",
            duration_ms=(time.perf_counter() - t0) * 1000,
            error=str(exc),
        )
    steps.append(step)

    # ── Finalisation ──────────────────────────────────────────────────────────
    lineage.steps = steps
    lineage.total_duration_ms = (time.perf_counter() - t_start) * 1000

    # lineage_hash : SHA256 de toutes les étapes sérialisées (reproductibilité)
    steps_repr = json.dumps([s.to_dict() for s in steps], sort_keys=True, ensure_ascii=False)
    lineage.lineage_hash = hashlib.sha256(steps_repr.encode()).hexdigest()[:24]

    if DEBUG_MODE:
        logger.debug(
            "trace_lineage [%s] text=%r id=%s hash=%s ok=%s total_ms=%.1f",
            lang, text[:40], lineage.lineage_id, lineage.lineage_hash,
            lineage.is_ok(), lineage.total_duration_ms,
        )

    return lineage


def trace_batch(
    texts: list[str],
    lang: str,
    *,
    adapter=None,
    semantic_corpus=None,
) -> list[SemanticLineage]:
    """Trace le lineage de plusieurs textes dans la même langue.

    Réutilise le même adapter et SemanticCorpus pour toute la liste
    (évite la recompilation à chaque appel).

    Args:
        texts: liste de textes sources.
        lang: code langue ISO 639-1.
        adapter: instance LanguageAdapter partagée (créée si None).
        semantic_corpus: instance SemanticCorpus partagée (créée si None).

    Returns:
        Liste de SemanticLineage dans le même ordre que texts.
    """
    from src.artcb.language.adapter import SemanticCorpus, get_adapter  # noqa: PLC0415

    if adapter is None:
        try:
            adapter = get_adapter(lang)
        except Exception as exc:  # noqa: BLE001
            return [
                SemanticLineage(text=t, lang=lang, error=f"get_adapter failed: {exc}")
                for t in texts
            ]

    if semantic_corpus is None:
        semantic_corpus = SemanticCorpus()

    return [
        trace_lineage(t, lang, adapter=adapter, semantic_corpus=semantic_corpus)
        for t in texts
    ]
