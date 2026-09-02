"""Phase 205 — start without rescue; biometric enrollment on artcb.me.

Rescue disk injection is forbidden. OVH4 keep-book still needs KEY_API_ARTCB_DOPPLER_4.
Certification stays false.
"""

from __future__ import annotations

from pathlib import Path

from artcb.devnet_validation import (
    DECISIONS_205,
    OPERATOR_MAINNET_CERTIFICATION_GO,
    certification_gate,
    public_lock,
)

ROOT = Path(__file__).resolve().parents[1]


def test_d055_forbids_rescue_and_does_not_certify() -> None:
    gate = certification_gate()
    assert gate["certified_distributed_mainnet"] is False
    assert OPERATOR_MAINNET_CERTIFICATION_GO is True
    text = DECISIONS_205["D-055"]
    assert "rescue" in text.lower()
    assert "WebAuthn" in text
    assert "raw biometric" in text.lower() or "empreinte brute" in text.lower()
    lock = public_lock()
    assert lock["distributed_certified"] is False
    assert "decisions_205" in lock


def test_no_rescue_script_never_enters_rescue_mode() -> None:
    script = (ROOT / "scripts" / "inject_ssh_no_rescue.py").read_text(encoding="utf-8")
    assert "rescueMode" not in script
    assert "FORBID_RESCUE" in script
    assert "remoteConsole" in script or "vnc" in script.lower()
    assert "install.sh" not in script or "not executed" in script
    deploy = (ROOT / "scripts" / "deploy_ovh4.sh").read_text(encoding="utf-8")
    assert "Refusing to deploy OVH4 script onto OVH1" in deploy


def test_frontend_register_route_and_webauthn_client() -> None:
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    home = (ROOT / "frontend" / "src" / "pages" / "Home.tsx").read_text(encoding="utf-8")
    page = (ROOT / "frontend" / "src" / "pages" / "RegisterBiometric.tsx").read_text(encoding="utf-8")
    client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    assert 'path="register"' in app
    assert "/register" in home
    assert "bio_fingerprint" in page
    assert "bio_face" in page
    assert "bio_both" in page
    assert "webauthn/register" in client
    assert "face/enroll" in client
    routes = ROOT / "src" / "api" / "webauthn_routes.py"
    body = routes.read_text(encoding="utf-8")
    assert "raw_biometric_rejected" in body
    assert "userVerification" in (ROOT / "src" / "artcb" / "security" / "webauthn_protocol.py").read_text(
        encoding="utf-8"
    )
