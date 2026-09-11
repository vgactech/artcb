"""R320 — soak session : logout, révocation, expiration, changement d'appareil.

R319 laissait ce lot OPEN : le TTL n'était qu'une constante dans le code, jamais
mesuré, et rien n'empêchait de rejouer un token volé depuis une autre machine.
Ici on mesure le comportement réel du serveur, pas la constante.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app

PWD = "pwd_r320_session_soak"
UA_PHONE = {"User-Agent": "artcb-phone/1.0", "X-ARTCB-Device-Id": "device-phone"}
UA_LAPTOP = {"User-Agent": "artcb-laptop/1.0", "X-ARTCB-Device-Id": "device-laptop"}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_ALLOW_MULTI_WALLET", "true")
    from src.api import auth_routes

    auth_routes._sessions.clear()
    return TestClient(create_app())


def _mk(client: TestClient, name: str) -> str:
    r = client.post("/api/v1/wallet/create", json={"name": name, "password": PWD})
    assert r.status_code == 200, r.text
    return r.json()["address"]


def _login(client: TestClient, name: str, headers: dict | None = None) -> dict:
    r = client.post(
        "/api/v1/auth/login",
        json={"name": name, "password": PWD},
        headers=headers or UA_PHONE,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _auth(token: str, headers: dict | None = None) -> dict:
    return {"Authorization": f"Bearer {token}", **(headers or UA_PHONE)}


# ── TTL réellement appliqué par le serveur ───────────────────────────────────

def test_ttl_values_are_exposed_and_absolute_is_1800(client: TestClient) -> None:
    addr = _mk(client, "ttl_expose")
    sess = _login(client, "ttl_expose")
    assert sess["expires_in"] == 1800
    assert sess["idle_expires_in"] > 0
    r = client.get("/api/v1/auth/sessions", headers=_auth(sess["session_token"]))
    assert r.status_code == 200
    body = r.json()
    assert body["address"] == addr
    assert body["absolute_ttl_s"] == 1800
    assert body["active_sessions"] == 1
    assert body["sessions"][0]["current"] is True
    # Jamais de token ni de hash complet exposé.
    assert "session_token" not in str(body)
    assert len(body["sessions"][0]["session_id"]) == 16


def test_expired_session_is_rejected_measured(client: TestClient) -> None:
    """On mesure l'expiration réelle en vieillissant l'enregistrement serveur."""
    addr = _mk(client, "ttl_expire")
    sess = _login(client, "ttl_expire")
    tok = sess["session_token"]
    assert client.get(
        f"/api/v1/wallet/balance/{addr}", headers=_auth(tok)
    ).status_code == 200

    from src.api import auth_routes

    for record in auth_routes._sessions.values():
        record["expires_at"] = time.time() - 1

    r = client.get(f"/api/v1/wallet/balance/{addr}", headers=_auth(tok))
    assert r.status_code == 401
    assert auth_routes._sessions == {}, "la session expirée doit être purgée"


def test_idle_timeout_kills_a_forgotten_token(client: TestClient) -> None:
    addr = _mk(client, "idle_kill")
    tok = _login(client, "idle_kill")["session_token"]
    from src.api import auth_routes

    for record in auth_routes._sessions.values():
        record["last_seen"] = time.time() - (record["idle_ttl"] + 5)

    r = client.get(f"/api/v1/wallet/balance/{addr}", headers=_auth(tok))
    assert r.status_code == 401
    assert r.json()["detail"] == "session_idle_timeout"


def test_activity_refreshes_idle_window(client: TestClient) -> None:
    addr = _mk(client, "idle_refresh")
    tok = _login(client, "idle_refresh")["session_token"]
    from src.api import auth_routes

    before = next(iter(auth_routes._sessions.values()))["last_seen"]
    time.sleep(0.01)
    assert client.get(
        f"/api/v1/wallet/balance/{addr}", headers=_auth(tok)
    ).status_code == 200
    after = next(iter(auth_routes._sessions.values()))["last_seen"]
    assert after > before


# ── Changement d'appareil ────────────────────────────────────────────────────

def test_stolen_token_replayed_from_another_device_is_rejected(client: TestClient) -> None:
    addr = _mk(client, "device_bind")
    tok = _login(client, "device_bind", UA_PHONE)["session_token"]
    assert client.get(
        f"/api/v1/wallet/balance/{addr}", headers=_auth(tok, UA_PHONE)
    ).status_code == 200

    r = client.get(f"/api/v1/wallet/balance/{addr}", headers=_auth(tok, UA_LAPTOP))
    assert r.status_code == 401
    assert r.json()["detail"] == "session_device_mismatch"

    # L'appareil légitime n'est pas puni par la tentative d'un tiers.
    assert client.get(
        f"/api/v1/wallet/balance/{addr}", headers=_auth(tok, UA_PHONE)
    ).status_code == 200


def test_device_binding_can_be_disabled_for_autonomous_agents(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase de développement : un agent ne doit jamais rester bloqué."""
    addr = _mk(client, "device_off")
    tok = _login(client, "device_off", UA_PHONE)["session_token"]
    monkeypatch.setenv("ARTCB_SESSION_BIND_DEVICE", "0")
    assert client.get(
        f"/api/v1/wallet/balance/{addr}", headers=_auth(tok, UA_LAPTOP)
    ).status_code == 200


