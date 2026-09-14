"""R348 — USER↔NODE association unit tests (no privkey; R345 untouched)."""

from pathlib import Path

from nacl.signing import SigningKey

from src.artcb.identity.user_node_association import (
    UserNodeAssociationError,
    UserNodeAssociationStore,
    canonical_message,
    issue_challenge,
    reject_private_key_fields,
    verify_and_build_association,
)


def test_reject_private_key_fields() -> None:
    try:
        reject_private_key_fields({"user_address": "a", "seed_hex": "dead"})
        raised = False
    except UserNodeAssociationError:
        raised = True
    assert raised is True


def test_associate_roundtrip(tmp_path: Path) -> None:
    sk = SigningKey.generate()
    pk = sk.verify_key.encode().hex()
    # fake bech32-looking address label for test — association stores string as given
    user_addr = "artcb1testuser348xxxxxxxxxxxxxxxxxxxxxxxx"
    store: dict = {}
    ch = issue_challenge(node_id="ovh-node-1", node_wallet_address="artcb1nodeop", store=store)
    msg = canonical_message(
        challenge=ch["challenge"],
        node_id="ovh-node-1",
        node_wallet_address="artcb1nodeop",
        user_address=user_addr,
        role="client",
    )
    sig = sk.sign(msg).signature.hex()
    rec = verify_and_build_association(
        challenge=ch["challenge"],
        store=store,
        user_address=user_addr,
        user_public_key_hex=pk,
        signature_hex=sig,
        role="client",
    )
    path = tmp_path / "assoc.json"
    saved = UserNodeAssociationStore(path).upsert(rec)
    assert saved.role == "client"
    assert saved.node_id == "ovh-node-1"
    rows = UserNodeAssociationStore(path).list_for_user(user_addr)
    assert len(rows) == 1


def test_bad_signature_rejected() -> None:
    sk = SigningKey.generate()
    other = SigningKey.generate()
    store: dict = {}
    ch = issue_challenge(node_id="n1", node_wallet_address=None, store=store)
    msg = canonical_message(
        challenge=ch["challenge"],
        node_id="n1",
        node_wallet_address=None,
        user_address="artcb1x",
        role="client",
    )
    sig = other.sign(msg).signature.hex()
    try:
        verify_and_build_association(
            challenge=ch["challenge"],
            store=store,
            user_address="artcb1x",
            user_public_key_hex=sk.verify_key.encode().hex(),
            signature_hex=sig,
        )
        ok = False
    except UserNodeAssociationError as exc:
        ok = str(exc) == "signature_invalid"
    assert ok is True
