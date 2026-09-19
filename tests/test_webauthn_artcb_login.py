"""Tests P0-A v2 — /auth/webauthn/biometric/options + /verify (R384 — 2026-09-18).

Vérifie :
  - Options retourne un challenge + hint
  - Verify avec template enregistré → session (login OK)
  - Verify avec template inconnu → 401
  - Verify avec image brute → 400
  - Verify avec challenge inconnu → 400
  - Verify avec challenge expiré → 400
  - Challenge usage unique (deuxième appel → 400)
  - unique_human_proven=False sur la session
  - certified_100=False

NOTE R384 : Routes renommées /biometric/ pour éviter la collision avec le flux
FIDO2 standard (/auth/webauthn/login/options dans webauthn_routes.py).
"""
from __future__ import annotations

import os
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ARTCB_WALLET_PASSPHRASE", "artcb_local_dev_passphrase_2026")

# ─── Helpers ──────────────────────────────────────────────────────────────────

TEMPLATE_HEX = "ab" * 64  # 64 bytes normalisés — suffisant pour un template stub

# Image PNG minimale (magic bytes PNG)
PNG_MAGIC_HEX = "89504e47" + "00" * 60  # \x89PNG...

# Image JPEG minimale (magic bytes JPEG)
JPEG_MAGIC_HEX = "ffd8ff" + "e0" + "00" * 60


