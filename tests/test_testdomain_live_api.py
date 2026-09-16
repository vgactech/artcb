"""TEST DOMAIN — tests live via FastAPI TestClient (niveau API HTTP réel).

Ce fichier couvre le même périmètre que test_testdomain_e2e.py MAIS en passant
par la couche HTTP complète : routeur FastAPI → WalletManager → TestChainManager.

Différence fondamentale avec test_testdomain_e2e.py :
  - E2E local      : appels directs Python, pas de HTTP, pas de binding d'état
  - Live API (ici) : POST /api/v1/wallet/create passe par la pile complète
                     auth, device binding, middleware CORS, sérialisation JSON

Trois niveaux de preuves :
  L1 — Route /wallet/create répond correctement à wallet_namespace=TEST
  L2 — La réponse contient domain=TEST, adresse artcbdev1…, asset=tARTCB
  L3 — Deux wallets TEST sur le même device sont autorisés (registre TEST séparé)
       tandis qu'un deuxième wallet MAINNET sur le même device est rejeté 409

OVH1 désactivé — ces tests n'essaient aucune connexion réseau externe.
Tout tourne en mémoire via TestClient (conftest _wallet_passphrase_env).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ─────────────────────────────────────────────────────────────────────────────
# Fixture : nœud API en mémoire isolé
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """FastAPI TestClient avec état isolé dans tmp_path.

    ARTCB_ALLOW_MULTI_WALLET=true est volontairement absent :
    on veut tester le vrai comportement de binding (MAINNET = 1 wallet/device,
    TEST = multiple wallets/device dans registre séparé).
    """
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ARTCB_BOOTSTRAP_NODE", "false")
    # Fournir une fausse adresse de nœud pour que create_app() démarre
    monkeypatch.setenv(
        "ARTCB_NODE_WALLET_ADDRESS",
        "artcb1testnode000000000000000000000000000",
    )
    from src.api.main import create_app
    return TestClient(create_app(), raise_server_exceptions=True)


# ─────────────────────────────────────────────────────────────────────────────
# L1 — Route accessible et payload valide
# ─────────────────────────────────────────────────────────────────────────────

class TestL1RouteBasic:
    """L1 — /wallet/create répond 200 avec wallet_namespace=TEST."""

    def test_create_test_wallet_returns_200(self, api: TestClient) -> None:
        resp = api.post(
            "/api/v1/wallet/create",
            json={"name": "live-test-001", "password": "password123!", "wallet_namespace": "TEST"},
            headers={"X-ARTCB-Device-Id": "device-live-test-001"},
        )
        assert resp.status_code == 200, resp.text

    def test_create_mainnet_wallet_returns_200(self, api: TestClient) -> None:
        resp = api.post(
            "/api/v1/wallet/create",
            json={"name": "live-main-001", "password": "password123!", "wallet_namespace": "MAINNET"},
            headers={"X-ARTCB-Device-Id": "device-live-main-001"},
        )
        assert resp.status_code == 200, resp.text

    def test_create_wallet_default_namespace_returns_200(self, api: TestClient) -> None:
        """Sans wallet_namespace explicite → MAINNET par défaut."""
        resp = api.post(
            "/api/v1/wallet/create",
            json={"name": "live-default-001", "password": "password123!"},
            headers={"X-ARTCB-Device-Id": "device-live-default-001"},
        )
        assert resp.status_code == 200, resp.text

    def test_invalid_namespace_returns_422(self, api: TestClient) -> None:
        resp = api.post(
            "/api/v1/wallet/create",
            json={"name": "live-bad-ns", "password": "password123!", "wallet_namespace": "DEVNET"},
            headers={"X-ARTCB-Device-Id": "device-live-bad-001"},
        )
        assert resp.status_code == 422, resp.text
        body = resp.json()
        # Peut venir du validateur Pydantic ou de notre guard explicite
        assert resp.status_code in (422,)

    def test_missing_password_returns_422(self, api: TestClient) -> None:
        resp = api.post(
            "/api/v1/wallet/create",
            json={"name": "live-no-pwd", "wallet_namespace": "TEST"},
            headers={"X-ARTCB-Device-Id": "device-live-nopwd-001"},
        )
        assert resp.status_code == 422, resp.text

    def test_short_password_returns_422(self, api: TestClient) -> None:
        resp = api.post(
            "/api/v1/wallet/create",
            json={"name": "live-short-pwd", "password": "abc", "wallet_namespace": "TEST"},
            headers={"X-ARTCB-Device-Id": "device-live-short-001"},
        )
        assert resp.status_code == 422, resp.text


# ─────────────────────────────────────────────────────────────────────────────
# L2 — Contenu de la réponse TEST vs MAINNET
# ─────────────────────────────────────────────────────────────────────────────

class TestL2ResponseContent:
    """L2 — La réponse reflète exactement le domaine demandé."""

    def test_test_wallet_address_is_artcbdev(self, api: TestClient) -> None:
        resp = api.post(
            "/api/v1/wallet/create",
            json={"name": "l2-test-addr", "password": "password123!", "wallet_namespace": "TEST"},
            headers={"X-ARTCB-Device-Id": "device-l2-test-001"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["address"].startswith("artcbdev1"), (
            f"TEST wallet doit commencer par artcbdev1, obtenu: {body['address']}"
        )

    def test_mainnet_wallet_address_is_artcb1(self, api: TestClient) -> None:
        resp = api.post(
            "/api/v1/wallet/create",
            json={"name": "l2-main-addr", "password": "password123!", "wallet_namespace": "MAINNET"},
            headers={"X-ARTCB-Device-Id": "device-l2-main-001"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["address"].startswith("artcb1"), (
            f"MAINNET wallet doit commencer par artcb1, obtenu: {body['address']}"
        )

    def test_test_wallet_namespace_in_response(self, api: TestClient) -> None:
        resp = api.post(
            "/api/v1/wallet/create",
            json={"name": "l2-test-ns", "password": "password123!", "wallet_namespace": "TEST"},
            headers={"X-ARTCB-Device-Id": "device-l2-ns-001"},
        )
        body = resp.json()
        assert body.get("wallet_namespace") == "TEST", body
        assert body.get("domain") == "TEST", body

    def test_mainnet_wallet_namespace_in_response(self, api: TestClient) -> None:
        resp = api.post(
            "/api/v1/wallet/create",
            json={"name": "l2-main-ns", "password": "password123!", "wallet_namespace": "MAINNET"},
            headers={"X-ARTCB-Device-Id": "device-l2-main-ns-001"},
        )
        body = resp.json()
        assert body.get("wallet_namespace") == "MAINNET", body
        assert body.get("domain") == "MAINNET", body

    def test_test_wallet_asset_is_tartcb(self, api: TestClient) -> None:
        resp = api.post(
            "/api/v1/wallet/create",
            json={"name": "l2-test-asset", "password": "password123!", "wallet_namespace": "TEST"},
            headers={"X-ARTCB-Device-Id": "device-l2-asset-001"},
        )
        body = resp.json()
        assert body.get("asset") == "tARTCB", body

    def test_mainnet_wallet_asset_is_artcb(self, api: TestClient) -> None:
        resp = api.post(
            "/api/v1/wallet/create",
            json={"name": "l2-main-asset", "password": "password123!", "wallet_namespace": "MAINNET"},
            headers={"X-ARTCB-Device-Id": "device-l2-main-asset-001"},
        )
        body = resp.json()
        assert body.get("asset") == "ARTCB", body

    def test_seed_hex_present_and_64_chars(self, api: TestClient) -> None:
        """seed_hex retournée une seule fois à la création."""
        resp = api.post(
            "/api/v1/wallet/create",
            json={"name": "l2-test-seed", "password": "password123!", "wallet_namespace": "TEST"},
            headers={"X-ARTCB-Device-Id": "device-l2-seed-001"},
        )
        body = resp.json()
        seed = body.get("seed_hex", "")
        assert len(seed) == 64, f"seed_hex doit être 64 hex chars, obtenu len={len(seed)}"

    def test_same_device_test_and_mainnet_different_addresses(self, api: TestClient) -> None:
        """Même device → TEST et MAINNET peuvent coexister avec des adresses différentes."""
        device = "device-l2-both-001"
        r_test = api.post(
            "/api/v1/wallet/create",
            json={"name": "l2-both-test", "password": "password123!", "wallet_namespace": "TEST"},
            headers={"X-ARTCB-Device-Id": device},
        )
        r_main = api.post(
            "/api/v1/wallet/create",
            json={"name": "l2-both-main", "password": "password123!", "wallet_namespace": "MAINNET"},
            headers={"X-ARTCB-Device-Id": device},
        )
        assert r_test.status_code == 200, r_test.text
        assert r_main.status_code == 200, r_main.text
        addr_test = r_test.json()["address"]
        addr_main = r_main.json()["address"]
        assert addr_test != addr_main
        assert addr_test.startswith("artcbdev1")
        assert addr_main.startswith("artcb1")


# ─────────────────────────────────────────────────────────────────────────────
# L3 — Binding device : règles anti-fraude par namespace
# ─────────────────────────────────────────────────────────────────────────────

class TestL3DeviceBinding:
    """L3 — MAINNET = 1 wallet/device ; TEST = plusieurs wallets/device autorisés."""

    def test_second_mainnet_wallet_same_device_returns_409(self, api: TestClient) -> None:
        """MAINNET : 1 wallet max par device (anti-Sybil MAINNET)."""
        device = "device-l3-mainnet-dup"
        r1 = api.post(
            "/api/v1/wallet/create",
            json={"name": "l3-main-first", "password": "password123!", "wallet_namespace": "MAINNET"},
            headers={"X-ARTCB-Device-Id": device},
        )
        assert r1.status_code == 200, r1.text

        r2 = api.post(
            "/api/v1/wallet/create",
            json={"name": "l3-main-second", "password": "password123!", "wallet_namespace": "MAINNET"},
            headers={"X-ARTCB-Device-Id": device},
        )
        assert r2.status_code == 409, (
            f"Le 2e wallet MAINNET sur le même device doit retourner 409, obtenu {r2.status_code}"
        )
        body = r2.json()
        detail = body.get("detail", {})
        assert detail.get("code") == "device_wallet_limit", detail

    def test_multiple_test_wallets_same_device_all_return_200(self, api: TestClient) -> None:
        """TEST : plusieurs wallets par device autorisés (registre TEST séparé)."""
        device = "device-l3-test-multi"
        for i in range(3):
            resp = api.post(
                "/api/v1/wallet/create",
                json={
                    "name": f"l3-test-multi-{i:03d}",
                    "password": "password123!",
                    "wallet_namespace": "TEST",
                },
                headers={"X-ARTCB-Device-Id": device},
            )
            assert resp.status_code == 200, (
                f"Wallet TEST #{i} sur le même device doit être 200, obtenu {resp.status_code}: {resp.text}"
            )

    def test_test_wallet_does_not_block_mainnet_wallet_on_same_device(
        self, api: TestClient
    ) -> None:
        """Créer un wallet TEST ne bloque pas la création d'un wallet MAINNET sur le même device."""
        device = "device-l3-cross-ns"
        r_test = api.post(
            "/api/v1/wallet/create",
            json={"name": "l3-cross-test", "password": "password123!", "wallet_namespace": "TEST"},
            headers={"X-ARTCB-Device-Id": device},
        )
        assert r_test.status_code == 200, r_test.text

        r_main = api.post(
            "/api/v1/wallet/create",
            json={"name": "l3-cross-main", "password": "password123!", "wallet_namespace": "MAINNET"},
            headers={"X-ARTCB-Device-Id": device},
        )
        assert r_main.status_code == 200, (
            f"Un wallet TEST ne doit pas bloquer la création MAINNET, obtenu {r_main.status_code}: {r_main.text}"
        )

    def test_mainnet_wallet_does_not_block_test_wallet_on_same_device(
        self, api: TestClient
    ) -> None:
        """Créer un wallet MAINNET ne bloque pas la création d'un wallet TEST sur le même device."""
        device = "device-l3-cross-ns-rev"
        r_main = api.post(
            "/api/v1/wallet/create",
            json={"name": "l3-rev-main", "password": "password123!", "wallet_namespace": "MAINNET"},
            headers={"X-ARTCB-Device-Id": device},
        )
        assert r_main.status_code == 200, r_main.text

        r_test = api.post(
            "/api/v1/wallet/create",
            json={"name": "l3-rev-test", "password": "password123!", "wallet_namespace": "TEST"},
            headers={"X-ARTCB-Device-Id": device},
        )
        assert r_test.status_code == 200, (
            f"Un wallet MAINNET ne doit pas bloquer la création TEST, obtenu {r_test.status_code}: {r_test.text}"
        )

    def test_duplicate_wallet_name_same_device_returns_409(
        self, api: TestClient
    ) -> None:
        """Collision de nom (filesystem) sur le même device → 409 wallet_name_exists.

        Le binding TEST autorise plusieurs wallets par device, mais le filesystem
        interdit deux wallets portant exactement le même nom.
        On utilise le même device pour éviter que le binding TEST n'absorbe
        la tentative (pair wallet_name+device déjà présent → idempotent).
        """
        device = "device-l3-dup-name"
        r1 = api.post(
            "/api/v1/wallet/create",
            json={"name": "l3-dup-name", "password": "password123!", "wallet_namespace": "TEST"},
            headers={"X-ARTCB-Device-Id": device},
        )
        assert r1.status_code == 200, r1.text

        # Même nom, même device — binding TEST détecte la paire déjà enregistrée
        # puis WalletManager lève FileExistsError → 409 wallet_name_exists
        r2 = api.post(
            "/api/v1/wallet/create",
            json={"name": "l3-dup-name", "password": "password123!", "wallet_namespace": "TEST"},
            headers={"X-ARTCB-Device-Id": device},
        )
        assert r2.status_code == 409, f"Collision de nom doit retourner 409, obtenu {r2.status_code}"
        body = r2.json()
        assert body.get("detail", {}).get("code") == "wallet_name_exists", body


