"""Tests P0-C — Biométrie on-chain ARTCB (2026-09-16).

Couvre :
  A. FuzzyExtractorStub : fuzzy_extract() + fuzzy_reproduce()
  B. BiometricCommitment : commit_biometric_template() + to_public_record()
  C. enroll_biometric() : HumanIdentityRecord structure + champs privés
  D. check_uniqueness() : anti-double-inscription
  E. Routes API HTTP :
       POST /api/v1/identity/biometric/enroll
       POST /api/v1/identity/biometric/uniqueness-check
       GET  /api/v1/identity/biometric/{human_id}
       GET  /api/v1/identity/biometric/
  F. Sécurité : rejet image brute, rejet champs interdits
  G. TEST DOMAIN : enrollment dans un espace TEST isolé

Honnêteté (CERTIFIED_100=false) :
  - unique_human_proven=False partout
  - FAR/FRR/PAD non mesurés — stubs uniquement
  - fuzzy reproduce : même template → même secret (stub exact, pas fuzzy réel)
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATE_ALICE = bytes.fromhex("aa" * 64)   # template normalisé simulé Alice (512 bits)
TEMPLATE_BOB   = bytes.fromhex("bb" * 64)   # template normalisé simulé Bob
TEMPLATE_ALICE2 = bytes.fromhex("aa" * 64)  # deuxième capture Alice (identique — stub)


@pytest.fixture()
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """FastAPI TestClient avec state isolé dans tmp_path (aucun réseau externe)."""
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ARTCB_BOOTSTRAP_NODE", "false")
    monkeypatch.setenv("ARTCB_NODE_WALLET_ADDRESS", "artcb1testnode000000000000000000000000000")
    from src.api.main import create_app
    return TestClient(create_app(), raise_server_exceptions=True)


# ══════════════════════════════════════════════════════════════════════════════
# Phase A — FuzzyExtractorStub
# ══════════════════════════════════════════════════════════════════════════════

class TestFuzzyExtractorStub:
    """Phase A — FuzzyExtractorStub : interface enroll/reproduce."""

    def test_extract_returns_result(self):
        from src.artcb.identity.biometric_onchain import fuzzy_extract
        fe = fuzzy_extract(TEMPLATE_ALICE)
        assert fe.secret_hex
        assert fe.helper_data_hex
        assert fe.template_hash_hex

    def test_extract_secret_is_private_not_empty(self):
        from src.artcb.identity.biometric_onchain import fuzzy_extract
        fe = fuzzy_extract(TEMPLATE_ALICE)
        assert len(fe.secret_hex) >= 32  # au moins 16 bytes en hex

    def test_extract_certified_false(self):
        from src.artcb.identity.biometric_onchain import fuzzy_extract
        fe = fuzzy_extract(TEMPLATE_ALICE)
        assert fe.certified is False

    def test_reproduce_same_template_same_secret(self):
        from src.artcb.identity.biometric_onchain import fuzzy_extract, fuzzy_reproduce
        fe = fuzzy_extract(TEMPLATE_ALICE)
        secret2 = fuzzy_reproduce(TEMPLATE_ALICE, fe.helper_data_hex)
        assert secret2 == fe.secret_hex

    def test_reproduce_different_template_different_secret(self):
        from src.artcb.identity.biometric_onchain import fuzzy_extract, fuzzy_reproduce
        fe = fuzzy_extract(TEMPLATE_ALICE)
        # Stub : template différent → secret différent (pas de vraie tolérance fuzzy)
        secret_bob = fuzzy_reproduce(TEMPLATE_BOB, fe.helper_data_hex)
        assert secret_bob != fe.secret_hex

    def test_extract_empty_raises(self):
        from src.artcb.identity.biometric_onchain import fuzzy_extract
        with pytest.raises(ValueError):
            fuzzy_extract(b"")

    def test_reproduce_empty_returns_none(self):
        from src.artcb.identity.biometric_onchain import fuzzy_reproduce
        assert fuzzy_reproduce(b"", "deadbeef" * 8) is None

    def test_helper_data_is_deterministic_with_same_salt(self):
        from src.artcb.identity.biometric_onchain import fuzzy_extract
        salt = b"\x01" * 32
        fe1 = fuzzy_extract(TEMPLATE_ALICE, salt=salt)
        fe2 = fuzzy_extract(TEMPLATE_ALICE, salt=salt)
        assert fe1.secret_hex == fe2.secret_hex
        assert fe1.helper_data_hex == fe2.helper_data_hex


# ══════════════════════════════════════════════════════════════════════════════
# Phase B — BiometricCommitment
# ══════════════════════════════════════════════════════════════════════════════

class TestBiometricCommitment:
    """Phase B — BiometricCommitment : propriétés de sécurité."""

    def test_commit_returns_commitment(self):
        from src.artcb.crypto.homomorphic import commit_biometric_template
        c = commit_biometric_template(TEMPLATE_ALICE)
        assert c.commitment_hex
        assert c.template_hash_hex

    def test_public_record_has_no_blinding(self):
        from src.artcb.crypto.homomorphic import commit_biometric_template
        c = commit_biometric_template(TEMPLATE_ALICE)
        pub = c.to_public_record()
        assert "blinding_hex" not in pub  # jamais on-chain
        assert "blinding" not in pub

    def test_public_record_has_commitment(self):
        from src.artcb.crypto.homomorphic import commit_biometric_template
        c = commit_biometric_template(TEMPLATE_ALICE)
        pub = c.to_public_record()
        assert "commitment" in pub
        assert "template_hash" in pub
        assert "algorithm" in pub

    def test_unique_human_proven_is_false(self):
        from src.artcb.crypto.homomorphic import commit_biometric_template
        c = commit_biometric_template(TEMPLATE_ALICE)
        assert c.unique_human_proven is False

    def test_different_templates_different_commitments(self):
        from src.artcb.crypto.homomorphic import commit_biometric_template
        ca = commit_biometric_template(TEMPLATE_ALICE)
        cb = commit_biometric_template(TEMPLATE_BOB)
        assert ca.commitment_hex != cb.commitment_hex
        assert ca.template_hash_hex != cb.template_hash_hex

    def test_empty_template_raises(self):
        from src.artcb.crypto.homomorphic import commit_biometric_template
        with pytest.raises(ValueError):
            commit_biometric_template(b"")


# ══════════════════════════════════════════════════════════════════════════════
# Phase C — enroll_biometric()
# ══════════════════════════════════════════════════════════════════════════════

class TestEnrollBiometric:
    """Phase C — enroll_biometric() : structure HumanIdentityRecord."""

    def test_enroll_returns_result_and_private_fields(self):
        from src.artcb.identity.biometric_onchain import enroll_biometric
        result, secret, blinding = enroll_biometric(TEMPLATE_ALICE)
        assert result.human_id.startswith("human_")
        assert secret  # privé
        assert blinding  # privé

    def test_record_has_required_public_fields(self):
        from src.artcb.identity.biometric_onchain import enroll_biometric
        result, _, _ = enroll_biometric(TEMPLATE_ALICE)
        rec = result.human_identity_record
        for field in ("human_id", "commitment", "template_hash", "helper_data", "algorithm",
                      "status", "created_at", "unique_human_proven"):
            assert field in rec, f"Champ manquant: {field}"

    def test_record_has_no_private_fields(self):
        from src.artcb.identity.biometric_onchain import enroll_biometric
        result, _, _ = enroll_biometric(TEMPLATE_ALICE)
        rec = result.human_identity_record
        assert "blinding_hex" not in rec
        assert "blinding" not in rec
        assert "secret_hex" not in rec
        assert "template_bytes" not in rec

    def test_unique_human_proven_always_false(self):
        from src.artcb.identity.biometric_onchain import enroll_biometric
        result, _, _ = enroll_biometric(TEMPLATE_ALICE)
        assert result.unique_human_proven is False
        assert result.human_identity_record["unique_human_proven"] is False

    def test_enroll_with_wallet_address(self):
        from src.artcb.identity.biometric_onchain import enroll_biometric
        result, _, _ = enroll_biometric(TEMPLATE_ALICE, wallet_address="artcb1abc")
        assert result.human_identity_record["wallet_address"] == "artcb1abc"

    def test_two_different_templates_different_human_ids(self):
        from src.artcb.identity.biometric_onchain import enroll_biometric
        ra, _, _ = enroll_biometric(TEMPLATE_ALICE)
        rb, _, _ = enroll_biometric(TEMPLATE_BOB)
        assert ra.human_id != rb.human_id

    def test_enroll_empty_raises(self):
        from src.artcb.identity.biometric_onchain import enroll_biometric
        with pytest.raises(ValueError):
            enroll_biometric(b"")


# ══════════════════════════════════════════════════════════════════════════════
# Phase D — check_uniqueness() : anti-double-inscription
# ══════════════════════════════════════════════════════════════════════════════

class TestCheckUniqueness:
    """Phase D — Propriété fondamentale : 1 humain = 1 HumanIdentity."""

    def test_same_template_match_found(self):
        from src.artcb.identity.biometric_onchain import enroll_biometric, check_uniqueness
        from src.artcb.crypto.homomorphic import commit_biometric_template
        result, _, _ = enroll_biometric(TEMPLATE_ALICE)
        c = commit_biometric_template(TEMPLATE_ALICE)
        u = check_uniqueness(c, [result.human_identity_record])
        assert u.match_found is True
        assert u.existing_human_id == result.human_id

    def test_different_template_no_match(self):
        from src.artcb.identity.biometric_onchain import enroll_biometric, check_uniqueness
        from src.artcb.crypto.homomorphic import commit_biometric_template
        result, _, _ = enroll_biometric(TEMPLATE_ALICE)
        c_bob = commit_biometric_template(TEMPLATE_BOB)
        u = check_uniqueness(c_bob, [result.human_identity_record])
        assert u.match_found is False
        assert u.existing_human_id is None

    def test_empty_registry_no_match(self):
        from src.artcb.identity.biometric_onchain import check_uniqueness
        from src.artcb.crypto.homomorphic import commit_biometric_template
        c = commit_biometric_template(TEMPLATE_ALICE)
        u = check_uniqueness(c, [])
        assert u.match_found is False

    def test_uniqueness_certified_always_false(self):
        from src.artcb.identity.biometric_onchain import enroll_biometric, check_uniqueness
        from src.artcb.crypto.homomorphic import commit_biometric_template
        result, _, _ = enroll_biometric(TEMPLATE_ALICE)
        c = commit_biometric_template(TEMPLATE_ALICE)
        u = check_uniqueness(c, [result.human_identity_record])
        assert u.certified is False
        assert u.unique_human_proven is False

    def test_multiple_records_correct_match(self):
        from src.artcb.identity.biometric_onchain import enroll_biometric, check_uniqueness
        from src.artcb.crypto.homomorphic import commit_biometric_template
        ra, _, _ = enroll_biometric(TEMPLATE_ALICE)
        rb, _, _ = enroll_biometric(TEMPLATE_BOB)
        existing = [ra.human_identity_record, rb.human_identity_record]
        # Alice retrouvée
        ca = commit_biometric_template(TEMPLATE_ALICE)
        ua = check_uniqueness(ca, existing)
        assert ua.match_found is True
        assert ua.existing_human_id == ra.human_id
        # Bob retrouvé
        cb = commit_biometric_template(TEMPLATE_BOB)
        ub = check_uniqueness(cb, existing)
        assert ub.match_found is True
        assert ub.existing_human_id == rb.human_id


# ══════════════════════════════════════════════════════════════════════════════
# Phase E — Routes API HTTP
# ══════════════════════════════════════════════════════════════════════════════

class TestBiometricAPIEnroll:
    """Phase E-1 — POST /api/v1/identity/biometric/enroll"""

    def test_enroll_valid_template(self, api: TestClient) -> None:
        r = api.post("/api/v1/identity/biometric/enroll", json={
            "template_hex": "aa" * 64,
            "wallet_address": "artcb1alice",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["human_id"].startswith("human_")
        assert body["unique_human_proven"] is False
        assert body["certified"] is False

    def test_enroll_returns_public_record(self, api: TestClient) -> None:
        r = api.post("/api/v1/identity/biometric/enroll", json={
            "template_hex": "cc" * 64,
        })
        assert r.status_code == 200
        body = r.json()
        rec = body["human_identity_record"]
        assert "commitment" in rec
        assert "helper_data" in rec
        assert "blinding_hex" not in rec  # jamais on-chain

    def test_enroll_returns_private_for_client(self, api: TestClient) -> None:
        r = api.post("/api/v1/identity/biometric/enroll", json={
            "template_hex": "dd" * 64,
        })
        assert r.status_code == 200
        body = r.json()
        priv = body.get("private_for_client", {})
        assert "secret_hex" in priv
        assert "blinding_hex" in priv
        assert "WARNING" in priv

    def test_enroll_duplicate_rejected_409(self, api: TestClient) -> None:
        payload = {"template_hex": "ee" * 64, "wallet_address": "artcb1dup"}
        r1 = api.post("/api/v1/identity/biometric/enroll", json=payload)
        assert r1.status_code == 200
        r2 = api.post("/api/v1/identity/biometric/enroll", json=payload)
        assert r2.status_code == 409
        detail = r2.json()["detail"]
        assert detail["code"] == "human_identity_already_registered"
        assert "existing_human_id" in detail

    def test_enroll_template_too_short_rejected(self, api: TestClient) -> None:
        r = api.post("/api/v1/identity/biometric/enroll", json={
            "template_hex": "aa" * 10,  # trop court
        })
        assert r.status_code in (400, 422)

    def test_enroll_invalid_hex_rejected(self, api: TestClient) -> None:
        r = api.post("/api/v1/identity/biometric/enroll", json={
            "template_hex": "ZZ" * 64,  # hex invalide
        })
        assert r.status_code == 400


class TestBiometricAPIRawImageRejected:
    """Phase F — Sécurité : rejet image brute."""

    def test_enroll_with_image_field_rejected(self, api: TestClient) -> None:
        r = api.post("/api/v1/identity/biometric/enroll", json={
            "template_hex": "aa" * 64,
            "image": "data:image/png;base64,AAAA",
        })
        assert r.status_code == 400
        assert "raw_biometric_rejected" in r.json()["detail"]

    def test_enroll_with_photo_field_rejected(self, api: TestClient) -> None:
        r = api.post("/api/v1/identity/biometric/enroll", json={
            "template_hex": "aa" * 64,
            "photo": "data:image/jpeg;base64,BBBB",
        })
        assert r.status_code == 400

    def test_uniqueness_check_with_image_rejected(self, api: TestClient) -> None:
        r = api.post("/api/v1/identity/biometric/uniqueness-check", json={
            "template_hex": "aa" * 64,
            "image": "data:image/png;base64,CCCC",
        })
        assert r.status_code == 400


class TestBiometricAPIUniqueness:
    """Phase E-2 — POST /api/v1/identity/biometric/uniqueness-check"""

    def test_uniqueness_check_no_match_on_empty(self, api: TestClient) -> None:
        r = api.post("/api/v1/identity/biometric/uniqueness-check", json={
            "template_hex": "ff" * 64,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["match_found"] is False
        assert body["unique_human_proven"] is False

    def test_uniqueness_check_match_after_enroll(self, api: TestClient) -> None:
        # Enrôler Alice
        api.post("/api/v1/identity/biometric/enroll", json={"template_hex": "11" * 64})
        # Vérifier que le même template est détecté
        r = api.post("/api/v1/identity/biometric/uniqueness-check", json={
            "template_hex": "11" * 64,
        })
        assert r.status_code == 200
        assert r.json()["match_found"] is True

    def test_uniqueness_check_no_match_different_template(self, api: TestClient) -> None:
        api.post("/api/v1/identity/biometric/enroll", json={"template_hex": "22" * 64})
        r = api.post("/api/v1/identity/biometric/uniqueness-check", json={
            "template_hex": "33" * 64,
        })
        assert r.status_code == 200
        assert r.json()["match_found"] is False


class TestBiometricAPIGet:
    """Phase E-3 — GET /api/v1/identity/biometric/{human_id}"""

    def test_get_enrolled_identity(self, api: TestClient) -> None:
        enroll = api.post("/api/v1/identity/biometric/enroll", json={
            "template_hex": "44" * 64,
            "wallet_address": "artcb1gettest",
        })
        human_id = enroll.json()["human_id"]
        r = api.get(f"/api/v1/identity/biometric/{human_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["found"] is True
        assert body["human_id"] == human_id
        assert "commitment" in body
        assert "helper_data" in body
        assert body["unique_human_proven"] is False

    def test_get_unknown_identity_returns_404(self, api: TestClient) -> None:
        r = api.get("/api/v1/identity/biometric/human_nonexistent")
        assert r.status_code == 404

    def test_get_does_not_return_blinding(self, api: TestClient) -> None:
        enroll = api.post("/api/v1/identity/biometric/enroll", json={"template_hex": "55" * 64})
        human_id = enroll.json()["human_id"]
        r = api.get(f"/api/v1/identity/biometric/{human_id}")
        body = r.json()
        assert "blinding_hex" not in body
        assert "secret_hex" not in body

    def test_list_identities(self, api: TestClient) -> None:
        api.post("/api/v1/identity/biometric/enroll", json={"template_hex": "66" * 64})
        r = api.get("/api/v1/identity/biometric/")
        assert r.status_code == 200
        body = r.json()
        assert "human_ids" in body
        assert body["count"] >= 1
        assert body["unique_human_proven"] is False


# ══════════════════════════════════════════════════════════════════════════════
# Phase G — Scénario complet : flux manuel simulé (comme ton test d'empreinte)
# ══════════════════════════════════════════════════════════════════════════════

class TestManualFingerprintFlow:
    """Phase G — Flux complet simulant un vrai test manuel d'empreinte.

    Ce test simule exactement ce que l'utilisateur va faire manuellement :
      1. L'appareil capture l'empreinte et extrait le template normalisé.
      2. POST /enroll → human_id créé, secret + blinding retournés au client.
      3. Vérification d'unicité sur un deuxième essai → 409 refusé.
      4. Un autre humain peut s'inscrire.
      5. GET /{human_id} → consultation publique.
      6. Aucune image brute dans aucune réponse.
    """

    TEMPLATE_USER = "ab" * 64    # Ton empreinte simulée
    TEMPLATE_OTHER = "cd" * 64   # Autre personne simulée

    def test_full_enrollment_flow(self, api: TestClient) -> None:
        # Étape 1 : vérifier l'unicité avant inscription
        r_check = api.post("/api/v1/identity/biometric/uniqueness-check", json={
            "template_hex": self.TEMPLATE_USER,
        })
        assert r_check.status_code == 200
        assert r_check.json()["match_found"] is False  # pas encore inscrit

        # Étape 2 : inscription
        r_enroll = api.post("/api/v1/identity/biometric/enroll", json={
            "template_hex": self.TEMPLATE_USER,
            "wallet_address": "artcb1myownwallet",
        })
        assert r_enroll.status_code == 200
        body = r_enroll.json()
        human_id = body["human_id"]
        assert human_id.startswith("human_")
        assert body["status"] == "enrolled"
        assert body["unique_human_proven"] is False
        priv = body["private_for_client"]
        assert priv["secret_hex"]
        assert priv["blinding_hex"]

        # Étape 3 : deuxième tentative = refus 409
        r_dup = api.post("/api/v1/identity/biometric/enroll", json={
            "template_hex": self.TEMPLATE_USER,
        })
        assert r_dup.status_code == 409
        assert r_dup.json()["detail"]["code"] == "human_identity_already_registered"

        # Étape 4 : autre personne peut s'inscrire
        r_other = api.post("/api/v1/identity/biometric/enroll", json={
            "template_hex": self.TEMPLATE_OTHER,
        })
        assert r_other.status_code == 200
        assert r_other.json()["human_id"] != human_id

        # Étape 5 : consultation publique
        r_get = api.get(f"/api/v1/identity/biometric/{human_id}")
        assert r_get.status_code == 200
        assert r_get.json()["wallet_address"] == "artcb1myownwallet"

        # Étape 6 : aucune image brute
        assert "image" not in r_enroll.text
        assert "template_bytes" not in r_enroll.text
