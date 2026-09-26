"""R491 — ARTCB Pareto Inversé — garde-fou anti-régression sémantique.

Brique de développement du langage ARTCB (R486 ordre expert) :

  R491 : Pareto inversé — détecte les optimisations qui semblent bonnes
         sur des métriques brutes (vitesse, taille) mais qui détruisent
         la fidelité sémantique.

Architecture :
    ┌──────────────────────────────────────────────────────┐
    │  InvertedParetoGuard                                 │
    │                                                      │
    │  compare(baseline, candidate)                        │
    │    → RuntimeDelta : Δ pour chaque dimension          │
    │    → DangerousOptimization si :                      │
    │        runtime_gain > 0 ET semantic_loss > threshold │
    └──────────────────────────────────────────────────────┘

Règle fondamentale (R491 — ARTCB) :
    Une optimisation est "dangereuse" si elle satisfait les deux conditions :
    1. Elle améliore au moins une métrique runtime (latence, mémoire, IR size)
    2. Elle dégrade la fidelité sémantique de plus de FIDELITY_LOSS_THRESHOLD

    Dans ce cas, R491 retourne DangerousOptimization.is_dangerous=True,
    bloquant l'adoption de l'optimisation.

    Exemples :
        - Compression IR : -40% taille, -15% latence, -0.8% fidelité → DANGEREUX
        - Cache lexical  : -20% latence, 0% fidelité                  → OK
        - Alias simplifiés: -50% mémoire, -5% fidelité                → DANGEREUX

CERTIFIED_100=false | unique_human_proven=False
"""
from __future__ import annotations

MODULE_VERSION = "1.0.1"  # R491

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("artcb.language.pareto_inverse")

DEBUG_MODE = True  # PROTOCOLE ARTCB — mode DEBUG permanent

# Invariants absolus
CERTIFIED_100 = False
UNIQUE_HUMAN_PROVEN = False

# Seuil de perte sémantique acceptable (0.01 = 1%)
# Au-delà de ce seuil, l'optimisation est marquée DANGEREUSE
FIDELITY_LOSS_THRESHOLD = 0.01


# ─── Delta entre deux configurations ─────────────────────────────────────────

@dataclass
class RuntimeDelta:
    """Différences entre une configuration baseline et candidate.

    Valeurs positives = amélioration de la métrique (pour la candidat).
    Valeurs négatives = dégradation.

    Convention (pour les métriques "à minimiser" comme latence) :
        delta_latency_ms = baseline.latency - candidate.latency
        → positif = candidate plus rapide = amélioration
    """

    baseline_label: str = "baseline"
    candidate_label: str = "candidate"

    # Deltas bruts (positif = amélioration pour candidate)
    delta_semantic_fidelity: float = 0.0   # positif = meilleure fidelité
    delta_latency_ms: float = 0.0          # positif = plus rapide
    delta_memory_bytes: float = 0.0        # positif = moins de mémoire
    delta_ir_size_chars: float = 0.0       # positif = IR plus petit
    delta_round_trip_rate: float = 0.0     # positif = meilleur round-trip

    # Méta
    n_texts: int = 0
    computation_ms: float = 0.0

    # Invariants
    unique_human_proven: bool = False
    certified: bool = False

    def is_runtime_gain(self) -> bool:
        """True si la candidat améliore au moins une métrique runtime."""
        return (
            self.delta_latency_ms > 0
            or self.delta_memory_bytes > 0
            or self.delta_ir_size_chars > 0
        )

    def is_semantic_loss(self, threshold: float = FIDELITY_LOSS_THRESHOLD) -> bool:
        """True si la candidat dégrade la fidelité sémantique au-delà du seuil."""
        return self.delta_semantic_fidelity < -threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_label": self.baseline_label,
            "candidate_label": self.candidate_label,
            "delta_semantic_fidelity": round(self.delta_semantic_fidelity, 6),
            "delta_latency_ms": round(self.delta_latency_ms, 3),
            "delta_memory_bytes": round(self.delta_memory_bytes, 3),
            "delta_ir_size_chars": round(self.delta_ir_size_chars, 3),
            "delta_round_trip_rate": round(self.delta_round_trip_rate, 6),
            "n_texts": self.n_texts,
            "is_runtime_gain": self.is_runtime_gain(),
            "is_semantic_loss": self.is_semantic_loss(),
            "unique_human_proven": self.unique_human_proven,
            "certified": self.certified,
        }


