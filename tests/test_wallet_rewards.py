"""Tests wallet + rewards system — TOKENOMICS §6-7."""

import json

import pytest
from nacl import signing

from artcb.chain.manager import ChainManager
from artcb.pol.scorer import PolScorer
from artcb.wallet.address import (
    address_from_signing_key,
    generate_address,
    verify_address,
)
from artcb.wallet.manager import WalletManager


class TestAddressGeneration:
    """Test ARTCB address generation (Bech32-like)."""

    def test_generate_address_from_pubkey(self):
        """Generate address from Ed25519 public key."""
        signing_key = signing.SigningKey.generate()
        pubkey_bytes = signing_key.verify_key.encode()

        address = generate_address(pubkey_bytes)

        assert address.startswith("artcb1")
        assert len(address) > 10
        assert verify_address(address)

    def test_generate_address_from_signing_key(self):
        """Generate address from SigningKey."""
        signing_key = signing.SigningKey.generate()
        address = address_from_signing_key(signing_key)

        assert address.startswith("artcb1")
        assert verify_address(address)

    def test_verify_address_valid(self):
        """Verify valid address."""
        signing_key = signing.SigningKey.generate()
        address = address_from_signing_key(signing_key)

        assert verify_address(address) is True

    def test_verify_address_invalid_prefix(self):
        """Reject address with wrong prefix."""
        assert verify_address("btc1qxyz") is False

    def test_verify_address_invalid_checksum(self):
        """Reject address with bad checksum."""
        assert verify_address("artcb1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq") is False

    def test_address_deterministic(self):
        """Same key generates same address."""
        key_bytes = b"\x00" * 32
        signing_key = signing.SigningKey(key_bytes)

        addr1 = address_from_signing_key(signing_key)
        addr2 = address_from_signing_key(signing_key)

        assert addr1 == addr2


class TestWalletManager:
    """Test wallet creation and management."""

    def test_create_wallet(self, tmp_path):
        """Create new wallet."""
        wallet_mgr = WalletManager(wallet_dir=tmp_path)
        wallet = wallet_mgr.create_wallet(name="test_wallet")

        assert wallet.address.startswith("artcb1")
        assert len(wallet.public_key_hex) == 64
        assert verify_address(wallet.address)

        # Check files created
        assert (tmp_path / "test_wallet.key").exists()
        assert (tmp_path / "test_wallet.json").exists()
        key_bytes = (tmp_path / "test_wallet.key").read_bytes()
        assert key_bytes.startswith(b"ARTCBENC1")
        assert len(key_bytes) > 32

    def test_create_wallet_duplicate_fails(self, tmp_path):
        """Cannot create duplicate wallet."""
        wallet_mgr = WalletManager(wallet_dir=tmp_path)
        wallet_mgr.create_wallet(name="test_wallet")

        with pytest.raises(FileExistsError):
            wallet_mgr.create_wallet(name="test_wallet")

    def test_load_wallet(self, tmp_path):
        """Load existing wallet."""
        wallet_mgr = WalletManager(wallet_dir=tmp_path)
        created = wallet_mgr.create_wallet(name="test_wallet")

        loaded = wallet_mgr.load_wallet(name="test_wallet")

        assert loaded.address == created.address
        assert loaded.public_key_hex == created.public_key_hex

    def test_load_wallet_not_found(self, tmp_path):
        """Loading non-existent wallet fails."""
        wallet_mgr = WalletManager(wallet_dir=tmp_path)

        with pytest.raises(FileNotFoundError):
            wallet_mgr.load_wallet(name="nonexistent")

    def test_list_wallets(self, tmp_path):
        """List all wallets."""
        wallet_mgr = WalletManager(wallet_dir=tmp_path)
        wallet_mgr.create_wallet(name="wallet1")
        wallet_mgr.create_wallet(name="wallet2")

        wallets = wallet_mgr.list_wallets()

        assert len(wallets) == 2
        addresses = [w["address"] for w in wallets]
        assert all(addr.startswith("artcb1") for addr in addresses)

    def test_wallet_sign_message(self, tmp_path):
        """Wallet can sign messages."""
        wallet_mgr = WalletManager(wallet_dir=tmp_path)
        wallet = wallet_mgr.create_wallet(name="test_wallet")

        message = b"test message"
        signature = wallet.sign(message)

        if wallet.is_hybrid:
            assert signature.startswith("hybrid:")
            assert len(signature) > 128
        else:
            assert len(signature) == 128  # 64 bytes hex


