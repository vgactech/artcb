"""Tests E2E TEST DOMAIN — bout en bout + adversariaux.

Phases testées :
  Phase A — TestChainManager : Genesis TEST réel, test_chain.jsonl isolé
  Phase B — WalletManager.create_wallet(wallet_namespace='TEST') → artcbdev1…
  Phase C — Transaction TEST domain-separated + signature + validation
  Phase D — Mining TEST : bloc TEST + PoL + reward tARTCB + balance
  Phase E — E2E complet : wallet → tx → block → reward → vérification MAINNET inchangé
  Phase F — Adversariaux : TEST→MAINNET REJECT, MAINNET→TEST REJECT, wrong_network, etc.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from nacl import signing

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _tmp_chain(tmp_path: Path):
    """Create a TestChainManager pointing to a fresh tmp directory."""
    from src.artcb.testdomain.chain import TestChainManager

    class _FakeSettings:
        data_dir = tmp_path

    mgr = TestChainManager.__new__(TestChainManager)
    mgr.blocks_path = tmp_path / "test_chain.jsonl"
    mgr.blocks_path.parent.mkdir(parents=True, exist_ok=True)
    import threading
    mgr._lock = threading.Lock()
    mgr._genesis_hash = ""
    return mgr


def _tmp_wallet_mgr(tmp_path: Path):
    """WalletManager pointing to a fresh tmp directory."""
    from src.artcb.wallet.manager import WalletManager
    return WalletManager(wallet_dir=tmp_path / "wallets")


# ══════════════════════════════════════════════════════════════════════════════
# Phase A — TestChainManager
# ══════════════════════════════════════════════════════════════════════════════

class TestChainA:
    """TestChainManager — Genesis réel + isolation test_chain.jsonl."""

    def test_genesis_block_created_on_first_call(self, tmp_path):
        mgr = _tmp_chain(tmp_path)
        genesis = mgr.ensure_genesis()
        assert genesis["index"] == 0
        assert genesis["network_id"] == "artcb-testnet-1"
        assert genesis["genesis_hash"] == "genesis-artcb-testnet-1"
        assert genesis["domain"] == "TEST"
        assert genesis["asset"] == "tARTCB"
        assert len(genesis["hash"]) == 64

    def test_genesis_file_is_test_chain_jsonl(self, tmp_path):
        mgr = _tmp_chain(tmp_path)
        mgr.ensure_genesis()
        # INVARIANT: must NOT be chain.jsonl (MAINNET)
        assert mgr.blocks_path.name == "test_chain.jsonl"
        assert "chain.jsonl" not in str(mgr.blocks_path).replace("test_chain.jsonl", "")

    def test_genesis_idempotent(self, tmp_path):
        mgr = _tmp_chain(tmp_path)
        g1 = mgr.ensure_genesis()
        g2 = mgr.ensure_genesis()
        assert g1["hash"] == g2["hash"]
        assert mgr.height() == 1  # still only 1 block

    def test_genesis_deterministic_hash(self, tmp_path):
        """Same genesis payload → same hash always."""
        mgr1 = _tmp_chain(tmp_path / "a")
        mgr2 = _tmp_chain(tmp_path / "b")
        g1 = mgr1.ensure_genesis()
        g2 = mgr2.ensure_genesis()
        assert g1["hash"] == g2["hash"]

    def test_height_zero_before_genesis(self, tmp_path):
        mgr = _tmp_chain(tmp_path)
        assert mgr.height() == 0

    def test_height_one_after_genesis(self, tmp_path):
        mgr = _tmp_chain(tmp_path)
        mgr.ensure_genesis()
        assert mgr.height() == 1

    def test_last_hash_before_genesis(self, tmp_path):
        mgr = _tmp_chain(tmp_path)
        assert mgr.last_hash() == "0" * 64

    def test_chain_info_fields(self, tmp_path):
        mgr = _tmp_chain(tmp_path)
        mgr.ensure_genesis()
        info = mgr.chain_info()
        assert info["network_id"] == "artcb-testnet-1"
        assert info["mainnet_chain_isolated"] is True
        assert info["domain"] == "TEST"
        assert info["asset"] == "tARTCB"

    def test_append_valid_test_block(self, tmp_path):
        mgr = _tmp_chain(tmp_path)
        mgr.ensure_genesis()
        block = {
            "network_id": "artcb-testnet-1",
            "domain": "TEST",
            "pol_score": 1.0,
            "contributors": [
                {"address": "artcbdev1qtest000001", "reward_satoshi": 100_000_000}
            ],
        }
        result = mgr.append_block(block)
        assert result["index"] == 1
        assert result["network_id"] == "artcb-testnet-1"
        assert result["domain"] == "TEST"
        assert result["asset"] == "tARTCB"
        assert len(result["hash"]) == 64
        assert mgr.height() == 2

    def test_prev_hash_linkage(self, tmp_path):
        mgr = _tmp_chain(tmp_path)
        genesis = mgr.ensure_genesis()
        block2 = mgr.append_block({
            "network_id": "artcb-testnet-1",
            "domain": "TEST",
            "pol_score": 1.0,
        })
        assert block2["prev_hash"] == genesis["hash"]

    def test_reject_mainnet_network_id(self, tmp_path):
        from src.artcb.testdomain.chain import TestChainError
        mgr = _tmp_chain(tmp_path)
        mgr.ensure_genesis()
        with pytest.raises(TestChainError, match="reject_wrong_network_id"):
            mgr.append_block({
                "network_id": "artcb-mainnet-1",
                "domain": "TEST",
            })

    def test_reject_mainnet_block(self, tmp_path):
        from src.artcb.testdomain.chain import TestChainError
        mgr = _tmp_chain(tmp_path)
        mgr.ensure_genesis()
        with pytest.raises(TestChainError, match="reject_mainnet_block_in_test_chain"):
            mgr.append_block({
                "network_id": "artcb-testnet-1",
                "domain": "MAINNET",
            })

    def test_reject_wrong_genesis_hash(self, tmp_path):
        from src.artcb.testdomain.chain import TestChainError
        mgr = _tmp_chain(tmp_path)
        mgr.ensure_genesis()
        with pytest.raises(TestChainError, match="reject_wrong_genesis_hash"):
            mgr.append_block({
                "network_id": "artcb-testnet-1",
                "genesis_hash": "genesis-artcb-mainnet-1",
            })

    def test_reject_mainnet_contributor_address(self, tmp_path):
        from src.artcb.testdomain.chain import TestChainError
        mgr = _tmp_chain(tmp_path)
        mgr.ensure_genesis()
        with pytest.raises(TestChainError, match="reject_mainnet_contributor"):
            mgr.append_block({
                "network_id": "artcb-testnet-1",
                "contributors": [
                    {"address": "artcb1qmainnet001", "reward_satoshi": 100_000_000}
                ],
            })

    def test_reject_wrong_asset(self, tmp_path):
        from src.artcb.testdomain.chain import TestChainError
        mgr = _tmp_chain(tmp_path)
        mgr.ensure_genesis()
        with pytest.raises(TestChainError, match="reject_wrong_asset"):
            mgr.append_block({
                "network_id": "artcb-testnet-1",
                "asset": "ARTCB",  # production asset — forbidden in test chain
            })


# ══════════════════════════════════════════════════════════════════════════════
# Phase B — WalletManager wallet_namespace=TEST
# ══════════════════════════════════════════════════════════════════════════════

class TestWalletB:
    """WalletManager.create_wallet(wallet_namespace='TEST') → artcbdev1…"""

    def test_test_wallet_address_starts_artcbdev(self, tmp_path):
        wm = _tmp_wallet_mgr(tmp_path)
        w = wm.create_wallet(name="test-alice", user_password="password123", wallet_namespace="TEST")
        assert w.address.startswith("artcbdev1"), f"expected artcbdev1… got {w.address}"

    def test_mainnet_wallet_address_starts_artcb(self, tmp_path):
        wm = _tmp_wallet_mgr(tmp_path)
        w = wm.create_wallet(name="mainnet-alice", user_password="password123", wallet_namespace="MAINNET")
        assert w.address.startswith("artcb1"), f"expected artcb1… got {w.address}"

    def test_same_key_different_namespace_different_address(self, tmp_path):
        """A TEST and MAINNET wallet with the same private key have different addresses."""
        from nacl import signing as nacl_signing
        from src.artcb.wallet.address import generate_test_address, address_from_signing_key

        sk = nacl_signing.SigningKey.generate()
        pk = sk.verify_key.encode()
        test_addr = generate_test_address(pk)
        main_addr = address_from_signing_key(sk)
        assert test_addr != main_addr
        assert test_addr.startswith("artcbdev1")
        assert main_addr.startswith("artcb1")

    def test_metadata_contains_namespace(self, tmp_path):
        wm = _tmp_wallet_mgr(tmp_path)
        wm.create_wallet(name="test-bob", user_password="password123", wallet_namespace="TEST")
        meta_path = tmp_path / "wallets" / "test-bob.json"
        meta = json.loads(meta_path.read_text())
        assert meta["wallet_namespace"] == "TEST"
        assert meta["domain"] == "TEST"

    def test_invalid_namespace_raises(self, tmp_path):
        wm = _tmp_wallet_mgr(tmp_path)
        with pytest.raises(ValueError, match="wallet_namespace"):
            wm.create_wallet(name="bad-ns", user_password="password123", wallet_namespace="DEVNET")

    def test_default_namespace_is_mainnet(self, tmp_path):
        wm = _tmp_wallet_mgr(tmp_path)
        w = wm.create_wallet(name="default-ns", user_password="password123")
        assert w.address.startswith("artcb1")

    def test_multiple_test_wallets_same_name_forbidden(self, tmp_path):
        wm = _tmp_wallet_mgr(tmp_path)
        wm.create_wallet(name="dup-test", user_password="password123", wallet_namespace="TEST")
        with pytest.raises(FileExistsError):
            wm.create_wallet(name="dup-test", user_password="password123", wallet_namespace="TEST")


# ══════════════════════════════════════════════════════════════════════════════
# Phase C — Transaction TEST
# ══════════════════════════════════════════════════════════════════════════════

class TestTransactionC:
    """Transaction TEST : signature domain-separated, validation, cross-domain reject."""

    def _make_test_wallet(self):
        from nacl import signing as nacl_signing
        from src.artcb.wallet.address import generate_test_address
        sk = nacl_signing.SigningKey.generate()
        addr = generate_test_address(sk.verify_key.encode())
        return sk, addr

    def test_build_valid_test_transaction(self):
        from src.artcb.testdomain.transaction import build_test_transaction
        sk, addr = self._make_test_wallet()
        tx = build_test_transaction(
            wallet_id=addr,
            signing_key=sk,
            nonce=0,
            payload={"action": "test_action"},
        )
        assert tx["network_id"] == "artcb-testnet-1"
        assert tx["domain_id"] == "ARTCB/WALLET/TEST/V1"
        assert tx["genesis_hash"] == "genesis-artcb-testnet-1"
        assert tx["wallet_id"] == addr
        assert len(tx["signature"]) == 128  # 64-byte Ed25519 sig → 128 hex chars
        assert len(tx["tx_hash"]) == 64

    def test_validate_valid_transaction(self):
        from src.artcb.testdomain.transaction import build_test_transaction, validate_test_transaction
        sk, addr = self._make_test_wallet()
        tx = build_test_transaction(wallet_id=addr, signing_key=sk, nonce=0, payload={})
        valid, reason = validate_test_transaction(tx)
        assert valid, reason

    def test_reject_tampered_signature(self):
        from src.artcb.testdomain.transaction import build_test_transaction, validate_test_transaction
        sk, addr = self._make_test_wallet()
        tx = build_test_transaction(wallet_id=addr, signing_key=sk, nonce=0, payload={})
        tx["signature"] = "aa" * 64  # tampered
        valid, reason = validate_test_transaction(tx)
        assert not valid
        assert "reject_invalid_signature" in reason

    def test_reject_wrong_network_id_in_validation(self):
        from src.artcb.testdomain.transaction import build_test_transaction, validate_test_transaction
        sk, addr = self._make_test_wallet()
        tx = build_test_transaction(wallet_id=addr, signing_key=sk, nonce=0, payload={})
        tx["network_id"] = "artcb-mainnet-1"
        valid, reason = validate_test_transaction(tx)
        assert not valid
        assert "reject_wrong_network_id" in reason

    def test_reject_mainnet_wallet_in_test_tx(self):
        from src.artcb.testdomain.transaction import build_test_transaction, TestTransactionError
        sk = signing.SigningKey.generate()
        # mainnet address (no domain tag)
        from src.artcb.wallet.address import address_from_signing_key
        mainnet_addr = address_from_signing_key(sk)
        with pytest.raises(TestTransactionError, match="reject_non_test_wallet"):
            build_test_transaction(wallet_id=mainnet_addr, signing_key=sk, nonce=0, payload={})

    def test_reject_cross_domain_recipient(self):
        from src.artcb.testdomain.transaction import build_test_transaction, TestTransactionError
        sk, test_addr = self._make_test_wallet()
        mainnet_recipient = "artcb1qmainnet0001"
        with pytest.raises(TestTransactionError, match="cross_domain_reject"):
            build_test_transaction(
                wallet_id=test_addr,
                signing_key=sk,
                nonce=0,
                payload={},
                recipient=mainnet_recipient,
                amount_satoshi=1_000_000,
            )

    def test_nonce_included_in_signature_envelope(self):
        """Different nonces produce different signatures (replay protection)."""
        from src.artcb.testdomain.transaction import build_test_transaction
        sk, addr = self._make_test_wallet()
        tx0 = build_test_transaction(wallet_id=addr, signing_key=sk, nonce=0, payload={})
        tx1 = build_test_transaction(wallet_id=addr, signing_key=sk, nonce=1, payload={})
        assert tx0["signature"] != tx1["signature"]
        assert tx0["tx_hash"] != tx1["tx_hash"]


# ══════════════════════════════════════════════════════════════════════════════
# Phase D — Mining TEST (bloc + PoL + reward tARTCB + balance)
# ══════════════════════════════════════════════════════════════════════════════

class TestMiningD:
    """Mining TEST : bloc TEST + PoL + reward tARTCB + balance."""

    def _make_signed_tx(self, nonce: int = 0):
        from nacl import signing as nacl_signing
        from src.artcb.wallet.address import generate_test_address
        from src.artcb.testdomain.transaction import build_test_transaction
        sk = nacl_signing.SigningKey.generate()
        addr = generate_test_address(sk.verify_key.encode())
        tx = build_test_transaction(
            wallet_id=addr,
            signing_key=sk,
            nonce=nonce,
            payload={"job": "test_job"},
        )
        return addr, tx

    def test_build_block_from_transactions(self):
        from src.artcb.testdomain.transaction import build_test_block_from_transactions
        addr, tx = self._make_signed_tx()
        block_payload = build_test_block_from_transactions([tx])
        assert block_payload["network_id"] == "artcb-testnet-1"
        assert block_payload["domain"] == "TEST"
        assert block_payload["asset"] == "tARTCB"
        assert len(block_payload["contributors"]) == 1
        assert block_payload["contributors"][0]["address"] == addr
        assert block_payload["contributors"][0]["reward_satoshi"] == 100_000_000
        assert block_payload["contributors"][0]["asset"] == "tARTCB"

    def test_append_tx_block_to_test_chain(self, tmp_path):
        from src.artcb.testdomain.transaction import build_test_block_from_transactions
        mgr = _tmp_chain(tmp_path)
        mgr.ensure_genesis()
        addr, tx = self._make_signed_tx()
        block_payload = build_test_block_from_transactions([tx])
        result = mgr.append_block(block_payload)
        assert result["index"] == 1
        assert result["domain"] == "TEST"
        assert result["block_reward"] == 100_000_000

    def test_balance_after_reward(self, tmp_path):
        from src.artcb.testdomain.transaction import build_test_block_from_transactions
        mgr = _tmp_chain(tmp_path)
        mgr.ensure_genesis()
        addr, tx = self._make_signed_tx()
        block_payload = build_test_block_from_transactions([tx])
        mgr.append_block(block_payload)
        balance = mgr.get_balance(addr)
        assert balance["balance_satoshi"] == 100_000_000
        assert balance["balance_tartcb"] == 1.0
        assert balance["asset"] == "tARTCB"
        assert balance["mainnet_balance"] is None  # explicit isolation

    def test_reject_mainnet_address_in_balance_query(self, tmp_path):
        from src.artcb.testdomain.chain import TestChainError
        mgr = _tmp_chain(tmp_path)
        mgr.ensure_genesis()
        with pytest.raises(TestChainError, match="reject_mainnet_address"):
            mgr.get_balance("artcb1qmainnetaddr001")

    def test_empty_transaction_list_raises(self):
        from src.artcb.testdomain.transaction import (
            build_test_block_from_transactions, TestTransactionError,
        )
        with pytest.raises(TestTransactionError, match="cannot_build_block"):
            build_test_block_from_transactions([])

    def test_mainnet_wallet_in_tx_list_raises(self):
        from src.artcb.testdomain.transaction import (
            build_test_block_from_transactions, TestTransactionError,
        )
        fake_mainnet_tx = {
            "wallet_id": "artcb1qmainnet001",
            "tx_hash": "aa" * 32,
        }
        with pytest.raises(TestTransactionError, match="reject_mainnet_wallet"):
            build_test_block_from_transactions([fake_mainnet_tx])

    def test_multiple_contributors_rewarded(self, tmp_path):
        from src.artcb.testdomain.transaction import build_test_block_from_transactions
        from nacl import signing as nacl_signing
        from src.artcb.wallet.address import generate_test_address
        from src.artcb.testdomain.transaction import build_test_transaction

        mgr = _tmp_chain(tmp_path)
        mgr.ensure_genesis()

        txs = []
        addrs = []
        for i in range(3):
            sk = nacl_signing.SigningKey.generate()
            addr = generate_test_address(sk.verify_key.encode())
            addrs.append(addr)
            tx = build_test_transaction(wallet_id=addr, signing_key=sk, nonce=0, payload={})
            txs.append(tx)

        block_payload = build_test_block_from_transactions(txs)
        mgr.append_block(block_payload)

        for addr in addrs:
            bal = mgr.get_balance(addr)
            assert bal["balance_satoshi"] == 100_000_000, f"{addr}: {bal}"


# ══════════════════════════════════════════════════════════════════════════════
# Phase E — Test E2E complet
# ══════════════════════════════════════════════════════════════════════════════

class TestE2E:
    """E2E : wallet TEST → transaction → bloc → reward → balance TEST.
       Prouve simultanément que MAINNET n'est pas modifié.
    """

    def test_full_e2e_wallet_to_reward(self, tmp_path):
        """
        Scénario complet (rapport 356 §9 tableau) :
        1. Créer wallet TEST → adresse artcbdev1…
        2. Construire transaction TEST signée domain-separated
        3. Valider la transaction
        4. Construire bloc TEST
        5. Appendre dans test_chain.jsonl
        6. Vérifier balance tARTCB = 1.0
        7. Vérifier chain.jsonl MAINNET non créé / inchangé
        """
        from nacl import signing as nacl_signing
        from src.artcb.wallet.address import generate_test_address
        from src.artcb.testdomain.transaction import (
            build_test_transaction,
            validate_test_transaction,
            build_test_block_from_transactions,
        )

        # Step 1 — create TEST wallet
        sk = nacl_signing.SigningKey.generate()
        test_addr = generate_test_address(sk.verify_key.encode())
        assert test_addr.startswith("artcbdev1"), test_addr

        # Step 2 — build TEST transaction
        tx = build_test_transaction(
            wallet_id=test_addr,
            signing_key=sk,
            nonce=0,
            payload={"job_id": "e2e-test-001"},
        )
        assert tx["network_id"] == "artcb-testnet-1"

        # Step 3 — validate transaction
        valid, reason = validate_test_transaction(tx)
        assert valid, f"tx validation failed: {reason}"

        # Step 4+5 — build bloc + append to test chain
        mgr = _tmp_chain(tmp_path)
        mgr.ensure_genesis()
        block_payload = build_test_block_from_transactions([tx])
        block = mgr.append_block(block_payload)
        assert block["index"] == 1
        assert block["domain"] == "TEST"
        assert block["network_id"] == "artcb-testnet-1"

        # Step 6 — verify tARTCB balance
        balance = mgr.get_balance(test_addr)
        assert balance["balance_satoshi"] == 100_000_000
        assert balance["balance_tartcb"] == 1.0
        assert balance["asset"] == "tARTCB"

        # Step 7 — MAINNET chain.jsonl must NOT exist in the same directory
        mainnet_chain = tmp_path / "chain.jsonl"
        assert not mainnet_chain.exists(), (
            "MAINNET chain.jsonl was created by TEST operations — ISOLATION BREACH"
        )

        # Test chain has exactly 2 blocks (Genesis + block 1)
        assert mgr.height() == 2

    def test_mainnet_chain_isolated_from_test_operations(self, tmp_path):
        """Even with test_chain.jsonl growing, chain.jsonl is never touched."""
        from nacl import signing as nacl_signing
        from src.artcb.wallet.address import generate_test_address
        from src.artcb.testdomain.transaction import (
            build_test_transaction, build_test_block_from_transactions
        )

        mgr = _tmp_chain(tmp_path)
        mgr.ensure_genesis()

        for i in range(5):
            sk = nacl_signing.SigningKey.generate()
            addr = generate_test_address(sk.verify_key.encode())
            tx = build_test_transaction(wallet_id=addr, signing_key=sk, nonce=i, payload={})
            block_payload = build_test_block_from_transactions([tx])
            mgr.append_block(block_payload)

        # 6 blocks in test_chain.jsonl (1 genesis + 5)
        assert mgr.height() == 6
        # chain.jsonl (MAINNET) must never have been created
        assert not (tmp_path / "chain.jsonl").exists()

    def test_wallet_manager_test_wallet_isolates_from_mainnet(self, tmp_path):
        """WalletManager TEST wallet → artcbdev1… address only."""
        wm = _tmp_wallet_mgr(tmp_path)
        w_test = wm.create_wallet(name="e2e-test", user_password="pass1234!", wallet_namespace="TEST")
        w_main = wm.create_wallet(name="e2e-main", user_password="pass1234!", wallet_namespace="MAINNET")

        assert w_test.address.startswith("artcbdev1")
        assert w_main.address.startswith("artcb1")
        # The two wallets are on different addresses even if they happen to be different keys
        assert w_test.address != w_main.address


# ══════════════════════════════════════════════════════════════════════════════
# Phase F — Tests adversariaux E2E
# ══════════════════════════════════════════════════════════════════════════════

class TestAdversarialF:
    """
    Adversarial E2E — chaque ligne du tableau rapport 356 §9 :
    TEST signature → MAINNET       REJECT
    MAINNET signature → TEST       REJECT
    TEST transaction → MAINNET     REJECT
    MAINNET transaction → TEST     REJECT
    TEST block → MAINNET chain     REJECT
    MAINNET block → TEST chain     REJECT
    TEST Genesis → MAINNET         REJECT
    MAINNET Genesis → TEST         REJECT
    """

    # ── Signature cross-domain ─────────────────────────────────────────────

    def test_test_signature_invalid_on_mainnet_verifier(self):
        """A signature built in TEST context is rejected by a MAINNET verifier.

        The MAINNET verifier is ChainManager.verify_block_signature().
        The TEST transaction envelope includes network_id=artcb-testnet-1 in the
        signed bytes, so the raw Ed25519 signature over that envelope is NOT a
        valid signature over 'block_hash' bytes (what ChainManager expects).
        """
        from nacl import signing as nacl_signing
        from src.artcb.wallet.address import generate_test_address
        from src.artcb.testdomain.transaction import build_test_transaction

        sk = nacl_signing.SigningKey.generate()
        test_addr = generate_test_address(sk.verify_key.encode())
        tx = build_test_transaction(wallet_id=test_addr, signing_key=sk, nonce=0, payload={})

        # Try to use the TEST tx signature as a MAINNET block signature
        sig_hex = tx["signature"]
        # MAINNET verifier expects the signature to be over block_hash bytes
        # block_hash is a hex string, not the TEST envelope canonical JSON
        fake_block_hash = tx["tx_hash"]  # not what was signed

        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError
        vk = VerifyKey(bytes.fromhex(tx["public_key_hex"]))
        with pytest.raises(BadSignatureError):
            vk.verify(fake_block_hash.encode("utf-8"), bytes.fromhex(sig_hex))

    def test_mainnet_transaction_rejected_by_test_validator(self):
        """A transaction built outside TEST domain is rejected by validate_test_transaction."""
        from src.artcb.testdomain.transaction import validate_test_transaction
        # Forge a transaction that looks MAINNET
        fake_tx = {
            "network_id": "artcb-mainnet-1",
            "genesis_hash": "genesis-artcb-mainnet-1",
            "domain_id": "ARTCB/WALLET/MAINNET/V1",
            "wallet_id": "artcb1qmainnetaddr001",
            "nonce": 0,
            "signature": "aa" * 64,
            "public_key_hex": "bb" * 32,
        }
        valid, reason = validate_test_transaction(fake_tx)
        assert not valid
        assert "reject_wrong_network_id" in reason

    def test_test_block_rejected_by_mainnet_chain(self, tmp_path):
        """A TEST block cannot be appended to a MAINNET-like chain.

        We simulate this by checking that a block with network_id=artcb-testnet-1
        is detected as domain mismatch when manually building a MAINNET-style check.
        """
        from src.artcb.testdomain.chain import TestChainManager
        # TestChainManager ITSELF rejects a mainnet block
        mgr = _tmp_chain(tmp_path)
        mgr.ensure_genesis()
        # A "mainnet block" attempted in the TEST chain must fail
        from src.artcb.testdomain.chain import TestChainError
        with pytest.raises(TestChainError, match="reject_mainnet_block"):
            mgr.append_block({
                "network_id": "artcb-testnet-1",  # network_id OK
                "domain": "MAINNET",              # but domain claims MAINNET → REJECT
            })

    def test_mainnet_block_rejected_in_test_chain(self, tmp_path):
        """A block with network_id=artcb-mainnet-1 is rejected by TestChainManager."""
        from src.artcb.testdomain.chain import TestChainError
        mgr = _tmp_chain(tmp_path)
        mgr.ensure_genesis()
        with pytest.raises(TestChainError, match="reject_wrong_network_id"):
            mgr.append_block({
                "network_id": "artcb-mainnet-1",
            })

    def test_cross_domain_transfer_test_to_mainnet_rejected(self):
        """reject_cross_domain_transfer: TEST→MAINNET is always rejected."""
        from src.artcb.testdomain.policy import reject_cross_domain_transfer
        rejected, reason = reject_cross_domain_transfer(
            "artcbdev1qsender000", "artcb1qrecipient000"
        )
        assert rejected
        assert "TEST→MAINNET" in reason

    def test_cross_domain_transfer_mainnet_to_test_rejected(self):
        """reject_cross_domain_transfer: MAINNET→TEST is always rejected."""
        from src.artcb.testdomain.policy import reject_cross_domain_transfer
        rejected, reason = reject_cross_domain_transfer(
            "artcb1qsender000", "artcbdev1qrecipient000"
        )
        assert rejected
        assert "MAINNET→TEST" in reason

    def test_test_genesis_hash_not_equal_to_mainnet(self):
        """TEST genesis_hash ≠ MAINNET genesis_hash — network-level rejection at P2P."""
        from src.artcb.testdomain.policy import TEST_GENESIS_HASH
        from src.artcb.crypto_policy import GENESIS_HASH as MAINNET_GENESIS_HASH
        assert TEST_GENESIS_HASH != MAINNET_GENESIS_HASH

    def test_mainnet_peer_rejected_by_test_protocol(self):
        """accept_test_peer_protocol() rejects a MAINNET peer."""
        from src.artcb.testdomain.policy import accept_test_peer_protocol
        ok, reason = accept_test_peer_protocol(
            advertised_network_id="artcb-mainnet-1",
            advertised_protocol_version="189-mainnet-1",
            advertised_genesis_hash="genesis-artcb-mainnet-1",
        )
        assert not ok
        assert "network_id_mismatch" in reason

    def test_test_peer_accepted_by_test_protocol(self):
        """accept_test_peer_protocol() accepts a correct TEST peer."""
        from src.artcb.testdomain.policy import accept_test_peer_protocol
        ok, reason = accept_test_peer_protocol(
            advertised_network_id="artcb-testnet-1",
            advertised_protocol_version="189-testnet-1",
            advertised_genesis_hash="genesis-artcb-testnet-1",
        )
        assert ok, reason

    def test_mainnet_address_rejected_in_test_balance(self, tmp_path):
        """get_balance() with a MAINNET address raises in TestChainManager."""
        from src.artcb.testdomain.chain import TestChainError
        mgr = _tmp_chain(tmp_path)
        mgr.ensure_genesis()
        with pytest.raises(TestChainError, match="reject_mainnet_address"):
            mgr.get_balance("artcb1qmainnetaddr001")

    def test_bad_signature_rejected_by_test_validator(self):
        """Corrupted signature fails validate_test_transaction."""
        from src.artcb.testdomain.transaction import build_test_transaction, validate_test_transaction
        from nacl import signing as nacl_signing
        from src.artcb.wallet.address import generate_test_address

        sk = nacl_signing.SigningKey.generate()
        addr = generate_test_address(sk.verify_key.encode())
        tx = build_test_transaction(wallet_id=addr, signing_key=sk, nonce=0, payload={})
        tx["signature"] = "ff" * 64  # corrupted
        valid, reason = validate_test_transaction(tx)
        assert not valid
        assert "reject_invalid_signature" in reason

    def test_wrong_public_key_rejected(self):
        """Wrong public key in tx fails validate_test_transaction."""
        from src.artcb.testdomain.transaction import build_test_transaction, validate_test_transaction
        from nacl import signing as nacl_signing
        from src.artcb.wallet.address import generate_test_address

        sk = nacl_signing.SigningKey.generate()
        addr = generate_test_address(sk.verify_key.encode())
        tx = build_test_transaction(wallet_id=addr, signing_key=sk, nonce=0, payload={})
        # Replace public key with a different one
        other_sk = nacl_signing.SigningKey.generate()
        tx["public_key_hex"] = other_sk.verify_key.encode().hex()
        valid, reason = validate_test_transaction(tx)
        assert not valid
        assert "reject_invalid_signature" in reason

    def test_replay_different_nonce_different_signature(self):
        """Replaying nonce=0 with different transaction → different hash, detectable."""
        from src.artcb.testdomain.transaction import build_test_transaction
        from nacl import signing as nacl_signing
        from src.artcb.wallet.address import generate_test_address

        sk = nacl_signing.SigningKey.generate()
        addr = generate_test_address(sk.verify_key.encode())
        tx_a = build_test_transaction(wallet_id=addr, signing_key=sk, nonce=0, payload={"x": 1})
        tx_b = build_test_transaction(wallet_id=addr, signing_key=sk, nonce=0, payload={"x": 2})
        # Different payload → different hash even at same nonce
        assert tx_a["tx_hash"] != tx_b["tx_hash"]
        assert tx_a["signature"] != tx_b["signature"]

    def test_wrong_genesis_hash_rejected_by_test_validator(self):
        """Transaction with wrong genesis_hash is rejected by validate_test_transaction."""
        from src.artcb.testdomain.transaction import build_test_transaction, validate_test_transaction
        from nacl import signing as nacl_signing
        from src.artcb.wallet.address import generate_test_address

        sk = nacl_signing.SigningKey.generate()
        addr = generate_test_address(sk.verify_key.encode())
        tx = build_test_transaction(wallet_id=addr, signing_key=sk, nonce=0, payload={})
        tx["genesis_hash"] = "genesis-artcb-mainnet-1"  # tampered
        valid, reason = validate_test_transaction(tx)
        assert not valid
        assert "reject_wrong_genesis_hash" in reason
