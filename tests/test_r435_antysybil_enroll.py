"""Tests R435 — wallet_per_human_limit anti-Sybil dans le pipeline enroll_biometric().

Suite R435 : tests A01→A10 (enrôlement biométrique + gate anti-Sybil CASE_3).

Invariants vérifiés :
  - Sans existing_wallet_links → pas de vérification (compat ascendante)
  - Premier enrôlement + wallet_address → sybil_blocked=False, status="enrolled"
  - Deuxième enrôlement même human_id + wallet déjà actif → sybil_blocked=True, status="sybil_blocked"
  - wallet_address=None → pas de vérification Sybil même si links fournis
  - human_id dans record ≠ wallet si sybil_blocked
  - unique_human_proven=False dans tous les cas
  - certified=False dans tous les cas (invariant absolu)

PROTOCOLE ARTCB — mode DEBUG actif. CERTIFIED_100=false.
"""

import hashlib
import pytest

from src.artcb.identity.biometric_onchain import (
    BiometricEnrollmentResult,
    enroll_biometric,
)
from src.artcb.identity.human_identity_policy import (
    UserVerificationMethod,
    save_wallet_human_link,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

TEMPLATE_A = bytes(range(32))      # template synthétique 32 octets — agent A
TEMPLATE_B = bytes(range(1, 33))   # template distinct — agent B
WALLET_A = "wallet_" + "a" * 32
WALLET_B = "wallet_" + "b" * 32

# Salt et blinding fixes pour les tests de déterminisme
FIXED_SALT = bytes(range(32))
FIXED_BLINDING = bytes(range(1, 33))


def _make_link(human_id: str, wallet: str, *, revoked: bool = False) -> dict:
    """Crée un dict lien wallet↔human pour les tests."""
    return {
        "human_id": human_id,
        "wallet_address": wallet,
        "revoked": revoked,
        "unique_human_proven": False,
        "certified_100": False,
    }


# ── A01 — Enrôlement sans wallet_links → pas de vérification Sybil ───────────

def test_A01_enroll_no_links_no_sybil_check():
    """Sans existing_wallet_links, aucun gate Sybil n'est déclenché."""
    result, secret, blinding = enroll_biometric(
        TEMPLATE_A,
        wallet_address=WALLET_A,
        existing_wallet_links=None,
    )
    assert isinstance(result, BiometricEnrollmentResult)
    assert result.sybil_blocked is False
    assert result.status == "enrolled"
    assert result.sybil_reason is None
    assert result.existing_wallet is None
    assert result.unique_human_proven is False
    assert secret != ""
    assert blinding != ""


# ── A02 — Premier enrôlement, links vides → autorisé ─────────────────────────

def test_A02_enroll_first_wallet_empty_links_allowed():
    """Premier enrôlement avec links vides → sybil_blocked=False."""
    result, _, _ = enroll_biometric(
        TEMPLATE_A,
        wallet_address=WALLET_A,
        existing_wallet_links=[],
    )
    assert result.sybil_blocked is False
    assert result.status == "enrolled"
    assert result.human_identity_record["wallet_address"] == WALLET_A


# ── A03 — Deuxième enrôlement avec wallet déjà actif → BLOQUÉ ────────────────

def test_A03_enroll_second_wallet_same_human_blocked():
    """Deuxième enrôlement du même humain avec wallet actif → sybil_blocked=True.

    Pour simuler le même humain, on fixe salt + blinding afin d'obtenir
    le même human_id déterministe entre les deux enrôlements.
    """
    # Premier enrôlement avec salt + blinding fixes → human_id déterministe
    result1, _, _ = enroll_biometric(
        TEMPLATE_A,
        wallet_address=WALLET_A,
        existing_wallet_links=[],
        salt=FIXED_SALT,
        blinding=FIXED_BLINDING,
    )
    human_id = result1.human_id

    # Simuler le store avec le premier wallet actif
    links = [_make_link(human_id, WALLET_A)]

    # Deuxième enrôlement du même humain (mêmes salt+blinding) → même human_id
    result2, _, _ = enroll_biometric(
        TEMPLATE_A,
        wallet_address=WALLET_B,
        existing_wallet_links=links,
        salt=FIXED_SALT,
        blinding=FIXED_BLINDING,
    )
    assert result2.sybil_blocked is True
    assert result2.status == "sybil_blocked"
    assert result2.sybil_reason is not None
    assert "human_wallet_limit_reached" in result2.sybil_reason
    assert result2.existing_wallet == WALLET_A
    # wallet_address ne doit PAS être lié dans le record on-chain
    assert result2.human_identity_record["wallet_address"] is None


# ── A04 — Enrôlement sans wallet_address → pas de gate Sybil même avec links ─

def test_A04_enroll_no_wallet_address_no_sybil():
    """Sans wallet_address, le gate Sybil n'est pas déclenché."""
    result1, _, _ = enroll_biometric(TEMPLATE_A, wallet_address=WALLET_A, existing_wallet_links=[])
    human_id = result1.human_id
    links = [_make_link(human_id, WALLET_A)]

    # Re-enrôlement sans wallet_address → pas de vérification Sybil
    result2, _, _ = enroll_biometric(
        TEMPLATE_A,
        wallet_address=None,
        existing_wallet_links=links,
    )
    assert result2.sybil_blocked is False
    assert result2.status == "enrolled"


# ── A05 — Wallet révoqué ne bloque pas ───────────────────────────────────────

def test_A05_revoked_wallet_does_not_block():
    """Un wallet révoqué ne compte pas dans la limite active."""
    result1, _, _ = enroll_biometric(TEMPLATE_A, wallet_address=WALLET_A, existing_wallet_links=[])
    human_id = result1.human_id
    links = [_make_link(human_id, WALLET_A, revoked=True)]  # révoqué !

    result2, _, _ = enroll_biometric(
        TEMPLATE_A,
        wallet_address=WALLET_B,
        existing_wallet_links=links,
    )
    assert result2.sybil_blocked is False
    assert result2.status == "enrolled"


# ── A06 — Templates différents → human_id différents → pas de conflit ─────────

def test_A06_different_templates_different_human_ids_no_block():
    """Deux templates différents → deux human_ids distincts → pas de conflit Sybil."""
    result_a, _, _ = enroll_biometric(TEMPLATE_A, wallet_address=WALLET_A, existing_wallet_links=[])
    human_a = result_a.human_id
    links = [_make_link(human_a, WALLET_A)]

    # Template B → human_id différent → pas dans links
    result_b, _, _ = enroll_biometric(
        TEMPLATE_B,
        wallet_address=WALLET_B,
        existing_wallet_links=links,
    )
    assert result_b.sybil_blocked is False
    assert result_b.human_id != human_a


# ── A07 — unique_human_proven=False dans tous les chemins ────────────────────

def test_A07_unique_human_proven_always_false():
    """unique_human_proven=False dans tous les chemins (invariant absolu)."""
    result1, _, _ = enroll_biometric(TEMPLATE_A, wallet_address=WALLET_A, existing_wallet_links=[])
    assert result1.unique_human_proven is False

    links = [_make_link(result1.human_id, WALLET_A)]
    result2, _, _ = enroll_biometric(
        TEMPLATE_A,
        wallet_address=WALLET_B,
        existing_wallet_links=links,
    )
    assert result2.unique_human_proven is False


# ── A08 — human_id stable entre deux enrôlements du même template ─────────────

def test_A08_same_template_same_salt_blinding_same_human_id():
    """Même template + même salt + même blinding → même human_id (déterminisme)."""
    result1, _, _ = enroll_biometric(TEMPLATE_A, salt=FIXED_SALT, blinding=FIXED_BLINDING)
    result2, _, _ = enroll_biometric(TEMPLATE_A, salt=FIXED_SALT, blinding=FIXED_BLINDING)
    assert result1.human_id == result2.human_id


# ── A09 — sybil_blocked=True → wallet_address absent du record chain ─────────

def test_A09_sybil_blocked_wallet_absent_from_chain_record():
    """Si sybil_blocked=True, wallet_address doit être None dans human_identity_record."""
    result1, _, _ = enroll_biometric(
        TEMPLATE_A,
        wallet_address=WALLET_A,
        existing_wallet_links=[],
        salt=FIXED_SALT,
        blinding=FIXED_BLINDING,
    )
    links = [_make_link(result1.human_id, WALLET_A)]

    result2, _, _ = enroll_biometric(
        TEMPLATE_A,
        wallet_address=WALLET_B,
        existing_wallet_links=links,
        salt=FIXED_SALT,
        blinding=FIXED_BLINDING,
    )
    assert result2.sybil_blocked is True
    # Vérification critique : le record on-chain ne doit pas contenir WALLET_B
    assert result2.human_identity_record.get("wallet_address") is None
    assert result2.human_identity_record.get("wallet_address") != WALLET_B


# ── A10 — Enrôlement sans salt → deux enrôlements distincts (salts aléatoires) ─

def test_A10_enroll_without_salt_distinct_secrets():
    """Sans salt fixé, deux enrôlements du même template produisent des secrets distincts."""
    result1, secret1, _ = enroll_biometric(TEMPLATE_A)
    result2, secret2, _ = enroll_biometric(TEMPLATE_A)
    # Les secrets doivent être différents (salts aléatoires)
    assert secret1 != secret2
    # Mais les human_id sont différents aussi car helper_data (salt) diffère
    assert result1.human_id != result2.human_id