class TestBlockRewards:
    """Test block reward calculation and distribution."""

    def test_calculate_block_reward_genesis(self, tmp_path):
        """Genesis block reward = 50 ARTCB (D-024, R(H≤1M)=50, cap 21M)."""
        chain = ChainManager(blocks_path=tmp_path / "blocks.jsonl")

        reward = chain._calculate_block_reward(0)

        assert reward == 50 * 100_000_000  # 50 ARTCB in satoshi

    def test_calculate_block_reward_no_index_halving(self, tmp_path):
        """Index 210_000 no longer halves the reward (D-024 geopopulation)."""
        chain = ChainManager(blocks_path=tmp_path / "blocks.jsonl")

        assert chain._calculate_block_reward(0) == 50 * 100_000_000
        assert chain._calculate_block_reward(209_999) == 50 * 100_000_000
        assert chain._calculate_block_reward(210_000) == 50 * 100_000_000
        assert chain._calculate_block_reward(419_999) == 50 * 100_000_000
        assert chain._calculate_block_reward(420_000) == 50 * 100_000_000

    def test_calculate_block_reward_far_index_still_r_h(self, tmp_path):
        """A late index still pays R(H=0)=50 until the 21M cap is reached."""
        chain = ChainManager(blocks_path=tmp_path / "blocks.jsonl")

        reward = chain._calculate_block_reward(64 * 210_000)

        assert reward == 50 * 100_000_000

    def test_split_reward_collective(self):
        """Split reward proportionally (TOKENOMICS §6.2)."""
        block_reward = 50.0  # ARTCB
        contributor_scores = {
            "artcb1alice": 0.80,
            "artcb1bob": 0.70,
            "artcb1agent7": 0.50,
        }

        rewards = PolScorer.split_reward(block_reward, contributor_scores)

        # Check proportions
        total_score = 0.80 + 0.70 + 0.50  # 2.00
        assert rewards["artcb1alice"] == pytest.approx(block_reward * (0.80 / total_score))
        assert rewards["artcb1bob"] == pytest.approx(block_reward * (0.70 / total_score))
        assert rewards["artcb1agent7"] == pytest.approx(block_reward * (0.50 / total_score))

        # Check sum
        assert sum(rewards.values()) == pytest.approx(block_reward)

    def test_split_reward_single_contributor(self):
        """Single contributor gets full reward."""
        block_reward = 50.0
        contributor_scores = {"artcb1alice": 0.75}

        rewards = PolScorer.split_reward(block_reward, contributor_scores)

        assert rewards["artcb1alice"] == 50.0

    def test_split_reward_zero_scores(self):
        """Zero scores return zero rewards."""
        block_reward = 50.0
        contributor_scores = {"artcb1alice": 0.0, "artcb1bob": 0.0}

        rewards = PolScorer.split_reward(block_reward, contributor_scores)

        assert all(r == 0.0 for r in rewards.values())


class TestBlockWithRewards:
    """Test blockchain with rewards integration."""

    def test_append_block_with_contributors(self, tmp_path):
        """Append block with contributors and rewards."""
        chain = ChainManager(blocks_path=tmp_path / "blocks.jsonl")

        contributors = [
            {"address": "artcb1alice", "pol_score": 0.80, "signature": "sig1"},
            {"address": "artcb1bob", "pol_score": 0.70, "signature": "sig2"},
        ]

        block = chain.append_block(
            graph_id="g_test",
            graph_root="abc123",
            pol_score=0.75,
            contributors=contributors,
        )

        assert block.block_reward == 50 * 100_000_000  # Genesis reward
        assert len(block.contributors) == 2

        # Check rewards distributed
        alice_reward = block.contributors[0]["reward_satoshi"]
        bob_reward = block.contributors[1]["reward_satoshi"]

        assert alice_reward > bob_reward  # Alice has higher PoL
        assert alice_reward + bob_reward == block.block_reward

    def test_append_block_without_contributors(self, tmp_path):
        """Block without contributors has no rewards."""
        chain = ChainManager(blocks_path=tmp_path / "blocks.jsonl")

        block = chain.append_block(
            graph_id="g_test",
            graph_root="abc123",
            pol_score=0.75,
        )

        assert block.block_reward == 50 * 100_000_000
        assert len(block.contributors) == 0

    def test_block_json_includes_rewards(self, tmp_path):
        """Block JSON includes reward fields."""
        chain = ChainManager(blocks_path=tmp_path / "blocks.jsonl")

        contributors = [{"address": "artcb1alice", "pol_score": 0.80, "signature": "sig1"}]
        block = chain.append_block(
            graph_id="g_test",
            graph_root="abc123",
            pol_score=0.75,
            contributors=contributors,
        )

        json_line = block.to_json_line()
        data = json.loads(json_line)

        assert "block_reward" in data
        assert "contributors" in data
        assert data["block_reward"] == 50 * 100_000_000
        assert len(data["contributors"]) == 1


