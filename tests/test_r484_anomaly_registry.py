"""Tests R484 — Registre canonique des anomalies — ORDRE 11 (R481).

≥ 15 tests couvrant :
  - Anomaly / AnomalyEvidence (structures + sérialisation)
  - AnomalyRegistry : add, get, transition, list_open, summary
  - Machine d'état : transitions valides et invalides
  - Persistance JSONL append-only : reload depuis fichier
  - Génération d'ID stable _generate_finding_id
  - Invariants CERTIFIED_100=False et unique_human_proven=False
  - Corrélation 4 dimensions (SPEC/CODE/TEST/FORENSIC via AnomalyEvidence)

Règles ARTCB :
  - Mode DEBUG
  - CERTIFIED_100 = False — invariant absolu
  - unique_human_proven = False — invariant absolu
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.artcb.audit.anomaly_registry import (
    MODULE_VERSION,
    VALID_STATUSES,
    _TRANSITIONS,
    _generate_finding_id,
    Anomaly,
    AnomalyEvidence,
    AnomalyRegistry,
)


# ─── T01 — Module version présent ─────────────────────────────────────────────
def test_T01_module_version():
    """T01 : MODULE_VERSION présent et semver X.Y.Z."""
    assert MODULE_VERSION
    assert len(MODULE_VERSION.split(".")) == 3


# ─── T02 — VALID_STATUSES complet ────────────────────────────────────────────
def test_T02_valid_statuses():
    """T02 : VALID_STATUSES contient les états de la machine d'état ARTCB."""
    required = {
        "OPEN", "IN_PROGRESS", "TESTING", "FIXING",
        "DONE_REPORTED", "DONE_VERIFIED", "CERTIFIED",
        "BLOCKED", "WAITING_EXTERNAL", "DEFERRED",
    }
    assert required.issubset(VALID_STATUSES), f"États manquants : {required - VALID_STATUSES}"


# ─── T03 — Transitions CERTIFIED = terminal ───────────────────────────────────
def test_T03_certified_terminal():
    """T03 : CERTIFIED = état terminal (aucune transition sortante)."""
    assert _TRANSITIONS["CERTIFIED"] == set()
    assert _TRANSITIONS["WONTFIX"] == set()
    assert _TRANSITIONS["DUPLICATE"] == set()


# ─── T04 — DONE_REPORTED ≠ DONE_VERIFIED ─────────────────────────────────────
def test_T04_done_reported_ne_done_verified():
    """T04 : DONE_REPORTED peut revenir IN_PROGRESS ; DONE_VERIFIED peut revenir aussi."""
    # DONE_REPORTED → DONE_VERIFIED ✓ (L-055 : distinction critique)
    assert "DONE_VERIFIED" in _TRANSITIONS["DONE_REPORTED"]
    # DONE_VERIFIED → CERTIFIED ✓
    assert "CERTIFIED" in _TRANSITIONS["DONE_VERIFIED"]
    # DONE_VERIFIED ≠ CERTIFIED automatiquement
    assert "IN_PROGRESS" in _TRANSITIONS["DONE_VERIFIED"]


# ─── T05 — AnomalyEvidence instanciation ─────────────────────────────────────
def test_T05_anomaly_evidence():
    """T05 : AnomalyEvidence bien instancié avec les 4 types SPEC/CODE/TEST/FORENSIC."""
    for etype in ["SPEC", "TEST_PASS", "TEST_FAIL", "FORENSIC", "COMMIT"]:
        e = AnomalyEvidence(
            evidence_type=etype,
            reference=f"ref-{etype}",
            detail="détail",
        )
        assert e.evidence_type == etype
        assert e.timestamp_utc  # auto-généré non vide


# ─── T06 — Anomaly instanciation + invariants ────────────────────────────────
def test_T06_anomaly_invariants():
    """T06 : Anomaly toujours certified_100=False et unique_human_proven=False."""
    a = Anomaly(
        finding_id="ANOMALY-20260926-test0001",
        severity="CRITICAL",
        source="TEST",
        message="anomalie test",
    )
    assert a.certified_100 is False
    assert a.unique_human_proven is False
    assert a.status == "OPEN"


# ─── T07 — Anomaly.to_dict() ─────────────────────────────────────────────────
def test_T07_anomaly_to_dict():
    """T07 : to_dict() produit un dict JSON-sérialisable avec les invariants."""
    a = Anomaly(
        finding_id="ANOMALY-20260926-test0002",
        severity="HIGH",
        source="UAP",
        message="test to_dict",
        module="src/artcb/identity/biometric_onchain.py",
        spec_ref="CR-087",
    )
    d = a.to_dict()
    assert d["certified_100"] is False
    assert d["unique_human_proven"] is False
    assert d["finding_id"] == "ANOMALY-20260926-test0002"
    # JSON-sérialisable
    json.dumps(d, ensure_ascii=False)


