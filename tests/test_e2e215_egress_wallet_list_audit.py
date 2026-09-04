"""Phase 215 — corrections issues des rapports 210 / 211 / 214.

* egress policy (privacy.md Phase 2-3): secrets never leave through webhooks
  or LLM prompts; webhook destinations are SSRF-checked.
* /wallet/list: anonymous callers get the public projection only (210 §9.6).
* /auth/login 401: same text for every failure + biometric hint (210 §9.4).
* biometric routes: honest assurance levels + audit journal (214).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from artcb.privacy import egress

ROOT = Path(__file__).resolve().parents[1]
TEST_PASSWORD = "monMotDePasse42!"
PEM = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH PRIVATE KEY-----"
OPENAI_KEY = "sk-abcdefghijklmnopqrstuvwxyz0123456789"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    from api.main import create_app

    return TestClient(create_app())


def _session(client: TestClient, name: str) -> str:
    client.post("/api/v1/wallet/create", json={"name": name, "password": TEST_PASSWORD})
    r = client.post("/api/v1/auth/login", json={"name": name, "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


def _api_key(client: TestClient, name: str) -> str:
    sess = _session(client, name)
    r = client.post(
        "/api/v1/api-keys/generate",
        json={"label": "egress-test", "scopes": ["read", "write"]},
        headers={"Authorization": f"Bearer {sess}"},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


# --------------------------------------------------------------------------- #
#  egress kernel
# --------------------------------------------------------------------------- #

def test_egress_named_field_is_removed_not_masked() -> None:
    decision = egress.check_payload({"event": "x", "payload": {"index": 3, "api_key": "whatever", "hash": "a" * 64}})
    assert decision.outcome == egress.OUTCOME_REDACT
    assert "api_key" not in decision.payload["payload"]
    # a 64-hex block hash is NOT treated as a seed: same shape, different meaning
    assert decision.payload["payload"]["hash"] == "a" * 64
    assert decision.counts == {"credentials": 1}


def test_egress_inline_token_is_replaced_and_pem_blocks() -> None:
    redacted, findings = egress.redact_text(f"use {OPENAI_KEY} to call the API, contact alice@example.org")
    assert OPENAI_KEY not in redacted
    assert egress.REDACTED in redacted
    assert "alice@example.org" in redacted  # contact reported, not enforced
    assert {f.type for f in findings} == {"credentials", "contact"}

    blocked = egress.check_payload({"note": PEM})
    assert blocked.outcome == egress.OUTCOME_BLOCK
    assert blocked.payload is None


def test_egress_redaction_that_empties_payload_escalates_to_block() -> None:
    assert egress.check_payload({"token": "abc"}).outcome == egress.OUTCOME_BLOCK


def test_egress_detects_artcb_specific_shapes() -> None:
    labels = {f.label for f in egress.detect({"t": "artcb_" + "A" * 30, "s": "sess_" + "0" * 64, "d": "dp.st." + "x" * 24})}
    assert {"artcb_api_key", "artcb_session_token", "doppler_token"} <= labels


def test_webhook_url_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTCB_ALLOW_LOCAL_PEERS", "0")
    assert egress.webhook_url_ok("http://169.254.169.254/latest/meta-data/") == (False, "link_local_or_reserved_forbidden")
    assert egress.webhook_url_ok("http://127.0.0.1:8000/hook") == (False, "private_or_loopback_forbidden")
    assert egress.webhook_url_ok("http://10.0.0.5/hook") == (False, "private_or_loopback_forbidden")
    assert egress.webhook_url_ok("ftp://example.org/x") == (False, "scheme_forbidden")
    assert egress.webhook_url_ok("https://user:pw@8.8.8.8/x") == (False, "userinfo_forbidden")
    assert egress.webhook_url_ok("https://8.8.8.8/hook") == (True, "public_host")
    monkeypatch.setenv("ARTCB_WEBHOOK_HOSTS", "hooks.example.org")
    assert egress.webhook_url_ok("https://8.8.8.8/hook")[1] == "host_not_in_ARTCB_WEBHOOK_HOSTS"
    monkeypatch.setenv("ARTCB_ALLOW_LOCAL_PEERS", "1")
    monkeypatch.delenv("ARTCB_WEBHOOK_HOSTS")
    assert egress.webhook_url_ok("http://127.0.0.1:8787/hook")[0] is True


def test_webhook_register_rejects_metadata_target(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    key = _api_key(client, "hookowner")
    r = client.post(
        "/api/v1/webhooks/register",
        json={"url": "http://169.254.169.254/latest/", "label": "imds"},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 400
    assert r.json()["detail"].startswith("webhook_url_rejected:")

    ok = client.post(
        "/api/v1/webhooks/register",
        json={"url": "http://127.0.0.1:8787/hook", "label": "local-test"},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert ok.status_code == 200, ok.text


def test_llm_router_redacts_prompt_before_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from artcb.connectors.llm_router import LLMRouter
    from artcb.connectors.manager import ConnectorRecord

    sent: dict[str, str] = {}

    def fake_openai(self, api_key, prompt, *, model):  # noqa: ANN001
        sent["prompt"] = prompt
        return '[{"index": 0, "type": "FACT", "symbol": "O1"}]'

    monkeypatch.setattr(LLMRouter, "_openai_chat", fake_openai)
    record = ConnectorRecord(
        connector_id="c1", provider="openai", label="t", config={}, created_at="0", updated_at="0"
    )
    out = LLMRouter().classify_sentences([f"the key is {OPENAI_KEY}", "plain"], record=record, api_key="k")
    assert out and out[0]["type"] == "FACT"
    assert OPENAI_KEY not in sent["prompt"]
    assert egress.REDACTED in sent["prompt"]


# --------------------------------------------------------------------------- #
#  /wallet/list projection (rapport 210 §9.6)
# --------------------------------------------------------------------------- #

def test_wallet_list_anonymous_is_public_projection(client: TestClient) -> None:
    sess = _session(client, "listme")
    anon = client.get("/api/v1/wallet/list")
    assert anon.status_code == 200
    body = anon.json()
    assert body["projection"] == "public"
    entry = next(w for w in body["wallets"] if w["name"] == "listme")
    assert set(entry) <= {"name", "address", "address_v2", "hybrid", "created_at", "has_key_file"}
    assert "pqc_public_key_hex" not in json.dumps(body)
    assert "auth_methods" not in json.dumps(body)

    full = client.get("/api/v1/wallet/list", headers={"Authorization": f"Bearer {sess}"})
    assert full.json()["projection"] == "full"
    assert "public_key_hex" in next(w for w in full.json()["wallets"] if w["name"] == "listme")


def test_wallet_list_can_be_made_private(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTCB_WALLET_LIST_PUBLIC", "0")
    assert client.get("/api/v1/wallet/list").status_code == 401
    sess = _session(client, "privlist")
    assert client.get("/api/v1/wallet/list", headers={"Authorization": f"Bearer {sess}"}).status_code == 200


# --------------------------------------------------------------------------- #
#  /auth/login 401 (rapport 210 §9.4 / §9.8-E)
# --------------------------------------------------------------------------- #

def test_login_failure_same_detail_and_audited(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    client.post("/api/v1/wallet/create", json={"name": "known", "password": TEST_PASSWORD})
    with caplog.at_level(logging.WARNING, logger="artcb.api.auth"):
        unknown = client.post("/api/v1/auth/login", json={"name": "ghost", "password": "x"})
        wrong = client.post("/api/v1/auth/login", json={"name": "known", "password": "wrong"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]
    assert "biométrique" in wrong.json()["detail"]
    text = caplog.text
    assert "wallet=ghost reason=wallet_unknown" in text
    assert "wallet=known reason=password_mismatch" in text
    assert "wrong" not in text.split("reason=password_mismatch")[0][-200:]  # password never logged


def test_biometric_wallet_cannot_use_password_login(client: TestClient) -> None:
    """A camera-enrolled wallet is sealed with a random vault password: /auth/login must 401."""
    begin = client.post("/api/v1/auth/face/enroll/options", json={"name": "camonly", "create_wallet": True})
    assert begin.status_code == 200
    assert begin.json()["assurance"]["level"] == 1
    done = client.post(
        "/api/v1/auth/face/enroll/verify",
        json={"name": "camonly", "nonce": begin.json()["nonce"], "device_secret": "d" * 64, "liveness_ok": True, "create_wallet": True},
    )
    assert done.status_code == 200, done.text
    assert done.json()["unique_human_proven"] is False
    assert done.json()["label"] == "Vérification de présence faciale locale"
    r = client.post("/api/v1/auth/login", json={"name": "camonly", "password": "anything"})
    assert r.status_code == 401
    assert "/register" in r.json()["detail"]


# --------------------------------------------------------------------------- #
#  biometric assurance + audit journal (rapport 214)
# --------------------------------------------------------------------------- #

def test_webauthn_status_reports_assurance_and_audit_lines(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="artcb.api.webauthn.audit"):
        begin = client.post("/api/v1/auth/face/enroll/options", json={"name": "lvl", "create_wallet": True})
        client.post(
            "/api/v1/auth/face/enroll/verify",
            json={"name": "lvl", "nonce": begin.json()["nonce"], "device_secret": "e" * 64, "liveness_ok": True, "create_wallet": True},
        )
        opts = client.post("/api/v1/auth/face/login/options", json={"name": "lvl"})
        bad = client.post(
            "/api/v1/auth/face/login",
            json={"name": "lvl", "nonce": opts.json()["nonce"], "device_secret": "f" * 64, "liveness_ok": True},
        )
    assert bad.status_code == 401
    st = client.get("/api/v1/auth/webauthn/status", params={"name": "lvl"}).json()
    assert st["face_camera_enrolled"] is True
    assert st["max_assurance_level"] == 1
    assert st["unique_human_proven"] is False
    assert "face_camera" in st["assurance"]
    text = caplog.text
    assert "event=face_enroll_ok wallet=lvl" in text
    assert "event=face_login_failed wallet=lvl" in text and "reason=face_unlock_invalid" in text
    assert "e" * 64 not in text and "f" * 64 not in text  # secrets never in the journal


def test_frontend_wording_is_presence_not_recognition() -> None:
    page = (ROOT / "frontend" / "src" / "pages" / "RegisterBiometric.tsx").read_text(encoding="utf-8")
    i18n = (ROOT / "frontend" / "src" / "i18n" / "translations.ts").read_text(encoding="utf-8")
    assert "reconnaissance faciale" not in page.lower()
    assert "présence faciale locale" in page
    assert "face recognition" not in i18n.lower()
    assert "humain unique" in i18n


def test_readme_follows_d024_d025_not_halving() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "210 000" not in readme
    assert "Halving fixe" not in readme
    assert "D-024" in readme and "D-025" in readme
    assert (ROOT / "docs" / "PROTOCOL_SOURCE_OF_TRUTH.md").is_file()
    groups = (ROOT / "GROUPES_RESEAUX_ARTCB.md").read_text(encoding="utf-8")
    assert "OBSOL" in groups.upper()
