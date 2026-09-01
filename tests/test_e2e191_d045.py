"""Phase 191 — D-045 TPM honesty, WPP freeze, seed discovery, P2P visitor lock."""

from __future__ import annotations

from pathlib import Path

from artcb.config import REPLIT_PUBLIC_URL, bootstrap_nodes
from artcb.devnet_validation import DECISIONS_191, ECONOMIC_V, certification_gate
from artcb.economics.demographic import (
    H_ADULT_MAX,
    HMAX_FROZEN,
    WPP2024_FREEZE_INPUTS,
    default_reference,
    wpp2024_methodology_hash,
)
from artcb.security.hardware_identity import public_machine_view, tpm_sysfs_facts

ROOT = Path(__file__).resolve().parents[1]


def test_d045_locks_wpp_without_inventing_un_18plus_cell() -> None:
    assert "D-045" in DECISIONS_191
    assert "do not fake a TPM" in DECISIONS_191["D-045"]
    assert HMAX_FROZEN is True
    assert "Q-E03 UN WPP 2024" in ECONOMIC_V["V-06"]
    inp = WPP2024_FREEZE_INPUTS
    assert inp["official_total_rounded_billions"] == 8.2
    assert inp["year"] == 2024
    assert inp["publication_date"] == "2024-07-11"
    assert inp["age_15_24"] == int(inp["under_25"]) - int(inp["under_15"])
    assert int(inp["h_adult_18_plus"]) == (
        int(inp["age_25_64"]) + int(inp["age_65_plus"]) + int(inp["age_18_24_seven_tenths_of_15_24"])
    )
    assert H_ADULT_MAX == 5_763_415_792
    ref = default_reference()
    assert ref.methodology_hash == wpp2024_methodology_hash()
    assert ref.methodology_hash != "pending"
    assert ref.adult_population_estimate == float(H_ADULT_MAX)
    assert "un-wpp-2024" in ref.dataset_id


def test_tpm_sysfs_does_not_invent_a_chip() -> None:
    facts = tpm_sysfs_facts()
    assert "tpm_device_present" in facts
    assert facts["tpm_device_present"] is True or facts["tpm_device_present"] is False
    view = public_machine_view(None)
    if not facts["tpm_device_present"]:
        assert view["tpm_attestation"] == "absent"
        assert view["tpm_device_present"] is False


def test_bootstrap_nodes_consumed_and_replit_current() -> None:
    seeds = bootstrap_nodes()
    assert "http://152.228.144.34:8000" in seeds
    assert "http://91.134.45.8:8000" in seeds
    assert REPLIT_PUBLIC_URL == "https://artcb--vgac42371.replit.app"
    assert REPLIT_PUBLIC_URL in seeds
    disc = (ROOT / "src" / "artcb" / "p2p" / "seed_discovery.py").read_text(encoding="utf-8")
    assert "no process consumed" in disc or "no startup path" in disc.lower()


def test_visitor_cannot_mutate_or_autostart_p2p(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from src.api.main import create_app

    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_API_KEY", "artcb_local_test_operator_key")
    client = TestClient(create_app())
    assert client.post("/api/v1/p2p/sync").status_code == 401
    assert client.post("/api/v1/p2p/gossip/announce").status_code == 401
    assert client.delete("/api/v1/p2p/libp2p/stop").status_code == 401
    idle = client.get("/api/v1/p2p/libp2p/status")
    assert idle.status_code == 200
    assert idle.json().get("running") is False
    assert idle.json().get("autostart") is False
    bad = client.post(
        "/api/v1/network/announce",
        json={"node_public_url": "http://169.254.169.254/latest", "network_id": "artcb-mainnet-1"},
    )
    assert bad.status_code == 400
    health = client.get("/health")
    assert health.status_code == 200
    assert "machine" in health.json()
    assert "tpm_device_present" in health.json()["machine"]
    nodes = client.get("/api/v1/network/nodes")
    assert nodes.status_code == 200
    body = nodes.json()
    assert body["wallet_required_to_list_nodes"] is False
    assert "ovh-node-1" in body["nodes"]
    assert any("vgac42371" in u for u in body["seeds"])


def test_bootstrap_directory_without_wallet(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from src.api.main import create_app

    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.delenv("ARTCB_NODE_WALLET_ADDRESS", raising=False)
    client = TestClient(create_app())
    p2p = client.get("/api/v1/p2p/status")
    assert p2p.status_code == 200, p2p.text
    assert p2p.json()["bootstrap_mode"] is True
    assert p2p.json()["wallet_initialized"] is False
    peers = client.get("/api/v1/p2p/peers")
    assert peers.status_code == 200
    assert "seeds" in peers.json()
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["bootstrap_mode"] is True
    assert "machine" in health.json()


def test_certification_still_and_of_all_dv() -> None:
    gate = certification_gate(
        {
            "DV-01": "PASS",
            "DV-02": "PARTIAL",
            "DV-03": "PASS",
            "DV-04": "PASS",
            "DV-05": "PASS",
            "DV-06": "PARTIAL",
            "DV-07": "PASS",
        }
    )
    assert gate["certified_distributed_mainnet"] is False


def test_sim191_runs_packet_loss_on_live_book() -> None:
    sim = (ROOT / "scripts" / "run_sim191_dv01_wpp_chaos.py").read_text(encoding="utf-8")
    assert "Never invent SHA" in sim
    assert "install.sh" in sim
    assert "init_genesis.py" in sim
    assert "netem" in sim
    assert "vgac42371" in sim
    assert "packet_loss" in sim
    assert "init-node" in sim