# ─────────────────────────────────────────────────────────────────────────────
# L4 — Séparation cryptographique : adresses TEST ≠ MAINNET pour le même name
# ─────────────────────────────────────────────────────────────────────────────

class TestL4CryptoSeparation:
    """L4 — Séparation cryptographique vérifiée à travers la couche HTTP."""

    def test_test_address_never_equals_mainnet_address(self, api: TestClient) -> None:
        """Deux wallets avec noms différents : adresse TEST ≠ adresse MAINNET."""
        r_test = api.post(
            "/api/v1/wallet/create",
            json={"name": "l4-crypto-test", "password": "password123!", "wallet_namespace": "TEST"},
            headers={"X-ARTCB-Device-Id": "device-l4-test"},
        )
        r_main = api.post(
            "/api/v1/wallet/create",
            json={"name": "l4-crypto-main", "password": "password123!", "wallet_namespace": "MAINNET"},
            headers={"X-ARTCB-Device-Id": "device-l4-main"},
        )
        assert r_test.status_code == 200, r_test.text
        assert r_main.status_code == 200, r_main.text

        addr_test = r_test.json()["address"]
        addr_main = r_main.json()["address"]

        # Préfixe obligatoirement différent
        assert addr_test.startswith("artcbdev1"), addr_test
        assert addr_main.startswith("artcb1"), addr_main
        # Adresses différentes (même si différentes clés — invariant de domaine)
        assert addr_test != addr_main

    def test_test_wallet_listed_has_artcbdev_address(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GET /api/v1/wallet/list liste le wallet TEST avec adresse artcbdev1…

        ARTCB_WALLET_LIST_PUBLIC=1 requis pour accès anonyme (R318 fail-closed).
        """
        monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("ARTCB_BOOTSTRAP_NODE", "false")
        monkeypatch.setenv("ARTCB_NODE_WALLET_ADDRESS", "artcb1testnode000000000000000000000000000")
        monkeypatch.setenv("ARTCB_WALLET_LIST_PUBLIC", "1")
        from src.api.main import create_app
        client = TestClient(create_app(), raise_server_exceptions=True)

        client.post(
            "/api/v1/wallet/create",
            json={"name": "l4-list-test", "password": "password123!", "wallet_namespace": "TEST"},
            headers={"X-ARTCB-Device-Id": "device-l4-list"},
        )
        resp = client.get("/api/v1/wallet/list")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        wallets = body.get("wallets", body) if isinstance(body, dict) else body
        found = [w for w in wallets if w.get("name") == "l4-list-test"]
        assert found, f"wallet l4-list-test absent de la liste : {wallets}"
        assert found[0]["address"].startswith("artcbdev1"), found[0]

    def test_health_endpoint_still_works_after_test_wallet_creation(
        self, api: TestClient
    ) -> None:
        """Créer un wallet TEST ne casse pas le nœud."""
        api.post(
            "/api/v1/wallet/create",
            json={"name": "l4-health-test", "password": "password123!", "wallet_namespace": "TEST"},
            headers={"X-ARTCB-Device-Id": "device-l4-health"},
        )
        resp = api.get("/health")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "machine" in body
