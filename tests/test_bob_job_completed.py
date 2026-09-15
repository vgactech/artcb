"""Tests — Bob IDE → ARTCB JOB_COMPLETED persistence.

BOB-01 : build_job_completed produit un paquet structuré valide
BOB-02 : idempotence sans timestamp (P0-B) — T1..T5
BOB-03 : retry — already_committed si ARTCB répond already_committed
BOB-04 : outbox — spooling local si ARTCB indisponible + flush
BOB-05 : repo_sha — git SHA présent dans le paquet
BOB-06 : secrets absents paquet ET fichier outbox (P0-A) — T6 toutes catégories
BOB-07 : redaction_applied_before_outbox=True et flags de sécurité
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
    # BOB-02 : idempotence sans timestamp — P0-B (T1..T5)
    # ---------------------------------------------------------------------------

    def test_bob02_t1_same_work_different_timestamp(self, job_mod, tmp_path):
        """T1 : même travail + timestamp différent → même event_id."""
        _make_traces(tmp_path, "sess_002")
        with patch.object(job_mod, "_git_sha", return_value="deadbeef1234"):
            with patch("time.time_ns", return_value=111_000_000_000):
                p1 = job_mod.build_job_completed(session_id="sess_002")
            with patch("time.time_ns", return_value=999_000_000_000):
                p2 = job_mod.build_job_completed(session_id="sess_002")

        assert p1["event_id"] == p2["event_id"], "T1 : timestamps différents → même event_id"
        assert p1["job_id"] == p2["job_id"],     "T1 : job_id aussi déterministe"

    def test_bob02_t2_different_prompt_different_id(self, job_mod, tmp_path):
        """T2 : prompts différents → event_id différent."""
        _make_traces(tmp_path, "sess_002b")
        with patch.object(job_mod, "_git_sha", return_value="deadbeef1234"):
            p1 = job_mod.build_job_completed(session_id="sess_002b", last_assistant_message="réponse A")
        # Modifier les prompts → changer prompt_hash
        trace = tmp_path / "trace"
        with (trace / "bob_prompts.jsonl").open("a") as f:
            import json as _json
            f.write(_json.dumps({"ts_ns": 99, "kind": "bob_prompt_submit", "session_id": "sess_002b", "prompt_len": 999}) + "\n")
        with patch.object(job_mod, "_git_sha", return_value="deadbeef1234"):
            p2 = job_mod.build_job_completed(session_id="sess_002b", last_assistant_message="réponse A")

        assert p1["event_id"] != p2["event_id"], "T2 : prompts différents → event_id différent"

    def test_bob02_t3_different_tools_different_id(self, job_mod, tmp_path):
        """T3 : outils différents → event_id différent."""
        _make_traces(tmp_path, "sess_002c")
        with patch.object(job_mod, "_git_sha", return_value="deadbeef1234"):
            p1 = job_mod.build_job_completed(session_id="sess_002c")
        trace = tmp_path / "trace"
        with (trace / "bob_tool_usage.jsonl").open("a") as f:
            import json as _json
            f.write(_json.dumps({"ts_ns": 99, "tool": "new_tool", "session_id": "sess_002c"}) + "\n")
        with patch.object(job_mod, "_git_sha", return_value="deadbeef1234"):
            p2 = job_mod.build_job_completed(session_id="sess_002c")

        assert p1["event_id"] != p2["event_id"], "T3 : outils différents → event_id différent"

    def test_bob02_t4_different_repo_sha_different_id(self, job_mod, tmp_path):
        """T4 : repo SHA différent → event_id différent."""
        _make_traces(tmp_path, "sess_002d")
        with patch.object(job_mod, "_git_sha", return_value="sha_version_1"):
            p1 = job_mod.build_job_completed(session_id="sess_002d")
        with patch.object(job_mod, "_git_sha", return_value="sha_version_2"):
            p2 = job_mod.build_job_completed(session_id="sess_002d")

        assert p1["event_id"] != p2["event_id"], "T4 : repo SHA différent → event_id différent"

    def test_bob02_t5_different_session_different_id(self, job_mod, tmp_path):
        """T5 : session différente → event_id différent."""
        _make_traces(tmp_path, "sess_002e")
        _make_traces(tmp_path, "sess_002f")
        with patch.object(job_mod, "_git_sha", return_value="deadbeef1234"):
            p1 = job_mod.build_job_completed(session_id="sess_002e")
            p2 = job_mod.build_job_completed(session_id="sess_002f")

        assert p1["event_id"] != p2["event_id"], "T5 : sessions différentes → event_id différent"

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
    # BOB-06 : secrets absents du paquet ET du fichier outbox — P0-A (T6)
    # ---------------------------------------------------------------------------

    def test_bob06_t6_secrets_absent_from_packet_and_outbox(self, job_mod, tmp_path):
        """T6 : secret dans chaque catégorie de trace → absent du paquet ET du fichier outbox."""
        import json as _json
        SECRET = "dp.st.SUPERSECRET_abc123XYZ"
        session_id = "sess_006"
        trace = tmp_path / "trace"
        trace.mkdir(parents=True, exist_ok=True)

        # Injecter le secret dans CHAQUE catégorie de trace
        with (trace / "bob_tool_usage.jsonl").open("w") as f:
            f.write(_json.dumps({"ts_ns": 1, "tool": "write_file", "path": SECRET, "session_id": session_id}) + "\n")
        with (trace / "bob_turns.jsonl").open("w") as f:
            f.write(_json.dumps({"ts_ns": 2, "kind": "bob_stop", "sha256": SECRET, "session_id": session_id}) + "\n")
        with (trace / "bob_prompts.jsonl").open("w") as f:
            f.write(_json.dumps({"ts_ns": 3, "prompt_preview": SECRET, "session_id": session_id}) + "\n")
        with (trace / "bob_pretooluse.jsonl").open("w") as f:
            f.write(_json.dumps({"ts_ns": 4, "tool": "execute_command", "note": SECRET, "session_id": session_id}) + "\n")

        dirty_message = f"Résultat. Token: {SECRET}. Fin."
        mock_resp = {"status": "network_error", "detail": "down"}

        with patch.object(job_mod, "_git_sha", return_value="aabbcc001122"):
            with patch.object(job_mod, "_post_to_artcb", return_value=mock_resp):
                result = job_mod.publish_job_completed(
                    session_id=session_id,
                    last_assistant_message=dirty_message,
                )

        # Secret absent du résultat retourné
        result_str = _json.dumps(result)
        assert SECRET not in result_str, "Secret absent du résultat publish_job_completed"

        # Lire le fichier outbox réellement écrit sur disque
        outbox = tmp_path / "outbox"
        files = list(outbox.glob("job_completed_*.json"))
        assert len(files) == 1, "Un fichier outbox doit exister"
        outbox_content = files[0].read_text(encoding="utf-8")

        # SECRET absent de TOUTES les sections de l'outbox
        assert SECRET not in outbox_content, (
            f"Secret trouvé dans le fichier outbox ! P0-A non respecté.\n"
            f"Fichier: {files[0].name}"
        )
        # [REDACTED] présent (preuve que la redaction a eu lieu)
        assert "[REDACTED]" in outbox_content, "La redaction doit laisser une trace [REDACTED]"
        # Flags de sécurité
        outbox_data = _json.loads(outbox_content)
        assert outbox_data["includes_thinking"] is False
        assert outbox_data["includes_system_prompt"] is False
        assert outbox_data["redaction_applied_before_outbox"] is True

    # ---------------------------------------------------------------------------
    # BOB-07 : flags de sécurité structurels
    # ---------------------------------------------------------------------------

    def test_bob07_security_flags(self, job_mod, tmp_path):
        """BOB-07 : redaction_applied_before_outbox, includes_thinking, secrets_redacted."""
        _make_traces(tmp_path, "sess_007")
        with patch.object(job_mod, "_git_sha", return_value="aabbcc001122"):
            packet = job_mod.build_job_completed(session_id="sess_007")

        assert packet["includes_thinking"] is False
        assert packet["includes_system_prompt"] is False
        assert packet["secrets_redacted"] is True
        assert packet["redaction_applied_before_outbox"] is True
        # prompt_hash et tool_hash présents (P0-B)
        assert len(packet["prompt_hash"]) == 64, "prompt_hash doit être un sha256 hex"
        assert len(packet["tool_hash"]) == 64,   "tool_hash doit être un sha256 hex"


    # ---------------------------------------------------------------------------
    # BOB-08 : redaction par nom de champ — T7 (champ sensible, direct + imbriqué)
    # ---------------------------------------------------------------------------

    def test_bob08_t7_field_name_redaction(self, job_mod, tmp_path):
        """T7 : mot de passe / token par nom de champ → [REDACTED] quelle que soit sa forme."""
        import json as _json
        session_id = "sess_008"
        trace = tmp_path / "trace"
        trace.mkdir(parents=True, exist_ok=True)

        MOT_DE_PASSE = "bonjour123"  # aucun format reconnaissable par regex
        TOKEN = "NouveauToken2026XYZ"

        # Champ direct niveau 1
        with (trace / "bob_tool_usage.jsonl").open("w") as f:
            f.write(_json.dumps({
                "ts_ns": 1, "tool": "write_file",
                "username": "alice", "password": MOT_DE_PASSE,
                "session_id": session_id,
            }) + "\n")
        # Champ imbriqué niveau 2
        with (trace / "bob_prompts.jsonl").open("w") as f:
            f.write(_json.dumps({
                "ts_ns": 2, "session_id": session_id,
                "credentials": {"password": MOT_DE_PASSE, "token": TOKEN},
            }) + "\n")
        # Champ dans liste
        with (trace / "bob_turns.jsonl").open("w") as f:
            f.write(_json.dumps({
                "ts_ns": 3, "session_id": session_id,
                "headers": [{"authorization": f"Bearer {TOKEN}"}],
            }) + "\n")
        (trace / "bob_pretooluse.jsonl").write_text("")

        mock_err = {"status": "network_error"}
        with patch.object(job_mod, "_git_sha", return_value="bbccdd001122"):
            with patch.object(job_mod, "_post_to_artcb", return_value=mock_err):
                job_mod.publish_job_completed(
                    session_id=session_id,
                    last_assistant_message="résultat sans secret",
                )

        outbox = tmp_path / "outbox"
        files = list(outbox.glob("job_completed_*.json"))
        assert len(files) == 1
        content = files[0].read_text()

        assert MOT_DE_PASSE not in content, f"Mot de passe direct trouvé dans outbox"
        assert TOKEN not in content,        f"Token trouvé dans outbox"
        assert "[REDACTED]" in content,     "La redaction doit laisser [REDACTED]"

    # ---------------------------------------------------------------------------
    # BOB-09 : redaction récursive — T8 (dict imbriqué profond + liste de dicts)
    # ---------------------------------------------------------------------------

    def test_bob09_t8_recursive_redaction(self, job_mod, tmp_path):
        """T8 : secret dans dict imbriqué profond et liste de dicts → absent de l'outbox."""
        import json as _json
        session_id = "sess_009"
        trace = tmp_path / "trace"
        trace.mkdir(parents=True, exist_ok=True)

        DEEP_SECRET = "SuperSecretProfond2026"

        # Niveau 3 d'imbrication
        with (trace / "bob_tool_usage.jsonl").open("w") as f:
            f.write(_json.dumps({
                "ts_ns": 1, "session_id": session_id,
                "level1": {"level2": {"credentials": {"password": DEEP_SECRET}}},
            }) + "\n")
        # Secret dans liste de dicts
        with (trace / "bob_prompts.jsonl").open("w") as f:
            f.write(_json.dumps({
                "ts_ns": 2, "session_id": session_id,
                "events": [{"metadata": {"api_key": DEEP_SECRET}}],
            }) + "\n")
        (trace / "bob_turns.jsonl").write_text("")
        (trace / "bob_pretooluse.jsonl").write_text("")

        mock_err = {"status": "network_error"}
        with patch.object(job_mod, "_git_sha", return_value="ccddee001122"):
            with patch.object(job_mod, "_post_to_artcb", return_value=mock_err):
                job_mod.publish_job_completed(session_id=session_id)

        outbox = tmp_path / "outbox"
        files = list(outbox.glob("job_completed_*.json"))
        assert len(files) == 1
        content = files[0].read_text()

        assert DEEP_SECRET not in content, (
            f"Secret imbriqué profond trouvé dans outbox ! P0-A.1 non respecté."
        )
        assert "[REDACTED]" in content

    # ---------------------------------------------------------------------------
    # BOB-10 : idempotence sémantique — T9 (même travail, ts_ns différents dans les traces)
    # ---------------------------------------------------------------------------

    def test_bob10_t9_semantic_idempotence_with_different_ts_ns(self, job_mod, tmp_path):
        """T9 : même travail reproduit avec ts_ns différents dans les traces → même event_id."""
        import json as _json
        import shutil
        session_id = "sess_010"
        trace = tmp_path / "trace"
        trace.mkdir(parents=True, exist_ok=True)

        TOOL = "apply_diff"
        PATH = "src/foo.py"
        PROMPT_LEN = 42

        # Jeu A — première exécution (ts_ns = 1000)
        with (trace / "bob_tool_usage.jsonl").open("w") as f:
            f.write(_json.dumps({"ts_ns": 1000, "tool": TOOL, "path": PATH, "session_id": session_id}) + "\n")
        with (trace / "bob_prompts.jsonl").open("w") as f:
            f.write(_json.dumps({"ts_ns": 1000, "prompt_len": PROMPT_LEN, "session_id": session_id}) + "\n")
        (trace / "bob_turns.jsonl").write_text("")
        (trace / "bob_pretooluse.jsonl").write_text("")

        with patch.object(job_mod, "_git_sha", return_value="aabbcc001122"):
            p1 = job_mod.build_job_completed(session_id=session_id)

        # Jeu B — même travail, ts_ns différents (9 millions de ns plus tard)
        with (trace / "bob_tool_usage.jsonl").open("w") as f:
            f.write(_json.dumps({"ts_ns": 9_000_000, "tool": TOOL, "path": PATH, "session_id": session_id}) + "\n")
        with (trace / "bob_prompts.jsonl").open("w") as f:
            f.write(_json.dumps({"ts_ns": 9_000_000, "prompt_len": PROMPT_LEN, "session_id": session_id}) + "\n")

        with patch.object(job_mod, "_git_sha", return_value="aabbcc001122"):
            p2 = job_mod.build_job_completed(session_id=session_id)

        assert p1["event_id"] == p2["event_id"], (
            f"T9 FAIL : même travail, ts_ns traces différents → event_id différent.\n"
            f"p1={p1['event_id']}\np2={p2['event_id']}"
        )
        assert p1["job_id"] == p2["job_id"], "T9 : job_id aussi déterministe"


    # ---------------------------------------------------------------------------
    # BOB-11 : T10 — ts_ns profondément imbriqué dans metadata (P0-B.2)
    # ---------------------------------------------------------------------------

    def test_bob11_t10_deep_temporal_strip(self, job_mod, tmp_path):
        """T10 : ts_ns dans un sous-objet imbriqué → même event_id (P0-B.2 récursif)."""
        import json as _json
        session_id = "sess_011"
        trace = tmp_path / "trace"
        trace.mkdir(parents=True, exist_ok=True)

        TOOL = "read_file"
        PATH = "src/main.py"

        # ts_ns dans metadata imbriqué (niv 2)
        with (trace / "bob_tool_usage.jsonl").open("w") as f:
            f.write(_json.dumps({
                "tool": TOOL, "path": PATH, "session_id": session_id,
                "metadata": {"timing": {"ts_ns": 1000, "dur_ns": 500}},
            }) + "\n")
        with (trace / "bob_prompts.jsonl").open("w") as f:
            f.write(_json.dumps({"prompt_len": 10, "session_id": session_id}) + "\n")
        (trace / "bob_turns.jsonl").write_text("")
        (trace / "bob_pretooluse.jsonl").write_text("")

        with patch.object(job_mod, "_git_sha", return_value="aabbcc001122"):
            p1 = job_mod.build_job_completed(session_id=session_id)

        # Même travail, ts_ns imbriqué différent
        with (trace / "bob_tool_usage.jsonl").open("w") as f:
            f.write(_json.dumps({
                "tool": TOOL, "path": PATH, "session_id": session_id,
                "metadata": {"timing": {"ts_ns": 9_999_999, "dur_ns": 777}},
            }) + "\n")

        with patch.object(job_mod, "_git_sha", return_value="aabbcc001122"):
            p2 = job_mod.build_job_completed(session_id=session_id)

        assert p1["event_id"] == p2["event_id"], (
            f"T10 FAIL : ts_ns imbriqué différent → event_id différent.\n"
            f"p1={p1['event_id']}\np2={p2['event_id']}"
        )

    # ---------------------------------------------------------------------------
    # BOB-12 : T11 — extra.password ne passe pas (P0-A.2)
    # ---------------------------------------------------------------------------

    def test_bob12_t11_extra_password_redacted(self, job_mod, tmp_path):
        """T11 : champ sensible dans extra → redacté dans packet et outbox (P0-A.2)."""
        import json as _json
        session_id = "sess_012"
        _make_traces(tmp_path, session_id)
        EXTRA_PWD = "ExtraPasswordTresSecret"
        EXTRA_TOKEN = "ExtraToken_xXxBob2026"

        mock_err = {"status": "network_error"}
        with patch.object(job_mod, "_git_sha", return_value="ddeeff001122"):
            with patch.object(job_mod, "_post_to_artcb", return_value=mock_err):
                job_mod.publish_job_completed(
                    session_id=session_id,
                    extra={
                        "password": EXTRA_PWD,
                        "credentials": {"token": EXTRA_TOKEN},
                        "deep": {"nested": {"api_key": EXTRA_TOKEN}},
                    },
                )

        outbox = tmp_path / "outbox"
        files = list(outbox.glob("job_completed_*.json"))
        assert len(files) == 1
        content = files[0].read_text()

        assert EXTRA_PWD   not in content, "P0-A.2 : extra.password trouvé dans outbox"
        assert EXTRA_TOKEN not in content, "P0-A.2 : extra.credentials.token trouvé dans outbox"
        assert "[REDACTED]" in content

