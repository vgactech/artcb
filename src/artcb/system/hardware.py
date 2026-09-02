"""Detection materielle multi-plateforme — CPU, RAM, GPU, disque, reseau.

Mesure de bande passante reseau (rapport 113 — 2026-08-04) :
  measure_network_bandwidth() mesure la bande passante reelle sur 1 seconde.
  Cette valeur alimente compute_max_contributors_for_network() dans optimizer.py
  pour calculer dynamiquement combien de contributeurs un bloc peut contenir
  sans saturer le reseau du noeud.

  Classes reseau :
    TRES_FAIBLE : < 0.5 Mbps  — connexion tres lente (mobile 2G, satellite)
    FAIBLE      : < 5 Mbps    — connexion lente (mobile 3G, ADSL faible)
    MOYENNE     : < 50 Mbps   — connexion normale (ADSL, 4G)
    BONNE       : < 500 Mbps  — connexion rapide (fibre, 5G)
    EXCELLENTE  : >= 500 Mbps — datacenter, fibre 1G+
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("artcb.system.hardware")

# Classes reseau — utilisees pour calculer max_contributors dynamiquement
NETWORK_CLASS_TRES_FAIBLE = "TRES_FAIBLE"   # < 0.5 Mbps
NETWORK_CLASS_FAIBLE      = "FAIBLE"         # < 5 Mbps
NETWORK_CLASS_MOYENNE     = "MOYENNE"        # < 50 Mbps
NETWORK_CLASS_BONNE       = "BONNE"          # < 500 Mbps
NETWORK_CLASS_EXCELLENTE  = "EXCELLENTE"     # >= 500 Mbps


@dataclass
class HardwareProfile:
    platform_system: str
    platform_release: str
    architecture: str
    hostname: str
    processor: str
    cpu_count_logical: int
    cpu_count_physical: int
    cpu_freq_mhz: float
    memory_total_gb: float
    memory_available_gb: float
    disk_total_gb: float
    disk_free_gb: float
    gpus: list[dict[str, Any]] = field(default_factory=list)
    faiss_gpu_count: int = 0
    cuda_visible: bool = False
    # Bande passante reseau : estimated (optimizer) vs measured (metrology)
    network_bandwidth_mbps: float = 0.0
    network_class: str = NETWORK_CLASS_MOYENNE
    network_measured_mbps: float = 0.0
    network_fallback_mbps: float = 100.0
    network_bandwidth_source: str = "not_sampled"

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": {
                "system": self.platform_system,
                "release": self.platform_release,
                "architecture": self.architecture,
                "hostname": self.hostname,
                "processor": self.processor,
            },
            "cpu": {
                "logical_cores": self.cpu_count_logical,
                "physical_cores": self.cpu_count_physical,
                "freq_mhz": round(self.cpu_freq_mhz, 1),
            },
            "memory": {
                "total_gb": round(self.memory_total_gb, 2),
                "available_gb": round(self.memory_available_gb, 2),
            },
            "disk": {
                "total_gb": round(self.disk_total_gb, 2),
                "free_gb": round(self.disk_free_gb, 2),
            },
            "gpus": self.gpus,
            "faiss_gpu_count": self.faiss_gpu_count,
            "cuda_visible": self.cuda_visible,
            "network": {
                # bandwidth_mbps is the optimizer estimate (may be a fallback).
                # Official benches must read measured_* / bandwidth_source.
                "bandwidth_mbps": round(self.network_bandwidth_mbps, 2),
                "class": self.network_class,
                "measured_bandwidth_mbps": round(self.network_measured_mbps, 2),
                "estimated_bandwidth_mbps": round(self.network_bandwidth_mbps, 2),
                "fallback_bandwidth_mbps": round(self.network_fallback_mbps, 2),
                "bandwidth_source": self.network_bandwidth_source,
            },
        }


def _detect_nvidia_gpus() -> list[dict[str, Any]]:
    if not shutil.which("nvidia-smi"):
        return []
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if out.returncode != 0:
            return []
        gpus: list[dict[str, Any]] = []
        for line in out.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                gpus.append({
                    "index": int(parts[0]),
                    "name": parts[1],
                    "memory_mb": int(float(parts[2])),
                    "driver": parts[3],
                    "backend": "cuda",
                })
        return gpus
    except Exception as exc:
        logger.debug("nvidia-smi failed: %s", exc)
        return []


def _detect_faiss_gpus() -> int:
    if os.getenv("ARTCB_FAST_BOOT", "").strip() in {"1", "true", "yes"}:
        return 0
    try:
        import faiss  # type: ignore

        return int(faiss.get_num_gpus())
    except Exception:
        return 0


def detect_hardware() -> HardwareProfile:
    """Detecte le materiel utilisable sur Linux, macOS ou Windows."""
    import psutil

    cpu_freq = psutil.cpu_freq()
    mem = psutil.virtual_memory()
    disk_path = os.environ.get("ARTCB_DATA_DIR", ".")
    if not os.path.exists(disk_path):
        disk_path = "/"
    try:
        disk = psutil.disk_usage(disk_path)
    except Exception:
        disk = psutil.disk_usage("/")

    physical = psutil.cpu_count(logical=False) or psutil.cpu_count() or 1
    logical = psutil.cpu_count(logical=True) or physical

    gpus = _detect_nvidia_gpus()
    faiss_gpus = _detect_faiss_gpus()
    if faiss_gpus > 0 and not gpus:
        for i in range(faiss_gpus):
            gpus.append({"index": i, "name": "FAISS GPU", "backend": "faiss-cuda"})

    return HardwareProfile(
        platform_system=platform.system(),
        platform_release=platform.release(),
        architecture=platform.machine(),
        hostname=platform.node(),
        processor=platform.processor() or "unknown",
        cpu_count_logical=logical,
        cpu_count_physical=physical,
        cpu_freq_mhz=cpu_freq.current if cpu_freq else 0.0,
        memory_total_gb=mem.total / (1024**3),
        memory_available_gb=mem.available / (1024**3),
        disk_total_gb=disk.total / (1024**3),
        disk_free_gb=disk.free / (1024**3),
        gpus=gpus,
        faiss_gpu_count=faiss_gpus,
        cuda_visible=bool(os.environ.get("CUDA_VISIBLE_DEVICES")),
    )


def psutil_available() -> bool:
    """Verifie si psutil est installe et fonctionnel.

    psutil est une dependance OBLIGATOIRE de ARTCB (pyproject.toml + requirements.txt).
    Cette fonction est utilisee par les tests pour verifier que psutil est bien present.
    Si psutil est absent, le noeud tourne en mode degrade sans mesure reseau reelle.
    """
    try:
        import psutil as _p
        _p.cpu_percent(interval=0)  # Appel reel pour verifier que la lib est chargeable
        return True
    except Exception:
        return False


def _classify_mbps(mbps: float) -> str:
    if mbps < 0.5:
        return NETWORK_CLASS_TRES_FAIBLE
    if mbps < 5.0:
        return NETWORK_CLASS_FAIBLE
    if mbps < 50.0:
        return NETWORK_CLASS_MOYENNE
    if mbps < 500.0:
        return NETWORK_CLASS_BONNE
    return NETWORK_CLASS_EXCELLENTE


def measure_network_bandwidth_report(sample_seconds: float = 1.0) -> dict[str, Any]:
    """Honest network sample for official benches (D-053).

    Distinguishes:
      measured_bandwidth_mbps  — bytes observed during the sleep window
      estimated_bandwidth_mbps — value fed to optimizer (may be a convention)
      fallback_bandwidth_mbps  — the conventional constant when idle/missing
      bandwidth_source         — measured | idle_fallback | fast_boot | psutil_missing | error
    """
    idle_fallback = 100.0
    missing_fallback = 50.0
    base = {
        "sample_sleep_seconds": float(sample_seconds),
        "bytes_sampled": 0,
        "measured_bandwidth_mbps": 0.0,
        "estimated_bandwidth_mbps": missing_fallback,
        "fallback_bandwidth_mbps": missing_fallback,
        "bandwidth_source": "error",
        "class": NETWORK_CLASS_MOYENNE,
    }
    if os.getenv("ARTCB_FAST_BOOT", "").strip() in {"1", "true", "yes"}:
        logger.debug("Network bandwidth skipped (ARTCB_FAST_BOOT) class=BONNE")
        return {
            **base,
            "estimated_bandwidth_mbps": idle_fallback,
            "fallback_bandwidth_mbps": idle_fallback,
            "bandwidth_source": "fast_boot",
            "class": NETWORK_CLASS_BONNE,
        }
    try:
        import psutil as _psutil
    except ImportError:
        logger.warning(
            "AVERTISSEMENT : psutil n'est pas installe. "
            "La mesure de bande passante reseau est DESACTIVEE. "
            "max_contributors_per_block utilisera la valeur conservative (50 Mbps = MOYENNE). "
            "Pour une mesure reelle : pip install psutil>=5.9.0 "
            "ou : pip install -r requirements.txt"
        )
        return {
            **base,
            "estimated_bandwidth_mbps": missing_fallback,
            "fallback_bandwidth_mbps": missing_fallback,
            "bandwidth_source": "psutil_missing",
            "class": NETWORK_CLASS_MOYENNE,
        }
    try:
        net1 = _psutil.net_io_counters()
        time.sleep(sample_seconds)
        net2 = _psutil.net_io_counters()
        bytes_up = net2.bytes_sent - net1.bytes_sent
        bytes_down = net2.bytes_recv - net1.bytes_recv
        total_bytes = max(bytes_up, bytes_down)
        measured = (total_bytes * 8) / (sample_seconds * 1_000_000) if sample_seconds > 0 else 0.0
        if total_bytes < 10_000:
            estimated = idle_fallback
            source = "idle_fallback"
            cls = NETWORK_CLASS_BONNE
        else:
            estimated = measured
            source = "measured"
            cls = _classify_mbps(measured)
        return {
            "sample_sleep_seconds": float(sample_seconds),
            "bytes_sampled": int(total_bytes),
            "measured_bandwidth_mbps": round(measured, 4),
            "estimated_bandwidth_mbps": round(estimated, 4),
            "fallback_bandwidth_mbps": idle_fallback,
            "bandwidth_source": source,
            "class": cls,
        }
    except Exception as exc:
        logger.warning(
            "Mesure bande passante echouee malgre psutil : %s — "
            "fallback 50 Mbps (MOYENNE). Verifier les droits d'acces reseau.",
            exc,
        )
        return {
            **base,
            "estimated_bandwidth_mbps": missing_fallback,
            "fallback_bandwidth_mbps": missing_fallback,
            "bandwidth_source": "error",
            "class": NETWORK_CLASS_MOYENNE,
        }


def measure_network_bandwidth(sample_seconds: float = 1.0) -> tuple[float, str]:
    """Optimizer-facing estimate. Not a WAN speedtest.

    Returns (estimated_bandwidth_mbps, network_class). When the node is idle
    the estimate is a conventional 100 Mbps (idle_fallback). Official benches
    must call measure_network_bandwidth_report() or read live_metrics() fields
    measured_bandwidth_mbps / bandwidth_source.
    """
    report = measure_network_bandwidth_report(sample_seconds)
    return float(report["estimated_bandwidth_mbps"]), str(report["class"])


def live_metrics() -> dict[str, Any]:
    """Metriques temps reel (CPU%, RAM%, reseau)."""
    import psutil

    cpu_percent = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk_path = os.environ.get("ARTCB_DATA_DIR", ".")
    if not os.path.exists(disk_path):
        disk_path = "/"
    try:
        disk = psutil.disk_usage(disk_path)
    except Exception:
        disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    report = measure_network_bandwidth_report(sample_seconds=0.5)

    return {
        "cpu": {
            "percent": cpu_percent,
            "count": psutil.cpu_count(logical=True),
            "freq_mhz": (psutil.cpu_freq().current if psutil.cpu_freq() else 0),
        },
        "memory": {
            "total_gb": round(mem.total / (1024**3), 2),
            "used_gb": round(mem.used / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2),
            "percent": mem.percent,
        },
        "disk": {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "percent": disk.percent,
        },
        "network": {
            "bytes_sent_mb": round(net.bytes_sent / (1024**2), 2),
            "bytes_recv_mb": round(net.bytes_recv / (1024**2), 2),
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
            # Honest metrology (D-053): do not publish idle_fallback as a speedtest.
            "bandwidth_mbps": report["measured_bandwidth_mbps"],
            "measured_bandwidth_mbps": report["measured_bandwidth_mbps"],
            "estimated_bandwidth_mbps": report["estimated_bandwidth_mbps"],
            "fallback_bandwidth_mbps": report["fallback_bandwidth_mbps"],
            "bandwidth_source": report["bandwidth_source"],
            "sample_sleep_seconds": report["sample_sleep_seconds"],
            "bytes_sampled": report["bytes_sampled"],
            "bandwidth_class": report["class"],
        },
        "metrics_timing": {
            "cpu_percent_interval_seconds": 0.1,
            "network_sample_sleep_seconds": report["sample_sleep_seconds"],
            "note": "/metrics HTTP RTT includes the voluntary network sample sleep; it is not API compute latency.",
        },
    }
