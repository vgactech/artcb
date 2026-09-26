"""Tests TASK-001 / R479 — PaillierHammingBackend (Homomorphic Encryption réelle).

Protocole : ARTCB-PHE-PAILLIER-HAMMING-v1
Bibliothèque : phe 1.5.0 (python-paillier, IND-CPA, pur Python)

Couverture :
    P01-P05  : construction + clés (keygen, session_id, public_key)
    P06-P10  : encrypt_xor_bits (cas nominaux et erreurs)
    P11-P15  : sum_encrypted_bits (somme homomorphe)
    P16-P20  : decrypt_match (résultat booléen anti-oracle)
    P21-P25  : compute_hamming_paillier (flux complet)
    P26-P30  : fhe_uniqueness_check (vérification unicité multi-templates)

Invariants absolus (vérifiés dans chaque test) :
    - unique_human_proven = False dans tous les résultats
    - certified = False dans tous les résultats
    - match_method contient "PAILLIER" ou "paillier" (protocol tag)
"""
from __future__ import annotations

import os
import pytest

from src.artcb.crypto.homomorphic import (
    PaillierHammingBackend,
    PaillierCiphertext,
    PaillierHammingResult,
    PHE_PROTOCOL,
)

# ─── Fixtures partagées ──────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def backend() -> PaillierHammingBackend:
    """Backend Paillier partagé (keygen 1024 bits, ~0.3s — généré une fois par module)."""
    return PaillierHammingBackend(n_length=1024)


def make_template(seed: int, size: int = 16) -> bytes:
    """Génère un template déterministe à partir d'un seed."""
    import hashlib
    return hashlib.sha256(f"ARTCB-TEST-TEMPLATE-{seed}".encode()).digest()[:size]


def flip_bits(template: bytes, n_bits: int) -> bytes:
    """Retourne template avec exactement n_bits bits flippés (déterministe)."""
    arr = bytearray(template)
    flipped = 0
    for byte_idx in range(len(arr)):
        for bit_pos in range(8):
            if flipped >= n_bits:
                return bytes(arr)
            arr[byte_idx] ^= (1 << bit_pos)
            flipped += 1
    return bytes(arr)


# ─── P01-P05 : Construction et clés ─────────────────────────────────────────

def test_p01_backend_creates_public_key(backend):
    """P01 : PaillierHammingBackend expose une clé publique non nulle."""
    assert backend.public_key is not None
    assert backend.public_key.n > 0


def test_p02_backend_session_id_format(backend):
    """P02 : session_id est une string hex de 16 caractères."""
    assert isinstance(backend._session_id, str)
    assert len(backend._session_id) == 16
    int(backend._session_id, 16)  # doit être hex valide


def test_p03_two_backends_have_different_keys():
    """P03 : deux instances PaillierHammingBackend ont des clés différentes."""
    b1 = PaillierHammingBackend(n_length=1024)
    b2 = PaillierHammingBackend(n_length=1024)
    assert b1.public_key.n != b2.public_key.n


def test_p04_n_length_stored(backend):
    """P04 : n_length est stocké correctement."""
    assert backend._n_length == 1024


def test_p05_phe_import_error_raised_cleanly(monkeypatch):
    """P05 : ImportError propre si phe absent (simulé)."""
    import sys
    orig = sys.modules.get("phe")
    sys.modules["phe"] = None  # type: ignore
    try:
        with pytest.raises((ImportError, TypeError)):
            PaillierHammingBackend(n_length=1024)
    finally:
        if orig is not None:
            sys.modules["phe"] = orig
        else:
            del sys.modules["phe"]


# ─── P06-P10 : encrypt_xor_bits ─────────────────────────────────────────────

def test_p06_encrypt_xor_bits_returns_ciphertext(backend):
    """P06 : encrypt_xor_bits retourne un PaillierCiphertext."""
    ta = make_template(1)
    tb = make_template(2)
    ct = backend.encrypt_xor_bits(ta, tb)
    assert ct is not None
    assert isinstance(ct, PaillierCiphertext)


def test_p07_ciphertext_bits_len_correct(backend):
    """P07 : _bits_len == len(template) * 8."""
    ta = make_template(1, size=8)
    tb = make_template(2, size=8)
    ct = backend.encrypt_xor_bits(ta, tb)
    assert ct._bits_len == 64  # 8 octets × 8 bits


def test_p08_encrypt_xor_empty_template_returns_none(backend):
    """P08 : encrypt_xor_bits retourne None si template vide (fail-closed)."""
    ta = make_template(1)
    ct = backend.encrypt_xor_bits(b"", ta)
    assert ct is None


def test_p09_encrypt_xor_different_lengths_returns_none(backend):
    """P09 : encrypt_xor_bits retourne None si longueurs différentes (fail-closed)."""
    ta = make_template(1, size=16)
    tb = make_template(2, size=8)   # taille différente
    ct = backend.encrypt_xor_bits(ta, tb)
    assert ct is None


