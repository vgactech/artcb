"""Tests réflexe ARTCB (R350–R354) — 2026-09-17.

Vérifie :
  - ReflexEngine.activate() — détection priorité correcte
  - ReflexEngine.check_priority() — mémoire/sécurité/pqc/standard
  - ReflexEngine.detect_trigger() — keywords + fichiers
  - certified=False partout
  - unique_human_proven=False
  - artcb_reflex_check.py — 8/8 PASS
"""
from __future__ import annotations

import os
import sys
import time

import pytest

os.environ.setdefault("ARTCB_WALLET_PASSPHRASE", "artcb_local_dev_passphrase_2026")

from src.artcb.reflex.core import (
    ReflexEngine,
    ReflexPriority,
    ReflexTrigger,
    get_reflex_engine,
)


class TestReflexPriority:
    def test_priority_values(self):
        assert ReflexPriority.REFLEX_MEMORY < ReflexPriority.SECURITY
        assert ReflexPriority.SECURITY < ReflexPriority.PQC
        assert ReflexPriority.PQC < ReflexPriority.OTHER

    def test_reflex_memory_is_zero(self):
        assert int(ReflexPriority.REFLEX_MEMORY) == 0


class TestReflexTrigger:
    def test_trigger_has_required_fields(self):
        t = ReflexTrigger(
            name="TEST",
            priority=ReflexPriority.REFLEX_MEMORY,
            reason="test",
        )
        assert t.name == "TEST"
        assert t.priority == ReflexPriority.REFLEX_MEMORY
        assert t.reason == "test"
        assert t.detected_at > 0

    def test_to_dict(self):
        t = ReflexTrigger(
            name="REFLEX_MEMORY",
            priority=ReflexPriority.REFLEX_MEMORY,
            reason="mémoire",
            keywords=["mémoire"],
        )
        d = t.to_dict()
        assert d["name"] == "REFLEX_MEMORY"
        assert d["priority"] == 0
        assert d["priority_name"] == "REFLEX_MEMORY"
        assert "mémoire" in d["keywords"]


class TestReflexEngineDetect:
    def test_detect_memory_keyword(self):
        engine = ReflexEngine()
        triggers = engine.detect_trigger(text="améliorer la mémoire ARTCB")
        assert any(t.priority == ReflexPriority.REFLEX_MEMORY for t in triggers)

    def test_detect_reflex_keyword(self):
        engine = ReflexEngine()
        triggers = engine.detect_trigger(text="activer le réflexe autonome")
        assert any(t.priority == ReflexPriority.REFLEX_MEMORY for t in triggers)

    def test_detect_thinking_keyword(self):
        engine = ReflexEngine()
        triggers = engine.detect_trigger(text="gérer le thinking et reasoning")
        assert any(t.priority == ReflexPriority.REFLEX_MEMORY for t in triggers)

    def test_detect_security_keyword(self):
        engine = ReflexEngine()
        triggers = engine.detect_trigger(text="implémenter WebAuthn biométrique")
        assert any(t.priority == ReflexPriority.SECURITY for t in triggers)

    def test_detect_pqc_keyword(self):
        engine = ReflexEngine()
        triggers = engine.detect_trigger(text="certification ML-DSA post-quantique")
        assert any(t.priority == ReflexPriority.PQC for t in triggers)

    def test_no_trigger_standard(self):
        engine = ReflexEngine()
        triggers = engine.detect_trigger(text="corriger un bug mineur dans le CSS")
        assert all(t.priority >= ReflexPriority.OTHER for t in triggers)
        # Pas de trigger de haute priorité
        high_priority = [t for t in triggers if t.priority < ReflexPriority.OTHER]
        assert len(high_priority) == 0

    def test_detect_reflex_file(self):
        engine = ReflexEngine()
        triggers = engine.detect_trigger(
            text="mise à jour",
            files=["src/artcb/memory/store.py"],
        )
        assert any(t.priority == ReflexPriority.REFLEX_MEMORY for t in triggers)

    def test_detect_security_file(self):
        engine = ReflexEngine()
        triggers = engine.detect_trigger(
            text="",
            files=["src/api/webauthn_routes.py"],
        )
        assert any(t.priority == ReflexPriority.SECURITY for t in triggers)

    def test_triggers_sorted_by_priority(self):
        engine = ReflexEngine()
        # Prompt avec mémoire + sécurité → mémoire en premier
        triggers = engine.detect_trigger(text="mémoire biométrique WebAuthn réflexe")
        if len(triggers) >= 2:
            priorities = [t.priority for t in triggers]
            assert priorities == sorted(priorities)


