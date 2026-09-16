"""TEST DOMAIN transaction signing and validation.

Architecture (rapport 355 §5–§7, rapport 356 §14):
  Every TEST transaction payload includes the domain envelope:
    {domain_id, network_id, genesis_hash, protocol_version, wallet_id, nonce, payload}

  This makes a TEST signature mathematically invalid on MAINNET:
  the signed message differs because network_id differs.

  Cross-domain transaction rejection is enforced at build time AND at validation
  time — two independent barriers.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from src.artcb.testdomain.policy import (
    MAINNET_DOMAIN_TAG,
    TEST_ASSET_NAME,
    TEST_DOMAIN_TAG,
    TEST_GENESIS_HASH,
    TEST_NETWORK_ID,
    TEST_PROTOCOL_VERSION,
    domain_of_address,
    reject_cross_domain_transfer,
)

logger = logging.getLogger("artcb.testdomain.transaction")


class TestTransactionError(Exception):
    """Raised when a TEST transaction invariant is violated."""


def build_test_transaction(
    *,
    wallet_id: str,
    signing_key,          # nacl.signing.SigningKey
    nonce: int,
    payload: dict[str, Any],
    recipient: str | None = None,
    amount_satoshi: int = 0,
) -> dict:
    """Build and sign a domain-separated TEST transaction.

    The signed envelope includes network_id so the same private key produces a
    DIFFERENT signature on TEST vs MAINNET (cross-domain replay impossible).

    Args:
        wallet_id:      TEST wallet address (artcbdev1…)
        signing_key:    nacl SigningKey for the wallet
        nonce:          monotonically increasing counter (replay protection)
        payload:        application-level data to include
        recipient:      optional destination address for transfers
        amount_satoshi: tARTCB micro-units for transfer transactions

    Returns:
        Signed transaction dict with domain_id, network_id, signature, etc.

    Raises:
        TestTransactionError on any domain invariant violation.
    """
    # 1. Validate wallet domain
    if domain_of_address(wallet_id) != "TEST":
        raise TestTransactionError(
            f"reject_non_test_wallet_in_test_tx: {wallet_id}"
        )

    # 2. Validate recipient domain (if provided)
    if recipient is not None:
        rejected, reason = reject_cross_domain_transfer(wallet_id, recipient)
        if rejected:
            raise TestTransactionError(reason)

    # 3. Build the domain-separated envelope to sign
    envelope: dict[str, Any] = {
        "domain_id": TEST_DOMAIN_TAG,
        "network_id": TEST_NETWORK_ID,
        "genesis_hash": TEST_GENESIS_HASH,
        "protocol_version": TEST_PROTOCOL_VERSION,
        "wallet_id": wallet_id,
        "nonce": nonce,
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "payload": payload,
        "asset": TEST_ASSET_NAME,
    }
    if recipient is not None:
        envelope["recipient"] = recipient
        envelope["amount_satoshi"] = int(amount_satoshi)

    # 4. Sign the canonical JSON of the envelope
    canonical = json.dumps(envelope, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    message_bytes = canonical.encode("utf-8")
    signed = signing_key.sign(message_bytes)
    sig_hex = signed.signature.hex()

    tx_hash = hashlib.sha256(message_bytes).hexdigest()

    tx: dict[str, Any] = {
        **envelope,
        "tx_hash": tx_hash,
        "signature": sig_hex,
        "public_key_hex": signing_key.verify_key.encode().hex(),
    }
    logger.debug("TEST tx built wallet=%s nonce=%d hash=%s", wallet_id, nonce, tx_hash[:16])
    return tx


def validate_test_transaction(tx: dict) -> tuple[bool, str]:
    """Validate a TEST transaction's domain invariants and signature.

    Returns (valid: bool, reason: str).
    Does NOT check nonce ordering (caller's responsibility).
    """
    from nacl.signing import VerifyKey
    from nacl.exceptions import BadSignatureError

    # 1. Domain must be TEST
    if tx.get("network_id") != TEST_NETWORK_ID:
        return False, f"reject_wrong_network_id:{tx.get('network_id')}"
    if tx.get("genesis_hash") and tx.get("genesis_hash") != TEST_GENESIS_HASH:
        return False, f"reject_wrong_genesis_hash:{tx.get('genesis_hash')}"
    if tx.get("domain_id") == MAINNET_DOMAIN_TAG:
        return False, "reject_mainnet_domain_tag_in_test_tx"

    # 2. Sender must be TEST address
    wallet_id = tx.get("wallet_id", "")
    if domain_of_address(wallet_id) != "TEST":
        return False, f"reject_non_test_wallet:{wallet_id}"

    # 3. Cross-domain recipient check
    recipient = tx.get("recipient")
    if recipient:
        rejected, reason = reject_cross_domain_transfer(wallet_id, recipient)
        if rejected:
            return False, reason

    # 4. Reconstruct canonical envelope for signature verification
    envelope_keys = {
        "domain_id", "network_id", "genesis_hash", "protocol_version",
        "wallet_id", "nonce", "timestamp", "payload", "asset",
        "recipient", "amount_satoshi",
    }
    envelope = {k: tx[k] for k in envelope_keys if k in tx}
    canonical = json.dumps(envelope, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    message_bytes = canonical.encode("utf-8")

    sig_hex = tx.get("signature", "")
    pk_hex = tx.get("public_key_hex", "")
    if not sig_hex or not pk_hex:
        return False, "reject_missing_signature_or_pubkey"

    try:
        vk = VerifyKey(bytes.fromhex(pk_hex))
        vk.verify(message_bytes, bytes.fromhex(sig_hex))
    except (BadSignatureError, Exception) as exc:
        return False, f"reject_invalid_signature:{exc}"

    return True, "valid_test_transaction"


def build_test_block_from_transactions(
    transactions: list[dict],
    *,
    pol_score: float = 1.0,
    graph_id: str | None = None,
    visibility: str = "public",
) -> dict:
    """Build a TEST block payload from validated transactions.

    Computes contributors (reward_satoshi per wallet) for PoL-style rewards.
    The block dict is suitable for TestChainManager.append_block().

    Reward model: fixed 1 tARTCB (100_000_000 satoshi) per unique contributor,
    distributed equally among tx senders — simple enough to be E2E testable.
    """
    if not transactions:
        raise TestTransactionError("cannot_build_block_from_empty_tx_list")

    # Collect unique contributors (TEST wallet addresses only)
    contributor_set: dict[str, int] = {}
    for tx in transactions:
        addr = tx.get("wallet_id", "")
        if domain_of_address(addr) != "TEST":
            raise TestTransactionError(
                f"reject_mainnet_wallet_in_test_block_txs: {addr}"
            )
        contributor_set[addr] = contributor_set.get(addr, 0) + 1

    reward_per_contributor = 100_000_000  # 1 tARTCB per contributor
    contributors = [
        {
            "address": addr,
            "reward_satoshi": reward_per_contributor,
            "tx_count": count,
            "asset": TEST_ASSET_NAME,
        }
        for addr, count in contributor_set.items()
    ]

    # Merkle root of tx hashes
    tx_hashes = [tx.get("tx_hash", "") for tx in transactions]
    merkle_material = "|".join(sorted(tx_hashes)).encode("utf-8")
    merkle_root = hashlib.sha256(merkle_material).hexdigest()

    graph_root = hashlib.sha256(
        json.dumps(transactions, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    return {
        "network_id": TEST_NETWORK_ID,
        "protocol_version": TEST_PROTOCOL_VERSION,
        "genesis_hash": TEST_GENESIS_HASH,
        "domain": "TEST",
        "asset": TEST_ASSET_NAME,
        "graph_root": graph_root,
        "merkle_root": merkle_root,
        "pol_score": pol_score,
        "graph_id": graph_id or f"test-tx-block-{merkle_root[:8]}",
        "visibility": visibility,
        "group_id": None,
        "block_reward": reward_per_contributor * len(contributors),
        "contributors": contributors,
        "transactions": transactions,
    }
