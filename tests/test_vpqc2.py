"""V-PQC-2 — Tests séparation domaine pour adresses hybrides PQC (artcb2 / artcb2t).

Contexte (rapport 357 §5 backlog, V-PQC-2) :
  Avant V-PQC-2 :
    hybrid_address_v2(ed25519_pk, pqc_pk) → SHA256(ed25519_pk || pqc_pk)
    Même calcul MAINNET et TEST → même adresse artcb2… → cross-domain replay possible

  Après V-PQC-2 :
    MAINNET : hybrid_address_v2()           → artcb2…  (legacy, inchangé)
    TEST    : generate_test_hybrid_address_v2() → artcb2t… (domain tag dans le hash)
    H(MAINNET_TAG || ed25519_pk || pqc_pk) ≠ H(TEST_TAG || ed25519_pk || pqc_pk)

Ces tests prouvent :
  1. Les fonctions de dérivation domain-séparées fonctionnent correctement
  2. MAINNET artcb2 ≠ TEST artcb2t pour la même paire de clés
  3. WalletManager utilise artcb2t pour wallet_namespace=TEST
  4. is_test_address() reconnaît artcb2t
  5. cross-domain_reject() fonctionne avec artcb2t comme sender/recipient
"""

from __future__ import annotations

import pytest
from nacl import signing


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_keys():
    """Retourne (ed25519_sk, ed25519_pk_bytes, pqc_pk_bytes) reproductibles."""
    from src.artcb.crypto.pqc import generate_keypair, pqc_enabled
    sk = signing.SigningKey.generate()
    ed_pk = sk.verify_key.encode()
    if not pqc_enabled():
        pytest.skip("PQC non disponible dans cet environnement")
    _, pqc_pk = generate_keypair()
    return sk, ed_pk, pqc_pk


# ─────────────────────────────────────────────────────────────────────────────
# 1 — Fonctions de dérivation
# ─────────────────────────────────────────────────────────────────────────────

class TestVPQC2Derivation:
    """Tests des primitives hybrid_address_v2_domain_separated."""

    def test_mainnet_hybrid_address_starts_artcb2(self):
        _, ed_pk, pqc_pk = _make_keys()
        from src.artcb.wallet.address import generate_mainnet_hybrid_address_v2
        addr = generate_mainnet_hybrid_address_v2(ed_pk, pqc_pk)
        assert addr.startswith("artcb2"), f"MAINNET hybrid doit commencer par artcb2, obtenu: {addr}"

    def test_test_hybrid_address_starts_artcb2t(self):
        _, ed_pk, pqc_pk = _make_keys()
        from src.artcb.wallet.address import generate_test_hybrid_address_v2
        addr = generate_test_hybrid_address_v2(ed_pk, pqc_pk)
        assert addr.startswith("artcb2t"), f"TEST hybrid doit commencer par artcb2t, obtenu: {addr}"

    def test_same_keys_different_domain_different_address(self):
        """V-PQC-2 — même paire de clés → artcb2 ≠ artcb2t."""
        _, ed_pk, pqc_pk = _make_keys()
        from src.artcb.wallet.address import (
            generate_mainnet_hybrid_address_v2,
            generate_test_hybrid_address_v2,
        )
        main_addr = generate_mainnet_hybrid_address_v2(ed_pk, pqc_pk)
        test_addr = generate_test_hybrid_address_v2(ed_pk, pqc_pk)
        assert main_addr != test_addr, (
            f"V-PQC-2 : MAINNET artcb2 doit ≠ TEST artcb2t pour la même paire de clés\n"
            f"MAINNET: {main_addr}\nTEST:    {test_addr}"
        )

    def test_legacy_and_domain_separated_differ_for_mainnet(self):
        """hybrid_address_v2() legacy ≠ generate_mainnet_hybrid_address_v2() (domain tag ajouté)."""
        _, ed_pk, pqc_pk = _make_keys()
        from src.artcb.wallet.address import (
            hybrid_address_v2,
            generate_mainnet_hybrid_address_v2,
        )
        legacy = hybrid_address_v2(ed_pk, pqc_pk)
        new = generate_mainnet_hybrid_address_v2(ed_pk, pqc_pk)
        # Les deux commencent par artcb2 mais diffèrent (domain tag injecté)
        assert legacy.startswith("artcb2"), legacy
        assert new.startswith("artcb2"), new
        assert legacy != new, (
            "Le domaine tag MAINNET doit modifier le hash — legacy ≠ nouveau"
        )

    def test_domain_separated_deterministic(self):
        """Même entrées → même adresse (déterminisme)."""
        _, ed_pk, pqc_pk = _make_keys()
        from src.artcb.wallet.address import generate_test_hybrid_address_v2
        addr1 = generate_test_hybrid_address_v2(ed_pk, pqc_pk)
        addr2 = generate_test_hybrid_address_v2(ed_pk, pqc_pk)
        assert addr1 == addr2

    def test_empty_domain_tag_raises(self):
        _, ed_pk, pqc_pk = _make_keys()
        from src.artcb.wallet.address import hybrid_address_v2_domain_separated
        with pytest.raises(ValueError, match="domain_tag"):
            hybrid_address_v2_domain_separated(ed_pk, pqc_pk, domain_tag="")

    def test_wrong_ed25519_key_length_raises(self):
        _, _, pqc_pk = _make_keys()
        from src.artcb.wallet.address import generate_test_hybrid_address_v2
        with pytest.raises(ValueError, match="32 bytes"):
            generate_test_hybrid_address_v2(b"short", pqc_pk)

    def test_empty_pqc_key_raises(self):
        _, ed_pk, _ = _make_keys()
        from src.artcb.wallet.address import generate_test_hybrid_address_v2
        with pytest.raises(ValueError, match="PQC"):
            generate_test_hybrid_address_v2(ed_pk, b"")


