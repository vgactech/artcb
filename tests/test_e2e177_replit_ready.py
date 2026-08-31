"""Phase 177 — Replit git detection, /live, HTTPS peers, honest PQC message."""

from __future__ import annotations

from pathlib import Path

from artcb.node_registry import NODES
from artcb.p2p.peers import PeerRecord
from artcb.release import release_identity

ROOT = Path(__file__).resolve().parents[1]


def test_replit_start_always_logs_git_sync_reason() -> None:
    body = (ROOT / "scripts" / "replit_start.sh").read_text(encoding="utf-8")
    assert "no .git — fetching" in body
    assert ".artcb_release" in body
    assert "replit_live_shim.py" in body
    assert "install_native_liboqs_replit.sh" in body
    assert "cursor/replit-sync-ready-16d8" in body
    assert 'grep -q github' not in body or "WARN remotes have no github" in body


def test_release_identity_reads_artcb_release(tmp_path: Path, monkeypatch) -> None:
    import artcb.release as rel

    monkeypatch.setattr(rel, "ROOT", tmp_path)
    monkeypatch.delenv("ARTCB_GIT_SHA", raising=False)
    monkeypatch.delenv("ARTCB_GIT_BRANCH", raising=False)
    (tmp_path / ".artcb_release").write_text(
        "ARTCB_GIT_SHA=deadbeefcafebabe\nARTCB_GIT_BRANCH=cursor/replit-sync-ready-16d8\n",
        encoding="utf-8",
    )
    ident = rel.release_identity()
    assert ident["git_sha"] == "deadbeefcafebabe"
    assert ident["git_branch"] == "cursor/replit-sync-ready-16d8"


def test_https_peer_base_url_not_http_on_443() -> None:
    p = PeerRecord(
        peer_id="replit",
        host="artcb--vgac42.replit.app",
        port=443,
        kem_public_key_hex="ab" * 32,
        scheme="https",
    )
    assert p.base_url.startswith("https://")
    assert ":443" in p.base_url


def test_replit_node_registered_ovh1_untouched() -> None:
    assert NODES["ovh-node-1"].ssh_host == "152.228.144.34"
    r = NODES["replit-node-1"]
    assert r.health_http == "https://artcb--vgac42.replit.app"
    assert "D-036" in r.public_notes
    main = (ROOT / "src" / "api" / "main.py").read_text(encoding="utf-8")
    assert '@app.get("/live")' in main
    assert '@app.get("/api/v1/chain/verify")' in main
    pqc = (ROOT / "src" / "artcb" / "crypto" / "pqc.py").read_text(encoding="utf-8")
    assert "Not 'package absent'" in pqc


def test_pqc_warning_does_not_say_package_absent_when_binding_installed() -> None:
    pqc = (ROOT / "src" / "artcb" / "crypto" / "pqc.py").read_text(encoding="utf-8")
    assert "liboqs-python 0.16 + native liboqs 0.13" in pqc


def test_advertised_base_url_replit_is_https() -> None:
    from artcb.p2p.node_identity import advertised_base_url

    url = advertised_base_url("https://artcb--vgac42.replit.app", 5000)
    assert url.startswith("https://")
    assert "artcb--vgac42.replit.app" in url
    assert "http://artcb--vgac42.replit.app:443" not in url
    forced = advertised_base_url("http://artcb--vgac42.replit.app:443", 5000)
    assert forced.startswith("https://")


def test_bootstrap_live_and_chain_verify_not_404(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from src.api.main import create_app

    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.delenv("ARTCB_NODE_WALLET_ADDRESS", raising=False)
    client = TestClient(create_app())
    live = client.get("/live")
    assert live.status_code == 200
    assert live.json()["status"] == "alive"
    verify = client.get("/api/v1/chain/verify")
    assert verify.status_code == 200, verify.text
    body = verify.json()
    assert body["bootstrap_mode"] is True
    assert body["valid"] is False
    assert client.get("/ready").status_code == 503
    assert client.get("/api/v1/wallet/list").status_code == 503
    assert client.get("/api/v1/chain").status_code == 503
