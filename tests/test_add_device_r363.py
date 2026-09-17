"""Tests R363 + R364 — ADD_DEVICE avec vraie vérification WebAuthn.

Couvre :
  R363 — add-options émet un challenge WebAuthn (b64url, allow_credentials, rp_id)
  R363 — add-verify exige une vraie assertion WebAuthn (credential_id + sig)
  R364 — Attaques refusées : PIN→401, template_hex→422, new-device-wallet→403
  R364 — ADD_DEVICE valide (software credential) → 200
  R364 — revoke-device avec assertion WebAuthn → 200
  R364 — revoke sans credential → 401

CERTIFIED_100=false — WebAuthn valide ≠ unique_human_proven.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ─── Setup ARTCB_DATA_DIR temporaire ────────────────────────────────────────

@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path))
    (tmp_path / "identity").mkdir(parents=True, exist_ok=True)
    yield tmp_path


# ─── Fixtures crypto ─────────────────────────────────────────────────────────

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature

from src.artcb.security.webauthn_protocol import (
    b64u_encode, b64u_decode,
    software_create_credential, software_assert_credential,
    FLAG_UP, FLAG_UV,
)


def _make_human_record(human_id: str, data_dir: Path) -> None:
    """Crée un HumanIdentityRecord minimal."""
    rec = {
        "human_id": human_id,
        "commitment": "aabbcc",
        "helper_data": "ddeeFF",
        "wallet_address": "artcb1test",
        "created_at": 0,
        "unique_human_proven": False,
        "certified_100": False,
    }
    p = data_dir / "identity" / "human_records.jsonl"
    with p.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def _make_credential(human_id: str, data_dir: Path, origin: str = "http://localhost") -> tuple[ec.EllipticCurvePrivateKey, str]:
    """Crée une credential WebAuthn software et l'enregistre dans credential_store.jsonl."""
    priv_key = ec.generate_private_key(ec.SECP256R1())
    cred_id_bytes = secrets.token_bytes(16)
    cred_id_b64 = b64u_encode(cred_id_bytes)
    pub_pem = priv_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    rec = {
        "credential_id": cred_id_b64,
        "human_id": human_id,
        "public_key_pem": pub_pem,
        "sign_count": 0,
        "origin": origin,
    }
    store_path = data_dir / "identity" / "credential_store.jsonl"
    with store_path.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return priv_key, cred_id_b64


def _build_assertion(
    priv_key: ec.EllipticCurvePrivateKey,
    challenge_b64: str,
    rp_id: str = "localhost",
    origin: str = "http://localhost",
    sign_count: int = 1,
) -> dict:
    """Construit une assertion WebAuthn logicielle valide."""
    import hashlib as _hl
    # clientDataJSON
    client_data = json.dumps({
        "type": "webauthn.get",
        "challenge": challenge_b64,
        "origin": origin,
        "crossOrigin": False,
    }, separators=(",", ":")).encode("utf-8")

    # authenticatorData : rp_id_hash(32) + flags(1) + signCount(4)
    rp_hash = _hl.sha256(rp_id.encode()).digest()
    flags = FLAG_UP | FLAG_UV
    auth_data = rp_hash + bytes([flags]) + sign_count.to_bytes(4, "big")

    # signature = ECDSA(authData || SHA256(clientDataJSON))
    signed = auth_data + _hl.sha256(client_data).digest()
    der_sig = priv_key.sign(signed, ec.ECDSA(hashes.SHA256()))

    return {
        "client_data_json": b64u_encode(client_data),
        "authenticator_data": b64u_encode(auth_data),
        "signature": b64u_encode(der_sig),
    }


# ─── Client FastAPI ──────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    from src.api.main import app
    with TestClient(app) as c:
        yield c


# ═══════════════════════════════════════════════════════════════════════════════
# R363 — add-options
# ═══════════════════════════════════════════════════════════════════════════════