# ── Logout / révocation ──────────────────────────────────────────────────────

def test_logout_revokes_only_that_session(client: TestClient) -> None:
    addr = _mk(client, "logout_one")
    phone = _login(client, "logout_one", UA_PHONE)["session_token"]
    laptop = _login(client, "logout_one", UA_LAPTOP)["session_token"]

    assert client.post("/api/v1/auth/logout", headers=_auth(phone)).status_code == 200
    assert client.get(
        f"/api/v1/wallet/balance/{addr}", headers=_auth(phone)
    ).status_code == 401
    assert client.get(
        f"/api/v1/wallet/balance/{addr}", headers=_auth(laptop, UA_LAPTOP)
    ).status_code == 200


def test_revoke_by_session_id_and_ownership(client: TestClient) -> None:
    _mk(client, "revoke_a")
    _mk(client, "revoke_b")
    a_phone = _login(client, "revoke_a", UA_PHONE)
    a_laptop = _login(client, "revoke_a", UA_LAPTOP)
    b_phone = _login(client, "revoke_b", UA_PHONE)

    # B ne peut pas révoquer une session de A.
    r = client.post(
        "/api/v1/auth/revoke",
        json={"session_id": a_laptop["session_id"]},
        headers=_auth(b_phone["session_token"]),
    )
    assert r.status_code == 404

    # A révoque son propre autre appareil.
    r = client.post(
        "/api/v1/auth/revoke",
        json={"session_id": a_laptop["session_id"]},
        headers=_auth(a_phone["session_token"]),
    )
    assert r.status_code == 200 and r.json()["revoked"] == 1
    assert client.get(
        "/api/v1/auth/sessions", headers=_auth(a_laptop["session_token"], UA_LAPTOP)
    ).status_code == 401
    assert client.get(
        "/api/v1/auth/sessions", headers=_auth(a_phone["session_token"])
    ).status_code == 200


def test_logout_all_kills_every_device_of_that_address(client: TestClient) -> None:
    addr = _mk(client, "logout_all")
    _mk(client, "other_user")
    phone = _login(client, "logout_all", UA_PHONE)["session_token"]
    laptop = _login(client, "logout_all", UA_LAPTOP)["session_token"]
    other = _login(client, "other_user", UA_PHONE)["session_token"]

    r = client.post("/api/v1/auth/logout-all", headers=_auth(phone))
    assert r.status_code == 200 and r.json()["revoked"] == 2

    assert client.get(
        f"/api/v1/wallet/balance/{addr}", headers=_auth(phone)
    ).status_code == 401
    assert client.get(
        f"/api/v1/wallet/balance/{addr}", headers=_auth(laptop, UA_LAPTOP)
    ).status_code == 401
    # Un autre utilisateur n'est jamais affecté.
    assert client.get(
        "/api/v1/auth/sessions", headers=_auth(other)
    ).status_code == 200


def test_forged_and_empty_tokens_are_rejected(client: TestClient) -> None:
    addr = _mk(client, "forged")
    assert client.get(f"/api/v1/wallet/balance/{addr}").status_code == 401
    assert client.get(
        f"/api/v1/wallet/balance/{addr}", headers=_auth("sess_" + "0" * 64)
    ).status_code == 401
    assert client.get(
        f"/api/v1/wallet/balance/{addr}",
        headers={"Authorization": "Bearer not_a_session", **UA_PHONE},
    ).status_code == 401


def test_soak_many_sessions_then_revoke_all(client: TestClient) -> None:
    """Soak : 25 connexions successives, puis logout-all doit tout nettoyer."""
    addr = _mk(client, "soak_many")
    tokens = [
        _login(
            client,
            "soak_many",
            {"User-Agent": f"artcb-dev-{i}/1.0", "X-ARTCB-Device-Id": f"dev-{i}"},
        )
        for i in range(25)
    ]
    last = tokens[-1]
    ua_last = {"User-Agent": "artcb-dev-24/1.0", "X-ARTCB-Device-Id": "dev-24"}
    listing = client.get(
        "/api/v1/auth/sessions", headers=_auth(last["session_token"], ua_last)
    ).json()
    assert listing["active_sessions"] == 25
    assert len({s["session_id"] for s in listing["sessions"]}) == 25

    r = client.post("/api/v1/auth/logout-all", headers=_auth(last["session_token"], ua_last))
    assert r.json()["revoked"] == 25
    for t in tokens:
        assert client.get(
            f"/api/v1/wallet/balance/{addr}", headers=_auth(t["session_token"])
        ).status_code == 401
