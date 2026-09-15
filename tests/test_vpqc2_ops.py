"""V-PQC-2 — Tests unitaires POST /ops/pqc-challenge + POST /ops/pqc-verify.

Ces tests n'ont pas besoin de liboqs en live : on mocke pqc_available=True,
pqc_sign et pqc_verify_msg pour valider toute la logique de routage, de gestion
des challenges (TTL, usage unique, inconnu) et du chargement wallet.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# App minimal pour les tests
# ---------------------------------------------------------------------------

from fastapi import FastAPI
from src.api.ops_routes import router, _PQC_CHALLENGES

app = FastAPI()
app.include_router(router)
client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _issue_challenge() -> str:
    r = client.post("/api/v1/ops/pqc-challenge")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "challenge" in data
    assert len(data["challenge"]) == 64
    assert data["algorithm"] == "ML-DSA-65"
    assert data["expires_in"] == 300
    return data["challenge"]


# Fausse clé PQC (taille ML-DSA-65 réelle)
FAKE_SK = b"\xab" * 4032
FAKE_PK = b"\xcd" * 1952
FAKE_SIG = b"\xef" * 3309  # taille typique ML-DSA-65

_FAKE_WALLET = MagicMock(
    address="artcb1fakeaddress000000000000000000000000000",
    address_v2="artcb21fakeaddressv2000000000000000000000000",
    pqc_secret_key=FAKE_SK,
    pqc_public_key=FAKE_PK,
)


# ---------------------------------------------------------------------------
# Tests /pqc-challenge
# ---------------------------------------------------------------------------

class TestPqcChallenge:
    def test_returns_challenge(self):
        r = client.post("/api/v1/ops/pqc-challenge")
        assert r.status_code == 200
        d = r.json()
        assert len(d["challenge"]) == 64
        assert d["algorithm"] == "ML-DSA-65"
        assert d["expires_in"] == 300

    def test_each_challenge_unique(self):
        c1 = _issue_challenge()
        c2 = _issue_challenge()
        assert c1 != c2

    def test_challenge_stored_in_dict(self):
        c = _issue_challenge()
        assert c in _PQC_CHALLENGES
        assert _PQC_CHALLENGES[c] > time.time()


# ---------------------------------------------------------------------------
# Tests /pqc-verify
# ---------------------------------------------------------------------------

class TestPqcVerify:
    # Les imports pqc_available/pqc_sign/pqc_verify_msg sont faits en lazy (inside function)
    # → on mock le module source, pas ops_routes
    @patch("src.artcb.crypto.pqc.verify_message", return_value=True)
    @patch("src.artcb.crypto.pqc.sign_message", return_value=FAKE_SIG)
    @patch("src.artcb.crypto.pqc.pqc_available", return_value=True)
    @patch("src.artcb.wallet.manager.WalletManager.load_wallet", return_value=_FAKE_WALLET)
    def test_vpqc2_pass(self, *_):
        challenge = _issue_challenge()
        r = client.post("/api/v1/ops/pqc-verify", json={"challenge": challenge, "wallet_name": "default"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["vpqc2_pass"] is True
        assert d["verified"] is True
        assert d["algorithm"] == "ML-DSA-65"
        assert d["challenge"] == challenge
        # Challenge consommé (usage unique)
        assert challenge not in _PQC_CHALLENGES

    @patch("src.artcb.crypto.pqc.pqc_available", return_value=False)
    def test_vpqc2_pqc_unavailable(self, _):
        challenge = _issue_challenge()
        r = client.post("/api/v1/ops/pqc-verify", json={"challenge": challenge, "wallet_name": "default"})
        assert r.status_code == 503
        assert "vpqc2_pqc_unavailable" in r.json()["detail"]

    def test_vpqc2_unknown_challenge(self):
        r = client.post("/api/v1/ops/pqc-verify", json={"challenge": "a" * 64, "wallet_name": "default"})
        assert r.status_code == 400
        assert "vpqc2_challenge_unknown_or_already_used" in r.json()["detail"]

    def test_vpqc2_challenge_usage_once(self):
        """Un challenge ne peut être utilisé qu'une seule fois."""
        with (
            patch("src.artcb.crypto.pqc.verify_message", return_value=True),
            patch("src.artcb.crypto.pqc.sign_message", return_value=FAKE_SIG),
            patch("src.artcb.crypto.pqc.pqc_available", return_value=True),
            patch("src.artcb.wallet.manager.WalletManager.load_wallet", return_value=_FAKE_WALLET),
        ):
            challenge = _issue_challenge()
            r1 = client.post("/api/v1/ops/pqc-verify", json={"challenge": challenge, "wallet_name": "default"})
            assert r1.status_code == 200
            # Deuxième appel avec le même challenge
            r2 = client.post("/api/v1/ops/pqc-verify", json={"challenge": challenge, "wallet_name": "default"})
            assert r2.status_code == 400
            assert "vpqc2_challenge_unknown_or_already_used" in r2.json()["detail"]

    @patch("src.artcb.crypto.pqc.pqc_available", return_value=True)
    @patch("src.artcb.wallet.manager.WalletManager.load_wallet", side_effect=FileNotFoundError)
    def test_vpqc2_wallet_not_found(self, *_):
        challenge = _issue_challenge()
        r = client.post("/api/v1/ops/pqc-verify", json={"challenge": challenge, "wallet_name": "nonexistent"})
        assert r.status_code == 404
        assert "vpqc2_wallet_not_found" in r.json()["detail"]
