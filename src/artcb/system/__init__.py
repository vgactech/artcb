"""ARTCB system — hardware detection et optimisations runtime."""

from src.artcb.system.hardware import (
    HardwareProfile,
    detect_hardware,
    live_metrics,
    measure_network_bandwidth,
    measure_network_bandwidth_report,
    psutil_available,
)
from src.artcb.system.optimizer import (
    OptimizationProfile,
    apply_optimization_profile,
    build_optimization_profile,
    compute_max_contributors,
    default_pool_chunk_chars,
)

__all__ = [
    "HardwareProfile",
    "OptimizationProfile",
    "apply_optimization_profile",
    "build_optimization_profile",
    "compute_max_contributors",
    "default_pool_chunk_chars",
    "detect_hardware",
    "live_metrics",
    "measure_network_bandwidth",
    "measure_network_bandwidth_report",
    "psutil_available",
]