class TestReflexEngineActivate:
    def test_activate_returns_report(self):
        engine = ReflexEngine()
        report = engine.activate(text="améliorer la mémoire")
        assert report["reflex_activated"] is True
        assert "priority" in report
        assert "triggers" in report

    def test_activate_memory_priority(self):
        engine = ReflexEngine()
        report = engine.activate(text="réflexe mémoire thinking")
        assert report["priority_name"] == "REFLEX_MEMORY"
        assert report["priority"] == 0

    def test_activate_security_priority(self):
        engine = ReflexEngine()
        report = engine.activate(text="WebAuthn biométrie empreinte")
        assert report["priority_name"] == "SECURITY"

    def test_activate_pqc_priority(self):
        engine = ReflexEngine()
        report = engine.activate(text="ML-DSA post-quantique vpqc2")
        assert report["priority_name"] == "PQC"

    def test_activate_standard_priority(self):
        engine = ReflexEngine()
        report = engine.activate(text="refactorer le module économique")
        assert report["priority_name"] == "OTHER"

    def test_activate_certified_false(self):
        engine = ReflexEngine()
        report = engine.activate(text="test")
        assert report["certified"] is False
        assert report["unique_human_proven"] is False

    def test_activate_stores_activated_at(self):
        engine = ReflexEngine()
        before = time.time()
        engine.activate(text="test")
        after = time.time()
        assert before <= engine._activated_at <= after

    def test_action_memory_is_explicit(self):
        engine = ReflexEngine()
        report = engine.activate(text="réflexe mémoire")
        assert "PRIORITÉ ABSOLUE" in report["action"]

    def test_action_security_is_explicit(self):
        engine = ReflexEngine()
        report = engine.activate(text="WebAuthn biométrie")
        assert "PRIORITÉ 1" in report["action"]


class TestReflexEngineReport:
    def test_report_structure(self):
        engine = ReflexEngine()
        r = engine.report()
        assert "engine" in r
        assert "rules" in r
        assert "certified" in r
        assert r["certified"] is False
        assert r["unique_human_proven"] is False

    def test_report_has_priorities(self):
        engine = ReflexEngine()
        r = engine.report()
        assert "priorities" in r
        assert r["priorities"]["REFLEX_MEMORY"] == 0
        assert r["priorities"]["OTHER"] == 3


class TestReflexEngineCheckPriority:
    def test_check_priority_memory(self):
        engine = ReflexEngine()
        p = engine.check_priority(text="mémoire réflexe thinking")
        assert p == ReflexPriority.REFLEX_MEMORY

    def test_check_priority_standard(self):
        engine = ReflexEngine()
        p = engine.check_priority(text="test unitaire standard")
        assert p == ReflexPriority.OTHER


class TestReflexEngineFromPrompt:
    def test_from_prompt_classmethod(self):
        engine = ReflexEngine.from_prompt("réflexe mémoire ARTCB")
        assert engine._activated_at is not None
        assert len(engine._triggers) > 0

    def test_from_prompt_files(self):
        engine = ReflexEngine.from_prompt(
            "mise à jour",
            files=["src/artcb/memory/concept.py"],
        )
        assert any(t.priority == ReflexPriority.REFLEX_MEMORY for t in engine._triggers)


class TestGetReflexEngine:
    def test_singleton(self):
        e1 = get_reflex_engine()
        e2 = get_reflex_engine()
        assert e1 is e2

    def test_singleton_is_engine(self):
        e = get_reflex_engine()
        assert isinstance(e, ReflexEngine)


class TestReflexCheck:
    """Vérifie que artcb_reflex_check.py retourne 8/8 PASS."""

    def test_all_checks_pass(self):
        """Importe et exécute les checks directement."""
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
        from scripts.artcb_reflex_check import run_checks
        results = run_checks()
        failed = [r for r in results if not r.pass_]
        assert len(failed) == 0, f"Checks échoués: {[r.name + ': ' + r.detail for r in failed]}"
        assert len(results) == 8

    def test_check_names(self):
        from scripts.artcb_reflex_check import run_checks
        results = run_checks()
        names = {r.name for r in results}
        assert "bob_hooks" in names
        assert "cursor_rules" in names
        assert "reflex_module" in names
        assert "certified_100_false" in names
        assert "face_camera_inactive" in names
        assert "pin_not_identity" in names
        assert "unique_human_proven_false" in names
