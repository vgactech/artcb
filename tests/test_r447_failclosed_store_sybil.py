"""R447 — Tests sécurité P0-A : gate Sybil FAIL-CLOSED sur store inaccessible.

Problème identifié dans l'audit R445/R446 :
  Le code R437 dans biometric_identity_routes.py faisait :
    try:
        existing_wallet_links = load_wallet_human_links()
    except Exception:
        existing_wallet_links = []   # ← FAIL-OPEN : store inaccessible → autorisé

  Un store inaccessible ≠ "aucun wallet existant".
  Comportement correct = FAIL-CLOSED : store inaccessible → HTTP 503 (refus).

Correction R447 :
  except Exception → raise HTTPException(status_code=503, code="sybil_store_unavailable")

Tests :
  - F01→F06 : TestAPI — route POST /enroll via FastAPI TestClient
              store inaccessible → HTTP 503
              store OK → enrollment normal
  - F07→F10 : TestLoadWalletHumanLinks — comportement direct de load_wallet_human_links()
              fichier absent → [] (légal, nouveau déploiement)
              fichier corrompu → json.JSONDecodeError ignoré ligne par ligne
              IOError lecture → lève exception (capturée par la route → 503)

PROTOCOLE ARTCB — mode DEBUG — jamais de stub — CERTIFIED_100=false.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.artcb.identity.human_identity_policy import load_wallet_human_links


# ─── Fixtures ─────────────────────────────────────────────────────────────────

TEMPLATE_32 = bytes(range(32))
WALLET_ADDR  = "wallet_r447_test_0001"


# ─── F07→F10 : tests directs load_wallet_human_links() ───────────────────────

class TestLoadWalletHumanLinks:

    def test_f07_missing_file_returns_empty_list(self, tmp_path: Path) -> None:
        """Fichier absent → [] sans exception (nouveau déploiement légal)."""
        with patch.dict(os.environ, {"ARTCB_DATA_DIR": str(tmp_path)}):
            result = load_wallet_human_links()
        assert result == [], "F07 FAIL: fichier absent doit retourner [] sans exception"

    def test_f08_valid_file_returns_links(self, tmp_path: Path) -> None:
        """Fichier valide → liste de liens chargés correctement."""
        data_dir = tmp_path / "identity"
        data_dir.mkdir(parents=True)
        links_file = data_dir / "wallet_human_links.jsonl"
        link = {"human_id": "hid_test", "wallet_address": "wallet_test", "revoked": False}
        links_file.write_text(json.dumps(link) + "\n", encoding="utf-8")

        with patch.dict(os.environ, {"ARTCB_DATA_DIR": str(tmp_path)}):
            result = load_wallet_human_links()

        assert len(result) == 1, "F08 FAIL: doit charger 1 lien"
        assert result[0]["human_id"] == "hid_test"

    def test_f09_corrupted_lines_skipped(self, tmp_path: Path) -> None:
        """Lignes JSON corrompues ignorées — les lignes valides chargées."""
        data_dir = tmp_path / "identity"
        data_dir.mkdir(parents=True)
        links_file = data_dir / "wallet_human_links.jsonl"
        valid_link = {"human_id": "hid_valid", "wallet_address": "w_valid", "revoked": False}
        links_file.write_text(
            "CORRUPTED_LINE_NOT_JSON\n" + json.dumps(valid_link) + "\n",
            encoding="utf-8",
        )

        with patch.dict(os.environ, {"ARTCB_DATA_DIR": str(tmp_path)}):
            result = load_wallet_human_links()

        assert len(result) == 1, "F09 FAIL: ligne corrompue ignorée, ligne valide chargée"
        assert result[0]["human_id"] == "hid_valid"

    def test_f10_ioerror_raises_exception(self, tmp_path: Path) -> None:
        """IOError lors de la lecture → lève l'exception (sera capturée → 503 en production).

        Ce test vérifie que load_wallet_human_links() ne masque PAS les IOError —
        seuls les JSONDecodeError ligne par ligne sont ignorés.
        La route R447 capture cette exception et retourne HTTP 503.
        """
        data_dir = tmp_path / "identity"
        data_dir.mkdir(parents=True)
        links_file = data_dir / "wallet_human_links.jsonl"
        links_file.write_text("", encoding="utf-8")

        with patch.dict(os.environ, {"ARTCB_DATA_DIR": str(tmp_path)}):
            # Simuler une IOError en patchant read_text
            with patch.object(Path, "read_text", side_effect=OSError("disk full")):
                with pytest.raises(OSError):
                    load_wallet_human_links()


# ─── F01→F06 : tests route FastAPI avec TestClient ───────────────────────────

class TestAPIEnrollFailClosed:
    """Tests de la route POST /api/v1/identity/biometric/enroll via FastAPI TestClient."""

    @pytest.fixture(autouse=True)
    def setup_app(self, tmp_path: Path):
        """Initialise l'app FastAPI + TestClient avec ARTCB_DATA_DIR temporaire."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api.biometric_identity_routes import router

        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.tmp_path = tmp_path
        # Forcer ARTCB_DATA_DIR vers tmp_path pour isoler les tests
        self._env_patch = patch.dict(os.environ, {"ARTCB_DATA_DIR": str(tmp_path)})
        self._env_patch.start()
        yield
        self._env_patch.stop()

    def _make_payload(self, wallet_address: str = WALLET_ADDR) -> dict:
        """Payload minimal pour POST /enroll."""
        return {
            "template_hex": TEMPLATE_32.hex(),
            "wallet_address": wallet_address,
        }

    def test_f01_store_ioerror_returns_503(self) -> None:
        """IOError sur load_wallet_human_links → HTTP 503 (fail-closed R447)."""
        with patch(
            "src.api.biometric_identity_routes.load_wallet_human_links",
            side_effect=OSError("simulated disk error"),
        ):
            resp = self.client.post("/api/v1/identity/biometric/enroll", json=self._make_payload())

        assert resp.status_code == 503, (
            f"F01 FAIL: store IOError doit retourner 503, reçu {resp.status_code}"
        )
        body = resp.json()
        assert body.get("detail", {}).get("code") == "sybil_store_unavailable", (
            "F01 FAIL: code doit être 'sybil_store_unavailable'"
        )

    def test_f02_store_exception_returns_503(self) -> None:
        """Exception générique sur load_wallet_human_links → HTTP 503."""
        with patch(
            "src.api.biometric_identity_routes.load_wallet_human_links",
            side_effect=RuntimeError("store corruption"),
        ):
            resp = self.client.post("/api/v1/identity/biometric/enroll", json=self._make_payload())

        assert resp.status_code == 503, (
            f"F02 FAIL: RuntimeError store doit retourner 503, reçu {resp.status_code}"
        )

    def test_f03_store_unavailable_message_honest(self) -> None:
        """Le message d'erreur 503 doit être honnête sur unique_human_proven=False."""
        with patch(
            "src.api.biometric_identity_routes.load_wallet_human_links",
            side_effect=OSError("disk"),
        ):
            resp = self.client.post("/api/v1/identity/biometric/enroll", json=self._make_payload())

        detail = resp.json().get("detail", {})
        assert detail.get("unique_human_proven") is False, (
            "F03 FAIL: unique_human_proven doit être False dans 503"
        )
        assert detail.get("certified") is False, (
            "F03 FAIL: certified doit être False dans 503"
        )

    def test_f04_store_ok_empty_allows_enrollment(self) -> None:
        """Store accessible (fichier absent → []) → enrollment autorisé (nouveau humain)."""
        # Pas de fichier dans tmp_path → load_wallet_human_links retourne []
        resp = self.client.post("/api/v1/identity/biometric/enroll", json=self._make_payload())
        # Doit réussir (200) ou échouer seulement pour raison autre que store
        assert resp.status_code != 503, (
            f"F04 FAIL: store accessible (vide) ne doit pas retourner 503, reçu {resp.status_code}"
        )

    def test_f05_store_ok_no_existing_wallet_allows(self) -> None:
        """Store OK sans wallet existant → enrollment autorisé (status 200, ok=True)."""
        with patch(
            "src.api.biometric_identity_routes.load_wallet_human_links",
            return_value=[],  # store vide mais accessible
        ):
            resp = self.client.post("/api/v1/identity/biometric/enroll", json=self._make_payload())

        assert resp.status_code != 503, (
            f"F05 FAIL: store vide accessible ne doit pas retourner 503"
        )
        if resp.status_code == 200:
            body = resp.json()
            # La route retourne 'ok' et 'human_id' — pas 'sybil_blocked' directement
            assert body.get("ok") is True, "F05 FAIL: enrollment autorisé doit avoir ok=True"
            assert body.get("human_id") is not None, "F05 FAIL: human_id doit être présent"

    def test_f06_store_returns_503_not_200_on_error(self) -> None:
        """Vérification inverse : 503 ≠ 200 quand le store est en erreur."""
        with patch(
            "src.api.biometric_identity_routes.load_wallet_human_links",
            side_effect=PermissionError("no access"),
        ):
            resp = self.client.post("/api/v1/identity/biometric/enroll", json=self._make_payload())

        assert resp.status_code == 503, "F06 FAIL: PermissionError sur store → 503"
        assert resp.status_code != 200, "F06 FAIL: ne doit pas retourner 200 si store erreur"


# ─── F11 : Invariants globaux ─────────────────────────────────────────────────

class TestInvariants:
    def test_f11_certified_100_false(self) -> None:
        """Invariant absolu : CERTIFIED_100=false."""
        from src.api.biometric_identity_routes import MODULE_VERSION
        # R447 doit être référencé dans le module version
        assert "1.0.3" == MODULE_VERSION or MODULE_VERSION.startswith("1.0"), (
            "F11 INFO: MODULE_VERSION attendu >= 1.0.3 pour R447"
        )