class TestWalletBalance:
    """Test balance calculation from blockchain."""

    def test_get_balance_empty_chain(self, tmp_path):
        """Balance is 0 for empty chain."""
        wallet_mgr = WalletManager(wallet_dir=tmp_path)
        wallet = wallet_mgr.create_wallet(name="test")

        blocks_path = tmp_path / "blocks.jsonl"
        balance = wallet_mgr.get_balance(wallet.address, blocks_path)

        assert balance["balance_satoshi"] == 0
        assert balance["balance_artcb"] == 0.0
        assert balance["block_count"] == 0

    def test_get_balance_single_block(self, tmp_path):
        """Balance from single block."""
        wallet_mgr = WalletManager(wallet_dir=tmp_path)
        wallet = wallet_mgr.create_wallet(name="test")

        chain = ChainManager(blocks_path=tmp_path / "blocks.jsonl")
        contributors = [{"address": wallet.address, "pol_score": 1.0, "signature": "sig"}]
        chain.append_block(
            graph_id="g_test",
            graph_root="abc123",
            pol_score=0.75,
            contributors=contributors,
        )

        balance = wallet_mgr.get_balance(wallet.address, chain.blocks_path)

        assert balance["balance_satoshi"] == 50 * 100_000_000
        assert balance["balance_artcb"] == 50.0
        assert balance["block_count"] == 1

    def test_get_balance_multiple_blocks(self, tmp_path):
        """Balance accumulates across blocks."""
        wallet_mgr = WalletManager(wallet_dir=tmp_path)
        wallet = wallet_mgr.create_wallet(name="test")

        # Disable security for fast tests (no 60s delay)
        chain = ChainManager(blocks_path=tmp_path / "blocks.jsonl", enable_security=False)

        # Block 1: Full reward
        contributors1 = [{"address": wallet.address, "pol_score": 1.0, "signature": "sig1"}]
        chain.append_block(
            graph_id="g_test1",
            graph_root="abc123",
            pol_score=0.75,
            contributors=contributors1,
        )

        # Block 2: Half reward (shared with another)
        contributors2 = [
            {"address": wallet.address, "pol_score": 0.5, "signature": "sig2"},
            {"address": "artcb1other", "pol_score": 0.5, "signature": "sig3"},
        ]
        chain.append_block(
            graph_id="g_test2",
            graph_root="def456",
            pol_score=0.80,
            contributors=contributors2,
        )

        balance = wallet_mgr.get_balance(wallet.address, chain.blocks_path)

        # 50 ARTCB (block 1) + 25 ARTCB (block 2, 50% share) = 75 ARTCB
        assert balance["balance_artcb"] == 75.0
        assert balance["block_count"] == 2

    def test_get_balance_rewards_history(self, tmp_path):
        """Balance includes rewards history."""
        wallet_mgr = WalletManager(wallet_dir=tmp_path)
        wallet = wallet_mgr.create_wallet(name="test")

        chain = ChainManager(blocks_path=tmp_path / "blocks.jsonl")
        contributors = [{"address": wallet.address, "pol_score": 0.80, "signature": "sig"}]
        chain.append_block(
            graph_id="g_test",
            graph_root="abc123",
            pol_score=0.75,
            contributors=contributors,
        )

        balance = wallet_mgr.get_balance(wallet.address, chain.blocks_path)

        assert len(balance["rewards"]) == 1
        reward = balance["rewards"][0]
        assert reward["block_index"] == 0
        assert reward["reward_satoshi"] == 50 * 100_000_000
        assert reward["pol_score"] == 0.80