@dataclass
class DangerousOptimization:
    """Résultat de l'audit R491 : optimisation dangereuse ou sûre.

    is_dangerous=True signifie :
        L'optimisation améliore le runtime MAIS dégrade la fidelité sémantique
        au-delà du seuil FIDELITY_LOSS_THRESHOLD.

        → L'optimisation doit être REJETÉE.
    """

    is_dangerous: bool
    reason: str = ""
    delta: RuntimeDelta | None = None
    fidelity_loss_threshold: float = FIDELITY_LOSS_THRESHOLD
    recommendation: str = ""

    # Invariants
    unique_human_proven: bool = False
    certified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_dangerous": self.is_dangerous,
            "reason": self.reason,
            "fidelity_loss_threshold": self.fidelity_loss_threshold,
            "recommendation": self.recommendation,
            "delta": self.delta.to_dict() if self.delta else None,
            "unique_human_proven": self.unique_human_proven,
            "certified": self.certified,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


# ─── Calcul du delta ──────────────────────────────────────────────────────────

def compute_delta(
    baseline_texts: list[dict[str, Any]],
    candidate_texts: list[dict[str, Any]],
    *,
    baseline_label: str = "baseline",
    candidate_label: str = "candidate",
) -> RuntimeDelta:
    """Calcule le delta entre deux séries de mesures.

    baseline_texts et candidate_texts sont des listes de dicts avec les
    métriques de ParetoPoint.to_dict().

    Args:
        baseline_texts: mesures de la configuration de référence.
        candidate_texts: mesures de la configuration candidate.
        baseline_label: nom de la baseline pour le rapport.
        candidate_label: nom de la candidate pour le rapport.

    Returns:
        RuntimeDelta avec les deltas moyens par dimension.
    """
    if not baseline_texts or not candidate_texts:
        return RuntimeDelta(
            baseline_label=baseline_label,
            candidate_label=candidate_label,
            n_texts=0,
        )

    t0 = time.perf_counter()

    def avg(pts: list[dict], key: str) -> float:
        vals = [p.get(key, 0.0) for p in pts]
        return sum(vals) / len(vals) if vals else 0.0

    b_fid = avg(baseline_texts, "semantic_fidelity")
    c_fid = avg(candidate_texts, "semantic_fidelity")

    b_lat = avg(baseline_texts, "latency_ms")
    c_lat = avg(candidate_texts, "latency_ms")

    b_mem = avg(baseline_texts, "memory_bytes")
    c_mem = avg(candidate_texts, "memory_bytes")

    b_ir = avg(baseline_texts, "ir_size_chars")
    c_ir = avg(candidate_texts, "ir_size_chars")

    b_rt = avg(baseline_texts, "round_trip_ok")
    c_rt = avg(candidate_texts, "round_trip_ok")

    delta = RuntimeDelta(
        baseline_label=baseline_label,
        candidate_label=candidate_label,
        delta_semantic_fidelity=c_fid - b_fid,      # positif = candidate meilleure fidelité
        delta_latency_ms=b_lat - c_lat,              # positif = candidate plus rapide
        delta_memory_bytes=b_mem - c_mem,            # positif = candidate moins de mémoire
        delta_ir_size_chars=b_ir - c_ir,             # positif = candidate IR plus petit
        delta_round_trip_rate=c_rt - b_rt,           # positif = candidate meilleur round-trip
        n_texts=min(len(baseline_texts), len(candidate_texts)),
        computation_ms=(time.perf_counter() - t0) * 1000,
    )

    logger.debug(
        "compute_delta: Δfidelity=%.4f Δlatency=%.1fms Δmemory=%.0f Δir=%d",
        delta.delta_semantic_fidelity,
        delta.delta_latency_ms,
        delta.delta_memory_bytes,
        delta.delta_ir_size_chars,
    )

    return delta