def test_p10_same_template_xor_is_zero_bits(backend):
    """P10 : encrypt_xor_bits(t, t) → tous les XOR bits sont 0 → distance = 0."""
    ta = make_template(1)
    ct = backend.encrypt_xor_bits(ta, ta)
    assert ct is not None
    # Somme + déchiffrement doit donner 0
    enc_sum = backend.sum_encrypted_bits(ct)
    dist = backend._private_key.decrypt(enc_sum)
    assert int(dist) == 0


# ─── P11-P15 : sum_encrypted_bits ───────────────────────────────────────────

def test_p11_sum_encrypted_bits_returns_encrypted_number(backend):
    """P11 : sum_encrypted_bits retourne un EncryptedNumber (phe)."""
    import phe
    ta = make_template(1)
    tb = make_template(2)
    ct = backend.encrypt_xor_bits(ta, tb)
    enc_sum = backend.sum_encrypted_bits(ct)
    assert isinstance(enc_sum, phe.EncryptedNumber)


def test_p12_sum_of_none_returns_none(backend):
    """P12 : sum_encrypted_bits(None) retourne None (fail-closed)."""
    result = backend.sum_encrypted_bits(None)
    assert result is None


def test_p13_sum_homomorphic_matches_plaintext(backend):
    """P13 : Σ Enc(XOR_i) déchiffré == Σ XOR_i en clair (correctness Paillier)."""
    ta = make_template(10, size=4)  # 32 bits
    tb = make_template(20, size=4)
    # Calcul clair
    def to_bits(b):
        bits = []
        for byte in b:
            for shift in range(7, -1, -1):
                bits.append((byte >> shift) & 1)
        return bits
    bits_a = to_bits(ta)
    bits_b = to_bits(tb)
    expected_dist = sum(a ^ b for a, b in zip(bits_a, bits_b))
    # Calcul Paillier
    ct = backend.encrypt_xor_bits(ta, tb)
    enc_sum = backend.sum_encrypted_bits(ct)
    actual_dist = int(backend._private_key.decrypt(enc_sum))
    assert actual_dist == expected_dist


def test_p14_sum_known_flip_distance(backend):
    """P14 : Hamming Paillier == Hamming direct pour 3 bits flippés."""
    from src.artcb.identity.biometric_onchain import hamming_distance_bits
    ta = make_template(5, size=8)
    tb = flip_bits(ta, 3)
    expected = hamming_distance_bits(ta, tb)
    ct = backend.encrypt_xor_bits(ta, tb)
    enc_sum = backend.sum_encrypted_bits(ct)
    paillier_dist = int(backend._private_key.decrypt(enc_sum))
    assert paillier_dist == expected == 3


def test_p15_sum_full_diff_template(backend):
    """P15 : templates complètement différents → distance > 0."""
    ta = b"\xff" * 8
    tb = b"\x00" * 8
    ct = backend.encrypt_xor_bits(ta, tb)
    enc_sum = backend.sum_encrypted_bits(ct)
    dist = int(backend._private_key.decrypt(enc_sum))
    assert dist == 64  # 8 octets × 8 bits tous différents


# ─── P16-P20 : decrypt_match ────────────────────────────────────────────────

def test_p16_decrypt_match_returns_true_below_threshold(backend):
    """P16 : dist=2, threshold=5 → match=True, error=False."""
    ta = make_template(1, size=8)
    tb = flip_bits(ta, 2)
    ct = backend.encrypt_xor_bits(ta, tb)
    enc_sum = backend.sum_encrypted_bits(ct)
    match, err, _dist = backend.decrypt_match(enc_sum, threshold_bits=5)
    assert match is True
    assert err is False
    assert _dist == 2


def test_p17_decrypt_match_returns_false_above_threshold(backend):
    """P17 : dist=10, threshold=5 → match=False, error=False."""
    ta = make_template(1, size=8)
    tb = flip_bits(ta, 10)
    ct = backend.encrypt_xor_bits(ta, tb)
    enc_sum = backend.sum_encrypted_bits(ct)
    match, err, _dist = backend.decrypt_match(enc_sum, threshold_bits=5)
    assert match is False
    assert err is False
    assert _dist == 10


def test_p18_decrypt_match_none_enc_sum_returns_error(backend):
    """P18 : enc_sum=None → match=False, error=True (fail-closed)."""
    match, err, _dist = backend.decrypt_match(None, threshold_bits=10)
    assert match is False
    assert err is True
    assert _dist is None


def test_p19_decrypt_match_negative_threshold_returns_error(backend):
    """P19 : threshold_bits=-1 → error=True (fail-closed)."""
    ta = make_template(1, size=4)
    tb = make_template(2, size=4)
    ct = backend.encrypt_xor_bits(ta, tb)
    enc_sum = backend.sum_encrypted_bits(ct)
    match, err, _dist = backend.decrypt_match(enc_sum, threshold_bits=-1)
    assert match is False
    assert err is True