# ─────────────────────────────────────────────────────────────────────────────
# 2 — Intégration WalletManager
# ─────────────────────────────────────────────────────────────────────────────

class TestVPQC2WalletManager:
    """WalletManager produit artcb2t pour TEST, artcb2 pour MAINNET."""

    def test_test_wallet_address_v2_starts_artcb2t(self, tmp_path):
        from src.artcb.wallet.manager import WalletManager
        wm = WalletManager(wallet_dir=tmp_path / "wallets")
        w = wm.create_wallet(name="vpqc2-test", user_password="password123!", wallet_namespace="TEST")
        if w.address_v2 is None:
            pytest.skip("PQC non disponible — address_v2 absent")
        assert w.address_v2.startswith("artcb2t"), (
            f"TEST wallet address_v2 doit commencer par artcb2t, obtenu: {w.address_v2}"
        )

    def test_mainnet_wallet_address_v2_starts_artcb2(self, tmp_path):
        from src.artcb.wallet.manager import WalletManager
        wm = WalletManager(wallet_dir=tmp_path / "wallets")
        w = wm.create_wallet(name="vpqc2-main", user_password="password123!", wallet_namespace="MAINNET")
        if w.address_v2 is None:
            pytest.skip("PQC non disponible — address_v2 absent")
        assert w.address_v2.startswith("artcb2"), (
            f"MAINNET wallet address_v2 doit commencer par artcb2, obtenu: {w.address_v2}"
        )

    def test_test_and_mainnet_address_v2_differ(self, tmp_path):
        """Même machine, mêmes algos PQC → artcb2t ≠ artcb2 (clés différentes de toute façon)."""
        from src.artcb.wallet.manager import WalletManager
        wm = WalletManager(wallet_dir=tmp_path / "wallets")
        w_test = wm.create_wallet(name="vpqc2-cmp-test", user_password="password123!", wallet_namespace="TEST")
        w_main = wm.create_wallet(name="vpqc2-cmp-main", user_password="password123!", wallet_namespace="MAINNET")
        if w_test.address_v2 is None or w_main.address_v2 is None:
            pytest.skip("PQC non disponible")
        # Préfixes différents
        assert w_test.address_v2.startswith("artcb2t"), w_test.address_v2
        assert w_main.address_v2.startswith("artcb2"), w_main.address_v2
        # Adresses différentes
        assert w_test.address_v2 != w_main.address_v2

    def test_metadata_contains_address_v2(self, tmp_path):
        """Le .json metadata du wallet contient address_v2 avec bon préfixe."""
        import json
        from src.artcb.wallet.manager import WalletManager
        wm = WalletManager(wallet_dir=tmp_path / "wallets")
        w = wm.create_wallet(name="vpqc2-meta", user_password="password123!", wallet_namespace="TEST")
        if w.address_v2 is None:
            pytest.skip("PQC non disponible")
        meta = json.loads((tmp_path / "wallets" / "vpqc2-meta.json").read_text())
        assert meta.get("address_v2", "").startswith("artcb2t"), meta


