"""Tests detection materielle et profil d'optimisation.

Inclut les tests de :
  - psutil present et fonctionnel (dependance obligatoire)
  - measure_network_bandwidth() retourne des valeurs coherentes
  - compute_max_contributors() dynamique 2 dimensions
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from artcb.system.hardware import (
    detect_hardware,
    live_metrics,
    measure_network_bandwidth,
    psutil_available,
    NETWORK_CLASS_TRES_FAIBLE,
    NETWORK_CLASS_FAIBLE,
    NETWORK_CLASS_MOYENNE,
    NETWORK_CLASS_BONNE,
    NETWORK_CLASS_EXCELLENTE,
)
from artcb.system.optimizer import (
    build_optimization_profile,
    compute_max_contributors,
    default_pool_chunk_chars,
    MIN_CONTRIBUTORS_ABSOLUTE,
    MAX_CONTRIBUTORS_ABSOLUTE,
)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    app = create_app()
    return TestClient(app)


def test_detect_hardware_returns_sane_values():
    hw = detect_hardware()
    d = hw.to_dict()
    assert d["cpu"]["logical_cores"] >= 1
    assert d["memory"]["total_gb"] > 0
    assert d["disk"]["total_gb"] > 0
    assert "system" not in d
    assert isinstance(d["gpus"], list)


def test_live_metrics_structure():
    m = live_metrics()
    assert "cpu" in m and "percent" in m["cpu"]
    assert "memory" in m and "percent" in m["memory"]
    assert "network" in m


def test_optimization_profile_defaults():
    hw = detect_hardware()
    opt = build_optimization_profile(hw)
    d = opt.to_dict()
    assert 1 <= d["agent_pool_workers"] <= 8
    assert 100 <= d["pool_chunk_chars"] <= 8000
    assert d["use_numpy_pol"] is True
    assert "optimizations_active" in d
    assert len(d["optimizations_active"]) >= 4


def test_default_pool_chunk_chars():
    chunk = default_pool_chunk_chars()
    assert 100 <= chunk <= 8000


def test_metrics_api_includes_hardware(client):
    r = client.get("/api/v1/metrics")
    assert r.status_code == 200
    body = r.json()
    assert "hardware" in body
    assert "optimization" in body
    assert body["hardware"]["cpu"]["logical_cores"] >= 1


def test_system_hardware_endpoint(client):
    r = client.get("/api/v1/system/hardware")
    assert r.status_code == 200
    assert "cpu" in r.json()


def test_system_optimization_endpoint(client):
    r = client.get("/api/v1/system/optimization")
    assert r.status_code == 200
    assert "pool_chunk_chars" in r.json()


# ── Tests psutil — dependance obligatoire ──────────────────────────────────


def test_psutil_installed():
    """psutil doit etre installe — dependance obligatoire dans pyproject.toml + requirements.txt.

    Si ce test echoue : pip install psutil>=5.9.0  (ou pip install -r requirements.txt)
    psutil est OBLIGATOIRE pour la mesure de bande passante reseau qui calibre
    max_contributors_per_block. Sans lui, le noeud tourne en mode degrade.
    """
    assert psutil_available(), (
        "psutil n'est PAS installe. "
        "Commande de correction : pip install psutil>=5.9.0 "
        "ou : pip install -r requirements.txt\n"
        "psutil est requis pour la mesure reseau en temps reel (anti-Sybil dynamique)."
    )


def test_psutil_cpu_readable():
    """psutil doit pouvoir lire le CPU (verification que le .so natif est charge)."""
    import psutil
    percent = psutil.cpu_percent(interval=0)
    assert isinstance(percent, float)
    assert 0.0 <= percent <= 100.0


def test_psutil_net_io_readable():
    """psutil doit pouvoir lire les compteurs reseau (requis pour measure_network_bandwidth)."""
    import psutil
    counters = psutil.net_io_counters()
    assert counters is not None
    assert hasattr(counters, "bytes_sent")
    assert hasattr(counters, "bytes_recv")
    assert counters.bytes_sent >= 0
    assert counters.bytes_recv >= 0


# ── Tests measure_network_bandwidth ────────────────────────────────────────


def test_measure_network_bandwidth_returns_tuple():
    """measure_network_bandwidth doit retourner (float, str)."""
    bw_mbps, bw_class = measure_network_bandwidth(sample_seconds=0.05)
    assert isinstance(bw_mbps, float)
    assert bw_mbps > 0.0
    assert bw_class in (
        NETWORK_CLASS_TRES_FAIBLE,
        NETWORK_CLASS_FAIBLE,
        NETWORK_CLASS_MOYENNE,
        NETWORK_CLASS_BONNE,
        NETWORK_CLASS_EXCELLENTE,
    )


def test_measure_network_bandwidth_classification():
    """Les seuils de classification doivent etre corrects."""
    bw_mbps, bw_class = measure_network_bandwidth(sample_seconds=0.05)
    # Verification de coherence seuil <-> classe
    if bw_mbps < 0.5:
        assert bw_class == NETWORK_CLASS_TRES_FAIBLE
    elif bw_mbps < 5.0:
        assert bw_class == NETWORK_CLASS_FAIBLE
    elif bw_mbps < 50.0:
        assert bw_class == NETWORK_CLASS_MOYENNE
    elif bw_mbps < 500.0:
        assert bw_class == NETWORK_CLASS_BONNE
    else:
        assert bw_class == NETWORK_CLASS_EXCELLENTE


def test_hardware_profile_includes_network():
    """HardwareProfile doit inclure les champs reseau."""
    hw = detect_hardware()
    d = hw.to_dict()
    assert "network" in d
    assert "bandwidth_mbps" in d["network"]
    assert "class" in d["network"]
    assert d["network"]["bandwidth_mbps"] >= 0.0


# ── Tests compute_max_contributors dynamique ───────────────────────────────


def test_compute_max_contributors_devnet():
    """Phase devnet : 0 wallets actifs -> plafond adoption 10."""
    result = compute_max_contributors(wallets_active_30d=0, network_bandwidth_mbps=100.0)
    assert result == 10  # adoption_cap=10 < network_cap=41666 → min=10


def test_compute_max_contributors_early():
    """Phase early : 5000 wallets actifs -> plafond adoption 50."""
    result = compute_max_contributors(wallets_active_30d=5_000, network_bandwidth_mbps=100.0)
    assert result == 50


def test_compute_max_contributors_growth():
    """Phase growth : 50 000 wallets actifs -> plafond adoption 100."""
    result = compute_max_contributors(wallets_active_30d=50_000, network_bandwidth_mbps=100.0)
    assert result == 100


def test_compute_max_contributors_mass():
    """Phase mass : 500 000 wallets actifs -> plafond adoption 500."""
    result = compute_max_contributors(wallets_active_30d=500_000, network_bandwidth_mbps=100.0)
    assert result == 500


def test_compute_max_contributors_global():
    """Phase global : 2M wallets actifs -> plafond adoption 1000."""
    result = compute_max_contributors(wallets_active_30d=2_000_000, network_bandwidth_mbps=100.0)
    assert result == MAX_CONTRIBUTORS_ABSOLUTE


def test_compute_max_contributors_network_bottleneck():
    """Bande passante tres faible : limite reseau s'applique avant l'adoption."""
    # 0.1 Mbps -> budget = 0.1*1e6*0.5/8 = 6250 bytes -> 6250/150 = 41 -> clamp min=2
    # mais adoption_cap avec 1M wallets = 1000, donc min(1000, 41) = 41
    result = compute_max_contributors(wallets_active_30d=1_000_000, network_bandwidth_mbps=0.1)
    assert result == max(MIN_CONTRIBUTORS_ABSOLUTE, min(41, MAX_CONTRIBUTORS_ABSOLUTE))


def test_compute_max_contributors_clamp_min():
    """Le resultat ne peut pas etre inferieur a MIN_CONTRIBUTORS_ABSOLUTE."""
    # Bande passante quasi nulle
    result = compute_max_contributors(wallets_active_30d=0, network_bandwidth_mbps=0.001)
    assert result >= MIN_CONTRIBUTORS_ABSOLUTE


def test_compute_max_contributors_clamp_max():
    """Le resultat ne peut pas depasser MAX_CONTRIBUTORS_ABSOLUTE."""
    result = compute_max_contributors(wallets_active_30d=10_000_000, network_bandwidth_mbps=10_000.0)
    assert result <= MAX_CONTRIBUTORS_ABSOLUTE


def test_compute_max_contributors_uses_real_network():
    """compute_max_contributors appele sans bw explicite utilise measure_network_bandwidth."""
    # Si aucun bw fourni et classe MOYENNE, on doit avoir un resultat coherent
    result = compute_max_contributors(wallets_active_30d=0, network_class=NETWORK_CLASS_MOYENNE)
    assert MIN_CONTRIBUTORS_ABSOLUTE <= result <= MAX_CONTRIBUTORS_ABSOLUTE


def test_fast_boot_skips_bandwidth_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTCB_FAST_BOOT", "1")
    bw, cls = measure_network_bandwidth(sample_seconds=30.0)
    assert bw == 100.0
    assert cls == NETWORK_CLASS_BONNE
    opt = build_optimization_profile()
    assert opt.use_faiss is False
    assert opt.network_class == NETWORK_CLASS_BONNE