@pytest.fixture(scope="module")
def api(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    """FastAPI TestClient avec state isolé dans tmp_path."""
    tmp = tmp_path_factory.mktemp("webauthn_tests")
    os.environ["ARTCB_DATA_DIR"] = str(tmp)
    from src.api.main import create_app
    return TestClient(create_app(), raise_server_exceptions=True)


def _get_challenge(api: TestClient) -> str:
    """Obtient un challenge WebAuthn ARTCB biométrique (flux template_hex)."""
    r = api.post("/api/v1/auth/webauthn/biometric/options", json={"hint": "fingerprint"})
    assert r.status_code == 200
    return r.json()["challenge"]


# ─── Phase A : /auth/webauthn/biometric/options ───────────────────────────────


class TestWebAuthnOptions:
    def test_options_returns_challenge(self, api: TestClient):
        r = api.post("/api/v1/auth/webauthn/biometric/options", json={})
        assert r.status_code == 200
        data = r.json()
        assert "challenge" in data
        assert len(data["challenge"]) == 64  # hex 32 bytes

    def test_options_challenge_is_unique(self, api: TestClient):
        r1 = api.post("/api/v1/auth/webauthn/biometric/options", json={})
        r2 = api.post("/api/v1/auth/webauthn/biometric/options", json={})
        assert r1.json()["challenge"] != r2.json()["challenge"]

    def test_options_returns_hint(self, api: TestClient):
        r = api.post("/api/v1/auth/webauthn/biometric/options", json={"hint": "face"})
        assert r.json()["hint"] == "face"

    def test_options_default_hint_fingerprint(self, api: TestClient):
        r = api.post("/api/v1/auth/webauthn/biometric/options", json={})
        assert r.json()["hint"] == "fingerprint"

    def test_options_certified_false(self, api: TestClient):
        r = api.post("/api/v1/auth/webauthn/biometric/options", json={})
        assert r.json()["certified_100"] is False
        assert r.json()["unique_human_proven"] is False

    def test_options_returns_instructions(self, api: TestClient):
        r = api.post("/api/v1/auth/webauthn/biometric/options", json={})
        assert "instructions" in r.json()


# ─── Phase B : /auth/webauthn/biometric/verify ───────────────────────────────


class TestWebAuthnVerifyRawImageRejected:
    """Spec §3 : l'image brute ne doit JAMAIS être transmise."""

    def test_png_image_rejected(self, api: TestClient):
        chal = _get_challenge(api)
        r = api.post("/api/v1/auth/webauthn/biometric/verify", json={
            "challenge": chal,
            "template_hex": PNG_MAGIC_HEX,
        })
        assert r.status_code == 400
        assert "raw_image_rejected" in r.json()["detail"]

    def test_jpeg_image_rejected(self, api: TestClient):
        chal = _get_challenge(api)
        r = api.post("/api/v1/auth/webauthn/biometric/verify", json={
            "challenge": chal,
            "template_hex": JPEG_MAGIC_HEX,
        })
        assert r.status_code == 400
        assert "raw_image_rejected" in r.json()["detail"]

    def test_bmp_image_rejected(self, api: TestClient):
        chal = _get_challenge(api)
        # BMP magic = 0x424D "BM"
        bmp_hex = "424d" + "00" * 62
        r = api.post("/api/v1/auth/webauthn/biometric/verify", json={
            "challenge": chal,
            "template_hex": bmp_hex,
        })
        assert r.status_code == 400
        assert "raw_image_rejected" in r.json()["detail"]


class TestWebAuthnVerifyChallengeValidation:
    def test_unknown_challenge_rejected(self, api: TestClient):
        r = api.post("/api/v1/auth/webauthn/biometric/verify", json={
            "challenge": "00" * 32,
            "template_hex": TEMPLATE_HEX,
        })
        assert r.status_code == 400
        assert "webauthn_challenge_unknown" in r.json()["detail"]

    def test_expired_challenge_rejected(self, api: TestClient):
        """Challenge expiré (TTL passé)."""
        from src.api import auth_routes
        chal = "ee" * 32
        auth_routes._webauthn_challenges[chal] = time.time() - 1  # déjà expiré
        r = api.post("/api/v1/auth/webauthn/biometric/verify", json={
            "challenge": chal,
            "template_hex": TEMPLATE_HEX,
        })
        assert r.status_code == 400
        assert "expired" in r.json()["detail"]

    def test_invalid_hex_template_pydantic_rejected(self, api: TestClient):
        """template_hex non-hex → 422 (validation Pydantic) ou 400."""
        chal = _get_challenge(api)
        r = api.post("/api/v1/auth/webauthn/biometric/verify", json={
            "challenge": chal,
            "template_hex": "ZZZZZZ" * 20,  # pas du hex valide — longueur OK mais contenu invalide
        })
        # Pydantic laisse passer (min_length OK), notre code rejette en 400
        assert r.status_code in (400, 422)

    def test_challenge_single_use(self, api: TestClient):
        """Un challenge ne peut être utilisé qu'une seule fois."""
        chal = _get_challenge(api)
        # Premier appel (template inconnu → 401 mais challenge consommé)
        api.post("/api/v1/auth/webauthn/biometric/verify", json={
            "challenge": chal,
            "template_hex": TEMPLATE_HEX,
        })
        # Deuxième appel → challenge inconnu
        r2 = api.post("/api/v1/auth/webauthn/biometric/verify", json={
            "challenge": chal,
            "template_hex": TEMPLATE_HEX,
        })
        assert r2.status_code == 400
        assert "unknown" in r2.json()["detail"]


class TestWebAuthnVerifyNoIdentity:
    def test_no_registered_identity_returns_401(self, api: TestClient):
        """Sans identité enregistrée → 401."""
        chal = _get_challenge(api)
        with patch("src.api.biometric_identity_routes._load_records", return_value=[]):
            r = api.post("/api/v1/auth/webauthn/biometric/verify", json={
                "challenge": chal,
                "template_hex": TEMPLATE_HEX,
            })
        assert r.status_code == 401
        assert "not_found" in r.json()["detail"]

    def test_wrong_template_returns_401(self, api: TestClient):
        """Template différent de celui enregistré → 401."""
        from src.artcb.crypto.homomorphic import commit_biometric_template

        # Créer un record fictif avec un template différent
        other_template = bytes.fromhex("cc" * 64)
        commitment = commit_biometric_template(other_template)
        fake_record = {
            "human_id": "test_human_wrong",
            "template_hash": commitment.template_hash_hex,
            "wallet_address": "",
            "wallet_name": "test_wallet",
        }

        chal = _get_challenge(api)
        with patch("src.api.biometric_identity_routes._load_records", return_value=[fake_record]):
            r = api.post("/api/v1/auth/webauthn/biometric/verify", json={
                "challenge": chal,
                "template_hex": TEMPLATE_HEX,  # différent de other_template
            })
        assert r.status_code == 401


class TestWebAuthnVerifySuccess:
    def test_matching_template_returns_session(self, api: TestClient):
        """Template identique à celui enregistré → session émise."""
        from src.artcb.crypto.homomorphic import commit_biometric_template

        template_bytes = bytes.fromhex(TEMPLATE_HEX)
        commitment = commit_biometric_template(template_bytes)
        fake_record = {
            "human_id": "test_human_login",
            "template_hash": commitment.template_hash_hex,
            "wallet_address": "artcb1testaddress000000000000000000000000000",
            "wallet_name": "test_wallet_login",
        }

        chal = _get_challenge(api)
        with patch("src.api.biometric_identity_routes._load_records", return_value=[fake_record]):
            r = api.post("/api/v1/auth/webauthn/biometric/verify", json={
                "challenge": chal,
                "template_hex": TEMPLATE_HEX,
            })

        assert r.status_code == 200
        data = r.json()
        assert "session_token" in data
        assert data["session_token"].startswith("sess_")
        assert data["human_id"] == "test_human_login"
        assert data["login_method"] == "webauthn_artcb_biometric"

    def test_login_session_unique_human_proven_false(self, api: TestClient):
        """La session émise doit avoir unique_human_proven=False (spec §15)."""
        from src.artcb.crypto.homomorphic import commit_biometric_template

        template_bytes = bytes.fromhex(TEMPLATE_HEX)
        commitment = commit_biometric_template(template_bytes)
        fake_record = {
            "human_id": "test_human_uproven",
            "template_hash": commitment.template_hash_hex,
            "wallet_address": "artcb1testaddress000000000000000000000000001",
            "wallet_name": "test_wallet_uproven",
        }

        chal = _get_challenge(api)
        with patch("src.api.biometric_identity_routes._load_records", return_value=[fake_record]):
            r = api.post("/api/v1/auth/webauthn/biometric/verify", json={
                "challenge": chal,
                "template_hex": TEMPLATE_HEX,
            })

        assert r.status_code == 200
        assert r.json()["unique_human_proven"] is False
        assert r.json()["certified_100"] is False

    def test_login_with_human_id_filter(self, api: TestClient):
        """Login avec human_id ciblé (filtre)."""
        from src.artcb.crypto.homomorphic import commit_biometric_template

        template_bytes = bytes.fromhex(TEMPLATE_HEX)
        commitment = commit_biometric_template(template_bytes)
        record_a = {
            "human_id": "human_A",
            "template_hash": commitment.template_hash_hex,
            "wallet_address": "artcb1A",
            "wallet_name": "wallet_A",
        }
        # Record B avec template différent
        other_bytes = bytes.fromhex("ff" * 64)
        commitment_b = commit_biometric_template(other_bytes)
        record_b = {
            "human_id": "human_B",
            "template_hash": commitment_b.template_hash_hex,
            "wallet_address": "artcb1B",
            "wallet_name": "wallet_B",
        }

        chal = _get_challenge(api)
        with patch("src.api.biometric_identity_routes._load_records", return_value=[record_a, record_b]):
            r = api.post("/api/v1/auth/webauthn/biometric/verify", json={
                "challenge": chal,
                "template_hex": TEMPLATE_HEX,
                "human_id": "human_A",
            })
        assert r.status_code == 200
        assert r.json()["human_id"] == "human_A"

    def test_login_human_id_not_found(self, api: TestClient):
        """human_id demandé mais inexistant → 404."""
        chal = _get_challenge(api)
        with patch("src.api.biometric_identity_routes._load_records", return_value=[]):
            r = api.post("/api/v1/auth/webauthn/biometric/verify", json={
                "challenge": chal,
                "template_hex": TEMPLATE_HEX,
                "human_id": "nonexistent_human",
            })
        assert r.status_code == 404