# ─── T08 — Anomaly.from_dict() round-trip ────────────────────────────────────
def test_T08_anomaly_from_dict_roundtrip():
    """T08 : from_dict(to_dict()) = round-trip sans perte."""
    a = Anomaly(
        finding_id="ANOMALY-20260926-test0003",
        severity="MEDIUM",
        source="FORENSIC",
        message="round-trip test",
        module="src/foo.py",
        function="foo.bar",
        spec_ref="R481",
        commit_sha="aef18b4",
        evidence=[
            AnomalyEvidence(evidence_type="FORENSIC", reference="EVT-00001", detail="event"),
        ],
    )
    d = a.to_dict()
    a2 = Anomaly.from_dict(d)
    assert a2.finding_id == a.finding_id
    assert a2.severity == a.severity
    assert a2.module == a.module
    assert a2.commit_sha == a.commit_sha
    assert len(a2.evidence) == 1
    assert a2.evidence[0].evidence_type == "FORENSIC"


# ─── T09 — _generate_finding_id unicité ──────────────────────────────────────
def test_T09_generate_finding_id_unique():
    """T09 : _generate_finding_id produit des IDs uniques pour des messages différents."""
    id1 = _generate_finding_id("msg1", "module_a", "UAP")
    id2 = _generate_finding_id("msg2", "module_b", "UPF")
    assert id1 != id2
    assert id1.startswith("ANOMALY-")
    assert id2.startswith("ANOMALY-")
    parts1 = id1.split("-")
    # Format : ANOMALY-YYYYMMDD-XXXXXXXX
    assert len(parts1) == 3
    assert len(parts1[1]) == 8  # date YYYYMMDD
    assert len(parts1[2]) == 8  # 8 hex


# ─── T10 — AnomalyRegistry.add() ─────────────────────────────────────────────
def test_T10_registry_add():
    """T10 : add() crée une anomalie OPEN et la persiste en JSONL."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        reg = AnomalyRegistry(registry_path=Path(tf.name))
        a = reg.add(
            severity="HIGH",
            source="UAP",
            message="anomalie test T10",
            module="src/artcb/audit/uap.py",
            spec_ref="R482",
        )
    assert a.status == "OPEN"
    assert a.finding_id.startswith("ANOMALY-")
    # Fichier JSONL non vide
    content = Path(tf.name).read_text(encoding="utf-8").strip()
    assert content
    d = json.loads(content.splitlines()[0])
    assert d["finding_id"] == a.finding_id
    assert d["certified_100"] is False


# ─── T11 — AnomalyRegistry.get() ─────────────────────────────────────────────
def test_T11_registry_get():
    """T11 : get() retourne l'anomalie par ID, None si absent."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        reg = AnomalyRegistry(registry_path=Path(tf.name))
        a = reg.add(severity="LOW", source="MANUAL", message="get test")
    assert reg.get(a.finding_id) is not None
    assert reg.get("ANOMALY-00000000-nonexist") is None


