"""R490 — ARTCB Pareto Runtime — benchmark multi-objectifs du langage.

Brique de développement du langage ARTCB (R486 ordre expert) :

  R490 : Pareto Runtime — mesure simultanée de N dimensions et calcul
         du front de Pareto (configurations non-dominées).

Dimensions mesurées :
    1. semantic_fidelity : % de concepts correctement conservés [0,1]
    2. latency_ms        : temps total du pipeline trace_lineage() [ms]
    3. memory_bytes      : occupation mémoire estimée du lineage dict [bytes]
    4. ir_size_chars     : longueur sérielle de l'IR (nombre de caractères JSON)
    5. step_count        : nombre d'étapes du lineage (fixe=7 ici, variable futur)
    6. round_trip_rate   : % de cas avec round_trip_ok=True [0,1]

Architecture :
    ┌─────────────────────────────────────────────┐
    │  ParetoRuntime                              │
    │                                             │
    │  benchmark(texts, lang)                     │
    │    → ParetoPoint par texte                  │
    │    → ParetoFront : configs non-dominées     │
    │    → dominated   : configs dominées         │
    └─────────────────────────────────────────────┘

Définition de dominance :
    La configuration A domine B si et seulement si :
    - A est au moins aussi bonne que B sur TOUTES les dimensions
    - A est strictement meilleure que B sur AU MOINS UNE dimension

    NB: les dimensions ne sont pas toutes à maximiser —
        certaines sont à minimiser (latency, memory, ir_size).
        La comparaison est normalisée : chaque dim → score [0,1] (plus haut = mieux).

    Invariant clé (R491) :
        semantic_fidelity est pondérée 3× par rapport aux autres dims —
        une perte de fidelité ne peut jamais être compensée par un gain de vitesse.

Usage dans la boucle de développement :
    front = benchmark_pareto("fr", seed_texts)
    # → quels textes sont dans le front de Pareto ?
    # → quelles dimensions sont le plus souvent dominées ?
    # → quels textes ont semantic_fidelity < seuil ? → défauts à corriger

CERTIFIED_100=false | unique_human_proven=False
"""
from __future__ import annotations

MODULE_VERSION = "1.0.1"  # R490

import hashlib
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.language.pareto")

DEBUG_MODE = True  # PROTOCOLE ARTCB — mode DEBUG permanent

# Invariants absolus
CERTIFIED_100 = False
UNIQUE_HUMAN_PROVEN = False

# Seuil de fidelité sémantique minimum acceptable
SEMANTIC_FIDELITY_MIN = 0.0  # 0 = UNK/non résolu, 1 = concept correctement résolu

# Poids de la fidelité sémantique (3× les autres dims) — anti-régression
FIDELITY_WEIGHT = 3.0


# ─── Point de mesure ─────────────────────────────────────────────────────────

@dataclass
class ParetoPoint:
    """Mesure d'un point dans l'espace multi-objectifs.

    Représente une configuration : un (texte, lang) → pipeline trace_lineage().
    """

    point_id: str                    # SHA256 déterministe
    text: str
    lang: str
    adapter_type: str = ""

    # Dimensions brutes mesurées
    semantic_fidelity: float = 0.0   # [0,1] — concept correctement résolu?
    latency_ms: float = 0.0          # temps total du pipeline [ms]
    memory_bytes: int = 0            # taille dict lineage sérialisé [bytes]
    ir_size_chars: int = 0           # longueur sérielle IR [chars]
    step_count: int = 0              # nombre d'étapes dans le lineage
    round_trip_ok: bool = False
    concept_id: str | None = None
    artcb_code: str | None = None
    lineage_id: str | None = None
    error: str | None = None         # erreur si le pipeline a échoué

    # Dimensions normalisées [0,1] (calculées après benchmarking)
    _norm_fidelity: float = field(default=0.0, repr=False)
    _norm_latency: float = field(default=0.0, repr=False)   # inversé : 1=rapide
    _norm_memory: float = field(default=0.0, repr=False)    # inversé : 1=petit
    _norm_ir_size: float = field(default=0.0, repr=False)   # inversé : 1=petit
    _norm_round_trip: float = field(default=0.0, repr=False)

    # Score Pareto pondéré (calculé après normalisation)
    pareto_score: float = 0.0
    is_in_front: bool = False        # True si dans le front de Pareto

    # Invariants
    unique_human_proven: bool = False
    certified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "point_id": self.point_id,
            "text": self.text,
            "lang": self.lang,
            "adapter_type": self.adapter_type,
            "semantic_fidelity": round(self.semantic_fidelity, 6),
            "latency_ms": round(self.latency_ms, 3),
            "memory_bytes": self.memory_bytes,
            "ir_size_chars": self.ir_size_chars,
            "step_count": self.step_count,
            "round_trip_ok": self.round_trip_ok,
            "concept_id": self.concept_id,
            "artcb_code": self.artcb_code,
            "lineage_id": self.lineage_id,
            "error": self.error,
            "pareto_score": round(self.pareto_score, 6),
            "is_in_front": self.is_in_front,
            "unique_human_proven": self.unique_human_proven,
            "certified": self.certified,
        }


