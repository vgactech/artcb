"""R348b — adversarial USER↔NODE association tests."""

from __future__ import annotations

import time
from pathlib import Path

from nacl.signing import SigningKey

from src.artcb.identity.user_node_association import (
    UserNodeAssociationError,
    canonical_message,
    issue_challenge,
    reject_private_key_fields,
    verify_and_build_association,
)


def _sign(sk: SigningKey, *, challenge: str, node_id: str, node_wallet: str | None, user: str, role: str) -> str:
    msg = canonical_message(
        challenge=challenge,
        node_id=node_id,
        node_wallet_address=node_wallet,
        user_address=user,
        role=role,
    )
    return sk.sign(msg).signature.hex()


def test_replay_challenge_fails() -> None:
    sk = SigningKey.generate()
    store: dict = {}
    ch = issue_challenge(node_id="nA", node_wallet_address="wA", store=store)
    sig = _sign(sk, challenge=ch["challenge"], node_id="nA", node_wallet="wA", user="artcb1u", role="client")
    verify_and_build_association(
        challenge=ch["challenge"],
        store=store,
        user_address="artcb1u",
        user_public_key_hex=sk.verify_key.encode().hex(),
        signature_hex=sig,
    )
    try:
        verify_and_build_association(
            challenge=ch["challenge"],
            store=store,
            user_address="artcb1u",
            user_public_key_hex=sk.verify_key.encode().hex(),
            signature_hex=sig,
        )
        ok = False
    except UserNodeAssociationError as e:
        ok = str(e) == "challenge_unknown"
    assert ok


def test_expired_challenge_fails() -> None:
    sk = SigningKey.generate()
    store: dict = {}
    ch = issue_challenge(node_id="nA", node_wallet_address=None, store=store, ttl_s=1)
    store[ch["challenge"]]["expires_at"] = time.time() - 1
    sig = _sign(sk, challenge=ch["challenge"], node_id="nA", node_wallet=None, user="artcb1u", role="client")
    try:
        verify_and_build_association(
            challenge=ch["challenge"],
            store=store,
            user_address="artcb1u",
            user_public_key_hex=sk.verify_key.encode().hex(),
            signature_hex=sig,
        )
        ok = False
    except UserNodeAssociationError as e:
        ok = str(e) == "challenge_expired"
    assert ok


def test_signature_for_node_a_rejected_on_node_b_message() -> None:
    """Signature bound to node A must not verify for node B canonical message."""
    sk = SigningKey.generate()
    store: dict = {}
    ch = issue_challenge(node_id="nB", node_wallet_address="wB", store=store)
    # Attacker signs as if node were nA
    sig = _sign(sk, challenge=ch["challenge"], node_id="nA", node_wallet="wB", user="artcb1u", role="client")
    try:
        verify_and_build_association(
            challenge=ch["challenge"],
            store=store,
            user_address="artcb1u",
            user_public_key_hex=sk.verify_key.encode().hex(),
            signature_hex=sig,
            role="client",
        )
        ok = False
    except UserNodeAssociationError as e:
        ok = str(e) == "signature_invalid"
    assert ok


def test_role_tamper_after_sign_fails() -> None:
    sk = SigningKey.generate()
    store: dict = {}
    ch = issue_challenge(node_id="nA", node_wallet_address=None, store=store)
    sig = _sign(sk, challenge=ch["challenge"], node_id="nA", node_wallet=None, user="artcb1u", role="client")
    try:
        verify_and_build_association(
            challenge=ch["challenge"],
            store=store,
            user_address="artcb1u",
            user_public_key_hex=sk.verify_key.encode().hex(),
            signature_hex=sig,
            role="operator",  # tampered
        )
        ok = False
    except UserNodeAssociationError as e:
        ok = str(e) == "signature_invalid"
    assert ok


def test_user_address_tamper_fails() -> None:
    sk = SigningKey.generate()
    store: dict = {}
    ch = issue_challenge(node_id="nA", node_wallet_address=None, store=store)
    sig = _sign(sk, challenge=ch["challenge"], node_id="nA", node_wallet=None, user="artcb1alice", role="client")
    try:
        verify_and_build_association(
            challenge=ch["challenge"],
            store=store,
            user_address="artcb1bob",
            user_public_key_hex=sk.verify_key.encode().hex(),
            signature_hex=sig,
        )
        ok = False
    except UserNodeAssociationError as e:
        ok = str(e) == "signature_invalid"
    assert ok


def test_node_wallet_tamper_fails() -> None:
    sk = SigningKey.generate()
    store: dict = {}
    ch = issue_challenge(node_id="nA", node_wallet_address="wallet_real", store=store)
    sig = _sign(
        sk,
        challenge=ch["challenge"],
        node_id="nA",
        node_wallet="wallet_fake",
        user="artcb1u",
        role="client",
    )
    try:
        verify_and_build_association(
            challenge=ch["challenge"],
            store=store,
            user_address="artcb1u",
            user_public_key_hex=sk.verify_key.encode().hex(),
            signature_hex=sig,
        )
        ok = False
    except UserNodeAssociationError as e:
        ok = str(e) == "signature_invalid"
    assert ok


def test_private_key_fields_forbidden() -> None:
    for k in ("seed_hex", "private_key", "mnemonic", "secret_key"):
        try:
            reject_private_key_fields({k: "x", "user_address": "a"})
            raised = False
        except UserNodeAssociationError:
            raised = True
        assert raised, k
