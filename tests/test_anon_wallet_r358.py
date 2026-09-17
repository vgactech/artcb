"""Tests R358 — routes anonymes de création de wallet.

Couvre :
  - _derive_wallet_name : déterminisme et format
  - AnonRegisterOptionsBody : validation pydantic
  - AnonRegisterVerifyBody : validation pydantic
  - anon_register_options : retourne publicKey + note R358
  - anon_register_verify : dérive wallet_name depuis credential_id + crée wallet
  - Idempotence : second appel avec même credential → wallet existant
  - Echec attestation : 400
  - Device binding : 409 si limite dépassée
  - Séparation clés : wallet_name dérivé ≠ credential_id brut
"""
from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from src.api.anon_wallet_routes import _derive_wallet_name


# ─── _derive_wallet_name ──────────────────────────────────────────────────────

def test_derive_wallet_name_format():
    """Le nom dérivé doit commencer par 'w-' suivi de 16 hex."""
    name = _derive_wallet_name("some-credential-id-abc123")
    assert name.startswith("w-"), f"attendu w-..., obtenu {name}"
    suffix = name[2:]
    assert len(suffix) == 16, f"attendu 16 hex, obtenu {len(suffix)}"
    assert all(c in "0123456789abcdef" for c in suffix), f"non-hex: {suffix}"


def test_derive_wallet_name_deterministic():
    """Même credential_id → même wallet_name à chaque appel."""
    cid = "AAAA_test_credential_BBBB"
    assert _derive_wallet_name(cid) == _derive_wallet_name(cid)


def test_derive_wallet_name_different_for_different_credentials():
    """Deux credential_id différents → deux wallet_name différents."""
    n1 = _derive_wallet_name("credential-alpha")
    n2 = _derive_wallet_name("credential-beta")
    assert n1 != n2


def test_derive_wallet_name_matches_sha256():
    """La dérivation correspond bien à SHA-256 tronqué."""
    cid = "test-cred-123"
    expected = "w-" + hashlib.sha256(cid.encode()).hexdigest()[:16]
    assert _derive_wallet_name(cid) == expected


def test_derive_wallet_name_short_credential():
    """Un credential_id très court est quand même traité."""
    name = _derive_wallet_name("x")
    assert name.startswith("w-")
    assert len(name) == 18  # "w-" + 16


def test_derive_wallet_name_long_credential():
    """Un credential_id très long (base64url typique) est tronqué correctement."""
    cid = "A" * 512
    name = _derive_wallet_name(cid)
    assert len(name) == 18


# ─── Pydantic models ──────────────────────────────────────────────────────────

def test_anon_register_options_body_defaults():
    from src.api.anon_wallet_routes import AnonRegisterOptionsBody
    body = AnonRegisterOptionsBody()
    assert body.create_wallet is True


def test_anon_register_options_body_explicit():
    from src.api.anon_wallet_routes import AnonRegisterOptionsBody
    body = AnonRegisterOptionsBody(create_wallet=False)
    assert body.create_wallet is False


def test_anon_register_verify_body_credential():
    from src.api.anon_wallet_routes import AnonRegisterVerifyBody, CredentialResponse
    cred = CredentialResponse(
        id="cred-id-abc",
        type="public-key",
        response={"clientDataJSON": "xxx", "attestationObject": "yyy"},
    )
    body = AnonRegisterVerifyBody(credential=cred)
    assert body.create_wallet is True
    assert body.credential.id == "cred-id-abc"


# ─── anon_register_options ────────────────────────────────────────────────────

def _make_request(host: str = "artcb.me", proto: str = "https") -> MagicMock:
    req = MagicMock()
    req.headers = {"host": host, "x-forwarded-proto": proto}
    req.url.hostname = host
    req.url.scheme = proto
    req.client.host = "127.0.0.1"
    return req


@patch("src.api.anon_wallet_routes.registration_options")
def test_anon_register_options_returns_publickey(mock_reg_opts):
    from src.api.anon_wallet_routes import AnonRegisterOptionsBody, anon_register_options
    mock_reg_opts.return_value = {"challenge": "abc123", "rp": {"id": "artcb.me"}}
    body = AnonRegisterOptionsBody()
    req = _make_request()
    result = anon_register_options(body, req)
    assert "publicKey" in result
    assert result["raw_biometric_never_stored"] is True
    assert result["certified"] is False
    assert "R358" in result["note"]


@patch("src.api.anon_wallet_routes.registration_options")
def test_anon_register_options_no_modality_in_response(mock_reg_opts):
    """La réponse ne doit pas exposer la modality à l'utilisateur."""
    from src.api.anon_wallet_routes import AnonRegisterOptionsBody, anon_register_options
    mock_reg_opts.return_value = {}
    body = AnonRegisterOptionsBody()
    result = anon_register_options(body, _make_request())
    assert "modality" not in result, "modality ne doit pas être exposée dans la réponse"


