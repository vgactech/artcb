"""Profil d'optimisation runtime base sur le materiel detecte.

Calcul dynamique de max_contributors_per_block (rapport 113 — 2026-08-04) :
  compute_max_contributors() combine deux dimensions independantes :

  DIMENSION 1 — Adoption reseau (wallets actifs) :
    Determine le plafond MAXIMUM de participants possibles selon la taille du reseau.
    Plus il y a d'utilisateurs actifs, plus la limite monte automatiquement.
    Phase devnet (<1k wallets)  : plafond adoption = 10
    Phase early (1k-10k)        : plafond adoption = 50
    Phase growth (10k-100k)     : plafond adoption = 100
    Phase mass (100k-1M)        : plafond adoption = 500
    Phase global (>1M)          : plafond adoption = 1000

  DIMENSION 2 — Qualite de la connexion reseau du noeud :
    Determine combien de contributeurs le noeud peut techniquement gerer
    en tenant compte de la bande passante disponible.
    Budget : chaque contributeur = 150 bytes de donnees JSON (signature ed25519)
    Objectif : le bloc complet doit passer en < 500ms sur le reseau actuel.
    TRES_FAIBLE (< 0.5 Mbps) : limite reseau =   8 contributeurs
    FAIBLE      (< 5 Mbps)   : limite reseau =  80 contributeurs
    MOYENNE     (< 50 Mbps)  : limite reseau = 800 contributeurs
    BONNE       (< 500 Mbps) : limite reseau = 8000 contributeurs
    EXCELLENTE  (>= 500 Mbps): pas de limite reseau (>10000)

  RESULTAT FINAL = min(plafond_adoption, limite_reseau)
    -> Le noeud n'accepte jamais plus de contributeurs que ce que le reseau
       et la communaute active le permettent a ce moment precis.
    -> Aucune limite fixe arbitraire — le systeme s'auto-adapte.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from src.artcb.system.hardware import (
    HardwareProfile,
    detect_hardware,
    measure_network_bandwidth,
    NETWORK_CLASS_TRES_FAIBLE,
    NETWORK_CLASS_FAIBLE,
    NETWORK_CLASS_MOYENNE,
    NETWORK_CLASS_BONNE,
    NETWORK_CLASS_EXCELLENTE,
)

logger = logging.getLogger("artcb.system.optimizer")

# Taille JSON estimee par contributeur dans un bloc (bytes)
# Contient : address(44) + pol_score(8) + reward_satoshi(8) + signature_ed25519(64*2 hex) + role(12) + JSON overhead
# Total realistique : ~150 bytes par contributeur (sans signature PQC)
BYTES_PER_CONTRIBUTOR = 150

# Budget de transit reseau cible pour un bloc (secondes)
# On vise que le bloc passe en moins de 500ms sur le reseau le plus lent disponible
NETWORK_BUDGET_SECONDS = 0.5

# Minimum absolu de contributeurs par bloc (securite anti-Sybil plancher)
MIN_CONTRIBUTORS_ABSOLUTE = 2

# Maximum absolu de contributeurs par bloc (securite anti-DDoS plafond)
MAX_CONTRIBUTORS_ABSOLUTE = 1_000


@dataclass
class OptimizationProfile:
    agent_pool_workers: int
    pool_chunk_chars: int
    use_faiss: bool
    use_faiss_gpu: bool
    use_numpy_pol: bool
    ir_cache_enabled: bool
    pdf_async_io: bool
    graph_compression: bool
    node_index_enabled: bool
    # Limite dynamique de contributeurs par bloc (rapport 113)
    max_contributors_per_block: int = 10
    network_class: str = NETWORK_CLASS_MOYENNE
    network_bandwidth_mbps: float = 50.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_pool_workers":       self.agent_pool_workers,
            "pool_chunk_chars":         self.pool_chunk_chars,
            "use_faiss":                self.use_faiss,
            "use_faiss_gpu":            self.use_faiss_gpu,
            "use_numpy_pol":            self.use_numpy_pol,
            "ir_cache_enabled":         self.ir_cache_enabled,
            "pdf_async_io":             self.pdf_async_io,
            "graph_compression":        self.graph_compression,
            "node_index_enabled":       self.node_index_enabled,
            "max_contributors_per_block": self.max_contributors_per_block,
            "network_class":            self.network_class,
            "network_bandwidth_mbps":   round(self.network_bandwidth_mbps, 2),
            "optimizations_active": [
                "ir_cache",
                "numpy_pol",
                "pdf_async",
                "graph_compression",
                "node_index",
                f"max_contributors_{self.max_contributors_per_block}",
                f"network_{self.network_class.lower()}",
            ]
            + (["faiss_cpu"] if self.use_faiss and not self.use_faiss_gpu else [])
            + (["faiss_gpu"] if self.use_faiss_gpu else [])
            + (["agent_pool"] if self.agent_pool_workers > 1 else []),
        }


def _faiss_available() -> bool:
    try:
        import faiss  # noqa: F401

        return True
    except ImportError:
        return False


def compute_max_contributors(
    *,
    wallets_active_30d: int = 0,
    network_bandwidth_mbps: float | None = None,
    network_class: str | None = None,
) -> int:
    """Calcule le nombre maximum de contributeurs par bloc selon deux dimensions.

    DIMENSION 1 — Adoption reseau (wallets actifs dans les 30 derniers jours) :
      Plafond adoption croissant automatiquement avec la taille de la communaute.
      < 1 000 wallets  : plafond = 10
      < 10 000 wallets : plafond = 50
      < 100 000 wallets: plafond = 100
      < 1 000 000      : plafond = 500
      >= 1 000 000     : plafond = 1 000 (MAX_CONTRIBUTORS_ABSOLUTE)

    DIMENSION 2 — Qualite de la connexion reseau :
      Calcule combien de contributeurs peuvent transiter en NETWORK_BUDGET_SECONDS (500ms).
      Si network_bandwidth_mbps est fourni, calcul precis.
      Sinon utilise network_class comme approximation.
      Budget : BYTES_PER_CONTRIBUTOR * max_contrib < bandwidth * 0.5s

    RESULTAT = min(plafond_adoption, limite_reseau)
      Clamp final : [MIN_CONTRIBUTORS_ABSOLUTE, MAX_CONTRIBUTORS_ABSOLUTE]

    Args:
      wallets_active_30d     : nombre de wallets ayant mine dans les 30 derniers jours
      network_bandwidth_mbps : bande passante mesuree en Mbps (None = utiliser class)
      network_class          : classe reseau si bandwidth non mesuree

    Returns:
      int : nombre maximum de contributeurs acceptables pour ce bloc
    """
    # ── Dimension 1 : plafond selon adoption ────────────────────────────────
    if wallets_active_30d < 1_000:
        adoption_cap = 10
    elif wallets_active_30d < 10_000:
        adoption_cap = 50
    elif wallets_active_30d < 100_000:
        adoption_cap = 100
    elif wallets_active_30d < 1_000_000:
        adoption_cap = 500
    else:
        adoption_cap = MAX_CONTRIBUTORS_ABSOLUTE

    # ── Dimension 2 : limite selon bande passante ────────────────────────────
    if network_bandwidth_mbps is not None and network_bandwidth_mbps > 0:
        # Calcul precis : combien de contributeurs passent dans le budget reseau ?
        # budget_bytes = bande_passante_bps * NETWORK_BUDGET_SECONDS / 8
        # max_from_network = budget_bytes / BYTES_PER_CONTRIBUTOR
        budget_bytes = network_bandwidth_mbps * 1_000_000 * NETWORK_BUDGET_SECONDS / 8
        network_cap = int(budget_bytes / BYTES_PER_CONTRIBUTOR)
    else:
        # Estimation par classe si bande passante non mesuree
        _class_caps = {
            NETWORK_CLASS_TRES_FAIBLE: 8,
            NETWORK_CLASS_FAIBLE:     80,
            NETWORK_CLASS_MOYENNE:    800,
            NETWORK_CLASS_BONNE:      8_000,
            NETWORK_CLASS_EXCELLENTE: MAX_CONTRIBUTORS_ABSOLUTE,
        }
        network_cap = _class_caps.get(network_class or NETWORK_CLASS_MOYENNE, 800)

    # ── Resultat final ────────────────────────────────────────────────────────
    result = min(adoption_cap, network_cap)
    result = max(MIN_CONTRIBUTORS_ABSOLUTE, min(result, MAX_CONTRIBUTORS_ABSOLUTE))

    logger.debug(
        "compute_max_contributors: wallets_active=%d -> adoption_cap=%d | "
        "bandwidth=%.1f Mbps class=%s -> network_cap=%d | result=%d",
        wallets_active_30d, adoption_cap,
        network_bandwidth_mbps or 0, network_class or "?", network_cap,
        result,
    )
    return result


def build_optimization_profile(hw: HardwareProfile | None = None) -> OptimizationProfile:
    """Construit un profil d'optimisation adapte au materiel + reseau."""
    hw = hw or detect_hardware()
    workers = max(1, min(hw.cpu_count_logical - 1, 8))
    if hw.memory_total_gb < 4:
        workers = 1

    use_faiss = False if os.getenv("ARTCB_FAST_BOOT", "").strip() in {"1", "true", "yes"} else _faiss_available()
    use_faiss_gpu = use_faiss and (hw.faiss_gpu_count > 0 or len(hw.gpus) > 0)

    chunk = 400
    if hw.memory_total_gb >= 16:
        chunk = 600
    elif hw.memory_total_gb < 4:
        chunk = 200

    if os.getenv("ARTCB_FORCE_CPU", "").lower() in ("1", "true", "yes"):
        use_faiss_gpu = False
        workers = max(1, workers // 2)

    # Mesure de la bande passante reseau (rapide, 1 seconde)
    bw_mbps, bw_class = measure_network_bandwidth(sample_seconds=1.0)

    # Calcul initial de max_contributors (wallets_active=0 au demarrage)
    # Il sera recalcule dynamiquement a chaque bloc via AntiSybilValidator
    initial_max_contributors = compute_max_contributors(
        wallets_active_30d=0,
        network_bandwidth_mbps=bw_mbps,
        network_class=bw_class,
    )

    profile = OptimizationProfile(
        agent_pool_workers=workers,
        pool_chunk_chars=chunk,
        use_faiss=use_faiss,
        use_faiss_gpu=use_faiss_gpu,
        use_numpy_pol=True,
        ir_cache_enabled=True,
        pdf_async_io=True,
        graph_compression=True,
        node_index_enabled=True,
        max_contributors_per_block=initial_max_contributors,
        network_class=bw_class,
        network_bandwidth_mbps=bw_mbps,
    )
    logger.debug(
        "Optimization profile workers=%d faiss_gpu=%s chunk=%d "
        "max_contributors=%d network=%s(%.1fMbps)",
        profile.agent_pool_workers,
        profile.use_faiss_gpu,
        profile.pool_chunk_chars,
        profile.max_contributors_per_block,
        profile.network_class,
        profile.network_bandwidth_mbps,
    )
    return profile


def apply_optimization_profile(profile: OptimizationProfile) -> None:
    """Expose le profil via variables d'environnement pour le runtime."""
    os.environ.setdefault("ARTCB_POOL_CHUNK_CHARS", str(profile.pool_chunk_chars))
    os.environ.setdefault("ARTCB_AGENT_POOL_WORKERS", str(profile.agent_pool_workers))
    if profile.use_faiss_gpu:
        os.environ.setdefault("ARTCB_USE_FAISS_GPU", "true")
    elif profile.use_faiss:
        os.environ.setdefault("ARTCB_USE_FAISS_GPU", "false")


def default_pool_chunk_chars() -> int:
    """Chunk pool par defaut (profil materiel ou 400)."""
    raw = os.getenv("ARTCB_POOL_CHUNK_CHARS", "")
    if raw.isdigit():
        return max(100, min(int(raw), 8000))
    return build_optimization_profile().pool_chunk_chars