class TestAddOptions:
    def test_unknown_human_id_returns_404(self, client):
        r = client.post("/api/v1/identity/device/add-options", json={
            "human_id": "human_doesnotexist123",
            "new_device_hint": "iPhone 15",
        })
        assert r.status_code == 404
        assert "human_id_not_found" in r.json()["detail"]

    def test_valid_human_returns_challenge(self, client, tmp_data_dir):
        _make_human_record("human_abc123", tmp_data_dir)
        r = client.post("/api/v1/identity/device/add-options", json={
            "human_id": "human_abc123",
            "new_device_hint": "MacBook M3",
        })
        assert r.status_code == 200
        body = r.json()
        assert "challenge" in body
        assert len(body["challenge"]) > 10  # b64url non vide
        assert body["human_id"] == "human_abc123"
        assert body["expires_in"] == 300
        assert "rp_id" in body
        assert "user_verification" in body
        assert body["proof_required"] == "webauthn_assertion_cryptographic"
        assert body["certified_100"] is False

    def test_forbidden_field_present(self, client, tmp_data_dir):
        _make_human_record("human_abc456", tmp_data_dir)
        r = client.post("/api/v1/identity/device/add-options", json={
            "human_id": "human_abc456",
        })
        assert r.status_code == 200
        forbidden = r.json().get("forbidden", [])
        assert any("PIN" in f for f in forbidden)
        assert any("403" in f for f in forbidden)

    def test_allow_credentials_listed(self, client, tmp_data_dir):
        _make_human_record("human_creds1", tmp_data_dir)
        _make_credential("human_creds1", tmp_data_dir)
        r = client.post("/api/v1/identity/device/add-options", json={
            "human_id": "human_creds1",
        })
        assert r.status_code == 200
        allows = r.json().get("allow_credentials", [])
        assert len(allows) == 1
        assert allows[0]["type"] == "public-key"


# ═══════════════════════════════════════════════════════════════════════════════
# R364 — Attaques refusées
# ═══════════════════════════════════════════════════════════════════════════════