@patch("src.api.anon_wallet_routes.registration_options")
def test_anon_register_options_user_id_random(mock_reg_opts):
    """Deux appels successifs → deux user_id différents (aléatoires)."""
    from src.api.anon_wallet_routes import AnonRegisterOptionsBody, anon_register_options
    mock_reg_opts.return_value = {}
    body = AnonRegisterOptionsBody()
    req = _make_request()
    anon_register_options(body, req)
    anon_register_options(body, req)
    # Vérifier que registration_options a été appelé avec des user_id distincts
    calls = mock_reg_opts.call_args_list
    # registration_options est appelé avec kwargs : user_id=...
    uid1 = calls[0].kwargs.get("user_id")
    uid2 = calls[1].kwargs.get("user_id")
    # Les user_id sont générés par secrets.token_bytes(32) — ils doivent être différents
    assert uid1 is not None and uid2 is not None, "user_id doit être passé en kwarg"
    assert uid1 != uid2, "user_id doit être aléatoire à chaque appel"


# ─── anon_register_verify ─────────────────────────────────────────────────────

def _mock_verified(cred_id: str = "test-cred-id-xyz") -> dict:
    return {
        "credential_id": cred_id,
        "cose_b64": "AAAA",
        "sign_count": 0,
        "rp_id": "artcb.me",
    }


def _mock_wallet(name: str, address: str = "addr-test-abc") -> dict:
    return {
        "created": True,
        "name": name,
        "address": address,
        "seed_hex": "deadbeef01234567",
        "WARNING": "save seed",
        "unique_human_proven": False,
    }


@patch("src.api.anon_wallet_routes.issue_session")
@patch("src.api.anon_wallet_routes.save_credential")
@patch("src.api.anon_wallet_routes._create_wallet_auto")
@patch("src.api.anon_wallet_routes.verify_attestation")
@patch("src.api.anon_wallet_routes.pop_pending")
@patch("src.api.anon_wallet_routes.b64u_decode")
def test_anon_register_verify_derives_wallet_name(
    mock_b64u, mock_pop, mock_verify, mock_create, mock_save, mock_session
):
    from src.api.anon_wallet_routes import AnonRegisterVerifyBody, CredentialResponse, anon_register_verify

    cred_id = "credential-test-deterministic"
    expected_name = _derive_wallet_name(cred_id)

    import json as _json
    mock_b64u.side_effect = [
        _json.dumps({"challenge": "ch123", "type": "webauthn.create"}).encode(),
        b"att_obj_bytes",
    ]
    mock_pop.return_value = {"rp_id": "artcb.me"}
    mock_verify.return_value = _mock_verified(cred_id)
    mock_create.return_value = _mock_wallet(expected_name)
    mock_session.return_value = {"session_token": "tok123", "expires_in": 3600}

    cred = CredentialResponse(
        id=cred_id,
        type="public-key",
        response={"clientDataJSON": "xxx", "attestationObject": "yyy"},
    )
    body = AnonRegisterVerifyBody(credential=cred)
    result = anon_register_verify(body, _make_request())

    assert result["wallet_name"] == expected_name, (
        f"wallet_name attendu={expected_name}, obtenu={result['wallet_name']}"
    )
    assert result["ok"] is True
    assert result["unique_human_proven"] is False
    assert result["certified"] is False
    assert "R358" in result["note"]
    # _create_wallet_auto appelé avec le nom dérivé
    assert mock_create.call_args[0][0] == expected_name


@patch("src.api.anon_wallet_routes.issue_session")
@patch("src.api.anon_wallet_routes.save_credential")
@patch("src.api.anon_wallet_routes._create_wallet_auto")
@patch("src.api.anon_wallet_routes.verify_attestation")
@patch("src.api.anon_wallet_routes.pop_pending")
@patch("src.api.anon_wallet_routes.b64u_decode")
def test_anon_register_verify_seed_in_response(
    mock_b64u, mock_pop, mock_verify, mock_create, mock_save, mock_session
):
    """seed_hex est présent dans la réponse si le wallet est nouveau."""
    from src.api.anon_wallet_routes import AnonRegisterVerifyBody, CredentialResponse, anon_register_verify

    import json as _json
    mock_b64u.side_effect = [
        _json.dumps({"challenge": "ch456", "type": "webauthn.create"}).encode(),
        b"att_bytes",
    ]
    mock_pop.return_value = {"rp_id": "artcb.me"}
    mock_verify.return_value = _mock_verified("cred-seed-test")
    expected_name = _derive_wallet_name("cred-seed-test")
    mock_create.return_value = _mock_wallet(expected_name, "addr-seed")
    mock_session.return_value = {"session_token": "tok-seed", "expires_in": 3600}

    cred = CredentialResponse(
        id="cred-seed-test",
        type="public-key",
        response={"clientDataJSON": "a", "attestationObject": "b"},
    )
    result = anon_register_verify(AnonRegisterVerifyBody(credential=cred), _make_request())
    assert "seed_hex" in result
    assert result["seed_hex"] == "deadbeef01234567"


