"""Phase 169 unit tests — provenance, replica settlement, API key auth, TLS guard."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.artcb.economics.replicated_settlement import build_cluster
from src.artcb.live import LiveSecurityError, assert_live_transport
from src.artcb.sim_provenance import collect, dependency_lock_hash
from src.artcb.sdk.artcb_sdk import ArtcbClient, ArtcbError


def test_dependency_lock_is_not_python_plus_sha() -> None:
    dep = dependency_lock_hash()
    assert dep["source"] in {"pip_freeze", "requirements_txt_only"}
    assert dep["hash"]
    assert "package_count" in dep


def test_provenance_records_dirty_flag(tmp_path: Path) -> None:
    man = collect(
        protocol_version="169-test",
        economic_rules_version="test",
        simulation_id="unit",
        seed=169,
        script_path=Path(__file__),
    )
    assert "git_commit_sha" in man
    assert "git_status_clean" in man
    assert "working_tree_diff_hash" in man
    assert man["script_sha256"]
    assert "dependency_lock" in man


def test_replica_one_workid(tmp_path: Path) -> None:
    cluster = build_cluster(tmp_path, base_port=18701)
    try:
        time.sleep(0.1)
        first = cluster.settle(proposer="A", work_id="W1", snapshot_digest="s")
        second = cluster.settle(proposer="B", work_id="W1", snapshot_digest="s", forged_sid="other")
        assert first["ok"] is True
        assert second["ok"] is False
        assert max(cluster.consumed_counts("W1").values()) == 1
    finally:
        cluster.stop()


def test_refuse_bearer_over_remote_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARTCB_ALLOW_INSECURE_HTTP", raising=False)
    with pytest.raises(LiveSecurityError):
        assert_live_transport("http://152.228.144.34:8000", sending_bearer=True)


def test_sdk_refuses_remote_http_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARTCB_ALLOW_INSECURE_HTTP", raising=False)
    with pytest.raises(ArtcbError):
        ArtcbClient("http://152.228.144.34:8000", api_key="artcb_deadbeef")


def test_api_key_list_and_revoke_require_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Auth must return 401, never treat bootstrap 503 as a skip/pass (R310)."""
    monkeypatch.setenv("ARTCB_BOOTSTRAP_NODE", "false")
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ARTCB_NODE_WALLET_ADDRESS", "artcb1testnode000000000000000000000000000")
    monkeypatch.setenv("ARTCB_WALLET_PASSPHRASE", "test-passphrase-artcb-dev-32chars!")
    # Fresh create_app after env — module-level app is None under pytest.
    from src.api.main import create_app

    client = TestClient(create_app())
    status_list = client.get("/api/v1/api-keys/list").status_code
    status_del = client.delete("/api/v1/api-keys/kid_x").status_code
    assert status_list == 401, f"list expected 401 got {status_list}"
    assert status_del == 401, f"delete expected 401 got {status_del}"


def test_expired_key_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api.main import create_app

    monkeypatch.setenv("ARTCB_BOOTSTRAP_NODE", "false")
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ARTCB_NODE_WALLET_ADDRESS", "artcb1testnode000000000000000000000000000")
    monkeypatch.setenv("ARTCB_WALLET_PASSPHRASE", "test-passphrase-artcb-dev-32chars!")
    raw = "artcb_" + ("ab" * 32)
    import hashlib
    import json

    rec = {
        "key_id": "kid_expired",
        "label": "expired",
        "scopes": ["read"],
        "token_hash": hashlib.sha256(raw.encode()).hexdigest(),
        "key_preview": "artcb_ab…abab",
        "created_at": time.time() - 100,
        "expires_at": time.time() - 1,
        "last_used_at": None,
        "active": True,
    }
    (tmp_path / "api_keys.json").write_text(json.dumps([rec]), encoding="utf-8")
    client = TestClient(create_app())
    r = client.get("/api/v1/api-keys/me", headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code == 401, f"expired key must be 401, got {r.status_code} body={r.text[:200]}"