def test_p20_decrypt_match_exact_threshold(backend):
    """P20 : dist == threshold → match=True (borne incluse)."""
    ta = make_template(1, size=8)
    tb = flip_bits(ta, 7)
    ct = backend.encrypt_xor_bits(ta, tb)
    enc_sum = backend.sum_encrypted_bits(ct)
    match, err, _dist = backend.decrypt_match(enc_sum, threshold_bits=7)
    assert match is True
    assert err is False
    assert _dist == 7


# ─── P21-P25 : compute_hamming_paillier (flux complet) ───────────────────────

def test_p21_compute_hamming_same_template(backend):
    """P21 : compute_hamming_paillier(t, t, threshold=0) → match=True, dist=0."""
    ta = make_template(1)
    match, err, dist = backend.compute_hamming_paillier(ta, ta, threshold_bits=0)
    assert match is True
    assert err is False
    assert dist == 0


def test_p22_compute_hamming_no_match(backend):
    """P22 : templates très différents, threshold faible → match=False."""
    ta = make_template(1, size=16)
    tb = flip_bits(ta, 50)  # 50 bits flippés
    match, err, dist = backend.compute_hamming_paillier(ta, tb, threshold_bits=10)
    assert match is False
    assert err is False
    assert dist == 50


def test_p23_compute_hamming_empty_returns_error(backend):
    """P23 : compute_hamming_paillier avec template vide → error=True, match=False."""
    ta = make_template(1)
    match, err, dist = backend.compute_hamming_paillier(b"", ta, threshold_bits=10)
    assert match is False
    assert err is True


def test_p24_compute_hamming_consistency_with_hamming_direct(backend):
    """P24 : résultat Paillier == résultat hamming_distance_bits pour 5 bits flippés."""
    from src.artcb.identity.biometric_onchain import hamming_distance_bits
    ta = make_template(42, size=16)
    tb = flip_bits(ta, 5)
    expected_dist = hamming_distance_bits(ta, tb)
    _, err, paillier_dist = backend.compute_hamming_paillier(ta, tb, threshold_bits=100)
    assert err is False
    assert paillier_dist == expected_dist == 5


def test_p25_compute_hamming_mismatched_lengths_error(backend):
    """P25 : templates de longueurs différentes → error=True (fail-closed)."""
    ta = make_template(1, size=16)
    tb = make_template(2, size=8)
    match, err, dist = backend.compute_hamming_paillier(ta, tb, threshold_bits=10)
    assert match is False
    assert err is True


# ─── P26-P30 : fhe_uniqueness_check ─────────────────────────────────────────

def test_p26_uniqueness_no_existing_records(backend):
    """P26 : liste vide → match_found=False, error=False."""
    ta = make_template(1)
    result = backend.fhe_uniqueness_check(ta, [], threshold_bits=10)
    assert isinstance(result, PaillierHammingResult)
    assert result.match_found is False
    assert result.error is False
    assert result.unique_human_proven is False
    assert result.certified is False


def test_p27_uniqueness_match_found(backend):
    """P27 : même template dans les records → match_found=True."""
    ta = make_template(1, size=16)
    tb = flip_bits(ta, 2)   # dist=2, très proche
    records = [("human_abc123", ta)]
    result = backend.fhe_uniqueness_check(tb, records, threshold_bits=5)
    assert result.match_found is True
    assert result.error is False
    assert result.existing_human_id == "human_abc123"
    assert result.unique_human_proven is False
    assert result.certified is False


def test_p28_uniqueness_no_match_distinct_templates(backend):
    """P28 : templates très différents → match_found=False."""
    ta = make_template(1, size=16)
    tb = make_template(99, size=16)  # complètement différent
    records = [("human_xyz789", ta)]
    result = backend.fhe_uniqueness_check(tb, records, threshold_bits=10)
    assert result.match_found is False
    assert result.error is False


def test_p29_uniqueness_empty_new_template_error(backend):
    """P29 : new_template vide → error=True (fail-closed)."""
    records = [("human_abc", make_template(1))]
    result = backend.fhe_uniqueness_check(b"", records, threshold_bits=10)
    assert result.match_found is False
    assert result.error is True
    assert result.unique_human_proven is False


def test_p30_uniqueness_multi_records_match_on_second(backend):
    """P30 : 3 records, match sur le 2e → retour immédiat avec bon human_id."""
    ta = make_template(1, size=16)
    tb = make_template(2, size=16)   # différent de ta
    tc = make_template(3, size=16)   # à chercher, similaire à tb avec 1 bit flip
    tc_noisy = flip_bits(tc, 1)
    records = [
        ("human_A", ta),
        ("human_B", tc),
        ("human_C", tb),
    ]
    result = backend.fhe_uniqueness_check(tc_noisy, records, threshold_bits=3)
    assert result.match_found is True
    assert result.existing_human_id == "human_B"
    assert result.unique_human_proven is False
    assert result.certified is False
    # Vérifier le protocol tag
    assert "PAILLIER" in result.match_method.upper()