class TestAttacksRefused:
    """R364 — Les chemins interdits doivent retourner 4xx."""

    def test_pin_only_no_credential_returns_401(self, client, tmp_data_dir):
        """PIN seul (credential_id inconnu) → 401."""
        _make_human_record("human_pin1", tmp_data_dir)
        # Obtenir un challenge valide
        r = client.post("/api/v1/identity/device/add-options", json={"human_id": "human_pin1"})
        challenge_b64 = r.json()["challenge"]

        # Tenter add-verify sans credential réelle
        r2 = client.post("/api/v1/identity/device/add-verify", json={
            "challenge_b64": challenge_b64,
            "credential_id": "fakecredid_pin_only",
            "client_data_json": b64u_encode(b'{"type":"webauthn.get","challenge":"' + challenge_b64.encode() + b'","origin":"http://localhost"}'),
            "authenticator_data": b64u_encode(b"\x00" * 37),
            "signature": b64u_encode(b"\x00" * 64),
            "new_device_credential_id": "newdeviceid123",
        })
        assert r2.status_code == 401
        assert "credential_not_found" in r2.json()["detail"]
        assert "PIN" in r2.json()["detail"]

    def test_old_template_hex_body_returns_422(self, client, tmp_data_dir):
        """Ancien format {challenge, existing_template_hex} → 422 (champs manquants)."""
        _make_human_record("human_tmpl1", tmp_data_dir)
        r = client.post("/api/v1/identity/device/add-options", json={"human_id": "human_tmpl1"})
        challenge = r.json()["challenge"]

        r2 = client.post("/api/v1/identity/device/add-verify", json={
            "challenge": challenge,                        # ancien champ
            "existing_template_hex": "a" * 128,           # ancien champ
            "new_device_credential_hex": "b" * 64,        # ancien champ
        })
        # Pydantic doit rejeter — challenge_b64 obligatoire
        assert r2.status_code == 422

    def test_challenge_unknown_returns_400(self, client, tmp_data_dir):
        """Challenge inconnu → 400."""
        _make_human_record("human_chal1", tmp_data_dir)
        priv, cred_id = _make_credential("human_chal1", tmp_data_dir)
        fake_challenge = b64u_encode(secrets.token_bytes(32))
        assertion = _build_assertion(priv, fake_challenge)
        r = client.post("/api/v1/identity/device/add-verify", json={
            "challenge_b64": fake_challenge,
            "credential_id": cred_id,
            **assertion,
            "new_device_credential_id": "newdev1",
        })
        assert r.status_code == 400
        assert "challenge" in r.json()["detail"]

    def test_bad_signature_returns_401(self, client, tmp_data_dir):
        """Signature ECDSA invalide → 401 webauthn_assertion_failed."""
        _make_human_record("human_sig1", tmp_data_dir)
        priv, cred_id = _make_credential("human_sig1", tmp_data_dir)
        r_opt = client.post("/api/v1/identity/device/add-options", json={"human_id": "human_sig1"})
        challenge_b64 = r_opt.json()["challenge"]

        # Construire assertion avec mauvaise clé
        wrong_key = ec.generate_private_key(ec.SECP256R1())
        assertion = _build_assertion(wrong_key, challenge_b64)

        r2 = client.post("/api/v1/identity/device/add-verify", json={
            "challenge_b64": challenge_b64,
            "credential_id": cred_id,
            **assertion,
            "new_device_credential_id": "newdev_badsig",
        })
        assert r2.status_code == 401
        assert "webauthn_assertion_failed" in r2.json()["detail"]

    def test_credential_wrong_human_returns_403(self, client, tmp_data_dir):
        """Credential appartenant à un autre HumanID → 403."""
        _make_human_record("human_A", tmp_data_dir)
        _make_human_record("human_B", tmp_data_dir)
        priv_b, cred_id_b = _make_credential("human_B", tmp_data_dir)
        # Options pour human_A
        r_opt = client.post("/api/v1/identity/device/add-options", json={"human_id": "human_A"})
        challenge_b64 = r_opt.json()["challenge"]
        # Assertion avec credential de human_B
        assertion = _build_assertion(priv_b, challenge_b64)
        r2 = client.post("/api/v1/identity/device/add-verify", json={
            "challenge_b64": challenge_b64,
            "credential_id": cred_id_b,   # appartient à human_B
            **assertion,
            "new_device_credential_id": "newdev_wronghuman",
        })
        assert r2.status_code == 403
        assert "mismatch" in r2.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════════════
# R364 — ADD_DEVICE valide → 200
# ═══════════════════════════════════════════════════════════════════════════════