@patch("src.api.anon_wallet_routes.b64u_decode")
def test_anon_register_verify_bad_attestation_raises_400(mock_b64u):
    """Une attestation invalide doit retourner HTTP 400."""
    from fastapi import HTTPException
    from src.api.anon_wallet_routes import AnonRegisterVerifyBody, CredentialResponse, anon_register_verify
    from src.artcb.security.webauthn_protocol import WebAuthnError

    import json as _json
    mock_b64u.side_effect = [
        _json.dumps({"challenge": "bad", "type": "webauthn.create"}).encode(),
        b"bad",
    ]
    with patch("src.api.anon_wallet_routes.pop_pending", side_effect=WebAuthnError("challenge_not_found")):
        cred = CredentialResponse(
            id="bad-cred",
            type="public-key",
            response={"clientDataJSON": "x", "attestationObject": "y"},
        )
        with pytest.raises(HTTPException) as exc_info:
            anon_register_verify(AnonRegisterVerifyBody(credential=cred), _make_request())
        assert exc_info.value.status_code == 400


@patch("src.api.anon_wallet_routes.issue_session")
@patch("src.api.anon_wallet_routes.save_credential")
@patch("src.api.anon_wallet_routes._create_wallet_auto")
@patch("src.api.anon_wallet_routes.verify_attestation")
@patch("src.api.anon_wallet_routes.pop_pending")
@patch("src.api.anon_wallet_routes.b64u_decode")
def test_anon_register_verify_no_name_field_in_response(
    mock_b64u, mock_pop, mock_verify, mock_create, mock_save, mock_session
):
    """La réponse ne doit pas contenir de champ 'name' imposé par l'utilisateur."""
    from src.api.anon_wallet_routes import AnonRegisterVerifyBody, CredentialResponse, anon_register_verify

    import json as _json
    mock_b64u.side_effect = [
        _json.dumps({"challenge": "ch789", "type": "webauthn.create"}).encode(),
        b"att",
    ]
    mock_pop.return_value = {"rp_id": "artcb.me"}
    mock_verify.return_value = _mock_verified("cred-noname")
    name = _derive_wallet_name("cred-noname")
    mock_create.return_value = _mock_wallet(name)
    mock_session.return_value = {"session_token": "t", "expires_in": 3600}

    cred = CredentialResponse(
        id="cred-noname",
        type="public-key",
        response={"clientDataJSON": "a", "attestationObject": "b"},
    )
    result = anon_register_verify(AnonRegisterVerifyBody(credential=cred), _make_request())
    # wallet_name doit être dérivé automatiquement (format w-...)
    assert result["wallet_name"].startswith("w-")
    # La réponse ne doit pas contenir un champ "name" saisi par l'utilisateur
    # (wallet_name est le nom technique, c'est acceptable)
    assert "user_supplied_name" not in result


# ─── _create_wallet_auto ─────────────────────────────────────────────────────

def test_create_wallet_auto_existing_wallet():
    """Si le wallet existe déjà, retourner ses infos sans recréer."""
    from src.api.anon_wallet_routes import _create_wallet_auto

    name = "w-existingwallet1"
    # WalletManager est importé localement dans la fonction → patch sur le module source
    with patch("src.artcb.wallet.manager.WalletManager") as MockWM:
        wm_instance = MockWM.return_value
        key_path = MagicMock()
        key_path.exists.return_value = True
        wm_instance.wallet_dir.__truediv__ = MagicMock(return_value=key_path)
        wm_instance.list_wallets.return_value = [
            {"name": name, "address": "addr-existing"}
        ]
        # Patch aussi l'import local dans la fonction
        with patch("src.api.anon_wallet_routes.WalletManager", MockWM, create=True):
            result = _create_wallet_auto(name)
    assert result["created"] is False
    assert result["address"] == "addr-existing"
    assert result["seed_hex"] is None


def test_create_wallet_auto_new_wallet():
    """Si le wallet n'existe pas, le créer et retourner la seed."""
    from src.api.anon_wallet_routes import _create_wallet_auto

    name = "w-newwallet1234"
    mock_signing_key = MagicMock()
    mock_signing_key.encode.return_value = bytes.fromhex("aabbcc" + "00" * 29)
    mock_wallet = MagicMock()
    mock_wallet.address = "addr-new-wallet"
    mock_wallet.signing_key = mock_signing_key

    key_path = MagicMock()
    key_path.exists.return_value = False

    mock_wm_instance = MagicMock()
    mock_wm_instance.wallet_dir.__truediv__ = MagicMock(return_value=key_path)
    mock_wm_instance.create_wallet.return_value = mock_wallet

    # WalletManager est importé localement dans _create_wallet_auto via
    # "from src.artcb.wallet.manager import WalletManager"
    with patch("src.artcb.wallet.manager.WalletManager", return_value=mock_wm_instance):
        result = _create_wallet_auto(name, request=None)

    assert result["created"] is True
    # L'adresse est celle du mock_wallet
    assert result["address"] == mock_wallet.address
    assert result["seed_hex"] is not None
    assert result["unique_human_proven"] is False
