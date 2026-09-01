"""Phase 190 — D-044 operator validation, P2P auth, PIN ancestor, no Replit wallet."""

from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from artcb.crypto_policy import NETWORK_ID
from artcb.devnet_validation import DECISIONS_190, ECONOMIC_V_LOCKED, certification_gate
from artcb.p2p.public_url import public_register_url_ok
from artcb.release import _is_ancestor, _release_integrity

ROOT = Path(__file__).resolve().parents[1]


def test_d044_validates_d043_without_inventing_cert() -> None:
    assert ECONOMIC_V_LOCKED is True
    text = DECISIONS_190["D-044"]
    assert "no wallet" in text.lower() or "No wallet" in text or "no init-node" in text
    assert "certified_distributed_mainnet stays false" in text
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
    assert "DV-02" in gate["dv_not_pass"]


def test_register_url_rejects_ssrf() -> None:
    ok, reason = public_register_url_ok("http://169.254.169.254/latest/meta-data")
    assert ok is False
    assert "link_local" in reason or "reserved" in reason
    ok2, reason2 = public_register_url_ok("http://127.0.0.1:8000")
    # conftest sets ARTCB_ALLOW_LOCAL_PEERS for unit tests
    assert ok2 is True
    assert reason2 == "local_test"
    ok3, _ = public_register_url_ok("http://152.228.144.34:8000")
    assert ok3 is True
    ok4, reason4 = public_register_url_ok("https://evil.example.com")
    assert ok4 is False
    assert reason4 == "host_not_allowlisted"
    ok5, reason5 = public_register_url_ok("https://any-app--anyuser.replit.dev")
    assert ok5 is True
    assert reason5 == "platform_public"
    ok6, reason6 = public_register_url_ok("http://8.8.8.8:8000")
    assert ok6 is True
    assert reason6 == "public_ip"


def test_pin_ancestor_fast_forward(tmp_path: Path, monkeypatch) -> None:
    import artcb.release as rel

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True)
    (repo / "f").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "f"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "pin"], cwd=repo, check=True, capture_output=True)
    pin = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    (repo / "f").write_text("b", encoding="utf-8")
    subprocess.run(["git", "add", "f"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "tip"], cwd=repo, check=True, capture_output=True)
    tip = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    monkeypatch.setattr(rel, "ROOT", repo)
    assert _is_ancestor(pin, tip) is True
    assert _release_integrity(tip, [tip], pin) == "ok"
    assert _release_integrity(tip, [tip], "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef") == "pin_mismatch"


def test_replit_git_sync_does_not_print_pin() -> None:
    body = (ROOT / "scripts" / "replit_git_sync.sh").read_text(encoding="utf-8")
    assert "fetch --unshallow" in body
    assert "pin=$ARTCB_REPLIT_PIN_SHA" not in body
    assert "fetch --depth 1 origin" not in body


def test_p2p_delete_requires_bearer(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from src.api.main import create_app

    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_API_KEY", "artcb_local_test_operator_key")
    client = TestClient(create_app())
    r = client.delete("/api/v1/p2p/peers/peer_nosuch")
    assert r.status_code == 401
    r2 = client.delete(
        "/api/v1/p2p/peers/peer_nosuch",
        headers={"Authorization": "Bearer artcb_local_test_operator_key"},
    )
    assert r2.status_code == 404


def test_register_public_ssrf_metadata(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from src.api.main import create_app

    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_ALLOW_LOCAL_PEERS", "0")
    client = TestClient(create_app())
    r = client.post(
        "/api/v1/p2p/register-public",
        json={
            "node_public_url": "http://169.254.169.254/latest",
            "device_fingerprint": "d" * 64,
            "network_id": NETWORK_ID,
        },
    )
    assert r.status_code == 400
    assert "register_url_rejected" in r.json()["detail"]


def test_local_health_flood_stays_200(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from src.api.main import create_app

    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    client = TestClient(create_app())

    def once() -> int:
        return client.get("/health").status_code

    with ThreadPoolExecutor(max_workers=16) as pool:
        codes = list(pool.map(lambda _: once(), range(48)))
    assert codes.count(200) == 48


def test_sim190_refuses_wallet_init_and_live_flood() -> None:
    sim = (ROOT / "scripts" / "run_sim190_mainnet_validate.py").read_text(encoding="utf-8")
    assert "Never invent SHA" in sim
    assert "init-node" in sim
    assert "install.sh" in sim
    assert "flood_live_vms" in sim
    assert "vgacofficiel" in sim