def audit_optimization(
    delta: RuntimeDelta,
    *,
    fidelity_loss_threshold: float = FIDELITY_LOSS_THRESHOLD,
) -> DangerousOptimization:
    """Audite un delta et retourne si l'optimisation est dangereuse.

    Règle R491 :
        DANGEREUX si :
            delta.is_runtime_gain() AND delta.is_semantic_loss(threshold)

    Args:
        delta: RuntimeDelta calculé par compute_delta().
        fidelity_loss_threshold: seuil de perte acceptable [0,1].

    Returns:
        DangerousOptimization avec is_dangerous=True/False + raison.
    """
    runtime_gain = delta.is_runtime_gain()
    semantic_loss = delta.is_semantic_loss(fidelity_loss_threshold)

    if runtime_gain and semantic_loss:
        reason = (
            f"L'optimisation améliore le runtime "
            f"(Δlatency={delta.delta_latency_ms:+.1f}ms, "
            f"Δmemory={delta.delta_memory_bytes:+.0f}B, "
            f"Δir={delta.delta_ir_size_chars:+.0f}chars) "
            f"MAIS dégrade la fidelité sémantique de "
            f"{abs(delta.delta_semantic_fidelity):.2%} "
            f"(seuil={fidelity_loss_threshold:.2%})."
        )
        recommendation = (
            "REJETER l'optimisation. "
            "Investiguer comment réduire le runtime sans perte sémantique, "
            "ou accepter une perte ≤ "
            f"{fidelity_loss_threshold:.2%} si les cas dégradés sont documentés "
            "et approuvés explicitement."
        )
        logger.warning(
            "R491 DANGEROUS OPTIMIZATION: %r → %r | %s",
            delta.baseline_label, delta.candidate_label, reason,
        )
        return DangerousOptimization(
            is_dangerous=True,
            reason=reason,
            delta=delta,
            fidelity_loss_threshold=fidelity_loss_threshold,
            recommendation=recommendation,
        )
    elif not runtime_gain and not semantic_loss:
        reason = "L'optimisation n'améliore pas le runtime et ne dégrade pas la fidelité."
        recommendation = "Optimisation neutre — peut être acceptée sans risque."
    elif runtime_gain and not semantic_loss:
        reason = (
            f"L'optimisation améliore le runtime "
            f"(Δlatency={delta.delta_latency_ms:+.1f}ms) "
            f"sans perte sémantique significative "
            f"(Δfidelity={delta.delta_semantic_fidelity:+.4f})."
        )
        recommendation = "Optimisation SÛRE — peut être acceptée."
    else:
        reason = "La candidate dégrade le runtime sans gain sémantique."
        recommendation = "Optimisation inutile — rejeter."

    return DangerousOptimization(
        is_dangerous=False,
        reason=reason,
        delta=delta,
        fidelity_loss_threshold=fidelity_loss_threshold,
        recommendation=recommendation,
    )


def compare_fronts(
    baseline_front: "ParetoFront",  # noqa: F821
    candidate_front: "ParetoFront",  # noqa: F821
    *,
    baseline_label: str = "baseline",
    candidate_label: str = "candidate",
    fidelity_loss_threshold: float = FIDELITY_LOSS_THRESHOLD,
) -> DangerousOptimization:
    """Compare deux ParetoFront et audite si la candidate est dangereuse.

    Raccourci : convertit les points en dicts et appelle compute_delta + audit_optimization.

    Args:
        baseline_front: ParetoFront de référence.
        candidate_front: ParetoFront de la configuration candidate.
        baseline_label / candidate_label: noms pour le rapport.
        fidelity_loss_threshold: seuil de perte acceptable.

    Returns:
        DangerousOptimization.
    """
    baseline_dicts = [p.to_dict() for p in baseline_front.all_points]
    candidate_dicts = [p.to_dict() for p in candidate_front.all_points]

    delta = compute_delta(
        baseline_dicts,
        candidate_dicts,
        baseline_label=baseline_label,
        candidate_label=candidate_label,
    )

    return audit_optimization(delta, fidelity_loss_threshold=fidelity_loss_threshold)