# ─────────────────────────────────────────────────────────────────────────────
# 3 — policy.py : is_test_address reconnaît artcb2t
# ─────────────────────────────────────────────────────────────────────────────

class TestVPQC2Policy:
    """is_test_address() et domain_of_address() gèrent artcb2t."""

    def test_artcb2t_is_test_address(self):
        from src.artcb.testdomain.policy import is_test_address
        assert is_test_address("artcb2tqtest000001") is True

    def test_artcbdev1_is_test_address(self):
        from src.artcb.testdomain.policy import is_test_address
        assert is_test_address("artcbdev1qtest000001") is True

    def test_artcb2_is_not_test_address(self):
        from src.artcb.testdomain.policy import is_test_address
        assert is_test_address("artcb2qmainnet000001") is False

    def test_artcb1_is_not_test_address(self):
        from src.artcb.testdomain.policy import is_test_address
        assert is_test_address("artcb1qmainnet000001") is False

    def test_domain_of_artcb2t_is_test(self):
        from src.artcb.testdomain.policy import domain_of_address
        assert domain_of_address("artcb2tqtest000001") == "TEST"

    def test_domain_of_artcb2_is_mainnet(self):
        from src.artcb.testdomain.policy import domain_of_address
        assert domain_of_address("artcb2qmainnet000001") == "MAINNET"

    def test_cross_domain_artcb2t_to_artcb2_rejected(self):
        """Transfer artcb2t (TEST hybrid) → artcb2 (MAINNET hybrid) = rejeté."""
        from src.artcb.testdomain.policy import reject_cross_domain_transfer
        rejected, reason = reject_cross_domain_transfer(
            "artcb2tqsender000001", "artcb2qrecipient000001"
        )
        assert rejected, f"TEST hybrid → MAINNET hybrid doit être rejeté, reason: {reason}"
        assert "TEST→MAINNET" in reason

    def test_cross_domain_artcb2_to_artcb2t_rejected(self):
        """Transfer artcb2 (MAINNET hybrid) → artcb2t (TEST hybrid) = rejeté."""
        from src.artcb.testdomain.policy import reject_cross_domain_transfer
        rejected, reason = reject_cross_domain_transfer(
            "artcb2qsender000001", "artcb2tqrecipient000001"
        )
        assert rejected, f"MAINNET hybrid → TEST hybrid doit être rejeté, reason: {reason}"
        assert "MAINNET→TEST" in reason

    def test_same_domain_artcb2t_to_artcb2t_allowed(self):
        from src.artcb.testdomain.policy import reject_cross_domain_transfer
        rejected, reason = reject_cross_domain_transfer(
            "artcb2tqsender000001", "artcb2tqrecipient000001"
        )
        assert not rejected, reason

    def test_same_domain_artcb2_to_artcb2_allowed(self):
        from src.artcb.testdomain.policy import reject_cross_domain_transfer
        rejected, reason = reject_cross_domain_transfer(
            "artcb2qsender000001", "artcb2qrecipient000001"
        )
        assert not rejected, reason