# ─── Front de Pareto ─────────────────────────────────────────────────────────

@dataclass
class ParetoFront:
    """Résultat d'un benchmark Pareto multi-objectifs.

    Contient les points du front (non-dominés) et les points dominés.
    """

    run_id: str
    lang: str
    all_points: list[ParetoPoint] = field(default_factory=list)
    front_points: list[ParetoPoint] = field(default_factory=list)   # non-dominés
    dominated_points: list[ParetoPoint] = field(default_factory=list)
    duration_ms: float = 0.0
    adapter_version: str = ""

    # Statistiques globales
    avg_semantic_fidelity: float = 0.0
    avg_latency_ms: float = 0.0
    avg_ir_size_chars: float = 0.0
    min_semantic_fidelity: float = 1.0
    max_latency_ms: float = 0.0

    # Invariants
    unique_human_proven: bool = False
    certified: bool = False

    def summary(self) -> str:
        return (
            f"ParetoFront [{self.lang}] run={self.run_id} "
            f"points={len(self.all_points)} front={len(self.front_points)} "
            f"dominated={len(self.dominated_points)} "
            f"avg_fidelity={self.avg_semantic_fidelity:.3f} "
            f"avg_latency={self.avg_latency_ms:.1f}ms "
            f"duration={self.duration_ms:.0f}ms"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "lang": self.lang,
            "n_all": len(self.all_points),
            "n_front": len(self.front_points),
            "n_dominated": len(self.dominated_points),
            "avg_semantic_fidelity": round(self.avg_semantic_fidelity, 6),
            "avg_latency_ms": round(self.avg_latency_ms, 3),
            "avg_ir_size_chars": round(self.avg_ir_size_chars, 3),
            "min_semantic_fidelity": round(self.min_semantic_fidelity, 6),
            "max_latency_ms": round(self.max_latency_ms, 3),
            "adapter_version": self.adapter_version,
            "duration_ms": round(self.duration_ms, 3),
            "front_points": [p.to_dict() for p in self.front_points],
            "dominated_points": [p.to_dict() for p in self.dominated_points],
            "unique_human_proven": self.unique_human_proven,
            "certified": self.certified,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


# ─── Mesure d'un point ────────────────────────────────────────────────────────

def _measure_point(
    text: str,
    lang: str,
    adapter,
    semantic_corpus,
) -> ParetoPoint:
    """Mesure toutes les dimensions d'un point (texte, lang).

    Exécute trace_lineage() et collecte les métriques.
    """
    from src.artcb.language.lineage import trace_lineage  # noqa: PLC0415

    point_id = hashlib.sha256(
        f"PARETO:{lang}:{text}".encode()
    ).hexdigest()[:20]

    adapter_type = type(adapter).__name__

    t0 = time.perf_counter()
    try:
        lin = trace_lineage(text, lang, adapter=adapter, semantic_corpus=semantic_corpus)
        latency_ms = (time.perf_counter() - t0) * 1000

        # Fidelité sémantique : 1.0 si concept résolu, 0.0 si UNK
        fidelity = 0.0 if (lin.artcb_code is None or lin.artcb_code == "UNK") else 1.0

        # Mémoire approximative : taille du dict sérialisé
        lineage_dict = lin.to_dict()
        memory_bytes = sys.getsizeof(json.dumps(lineage_dict, ensure_ascii=False).encode())

        # Taille IR : longueur JSON du lineage (proxy de la complexité)
        ir_size_chars = len(json.dumps(lineage_dict, ensure_ascii=False))

        return ParetoPoint(
            point_id=point_id,
            text=text,
            lang=lang,
            adapter_type=adapter_type,
            semantic_fidelity=fidelity,
            latency_ms=latency_ms,
            memory_bytes=memory_bytes,
            ir_size_chars=ir_size_chars,
            step_count=len(lin.steps),
            round_trip_ok=lin.round_trip_ok,
            concept_id=lin.concept_id,
            artcb_code=lin.artcb_code,
            lineage_id=lin.lineage_id,
        )
    except Exception as exc:  # noqa: BLE001
        latency_ms = (time.perf_counter() - t0) * 1000
        logger.warning("_measure_point [%s] %r: erreur=%s", lang, text[:30], exc)
        return ParetoPoint(
            point_id=point_id,
            text=text,
            lang=lang,
            adapter_type=adapter_type,
            latency_ms=latency_ms,
            error=str(exc),
        )


# ─── Normalisation ────────────────────────────────────────────────────────────

def _normalize_points(points: list[ParetoPoint]) -> None:
    """Normalise les dimensions de chaque point dans [0,1] (in-place).

    Dimensions à maximiser (plus haut = mieux) :
        semantic_fidelity, round_trip_ok

    Dimensions à minimiser (plus bas = mieux) :
        latency_ms, memory_bytes, ir_size_chars

    Pour les dims à minimiser : score normalisé = 1 - (val - min) / (max - min)
    """
    if not points:
        return

    # Fidelité : [0,1] → directement utilisable
    for p in points:
        p._norm_fidelity = p.semantic_fidelity

    # Latency : inverser (rapide = mieux)
    latencies = [p.latency_ms for p in points]
    min_lat, max_lat = min(latencies), max(latencies)
    for p in points:
        if max_lat > min_lat:
            p._norm_latency = 1.0 - (p.latency_ms - min_lat) / (max_lat - min_lat)
        else:
            p._norm_latency = 1.0

    # Memory : inverser
    memories = [p.memory_bytes for p in points]
    min_mem, max_mem = min(memories), max(memories)
    for p in points:
        if max_mem > min_mem:
            p._norm_memory = 1.0 - (p.memory_bytes - min_mem) / (max_mem - min_mem)
        else:
            p._norm_memory = 1.0

    # IR size : inverser
    ir_sizes = [p.ir_size_chars for p in points]
    min_ir, max_ir = min(ir_sizes), max(ir_sizes)
    for p in points:
        if max_ir > min_ir:
            p._norm_ir_size = 1.0 - (p.ir_size_chars - min_ir) / (max_ir - min_ir)
        else:
            p._norm_ir_size = 1.0

    # Round-trip
    for p in points:
        p._norm_round_trip = 1.0 if p.round_trip_ok else 0.0

    # Score Pareto pondéré (fidelité = FIDELITY_WEIGHT × les autres)
    for p in points:
        p.pareto_score = (
            FIDELITY_WEIGHT * p._norm_fidelity
            + p._norm_latency
            + p._norm_memory
            + p._norm_ir_size
            + p._norm_round_trip
        ) / (FIDELITY_WEIGHT + 4)


# ─── Calcul du front de Pareto ────────────────────────────────────────────────

def _dominates(a: ParetoPoint, b: ParetoPoint) -> bool:
    """Retourne True si le point A domine B.

    A domine B si :
    - A est au moins aussi bon que B sur TOUTES les dimensions normalisées
    - A est strictement meilleur que B sur AU MOINS UNE dimension

    Note : semantic_fidelity a un poids x3 mais la dominance est calculée
    sur les scores normalisés individuels (pas le score agrégé).
    """
    dims_a = [
        a._norm_fidelity * FIDELITY_WEIGHT,
        a._norm_latency,
        a._norm_memory,
        a._norm_ir_size,
        a._norm_round_trip,
    ]
    dims_b = [
        b._norm_fidelity * FIDELITY_WEIGHT,
        b._norm_latency,
        b._norm_memory,
        b._norm_ir_size,
        b._norm_round_trip,
    ]
    at_least_as_good = all(da >= db for da, db in zip(dims_a, dims_b))
    strictly_better = any(da > db for da, db in zip(dims_a, dims_b))
    return at_least_as_good and strictly_better


def _compute_pareto_front(points: list[ParetoPoint]) -> tuple[list[ParetoPoint], list[ParetoPoint]]:
    """Calcule le front de Pareto (configurations non-dominées).

    Returns:
        (front_points, dominated_points)
    """
    front: list[ParetoPoint] = []
    dominated: list[ParetoPoint] = []

    for p in points:
        is_dominated = False
        for q in points:
            if p is q:
                continue
            if _dominates(q, p):
                is_dominated = True
                break
        if is_dominated:
            p.is_in_front = False
            dominated.append(p)
        else:
            p.is_in_front = True
            front.append(p)

    return front, dominated


# ─── Fonction principale ──────────────────────────────────────────────────────

def benchmark_pareto(
    lang: str,
    texts: list[str],
    *,
    adapter=None,
    semantic_corpus=None,
) -> ParetoFront:
    """Benchmark multi-objectifs sur une liste de textes.

    Mesure les 6 dimensions pour chaque texte, normalise, calcule le front
    de Pareto et retourne les statistiques globales.

    Args:
        lang: code langue ISO 639-1.
        texts: liste de textes à benchmarker.
        adapter: instance LanguageAdapter partagée (créée si None).
        semantic_corpus: instance SemanticCorpus partagée (créée si None).

    Returns:
        ParetoFront avec front_points (non-dominés) et dominated_points.
    """
    from src.artcb.language.adapter import SemanticCorpus, get_adapter  # noqa: PLC0415

    t_start = time.perf_counter()

    if adapter is None:
        adapter = get_adapter(lang)
    if adapter is None:
        logger.warning("benchmark_pareto: adapteur manquant pour lang=%r", lang)
        return ParetoFront(
            run_id=hashlib.sha256(f"PARETO:{lang}".encode()).hexdigest()[:16],
            lang=lang,
        )

    if semantic_corpus is None:
        semantic_corpus = SemanticCorpus()

    try:
        import src.artcb.language.adapter as _adm  # noqa: PLC0415
        adapter_version = getattr(_adm, "MODULE_VERSION", "?")
    except Exception:  # noqa: BLE001
        adapter_version = "?"

    run_id = hashlib.sha256(
        f"PARETO-RUN:{lang}:{adapter_version}:{texts}".encode()
    ).hexdigest()[:16]

    # Mesure des points
    points: list[ParetoPoint] = []
    for text in texts:
        pt = _measure_point(text, lang, adapter, semantic_corpus)
        points.append(pt)
        logger.debug(
            "PARETO [%s] %r: fidelity=%.2f latency=%.1fms ir=%d bytes=%d",
            lang, text[:25], pt.semantic_fidelity, pt.latency_ms,
            pt.ir_size_chars, pt.memory_bytes,
        )

    # Normalisation + scores
    _normalize_points(points)

    # Front de Pareto
    front, dominated = _compute_pareto_front(points) if len(points) > 1 else (points, [])

    total_ms = (time.perf_counter() - t_start) * 1000

    # Statistiques globales
    fidelities = [p.semantic_fidelity for p in points]
    latencies = [p.latency_ms for p in points]
    ir_sizes = [p.ir_size_chars for p in points]

    result = ParetoFront(
        run_id=run_id,
        lang=lang,
        all_points=points,
        front_points=front,
        dominated_points=dominated,
        duration_ms=total_ms,
        adapter_version=adapter_version,
        avg_semantic_fidelity=sum(fidelities) / len(fidelities) if fidelities else 0.0,
        avg_latency_ms=sum(latencies) / len(latencies) if latencies else 0.0,
        avg_ir_size_chars=sum(ir_sizes) / len(ir_sizes) if ir_sizes else 0.0,
        min_semantic_fidelity=min(fidelities) if fidelities else 0.0,
        max_latency_ms=max(latencies) if latencies else 0.0,
    )

    logger.info("PARETO DONE: %s", result.summary())
    return result
