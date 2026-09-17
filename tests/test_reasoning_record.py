"""Tests — REASONING_RECORD, ReferenceID, FIRST_REFLEX, EARLIEST_DETECTABLE_POINT.

R355 — 2026-09-17.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

# Assure que src/ est dans le path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("ARTCB_DATA_DIR", str(ROOT / "data"))

# ─────────────────────────────────────────────────────────────────────────────
# ReferenceID
# ─────────────────────────────────────────────────────────────────────────────

from src.artcb.reasoning.reference_id import (
    ReferenceID,
    RefType,
    ref_code,
    ref_block,
    ref_rule,
    ref_human,
    ref_from_dict,
)


class TestReferenceID:

    def test_ref_code_canonical(self):
        r = ref_code(path="src/artcb/reflex/core.py", commit="abc123")
        assert r.canonical.startswith("refid:code:")
        assert len(r.ref_id) == 64  # SHA-256 hex

    def test_ref_block_canonical(self):
        r = ref_block(block_index=42, block_hash="aabbcc")
        assert r.canonical.startswith("refid:block:")
        assert r.payload["block_index"] == 42

    def test_ref_rule_canonical(self):
        r = ref_rule(rule_name="R350", rule_file=".cursor/rules/artcb-reflex-priority.mdc")
        assert r.canonical.startswith("refid:rule:")
        assert "R350" in r.payload["rule_name"]

    def test_ref_human_canonical(self):
        r = ref_human(human_id="human_abc123", device_hint="iPhone")
        assert r.canonical.startswith("refid:human:")
        assert r.payload["unique_human_proven"] is False
        assert r.payload["certified_100"] is False

    def test_determinism(self):
        """Même input → même ref_id."""
        r1 = ref_code(path="src/x.py", commit="sha1")
        r2 = ref_code(path="src/x.py", commit="sha1")
        assert r1.ref_id == r2.ref_id
        assert r1.canonical == r2.canonical

    def test_different_paths_different_id(self):
        r1 = ref_code(path="src/a.py", commit="sha1")
        r2 = ref_code(path="src/b.py", commit="sha1")
        assert r1.ref_id != r2.ref_id

    def test_to_dict_roundtrip(self):
        r = ref_rule(rule_name="R355", rule_version="2026-09-17")
        d = r.to_dict()
        r2 = ref_from_dict(d)
        assert r2.ref_id == r.ref_id
        assert r2.canonical == r.canonical

    def test_to_dict_roundtrip_integrity_fail(self):
        r = ref_code(path="test.py")
        d = r.to_dict()
        d["ref_id"] = "tampered"
        with pytest.raises(ValueError, match="integrity mismatch"):
            ref_from_dict(d)

    def test_str_repr(self):
        r = ref_rule(rule_name="R350")
        assert "refid:rule:" in str(r)
        assert "ReferenceID" in repr(r)

    def test_created_at_ns(self):
        before = time.time_ns()
        r = ref_code(path="test.py")
        after = time.time_ns()
        assert before <= r.created_at <= after


# ─────────────────────────────────────────────────────────────────────────────
# FIRST_REFLEX
# ─────────────────────────────────────────────────────────────────────────────

from src.artcb.reasoning.first_reflex import (
    FirstReflex,
    EarliestDetectablePoint,
    EarliestDetectableMethod,
    estimate_earliest_from_logs,
)


class TestFirstReflex:

    def test_basic_creation(self):
        fr = FirstReflex(
            session_id="sess_001",
            trigger_name="REFLEX_MEMORY",
            priority=0,
            evidence={"keywords": ["mémoire", "reflex"], "files": []},
        )
        assert fr.trigger_name == "REFLEX_MEMORY"
        assert fr.priority == 0
        assert len(fr.sha256) == 64

    def test_sha256_determinism(self):
        ts = time.time_ns()
        fr1 = FirstReflex(
            session_id="sess_abc",
            trigger_name="SECURITY",
            priority=1,
            ts_ns=ts,
            evidence={"keywords": ["webauthn"]},
        )
        fr2 = FirstReflex(
            session_id="sess_abc",
            trigger_name="SECURITY",
            priority=1,
            ts_ns=ts,
            evidence={"keywords": ["webauthn"]},
        )
        assert fr1.sha256 == fr2.sha256

    def test_different_session_different_sha(self):
        ts = time.time_ns()
        fr1 = FirstReflex(session_id="s1", trigger_name="PQC", priority=2, ts_ns=ts)
        fr2 = FirstReflex(session_id="s2", trigger_name="PQC", priority=2, ts_ns=ts)
        assert fr1.sha256 != fr2.sha256

    def test_certified_is_false(self):
        fr = FirstReflex(session_id="s", trigger_name="OTHER", priority=3)
        assert fr.certified is False

    def test_to_dict_has_required_keys(self):
        fr = FirstReflex(session_id="s", trigger_name="REFLEX_MEMORY", priority=0)
        d = fr.to_dict()
        for k in ("session_id", "trigger_name", "priority", "ts_ns", "sha256", "certified", "note"):
            assert k in d

    def test_str(self):
        fr = FirstReflex(session_id="s", trigger_name="SECURITY", priority=1)
        assert "FIRST_REFLEX" in str(fr)
        assert "SECURITY" in str(fr)


class TestEarliestDetectablePoint:

    def test_basic_creation(self):
        edp = EarliestDetectablePoint(
            trigger_name="REFLEX_MEMORY",
            chain_height=1142,
            confidence=0.5,
            method=EarliestDetectableMethod.LOG_TRACE,
        )
        assert edp.confidence == 0.5
        assert edp.chain_height == 1142

    def test_confidence_out_of_range(self):
        with pytest.raises(ValueError):
            EarliestDetectablePoint(trigger_name="X", confidence=1.5)
        with pytest.raises(ValueError):
            EarliestDetectablePoint(trigger_name="X", confidence=-0.1)

    def test_certified_is_false(self):
        edp = EarliestDetectablePoint(trigger_name="PQC")
        assert edp.certified is False

    def test_to_dict_has_note(self):
        edp = EarliestDetectablePoint(trigger_name="SECURITY")
        d = edp.to_dict()
        assert "EARLIEST_DETECTABLE_POINT" in d["note"]
        assert "CERTIFIED_100=false" in d["note"]

    def test_estimate_from_logs_no_file(self, tmp_path):
        """Sans fichier de logs → résultat avec confidence=0.0."""
        edp = estimate_earliest_from_logs(
            "REFLEX_MEMORY",
            log_path=str(tmp_path / "nonexistent.jsonl"),
        )
        assert edp.trigger_name == "REFLEX_MEMORY"
        assert edp.confidence == 0.0

    def test_estimate_from_logs_with_match(self, tmp_path):
        """Avec un fichier contenant des mots-clés → confidence=0.35."""
        log_file = tmp_path / "agent_reasoning.jsonl"
        ts = time.time_ns() - 1_000_000_000  # 1s avant maintenant
        log_file.write_text(
            json.dumps({"ts_ns": ts, "kind": "observation", "text": "mémoire réflexe bootstrap"}) + "\n",
            encoding="utf-8",
        )
        edp = estimate_earliest_from_logs(
            "REFLEX_MEMORY",
            log_path=str(log_file),
        )
        assert edp.confidence == 0.35
        assert edp.method == EarliestDetectableMethod.LOG_TRACE


# ─────────────────────────────────────────────────────────────────────────────
# REASONING_RECORD
# ─────────────────────────────────────────────────────────────────────────────

from src.artcb.reasoning.record import (
    ReasoningRecord,
    RecordAction,
    RecordOutcome,
    ReasoningRecordStore,
)


class TestReasoningRecord:

    def _make_record(self, session_id: str = "test_sess") -> ReasoningRecord:
        return ReasoningRecord(
            session_id=session_id,
            agent_id="bob-ide",
            context_summary="Réflexe mémoire détecté",
            action=RecordAction.IMPLEMENT,
            action_detail="Implémentation REASONING_RECORD",
        )

    def test_record_id_is_sha256(self):
        r = self._make_record()
        assert len(r.record_id) == 64

    def test_outcome_default_unknown(self):
        r = self._make_record()
        assert r.outcome == RecordOutcome.UNKNOWN

    def test_seal_updates_outcome(self):
        r = self._make_record()
        r.seal(outcome=RecordOutcome.PASS, outcome_detail="3/3 tests PASS")
        assert r.outcome == RecordOutcome.PASS
        assert r.ts_end_ns is not None

    def test_duration_ms_before_seal(self):
        r = self._make_record()
        assert r.duration_ms() is None

    def test_duration_ms_after_seal(self):
        r = self._make_record()
        time.sleep(0.01)
        r.seal()
        dur = r.duration_ms()
        assert dur is not None
        assert dur >= 0.0

    def test_add_observation(self):
        r = self._make_record()
        r.add_observation("file_modified", path="src/artcb/reasoning/record.py")
        assert len(r.observations) == 1
        assert r.observations[0]["kind"] == "file_modified"

    def test_add_reference(self):
        r = self._make_record()
        ref = ref_rule(rule_name="R355")
        r.add_reference(ref)
        assert len(r.reference_ids) == 1
        assert r.reference_ids[0].canonical == ref.canonical

    def test_to_dict_has_required_keys(self):
        r = self._make_record()
        d = r.to_dict()
        for k in ("record_id", "session_id", "agent_id", "action", "outcome",
                  "ts_start_ns", "certified", "note"):
            assert k in d

    def test_certified_is_false(self):
        r = self._make_record()
        assert r.certified is False
        assert "CERTIFIED_100=false" in r.to_dict()["note"]

    def test_to_memo_content_is_json(self):
        r = self._make_record()
        content = r.to_memo_content()
        parsed = json.loads(content)
        assert parsed["session_id"] == "test_sess"

    def test_str_representation(self):
        r = self._make_record()
        r.seal(outcome=RecordOutcome.PASS)
        s = str(r)
        assert "ReasoningRecord" in s
        assert "pass" in s

    def test_with_first_reflex(self):
        fr = FirstReflex(
            session_id="test_sess",
            trigger_name="REFLEX_MEMORY",
            priority=0,
            evidence={"keywords": ["mémoire"]},
        )
        r = ReasoningRecord(
            session_id="test_sess",
            first_reflex=fr,
            action=RecordAction.ANALYZE,
        )
        d = r.to_dict()
        assert d["first_reflex"] is not None
        assert d["first_reflex"]["trigger_name"] == "REFLEX_MEMORY"


class TestReasoningRecordStore:

    def test_append_and_load(self, tmp_path):
        store = ReasoningRecordStore(tmp_path / "records.jsonl")
        r = ReasoningRecord(session_id="s1", action=RecordAction.TEST)
        store.append(r)
        rows = store.load_all()
        assert len(rows) == 1
        assert rows[0]["session_id"] == "s1"

    def test_load_by_session(self, tmp_path):
        store = ReasoningRecordStore(tmp_path / "records.jsonl")
        store.append(ReasoningRecord(session_id="s1"))
        store.append(ReasoningRecord(session_id="s2"))
        store.append(ReasoningRecord(session_id="s1"))
        rows = store.load_by_session("s1")
        assert len(rows) == 2
        assert all(r["session_id"] == "s1" for r in rows)

    def test_count(self, tmp_path):
        store = ReasoningRecordStore(tmp_path / "records.jsonl")
        for i in range(3):
            store.append(ReasoningRecord(session_id=f"s{i}"))
        assert store.count() == 3

    def test_empty_store(self, tmp_path):
        store = ReasoningRecordStore(tmp_path / "records.jsonl")
        assert store.load_all() == []
        assert store.count() == 0

    def test_append_only_immutable(self, tmp_path):
        """Vérifie qu'append ne modifie pas les lignes précédentes."""
        store = ReasoningRecordStore(tmp_path / "records.jsonl")
        r1 = ReasoningRecord(session_id="s1")
        store.append(r1)
        original_id = r1.record_id
        r2 = ReasoningRecord(session_id="s2")
        store.append(r2)
        rows = store.load_all()
        assert rows[0]["record_id"] == original_id  # r1 non modifié


