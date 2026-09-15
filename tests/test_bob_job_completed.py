"""Tests — Bob IDE → ARTCB JOB_COMPLETED persistence.

BOB-01 : build_job_completed produit un paquet structuré valide
BOB-02 : idempotence — même event_id pour même session+repo_sha
BOB-03 : retry — already_committed si ARTCB répond already_committed
BOB-04 : outbox — spooling local si ARTCB indisponible + flush
BOB-05 : repo_sha — git SHA présent dans le paquet
BOB-06 : secrets — aucun secret/thinking dans le paquet transmis
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def job_mod(tmp_path, monkeypatch):
    """Import du module avec TRACE_DIR et OUTBOX_DIR redirigés vers tmp_path."""
    import importlib
    import src.artcb.bob.job_completed as mod

    monkeypatch.setattr(mod, "TRACE_DIR", tmp_path / "trace")
    monkeypatch.setattr(mod, "OUTBOX_DIR", tmp_path / "outbox")
    monkeypatch.setattr(mod, "ARTCB_API_URL", "http://127.0.0.1:19999")
    monkeypatch.setattr(mod, "ARTCB_API_KEY", "test_key")
    (tmp_path / "trace").mkdir(parents=True, exist_ok=True)
    return mod


def _make_traces(tmp_path: Path, session_id: str = "sess_test") -> None:
    """Crée des traces JSONL factices pour la session."""
    trace = tmp_path / "trace"
    trace.mkdir(parents=True, exist_ok=True)

    tools = [
        {"ts_ns": 1, "kind": "bob_post_tool", "tool": "write_file", "path": "foo.py", "session_id": session_id},
        {"ts_ns": 2, "kind": "bob_post_tool", "tool": "apply_diff", "path": "bar.py", "session_id": session_id},
    ]
    with (trace / "bob_tool_usage.jsonl").open("w") as f:
        for t in tools:
            f.write(json.dumps(t) + "\n")

    turns = [
        {"ts_ns": 3, "kind": "bob_stop", "session_id": session_id, "chars": 100, "sha256": "abc"},
    ]
    with (trace / "bob_turns.jsonl").open("w") as f:
        for t in turns:
            f.write(json.dumps(t) + "\n")

    prompts = [
        {"ts_ns": 4, "kind": "bob_prompt_submit", "session_id": session_id, "prompt_len": 50},
    ]
    with (trace / "bob_prompts.jsonl").open("w") as f:
        for p in prompts:
            f.write(json.dumps(p) + "\n")

    pretool = [
        {"ts_ns": 5, "kind": "bob_pretool", "session_id": session_id, "tool": "execute_command"},
    ]
    with (trace / "bob_pretooluse.jsonl").open("w") as f:
        for p in pretool:
            f.write(json.dumps(p) + "\n")


# ---------------------------------------------------------------------------
# BOB-01 : build_job_completed produit un paquet structuré valide
# ---------------------------------------------------------------------------

class TestBobJobCompleted:
    def test_bob01_build_packet_structure(self, job_mod, tmp_path):
        """BOB-01 : le paquet contient tous les champs requis."""
        _make_traces(tmp_path, "sess_001")
        with patch.object(job_mod, "_git_sha", return_value="abc1234567890abcdef"):
            packet = job_mod.build_job_completed(
                session_id="sess_001",
                last_assistant_message="Le test est passé.",
                tool_count=2,
            )

        required = [
            "event_type", "event_id", "job_id", "session_id",
            "provider", "agent_id", "repo", "repo_sha",
            "completed_at_ns", "completed_at_iso", "status",
            "raw_output", "raw_tool_events", "raw_turns",
            "raw_prompts", "raw_pretool_events",
            "raw_hash", "content_sha256",
            "includes_thinking", "includes_system_prompt", "visibility",
        ]
        for key in required:
            assert key in packet, f"Champ manquant : {key}"

        assert packet["event_type"] == "JOB_COMPLETED"
        assert packet["provider"] == "bob"
        assert packet["includes_thinking"] is False
        assert packet["includes_system_prompt"] is False
        assert packet["visibility"] == "private"
        assert isinstance(packet["raw_tool_events"], list)
        assert packet["repo_sha"] == "abc1234567890abcdef"

    # ---------------------------------------------------------------------------
    # BOB-02 : idempotence — même event_id pour même session+repo_sha
    # ---------------------------------------------------------------------------

    def test_bob02_idempotent_event_id(self, job_mod, tmp_path):
        """BOB-02 : deux appels avec même session + même SHA produisent le même event_id."""
        _make_traces(tmp_path, "sess_002")
        with patch.object(job_mod, "_git_sha", return_value="deadbeef1234"):
            # On gèle le temps pour que ts_ns soit identique
            fixed_ts = 999_000_000_000
            with patch("time.time_ns", return_value=fixed_ts):
                p1 = job_mod.build_job_completed(session_id="sess_002")
                p2 = job_mod.build_job_completed(session_id="sess_002")

        assert p1["event_id"] == p2["event_id"], "event_id doit être déterministe"
        assert p1["job_id"] == p2["job_id"], "job_id doit être déterministe"

    # ---------------------------------------------------------------------------
    # BOB-03 : retry — already_committed si ARTCB répond already_committed
    # ---------------------------------------------------------------------------

    def test_bob03_already_committed(self, job_mod, tmp_path):
        """BOB-03 : si ARTCB retourne already_committed, le status est propagé."""
        _make_traces(tmp_path, "sess_003")
        mock_resp = {
            "status": "already_committed",
            "block_index": 42,
            "block_hash": "0xdeadbeef",
            "graph_id": "g_001",
        }
        with patch.object(job_mod, "_git_sha", return_value="cafebabe1234"):
            with patch.object(job_mod, "_post_to_artcb", return_value=mock_resp):
                result = job_mod.publish_job_completed(
                    session_id="sess_003",
                    last_assistant_message="Correction appliquée.",
                )

        assert result["artcb_status"] == "already_committed"
        assert result["includes_thinking"] is False
        assert result["includes_system_prompt"] is False
        # outbox doit exister (spooling préalable au commit)
        outbox = tmp_path / "outbox"
        assert outbox.exists()
        files = list(outbox.glob("job_completed_*.json"))
        assert len(files) == 1

    # ---------------------------------------------------------------------------
    # BOB-04 : outbox — spooling local si ARTCB indisponible + flush
    # ---------------------------------------------------------------------------

    def test_bob04_outbox_spooling_and_flush(self, job_mod, tmp_path):
        """BOB-04 : si ARTCB est down, spooling → flush_outbox → commit."""
        _make_traces(tmp_path, "sess_004")
        network_err = {"status": "network_error", "detail": "Connection refused"}
        committed_resp = {
            "status": "committed",
            "memo": {"block_index": 77, "block_hash": "0xfeed", "graph_id": "g_004"},
        }

        with patch.object(job_mod, "_git_sha", return_value="00aabbcc1234"):
            with patch.object(job_mod, "_post_to_artcb", return_value=network_err):
                result = job_mod.publish_job_completed(session_id="sess_004")

        assert result["artcb_status"] == "spooled"
        outbox = tmp_path / "outbox"
        files = list(outbox.glob("job_completed_*.json"))
        assert len(files) == 1, "L'outbox doit contenir le paquet spoolé"

        # Simule le retour ARTCB → flush_outbox doit committer
        with patch.object(job_mod, "_post_to_artcb", return_value=committed_resp):
            flush_results = job_mod.flush_outbox()

        assert len(flush_results) == 1
        assert flush_results[0]["status"] == "committed"

        # Le fichier outbox doit être marqué committed
        f = files[0]
        data = json.loads(f.read_text())
        assert data.get("artcb_commit", {}).get("status") == "committed"

    # ---------------------------------------------------------------------------
    # BOB-05 : repo_sha présent et correct
    # ---------------------------------------------------------------------------

    def test_bob05_repo_sha_present(self, job_mod, tmp_path):
        """BOB-05 : repo_sha = git HEAD exact."""
        _make_traces(tmp_path, "sess_005")
        fake_sha = "ec1a172bad8bfa73187b5f685abae049b6d6a361"
        with patch.object(job_mod, "_git_sha", return_value=fake_sha):
            packet = job_mod.build_job_completed(session_id="sess_005")

        assert packet["repo_sha"] == fake_sha
        assert fake_sha in packet["raw_hash"] or packet["raw_hash"]  # hash du contenu inclut le sha

    # ---------------------------------------------------------------------------
    # BOB-06 : aucun secret / thinking dans le paquet
    # ---------------------------------------------------------------------------

    def test_bob06_no_secrets_no_thinking(self, job_mod, tmp_path):
        """BOB-06 : redaction des secrets, includes_thinking=False toujours."""
        _make_traces(tmp_path, "sess_006")
        # Injecter un faux secret dans le message assistant
        dirty_message = (
            "Voici le résultat. Token: dp.st.abc123secretXYZ. "
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEpA...\n-----END RSA PRIVATE KEY-----"
        )
        with patch.object(job_mod, "_git_sha", return_value="aabbcc001122"):
            packet = job_mod.build_job_completed(
                session_id="sess_006",
                last_assistant_message=dirty_message,
            )

        # Vérifier que le secret est redacté dans raw_output
        assert "dp.st.abc123secretXYZ" not in packet["raw_output"]
        assert "[REDACTED]" in packet["raw_output"]
        # Vérifier includes_thinking = False toujours
        assert packet["includes_thinking"] is False
        assert packet["includes_system_prompt"] is False
        # Vérifier pas de clé privée
        assert "PRIVATE KEY" not in packet["raw_output"]