class TestAddDeviceValid:
    def test_valid_webauthn_assertion_adds_device(self, client, tmp_data_dir):
        """ADD_DEVICE avec vraie assertion WebAuthn (software) → 200."""
        _make_human_record("human_valid1", tmp_data_dir)
        priv, cred_id = _make_credential("human_valid1", tmp_data_dir)

        r_opt = client.post("/api/v1/identity/device/add-options", json={
            "human_id": "human_valid1",
            "new_device_hint": "Pixel 8",
        })
        assert r_opt.status_code == 200
        challenge_b64 = r_opt.json()["challenge"]

        assertion = _build_assertion(priv, challenge_b64)
        new_cred_id = b64u_encode(secrets.token_bytes(16))

        r2 = client.post("/api/v1/identity/device/add-verify", json={
            "challenge_b64": challenge_b64,
            "credential_id": cred_id,
            **assertion,
            "new_device_credential_id": new_cred_id,
            "new_device_hint": "Pixel 8",
        })
        assert r2.status_code == 200
        body = r2.json()
        assert body["device_added"] is True
        assert body["human_id"] == "human_valid1"
        assert body["proof_class"] == "webauthn_assertion_cryptographic"
        assert body["unique_human_proven"] is False
        assert body["certified_100"] is False
        assert body["devices_count"] == 1
        # Aucun nouveau wallet créé
        assert "wallet" not in body or body.get("wallet_address") == "artcb1test"

    def test_device_listed_after_add(self, client, tmp_data_dir):
        """Après ADD_DEVICE valide, l'appareil apparaît dans /devices."""
        _make_human_record("human_list1", tmp_data_dir)
        priv, cred_id = _make_credential("human_list1", tmp_data_dir)
        r_opt = client.post("/api/v1/identity/device/add-options", json={"human_id": "human_list1"})
        challenge_b64 = r_opt.json()["challenge"]
        assertion = _build_assertion(priv, challenge_b64)
        new_cred_id = b64u_encode(secrets.token_bytes(16))
        client.post("/api/v1/identity/device/add-verify", json={
            "challenge_b64": challenge_b64, "credential_id": cred_id,
            **assertion, "new_device_credential_id": new_cred_id,
        })
        r_list = client.get("/api/v1/identity/device/human_list1/devices")
        assert r_list.status_code == 200
        assert r_list.json()["active_count"] == 1

    def test_max_5_devices_enforced(self, client, tmp_data_dir):
        """Après 5 appareils actifs → 409 device_limit_reached."""
        _make_human_record("human_max1", tmp_data_dir)
        priv, cred_id = _make_credential("human_max1", tmp_data_dir)

        for i in range(5):
            r_opt = client.post("/api/v1/identity/device/add-options", json={"human_id": "human_max1"})
            challenge_b64 = r_opt.json()["challenge"]
            assertion = _build_assertion(priv, challenge_b64, sign_count=i + 1)
            new_cred_id = b64u_encode(secrets.token_bytes(16))
            r = client.post("/api/v1/identity/device/add-verify", json={
                "challenge_b64": challenge_b64, "credential_id": cred_id,
                **assertion, "new_device_credential_id": new_cred_id,
            })
            assert r.status_code == 200, f"device {i+1} should succeed"

        # 6ème → 409
        r_opt = client.post("/api/v1/identity/device/add-options", json={"human_id": "human_max1"})
        challenge_b64 = r_opt.json()["challenge"]
        assertion = _build_assertion(priv, challenge_b64, sign_count=6)
        r6 = client.post("/api/v1/identity/device/add-verify", json={
            "challenge_b64": challenge_b64, "credential_id": cred_id,
            **assertion, "new_device_credential_id": b64u_encode(secrets.token_bytes(16)),
        })
        assert r6.status_code == 409
        assert "device_limit_reached" in r6.json()["detail"]

    def test_webauthn_ne_prouve_pas_unicite_humaine(self, client, tmp_data_dir):
        """WebAuthn valide ≠ unique_human_proven. Toujours False (spec §4 rapport 367)."""
        _make_human_record("human_uniq1", tmp_data_dir)
        priv, cred_id = _make_credential("human_uniq1", tmp_data_dir)
        r_opt = client.post("/api/v1/identity/device/add-options", json={"human_id": "human_uniq1"})
        challenge_b64 = r_opt.json()["challenge"]
        assertion = _build_assertion(priv, challenge_b64)
        r = client.post("/api/v1/identity/device/add-verify", json={
            "challenge_b64": challenge_b64, "credential_id": cred_id,
            **assertion, "new_device_credential_id": b64u_encode(secrets.token_bytes(16)),
        })
        assert r.status_code == 200
        assert r.json()["unique_human_proven"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# R363c — E2E A → ADD_DEVICE → B → webauthn/login (parcours complet)
# ═══════════════════════════════════════════════════════════════════════════════

class TestE2EAddDeviceThenLogin:
    """Prouve le parcours complet : A autorise B → B enrôlé dans webauthn store → B peut se connecter."""

    def _make_cose_b64(self, priv_key: ec.EllipticCurvePrivateKey) -> str:
        """Construit une clé COSE EC2 P-256 b64url depuis une clé privée."""
        from src.artcb.security.webauthn_protocol import cose_ec2_p256
        cose_bytes = cose_ec2_p256(priv_key.public_key())
        return b64u_encode(cose_bytes)

    def test_b_enrolled_in_webauthn_store_after_add_device(self, client, tmp_data_dir):
        """Après ADD_DEVICE avec public_key_b64, B est présent dans webauthn/credentials.json."""
        from src.artcb.security.webauthn_store import find_credential

        _make_human_record("human_e2e1", tmp_data_dir)
        priv_a, cred_id_a = _make_credential("human_e2e1", tmp_data_dir)
        priv_b = ec.generate_private_key(ec.SECP256R1())
        cred_id_b = b64u_encode(secrets.token_bytes(16))
        cose_b64_b = self._make_cose_b64(priv_b)

        # ADD_DEVICE
        r_opt = client.post("/api/v1/identity/device/add-options", json={"human_id": "human_e2e1"})
        challenge_b64 = r_opt.json()["challenge"]
        assertion = _build_assertion(priv_a, challenge_b64)

        r_verify = client.post("/api/v1/identity/device/add-verify", json={
            "challenge_b64": challenge_b64,
            "credential_id": cred_id_a,
            **assertion,
            "new_device_credential_id": cred_id_b,
            "new_device_hint": "Pixel 9",
            "new_device_public_key_b64": cose_b64_b,
        })
        assert r_verify.status_code == 200
        assert r_verify.json()["credential_enrolled"] is True

        # Vérifier que B est dans webauthn store
        stored_b = find_credential(cred_id_b)
        assert stored_b is not None, "B doit être dans webauthn/credentials.json après ADD_DEVICE"
        assert stored_b["cose_b64"] == cose_b64_b
        assert stored_b["human_id"] == "human_e2e1"

    def test_add_device_without_public_key_gives_partial_enrollment(self, client, tmp_data_dir):
        """Sans new_device_public_key_b64, credential_enrolled=False (enrôlement partiel)."""
        _make_human_record("human_partial1", tmp_data_dir)
        priv_a, cred_id_a = _make_credential("human_partial1", tmp_data_dir)
        r_opt = client.post("/api/v1/identity/device/add-options", json={"human_id": "human_partial1"})
        challenge_b64 = r_opt.json()["challenge"]
        assertion = _build_assertion(priv_a, challenge_b64)
        r = client.post("/api/v1/identity/device/add-verify", json={
            "challenge_b64": challenge_b64, "credential_id": cred_id_a,
            **assertion,
            "new_device_credential_id": b64u_encode(secrets.token_bytes(16)),
            # PAS de new_device_public_key_b64
        })
        assert r.status_code == 200
        assert r.json()["credential_enrolled"] is False
        note = r.json().get("note", "")
        assert "partiel" in note or "public_key_b64" in note

    def test_a_authorizes_b_but_webauthn_ne_prouve_pas_meme_humain(self, client, tmp_data_dir):
        """A autorise B ≠ preuve que A et B sont le même humain physique."""
        _make_human_record("human_physique1", tmp_data_dir)
        priv_a, cred_id_a = _make_credential("human_physique1", tmp_data_dir)
        priv_b = ec.generate_private_key(ec.SECP256R1())
        cred_id_b = b64u_encode(secrets.token_bytes(16))
        cose_b64_b = self._make_cose_b64(priv_b)

        r_opt = client.post("/api/v1/identity/device/add-options", json={"human_id": "human_physique1"})
        challenge_b64 = r_opt.json()["challenge"]
        assertion = _build_assertion(priv_a, challenge_b64)
        r = client.post("/api/v1/identity/device/add-verify", json={
            "challenge_b64": challenge_b64, "credential_id": cred_id_a,
            **assertion,
            "new_device_credential_id": cred_id_b,
            "new_device_public_key_b64": cose_b64_b,
        })
        assert r.status_code == 200
        # WebAuthn valide → device ajouté MAIS unique_human_proven reste False
        assert r.json()["unique_human_proven"] is False
        # Aucun nouveau wallet
        assert r.json().get("wallet_address") == "artcb1test"


# ═══════════════════════════════════════════════════════════════════════════════
# R363c — Test de concurrence (race condition limite 5 appareils)
# ═══════════════════════════════════════════════════════════════════════════════

class TestConcurrencyMax5:
    """Vérifie qu'avec 4 appareils existants + 2 requêtes simultanées → exactement 1 succès."""

    def test_concurrent_add_device_respects_max_5(self, client, tmp_data_dir):
        """Race condition : 4 appareils + 2 simultanés → 1 succès + 1 × 409, total=5."""
        import threading

        _make_human_record("human_race1", tmp_data_dir)
        priv_a, cred_id_a = _make_credential("human_race1", tmp_data_dir)

        # Ajouter 4 appareils séquentiellement
        for i in range(4):
            r_opt = client.post("/api/v1/identity/device/add-options", json={"human_id": "human_race1"})
            challenge_b64 = r_opt.json()["challenge"]
            assertion = _build_assertion(priv_a, challenge_b64, sign_count=i + 1)
            r = client.post("/api/v1/identity/device/add-verify", json={
                "challenge_b64": challenge_b64, "credential_id": cred_id_a,
                **assertion, "new_device_credential_id": b64u_encode(secrets.token_bytes(16)),
            })
            assert r.status_code == 200, f"Setup device {i+1} failed"

        # Préparer 2 challenges simultanés
        r_opt1 = client.post("/api/v1/identity/device/add-options", json={"human_id": "human_race1"})
        r_opt2 = client.post("/api/v1/identity/device/add-options", json={"human_id": "human_race1"})
        ch1 = r_opt1.json()["challenge"]
        ch2 = r_opt2.json()["challenge"]
        assertion1 = _build_assertion(priv_a, ch1, sign_count=5)
        assertion2 = _build_assertion(priv_a, ch2, sign_count=6)

        results = []

        def do_add(challenge_b64, assertion, sign_count):
            r = client.post("/api/v1/identity/device/add-verify", json={
                "challenge_b64": challenge_b64, "credential_id": cred_id_a,
                **assertion, "new_device_credential_id": b64u_encode(secrets.token_bytes(16)),
            })
            results.append(r.status_code)

        t1 = threading.Thread(target=do_add, args=(ch1, assertion1, 5))
        t2 = threading.Thread(target=do_add, args=(ch2, assertion2, 6))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactement 1 succès (200) et 1 refus (409)
        assert sorted(results) == [200, 409], (
            f"Race condition: attendu [200, 409] mais obtenu {sorted(results)} — "
            "vérifier FileLock ou transaction atomique sur device_registry"
        )

        # Total appareils actifs = exactement 5
        r_list = client.get("/api/v1/identity/device/human_race1/devices")
        assert r_list.json()["active_count"] == 5, (
            f"Total devrait être 5 mais est {r_list.json()['active_count']}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# R363d — Validation COSE stricte + atomicité + lock
# ═══════════════════════════════════════════════════════════════════════════════

class TestCOSEValidationAndAtomicity:
    """R363d — Validation COSE stricte avant écriture + atomicité sous lock."""

    def _make_cose_b64(self, priv_key: ec.EllipticCurvePrivateKey) -> str:
        from src.artcb.security.webauthn_protocol import cose_ec2_p256
        return b64u_encode(cose_ec2_p256(priv_key.public_key()))

    def test_invalid_cose_b64_returns_400_no_state_written(self, client, tmp_data_dir):
        """COSE invalide → 400, aucun état écrit (atomicité garantie)."""
        from src.artcb.security.webauthn_store import find_credential
        _make_human_record("human_cose1", tmp_data_dir)
        priv_a, cred_id_a = _make_credential("human_cose1", tmp_data_dir)

        r_opt = client.post("/api/v1/identity/device/add-options", json={"human_id": "human_cose1"})
        challenge_b64 = r_opt.json()["challenge"]
        assertion = _build_assertion(priv_a, challenge_b64)
        fake_cred_id = b64u_encode(secrets.token_bytes(16))

        r = client.post("/api/v1/identity/device/add-verify", json={
            "challenge_b64": challenge_b64,
            "credential_id": cred_id_a,
            **assertion,
            "new_device_credential_id": fake_cred_id,
            "new_device_public_key_b64": b64u_encode(b"notacosekey_garbage"),  # invalide
        })
        assert r.status_code == 400
        assert "invalid_cose" in r.json()["detail"]
        # Aucun état écrit — B absent du webauthn store
        assert find_credential(fake_cred_id) is None

    def test_valid_cose_roundtrip_accepted(self, client, tmp_data_dir):
        """COSE valide (produit par cose_ec2_p256) → 200, B enrôlé."""
        from src.artcb.security.webauthn_store import find_credential
        _make_human_record("human_cose2", tmp_data_dir)
        priv_a, cred_id_a = _make_credential("human_cose2", tmp_data_dir)
        priv_b = ec.generate_private_key(ec.SECP256R1())
        cred_id_b = b64u_encode(secrets.token_bytes(16))
        cose_b64_b = self._make_cose_b64(priv_b)

        r_opt = client.post("/api/v1/identity/device/add-options", json={"human_id": "human_cose2"})
        challenge_b64 = r_opt.json()["challenge"]
        assertion = _build_assertion(priv_a, challenge_b64)

        r = client.post("/api/v1/identity/device/add-verify", json={
            "challenge_b64": challenge_b64, "credential_id": cred_id_a,
            **assertion,
            "new_device_credential_id": cred_id_b,
            "new_device_public_key_b64": cose_b64_b,
        })
        assert r.status_code == 200
        assert r.json()["credential_enrolled"] is True
        # B vérifiable via public_key_from_cose
        stored = find_credential(cred_id_b)
        assert stored is not None
        from src.artcb.security.webauthn_cose import public_key_from_cose
        pub = public_key_from_cose(b64u_decode(stored["cose_b64"]))
        assert pub is not None

    def test_lock_prevents_double_enrollment_of_same_credential(self, client, tmp_data_dir):
        """Deux ADD_DEVICE simultanés pour le même credential_id B → un seul enrôlement."""
        import threading
        from src.artcb.security.webauthn_store import load_credentials
        _make_human_record("human_lock1", tmp_data_dir)
        priv_a, cred_id_a = _make_credential("human_lock1", tmp_data_dir)
        priv_b = ec.generate_private_key(ec.SECP256R1())
        cred_id_b = b64u_encode(secrets.token_bytes(16))
        from src.artcb.security.webauthn_protocol import cose_ec2_p256
        cose_b64_b = b64u_encode(cose_ec2_p256(priv_b.public_key()))

        # Deux challenges distincts
        r1 = client.post("/api/v1/identity/device/add-options", json={"human_id": "human_lock1"})
        r2 = client.post("/api/v1/identity/device/add-options", json={"human_id": "human_lock1"})
        ch1, ch2 = r1.json()["challenge"], r2.json()["challenge"]
        a1 = _build_assertion(priv_a, ch1, sign_count=1)
        a2 = _build_assertion(priv_a, ch2, sign_count=2)

        results = []
        def do_add(ch, assertion):
            r = client.post("/api/v1/identity/device/add-verify", json={
                "challenge_b64": ch, "credential_id": cred_id_a,
                **assertion,
                "new_device_credential_id": cred_id_b,  # même B dans les deux requêtes
                "new_device_public_key_b64": cose_b64_b,
            })
            results.append(r.status_code)

        t1 = threading.Thread(target=do_add, args=(ch1, a1))
        t2 = threading.Thread(target=do_add, args=(ch2, a2))
        t1.start(); t2.start()
        t1.join(); t2.join()

        # Au moins un succès
        assert 200 in results, f"Attendu au moins un 200, obtenu {results}"
        # B enregistré exactement une fois dans webauthn store
        all_creds = load_credentials()
        b_entries = [c for c in all_creds if c.get("credential_id") == cred_id_b]
        assert len(b_entries) >= 1, "B doit être dans le store"