# ─────────────────────────────────────────────────────────────────────────────
# Intégration : ReflexEngine → REASONING_RECORD
# ─────────────────────────────────────────────────────────────────────────────

from src.artcb.reflex.core import ReflexEngine, ReflexPriority


class TestReflexEngineWithRecord:

    def test_activate_creates_record_id(self):
        engine = ReflexEngine()
        report = engine.activate(
            text="mémoire ARTCB thinking réflexe",
            session_id="test_integration_001",
        )
        assert "record_id" in report
        assert len(report["record_id"]) == 64

    def test_activate_memory_trigger_has_first_reflex(self):
        engine = ReflexEngine()
        report = engine.activate(
            text="mémoire thinking bootstrap réflexe",
            session_id="test_integration_002",
        )
        assert report.get("first_reflex") is not None
        fr = report["first_reflex"]
        assert fr["trigger_name"] == "REFLEX_MEMORY"
        assert fr["priority"] == 0

    def test_activate_noop_no_first_reflex(self):
        engine = ReflexEngine()
        report = engine.activate(
            text="hello world aucun trigger ici",
            session_id="test_integration_003",
        )
        # Aucun trigger → first_reflex None
        assert report.get("first_reflex") is None

    def test_activate_stores_record_locally(self, tmp_path, monkeypatch):
        """Vérifie que le record est persisté dans le store."""
        import src.artcb.reasoning.record as rec_mod
        store = ReasoningRecordStore(tmp_path / "records.jsonl")
        # Remplacer le store global temporairement
        monkeypatch.setattr(rec_mod, "_global_store", store)
        engine = ReflexEngine()
        engine.activate(text="webauthn biometric add_device", session_id="test_store_001")
        assert store.count() >= 1

    def test_activate_security_trigger(self):
        engine = ReflexEngine()
        report = engine.activate(
            text="webauthn biométrie human_identity",
            session_id="test_security_001",
        )
        assert report["priority_name"] == "SECURITY"
        assert report.get("first_reflex") is not None
        assert report["first_reflex"]["trigger_name"] == "SECURITY"

    def test_activate_pqc_trigger(self):
        engine = ReflexEngine()
        report = engine.activate(
            text="ml-dsa pqc certif_vpqc post-quantique",
            session_id="test_pqc_001",
        )
        assert report["priority_name"] == "PQC"

    def test_note_mentions_reasoning_record(self):
        engine = ReflexEngine()
        report = engine.activate(text="mémoire", session_id="test_note")
        assert "REASONING_RECORD" in report.get("note", "")
