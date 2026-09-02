"""WebAuthn fingerprint + camera face enrollment. No raw biometric storage."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from artcb.security.webauthn_protocol import software_assert_credential, software_create_credential
from artcb.security.webauthn_store import find_face, load_credentials

ORIGIN = "http://testserver"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_ALLOW_MULTI_WALLET", "true")
    from api.main import create_app

    return TestClient(create_app())


def test_fingerprint_register_and_login(client: TestClient) -> None:
    begin = client.post(
        "/api/v1/auth/webauthn/register/options",
        json={"name": "bio_alice", "modality": "fingerprint", "create_wallet": True},
    )
    assert begin.status_code == 200, begin.text
    options = begin.json()["publicKey"]
    _key, cred = software_create_credential(options=options, origin=ORIGIN)
    finish = client.post(
        "/api/v1/auth/webauthn/register/verify",
        json={"name": "bio_alice", "modality": "fingerprint", "credential": cred, "create_wallet": True},
    )
    assert finish.status_code == 200, finish.text
    body = finish.json()
    assert body["ok"] is True
    assert body["raw_biometric_stored"] is False
    assert body["session_token"].startswith("sess_")
    assert body["address"].startswith("artcb1")
    assert body["seed_hex"]
    assert load_credentials()

    login_opt = client.post(
        "/api/v1/auth/webauthn/login/options",
        json={"name": "bio_alice", "modality": "fingerprint"},
    )
    assert login_opt.status_code == 200, login_opt.text
    assertion = software_assert_credential(
        options=login_opt.json()["publicKey"],
        origin=ORIGIN,
        private_key=_key,
        credential_id=cred["id"],
        sign_count=2,
    )
    logged = client.post(
        "/api/v1/auth/webauthn/login/verify",
        json={"name": "bio_alice", "credential": assertion},
    )
    assert logged.status_code == 200, logged.text
    assert logged.json()["session_token"].startswith("sess_")
    assert logged.json()["raw_biometric_stored"] is False


def test_face_webauthn_second_factor(client: TestClient) -> None:
    begin = client.post(
        "/api/v1/auth/webauthn/register/options",
        json={"name": "bio_bob", "modality": "face", "create_wallet": True},
    )
    options = begin.json()["publicKey"]
    _key, cred = software_create_credential(options=options, origin=ORIGIN)
    finish = client.post(
        "/api/v1/auth/webauthn/register/verify",
        json={"name": "bio_bob", "modality": "face", "credential": cred, "create_wallet": True},
    )
    assert finish.status_code == 200, finish.text
    status = client.get("/api/v1/auth/webauthn/status", params={"name": "bio_bob"})
    assert status.json()["face_webauthn_enrolled"] is True
    assert status.json()["raw_biometric_stored"] is False


def test_camera_face_enroll_rejects_raw_image(client: TestClient) -> None:
    opt = client.post("/api/v1/auth/face/enroll/options", json={"name": "bio_cara", "create_wallet": True})
    assert opt.status_code == 200
    nonce = opt.json()["nonce"]
    rejected = client.post(
        "/api/v1/auth/face/enroll/verify",
        json={
            "name": "bio_cara",
            "nonce": nonce,
            "device_secret": "a" * 64,
            "liveness_ok": True,
            "image": "data:image/png;base64,AAAA",
        },
    )
    assert rejected.status_code == 400
    assert "raw_biometric" in rejected.json()["detail"]


def test_camera_face_enroll_and_login(client: TestClient) -> None:
    opt = client.post("/api/v1/auth/face/enroll/options", json={"name": "bio_dana", "create_wallet": True})
    nonce = opt.json()["nonce"]
    secret = "b" * 64
    enrolled = client.post(
        "/api/v1/auth/face/enroll/verify",
        json={
            "name": "bio_dana",
            "nonce": nonce,
            "device_secret": secret,
            "liveness_ok": True,
            "create_wallet": True,
        },
    )
    assert enrolled.status_code == 200, enrolled.text
    assert enrolled.json()["enrolled"] == "face_camera"
    assert find_face("bio_dana") is not None
    assert "image" not in (find_face("bio_dana") or {})

    login_opt = client.post("/api/v1/auth/face/login/options", json={"name": "bio_dana"})
    logged = client.post(
        "/api/v1/auth/face/login",
        json={
            "name": "bio_dana",
            "nonce": login_opt.json()["nonce"],
            "device_secret": secret,
            "liveness_ok": True,
        },
    )
    assert logged.status_code == 200, logged.text
    assert logged.json()["session_token"].startswith("sess_")


def test_wrong_face_secret_rejected(client: TestClient) -> None:
    opt = client.post("/api/v1/auth/face/enroll/options", json={"name": "bio_eve", "create_wallet": True})
    client.post(
        "/api/v1/auth/face/enroll/verify",
        json={
            "name": "bio_eve",
            "nonce": opt.json()["nonce"],
            "device_secret": "c" * 64,
            "liveness_ok": True,
        },
    )
    login_opt = client.post("/api/v1/auth/face/login/options", json={"name": "bio_eve"})
    bad = client.post(
        "/api/v1/auth/face/login",
        json={
            "name": "bio_eve",
            "nonce": login_opt.json()["nonce"],
            "device_secret": "d" * 64,
            "liveness_ok": True,
        },
    )
    assert bad.status_code == 401
