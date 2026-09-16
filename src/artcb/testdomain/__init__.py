"""ARTCB TEST DOMAIN — cryptographically separated test namespace.

Implements the architecture specified in rapports/353–356:
  - Cryptographic domain separation (MAINNET ≠ TESTNET address hashes)
  - Same validation engine, synthetic proofs
  - TEST transactions cannot replay on MAINNET (domain-bound signatures)
  - Isolated economics (TEST assets ≠ MAINNET assets)
  - Full wallet state machine (KEY_ONLY → ACTIVE + adversarial states)
  - TestChainManager: isolated test_chain.jsonl (rapport 356 §12)
  - Transaction domain-separated (rapport 355 §5–§7)

References: D-017 (artcb-devnet), rapports 353/354/355/356.
"""

from src.artcb.testdomain.policy import TEST_DOMAIN_TAG, TEST_GENESIS_HASH, TEST_NETWORK_ID, TEST_PROTOCOL_VERSION
from src.artcb.testdomain.wallet_states import WalletState
from src.artcb.testdomain.chain import TestChainManager, TestChainError
from src.artcb.testdomain.transaction import (
    TestTransactionError,
    build_test_transaction,
    validate_test_transaction,
    build_test_block_from_transactions,
)

__all__ = [
    "TEST_DOMAIN_TAG",
    "TEST_NETWORK_ID",
    "TEST_PROTOCOL_VERSION",
    "TEST_GENESIS_HASH",
    "WalletState",
    "TestChainManager",
    "TestChainError",
    "TestTransactionError",
    "build_test_transaction",
    "validate_test_transaction",
    "build_test_block_from_transactions",
]
