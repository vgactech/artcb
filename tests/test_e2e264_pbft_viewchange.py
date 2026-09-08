"""264 — PBFT view-change Q=3. Processes stay up. Not append_block 2f+1."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from artcb.chain.manager import ChainManager
from artcb.consensus.live_bft import LiveBftEngine
from artcb.consensus.pbft_view import (
    PbftViewStore,
    primary_of,
    verify_new_view,
    verify_view_change,
)
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS

ROOT = Path(__file__).resolve().parents[1]


def test_rule_requires_pbft_view_change_and_processes_stay() -> None:
    rule = (ROOT / ".cursor" / "rules" / "artcb-live-node.mdc").read_text(encoding="utf-8")
    assert "view-change PBFT" in rule or "PBFT view-change" in rule
    assert "processus restent" in rule.lower() or "processes stay" in rule.lower() or "Tous les processus restent" in rule
    prompt = (ROOT / "AUTO_PROMPT_ARTCB").read_text(encoding="utf-8")
    assert "PBFT view-change" in prompt or "view-change PBFT" in prompt


def test_primary_rotates_on_official_set() -> None:
    assert primary_of(0) == "ovh-node-1"
    assert primary_of(1) == "ovh-node-2"
    assert primary_of(2) == "aws-node-3"
    assert primary_of(3) == "ovh-node-4"
    assert primary_of(4) == "ovh-node-1"


def test_three_view_changes_install_new_view(tmp_path: Path) -> None:
    vcs = []
    chains = {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS[:3]:
        chain = ChainManager(tmp_path / nid / "blocks.jsonl", key_path=tmp_path / nid / "k", enable_security=False)
        chains[nid] = chain
        store = PbftViewStore(tmp_path / nid, replica_id=nid)
        row = store.emit_view_change(
            chain, view=1, height=10, last_hash="ab" * 32, reason="primary_unreachable"
        )
        assert verify_view_change(row) is True
        vcs.append(row)
    primary = PbftViewStore(tmp_path / "primary", replica_id="ovh-node-2")
    emitted = primary.emit_new_view(chains["ovh-node-2"], view=1, view_changes=vcs)
    assert emitted["ok"] is True
    assert primary.view == 1
    assert primary.primary == "ovh-node-2"
    assert verify_new_view(emitted["new_view"], vcs) is True
    follower = PbftViewStore(tmp_path / "aws-node-3", replica_id="aws-node-3")
    assert follower.install_new_view(emitted["new_view"], vcs)["ok"] is True
    assert follower.view == 1
    engine = LiveBftEngine(tmp_path / "eng", node_id="aws-node-3")
    engine.pbft.install_new_view(emitted["new_view"], vcs)
    assert engine.prepare_local("W-264", "sid-264-xxxx", view=0) == "wrong_view"
    assert engine.prepare_local("W-264", "sid-264-xxxx", view=1) == "prepared"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_SKIP_SEED_DISCOVERY", "1")
    monkeypatch.setenv("ARTCB_NODE_ID", "ovh-node-1")
    return TestClient(create_app())


def test_http_pbft_view_and_view_change(client: TestClient) -> None:
    got = client.get("/api/v1/consensus/pbft/view")
    assert got.status_code == 200
    body = got.json()
    assert body["view"] == 0
    assert body["primary"] == "ovh-node-1"
    assert body["q"] == 3
    assert body["processes_stay_up"] is True
    vc = client.post("/api/v1/consensus/pbft/view-change", json={"view": 1, "reason": "primary_unreachable"})
    assert vc.status_code == 200
    assert vc.json()["kind"] == "view-change"
    assert verify_view_change(vc.json()) is True
    listed = client.get("/api/v1/consensus/pbft/view-changes?view=1")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["ok"] is False
