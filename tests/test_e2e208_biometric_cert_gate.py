"""Phase 208 — biometric stack on main + honest certification gate.

Does not flip OPERATOR_MAINNET_CERTIFICATION_GO. Loads DV RESULT.json.
"""

from __future__ import annotations

from pathlib import Path

from artcb.devnet_validation import (
    DECISIONS_205,
    OPERATOR_MAINNET_CERTIFICATION_GO,
    certification_gate,
    load_dv_verdicts,
)
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS

ROOT = Path(__file__).resolve().parents[1]


def test_load_dv_verdicts_matches_result_files() -> None:
    verdicts = load_dv_verdicts()
    assert verdicts["DV-01"] == "PASS"
    assert verdicts["DV-03"] == "PASS"
    assert verdicts["DV-04"] == "PASS"
    assert verdicts["DV-05"] == "PASS"
    assert verdicts["DV-07"] == "PASS"
    # Remaining live blockers until sim 208 measures otherwise.
    assert verdicts["DV-02"] in {"PASS", "PARTIAL"}
    assert verdicts["DV-06"] in {"PASS", "PARTIAL"}
    gate = certification_gate(verdicts)
    assert gate["certified_distributed_mainnet"] is False
    assert OPERATOR_MAINNET_CERTIFICATION_GO is False
    assert gate["economic_v_locked"] is True
    assert gate["live_bft_implemented"] is True
    if verdicts["DV-02"] != "PASS":
        assert "DV-02" in gate["dv_not_pass"]
    if verdicts["DV-06"] != "PASS":
        assert "DV-06" in gate["dv_not_pass"]
    assert "operator_certification_go=false" in gate["reason"]


def test_biometric_stack_is_webauthn_not_raw_images() -> None:
    proto = (ROOT / "src" / "artcb" / "security" / "webauthn_protocol.py").read_text(encoding="utf-8")
    cose = (ROOT / "src" / "artcb" / "security" / "webauthn_cose.py").read_text(encoding="utf-8")
    routes = (ROOT / "src" / "api" / "webauthn_routes.py").read_text(encoding="utf-8")
    assert "userVerification" in proto
    assert "ALG_ES256" in cose
    assert "raw_biometric_rejected" in routes
    assert "simplewebauthn" not in proto.lower()
    assert "FaceDetector" in (ROOT / "frontend" / "src" / "components" / "FaceCapture.tsx").read_text(
        encoding="utf-8"
    )
    assert "WebAuthn" in DECISIONS_205["D-055"]
    assert OFFICIAL_COMPUTE_NODE_IDS[-1] == "ovh-node-4"


def test_health_uses_disk_verdicts_not_empty_gate() -> None:
    main = (ROOT / "src" / "api" / "main.py").read_text(encoding="utf-8")
    assert "load_dv_verdicts" in main
    assert "include_router(webauthn_router)" in main
    sim = (ROOT / "scripts" / "run_sim208_dv02_dv06_live.py").read_text(encoding="utf-8")
    assert "install.sh not executed" in sim
    assert "blocks.jsonl not emptied" in sim
    assert "flood_live_vms" not in sim or "SYN" in sim
    report = (ROOT / "rapports" / "208_biometric_cert_gate_2026-09-02.md").read_text(encoding="utf-8")
    assert "NOT MAINNET CERTIFIED" in report
    assert "WebAuthn" in report
    assert "DV-02" in report
    assert "DV-06" in report