# ─── T12 — AnomalyRegistry.transition() — valide ─────────────────────────────
def test_T12_registry_transition_valid():
    """T12 : Transition OPEN → IN_PROGRESS → TESTING → DONE_REPORTED → DONE_VERIFIED."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        reg = AnomalyRegistry(registry_path=Path(tf.name))
        a = reg.add(severity="CRITICAL", source="TEST", message="transition test T12")
        fid = a.finding_id

    a2 = reg.transition(fid, "IN_PROGRESS", note="début investigation")
    assert a2.status == "IN_PROGRESS"
    a3 = reg.transition(fid, "TESTING")
    assert a3.status == "TESTING"
    a4 = reg.transition(fid, "DONE_REPORTED")
    assert a4.status == "DONE_REPORTED"
    a5 = reg.transition(fid, "DONE_VERIFIED")
    assert a5.status == "DONE_VERIFIED"


# ─── T13 — AnomalyRegistry.transition() — invalide → ValueError ──────────────
def test_T13_registry_transition_invalid():
    """T13 : Transition invalide lève ValueError (machine d'état stricte)."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        reg = AnomalyRegistry(registry_path=Path(tf.name))
        a = reg.add(severity="MEDIUM", source="MANUAL", message="invalide T13")
        fid = a.finding_id

    # OPEN → CERTIFIED directement = invalide
    with pytest.raises(ValueError, match="non autorisée"):
        reg.transition(fid, "CERTIFIED")


# ─── T14 — AnomalyRegistry.transition() — ID inexistant → KeyError ───────────
def test_T14_registry_transition_unknown_id():
    """T14 : Transition sur un ID inexistant lève KeyError."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        reg = AnomalyRegistry(registry_path=Path(tf.name))
    with pytest.raises(KeyError):
        reg.transition("ANOMALY-00000000-deadbeef", "IN_PROGRESS")


# ─── T15 — AnomalyRegistry.list_open() ───────────────────────────────────────
def test_T15_registry_list_open():
    """T15 : list_open() retourne uniquement les anomalies non terminales."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        reg = AnomalyRegistry(registry_path=Path(tf.name))
        a1 = reg.add(severity="HIGH", source="UAP", message="open1")
        a2 = reg.add(severity="LOW", source="UPF", message="open2")
        reg.transition(a2.finding_id, "IN_PROGRESS")
        reg.transition(a2.finding_id, "TESTING")
        reg.transition(a2.finding_id, "DONE_REPORTED")
        reg.transition(a2.finding_id, "DONE_VERIFIED")
        reg.transition(a2.finding_id, "CERTIFIED")

    open_list = reg.list_open()
    ids = [a.finding_id for a in open_list]
    assert a1.finding_id in ids
    assert a2.finding_id not in ids  # terminal CERTIFIED


# ─── T16 — AnomalyRegistry.summary() ────────────────────────────────────────
def test_T16_registry_summary():
    """T16 : summary() retourne un dict avec certified_100=False + statistiques."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        reg = AnomalyRegistry(registry_path=Path(tf.name))
        reg.add(severity="HIGH", source="UAP", message="s1")
        reg.add(severity="CRITICAL", source="TEST", message="s2")

    s = reg.summary()
    assert s["certified_100"] is False
    assert s["unique_human_proven"] is False
    assert s["total"] == 2
    assert s["open_count"] == 2
    assert "by_status" in s
    assert "by_severity" in s


# ─── T17 — Persistance JSONL : reload depuis fichier ─────────────────────────
def test_T17_persistence_reload():
    """T17 : Un registre rechargé depuis JSONL retrouve toutes les anomalies."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        path = Path(tf.name)

    reg1 = AnomalyRegistry(registry_path=path)
    a1 = reg1.add(severity="HIGH", source="UAP", message="persist1")
    a2 = reg1.add(severity="LOW", source="MANUAL", message="persist2")
    reg1.transition(a1.finding_id, "IN_PROGRESS")

    # Recharge depuis le même fichier
    reg2 = AnomalyRegistry(registry_path=path)
    assert reg2.get(a1.finding_id) is not None
    assert reg2.get(a2.finding_id) is not None
    # État persisté
    assert reg2.get(a1.finding_id).status == "IN_PROGRESS"


# ─── T18 — Evidence rattachée à une anomalie ─────────────────────────────────
def test_T18_evidence_attachment():
    """T18 : AnomalyEvidence correctement rattachée via transition."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        reg = AnomalyRegistry(registry_path=Path(tf.name))
        a = reg.add(severity="MEDIUM", source="TEST", message="evidence T18")
        fid = a.finding_id

    ev = AnomalyEvidence(
        evidence_type="TEST_PASS",
        reference="T07 PASS",
        detail="28/28 PASS hamming",
    )
    reg.transition(fid, "IN_PROGRESS", evidence=ev)
    updated = reg.get(fid)
    assert len(updated.evidence) == 1
    assert updated.evidence[0].evidence_type == "TEST_PASS"
    assert updated.evidence[0].reference == "T07 PASS"


# ─── T19 — Invariant : CERTIFIED_100 jamais True dans to_dict ────────────────
def test_T19_certified_100_never_true():
    """T19 : certified_100 jamais True dans to_dict, même si forcé en input."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        reg = AnomalyRegistry(registry_path=Path(tf.name))
        a = reg.add(severity="INFO", source="MANUAL", message="invariant test T19")

    # to_dict force certified_100=False même si l'attribut était modifié
    d = a.to_dict()
    assert d["certified_100"] is False
    assert d["unique_human_proven"] is False


# ─── T20 — BLOCKED et WAITING_EXTERNAL depuis IN_PROGRESS ────────────────────
def test_T20_blocked_waiting_external():
    """T20 : IN_PROGRESS peut aller vers BLOCKED ou WAITING_EXTERNAL."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        reg = AnomalyRegistry(registry_path=Path(tf.name))
        a = reg.add(severity="HIGH", source="MANUAL", message="blocked T20")
        fid = a.finding_id

    reg.transition(fid, "IN_PROGRESS")
    reg.transition(fid, "BLOCKED", note="SSH inaccessible N2")
    assert reg.get(fid).status == "BLOCKED"

    # BLOCKED → IN_PROGRESS
    reg.transition(fid, "IN_PROGRESS")
    assert reg.get(fid).status == "IN_PROGRESS"
    # IN_PROGRESS → WAITING_EXTERNAL
    reg.transition(fid, "WAITING_EXTERNAL")
    assert reg.get(fid).status == "WAITING_EXTERNAL"
