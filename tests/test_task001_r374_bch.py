"""Tests TASK-001 / R374 — BCH(255,191,8) FuzzyExtractor avec tolérance dist ≤ 8.

Suite de tests R374 couvrant :
  S01 : _bch_encode_template — structure du blob ECC (header + ecc_per_bloc)
  S02 : _bch_encode_template — padding à multiple de BCH_DATA_BYTES
  S03 : _bch_decode_template — dist=0 → template corrigé identique
  S04 : _bch_decode_template — dist=1 → corrigé (1 bit flip)
  S05 : _bch_decode_template — dist=4 → corrigé (4 bits flip répartis)
  S06 : _bch_decode_template — dist=8 → corrigé (8 bits flip = maximum)
  S07 : _bch_decode_template — dist=9 → None (> t, incorrigible, fail-closed)
  S08 : _bch_decode_template — blob ECC trop court → None
  S09 : _bch_decode_template — blob ECC vide (< 2 octets) → None
  S10 : fuzzy_extract — algo = ARTCB-SECURE-SKETCH-HKDF-BCH-v3
  S11 : fuzzy_extract — noise_tolerance_bits = 8 × nb_blocs
  S12 : fuzzy_extract — helper contient BCH ECC (len > 80)
  S13 : fuzzy_reproduce — dist=0 → secret identique
  S14 : fuzzy_reproduce — dist=1 → secret identique (tolérance BCH)
  S15 : fuzzy_reproduce — dist=4 → secret identique (tolérance BCH)
  S16 : fuzzy_reproduce — dist=8 sur 1 bloc → secret identique (limite)
  S17 : fuzzy_reproduce — dist=9 sur 1 bloc → None (> t, fail-closed)
  S18 : fuzzy_reproduce — helper hex invalide → None
  S19 : fuzzy_reproduce — helper trop court → None
  S20 : fuzzy_reproduce — deux templates distincts (non bruités) → secrets différents
  S21 : fuzzy_reproduce — template multi-blocs dist=8/bloc (cumul) → réussi
  S22 : fuzzy_reproduce — template multi-blocs dist=9 sur 1 bloc → None
  S23 : unique_human_proven toujours False même avec BCH actif
  S24 : algorithm v3 dans FuzzyExtractorResult
  S25 : noise_tolerance_bits correctement calculé (nb_blocs × 8)
  S26 : enroll_biometric — verification_policy = secure_sketch_hkdf_bch_v3
  S27 : enroll_biometric — bch_tolerance_bits_per_block dans to_chain_record()
  S28 : fuzzy_extract — template vide → ValueError
  S29 : _bch_decode_template — paramètres ecc_size incompatibles → None (fail-closed)
  S30 : fuzzy_reproduce — dist=8 sur chaque bloc d'un template 2-blocs → réussi
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from artcb.identity.biometric_onchain import (
    _ALGO_NAME,
    _BCH_DATA_BYTES,
    _BCH_T,
    FuzzyExtractorResult,
    _bch_encode_template,
    _bch_decode_template,
    enroll_biometric,
    fuzzy_extract,
    fuzzy_reproduce,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _flip_n_bits(data: bytes, n: int, start_bit: int = 0) -> bytes:
    """Flip n bits consécutifs à partir de start_bit dans data (octet-centré)."""
    arr = bytearray(data)
    for i in range(n):
        bit = start_bit + i
        byte_idx = bit // 8
        bit_idx  = bit % 8
        arr[byte_idx] ^= (1 << bit_idx)
    return bytes(arr)


# Template 1 bloc exact (23 octets = BCH_DATA_BYTES)
TMPL_1BLK = b"biometric_template_23b"[:_BCH_DATA_BYTES].ljust(_BCH_DATA_BYTES, b"\x00")
assert len(TMPL_1BLK) == _BCH_DATA_BYTES

# Template 2 blocs (46 octets)
TMPL_2BLK = (b"block_A_biometric_123__" + b"block_B_biometric_456__")[:2 * _BCH_DATA_BYTES]
assert len(TMPL_2BLK) == 2 * _BCH_DATA_BYTES


# ─── S01 : _bch_encode_template — structure du blob ECC ───────────────────────

def test_S01_bch_encode_structure() -> None:
    padded, ecc = _bch_encode_template(TMPL_1BLK)
    # Header = 2 octets (n_blocks, ecc_bytes) + n_blocks * ecc_bytes
    n_blocks = ecc[0]
    ecc_per  = ecc[1]
    assert n_blocks == 1
    assert ecc_per  == 8           # BCH(t=8, m=8) → ecc_bytes=8
    assert len(ecc) == 2 + n_blocks * ecc_per


# ─── S02 : padding à multiple de BCH_DATA_BYTES ───────────────────────────────

def test_S02_bch_encode_padding() -> None:
    short_tmpl = b"only12bytes"
    padded, ecc = _bch_encode_template(short_tmpl)
    assert len(padded) % _BCH_DATA_BYTES == 0
    assert len(padded) >= len(short_tmpl)
    # Padding nul
    assert padded[len(short_tmpl):] == b"\x00" * (len(padded) - len(short_tmpl))


# ─── S03 : decode dist=0 ──────────────────────────────────────────────────────

def test_S03_bch_decode_dist0() -> None:
    padded, ecc = _bch_encode_template(TMPL_1BLK)
    corrected = _bch_decode_template(TMPL_1BLK, ecc)
    assert corrected == padded


# ─── S04 : decode dist=1 ──────────────────────────────────────────────────────

def test_S04_bch_decode_dist1() -> None:
    padded, ecc = _bch_encode_template(TMPL_1BLK)
    noisy = _flip_n_bits(TMPL_1BLK, 1)
    corrected = _bch_decode_template(noisy, ecc)
    assert corrected == padded


# ─── S05 : decode dist=4 ──────────────────────────────────────────────────────

def test_S05_bch_decode_dist4() -> None:
    padded, ecc = _bch_encode_template(TMPL_1BLK)
    noisy = _flip_n_bits(TMPL_1BLK, 4)
    corrected = _bch_decode_template(noisy, ecc)
    assert corrected == padded


# ─── S06 : decode dist=8 (limite) ─────────────────────────────────────────────

def test_S06_bch_decode_dist8_pass() -> None:
    padded, ecc = _bch_encode_template(TMPL_1BLK)
    noisy = _flip_n_bits(TMPL_1BLK, 8)
    corrected = _bch_decode_template(noisy, ecc)
    assert corrected == padded, "dist=8 doit être corrigible (t=8)"


# ─── S07 : decode dist=9 → None (fail-closed) ─────────────────────────────────

def test_S07_bch_decode_dist9_fail() -> None:
    padded, ecc = _bch_encode_template(TMPL_1BLK)
    noisy = _flip_n_bits(TMPL_1BLK, 9)
    result = _bch_decode_template(noisy, ecc)
    assert result is None, "dist=9 > t=8 doit retourner None (fail-closed)"


# ─── S08 : blob ECC trop court → None ─────────────────────────────────────────

def test_S08_bch_decode_ecc_too_short() -> None:
    _, ecc = _bch_encode_template(TMPL_1BLK)
    truncated = ecc[:3]  # trop court
    assert _bch_decode_template(TMPL_1BLK, truncated) is None


# ─── S09 : blob ECC vide → None ───────────────────────────────────────────────

def test_S09_bch_decode_empty_ecc() -> None:
    assert _bch_decode_template(TMPL_1BLK, b"") is None
    assert _bch_decode_template(TMPL_1BLK, b"\x01") is None  # 1 octet < 2


# ─── S10 : fuzzy_extract — algo v3 ────────────────────────────────────────────

def test_S10_fuzzy_extract_algo_v3() -> None:
    res = fuzzy_extract(TMPL_1BLK)
    assert res.algorithm == "ARTCB-SECURE-SKETCH-HKDF-BCH-v3"


# ─── S11 : fuzzy_extract — noise_tolerance_bits correct ───────────────────────

def test_S11_noise_tolerance_bits() -> None:
    res1 = fuzzy_extract(TMPL_1BLK)
    assert res1.noise_tolerance_bits == _BCH_T * 1  # 1 bloc

    res2 = fuzzy_extract(TMPL_2BLK)
    assert res2.noise_tolerance_bits == _BCH_T * 2  # 2 blocs


# ─── S12 : fuzzy_extract — helper contient BCH ECC (len > 80) ─────────────────

def test_S12_helper_contains_bch_ecc() -> None:
    res = fuzzy_extract(TMPL_1BLK)
    helper = bytes.fromhex(res.helper_data_hex)
    # 80 octets fixes (salt+sketch+confirm) + au moins 10 octets BCH (header+ecc)
    assert len(helper) > 80, "helper doit contenir salt+sketch+confirm+bch_ecc"


# ─── S13 : fuzzy_reproduce — dist=0 ───────────────────────────────────────────

def test_S13_reproduce_dist0() -> None:
    res = fuzzy_extract(TMPL_1BLK)
    sec = fuzzy_reproduce(TMPL_1BLK, res.helper_data_hex)
    assert sec == res.secret_hex


# ─── S14 : fuzzy_reproduce — dist=1 ──────────────────────────────────────────

def test_S14_reproduce_dist1() -> None:
    res = fuzzy_extract(TMPL_1BLK)
    noisy = _flip_n_bits(TMPL_1BLK, 1)
    sec = fuzzy_reproduce(noisy, res.helper_data_hex)
    assert sec == res.secret_hex, "dist=1 doit réussir avec BCH"


# ─── S15 : fuzzy_reproduce — dist=4 ──────────────────────────────────────────

def test_S15_reproduce_dist4() -> None:
    res = fuzzy_extract(TMPL_1BLK)
    noisy = _flip_n_bits(TMPL_1BLK, 4)
    sec = fuzzy_reproduce(noisy, res.helper_data_hex)
    assert sec == res.secret_hex, "dist=4 doit réussir avec BCH"


# ─── S16 : fuzzy_reproduce — dist=8 (limite exacte) ──────────────────────────

def test_S16_reproduce_dist8_pass() -> None:
    res = fuzzy_extract(TMPL_1BLK)
    noisy = _flip_n_bits(TMPL_1BLK, 8)
    sec = fuzzy_reproduce(noisy, res.helper_data_hex)
    assert sec == res.secret_hex, "dist=8 = limite t=8 : doit réussir"


# ─── S17 : fuzzy_reproduce — dist=9 → None ────────────────────────────────────

def test_S17_reproduce_dist9_fail() -> None:
    res = fuzzy_extract(TMPL_1BLK)
    noisy = _flip_n_bits(TMPL_1BLK, 9)
    sec = fuzzy_reproduce(noisy, res.helper_data_hex)
    assert sec is None, "dist=9 > t=8 : doit retourner None (fail-closed)"


# ─── S18 : fuzzy_reproduce — helper hex invalide → None ──────────────────────

def test_S18_reproduce_invalid_hex() -> None:
    assert fuzzy_reproduce(TMPL_1BLK, "ZZZZZZZZ") is None


# ─── S19 : fuzzy_reproduce — helper trop court → None ────────────────────────

def test_S19_reproduce_helper_too_short() -> None:
    # Moins de 82 octets (80 fixes + 2 header BCH minimum)
    short_hex = "aa" * 40
    assert fuzzy_reproduce(TMPL_1BLK, short_hex) is None


# ─── S20 : deux templates distincts → secrets différents ─────────────────────

def test_S20_distinct_templates_distinct_secrets() -> None:
    tmpl_a = b"template_user_alice_23b"[:_BCH_DATA_BYTES].ljust(_BCH_DATA_BYTES, b"\x00")
    tmpl_b = b"template_user_bob_234__"[:_BCH_DATA_BYTES].ljust(_BCH_DATA_BYTES, b"\x00")
    assert tmpl_a != tmpl_b

    res_a = fuzzy_extract(tmpl_a)
    # Reproduire avec template_b sur helper de a → None ou secret différent
    sec_cross = fuzzy_reproduce(tmpl_b, res_a.helper_data_hex)
    # Les templates sont trop différents (>>8 bits) → None
    assert sec_cross is None, "Template différent → reproduction impossible"


# ─── S21 : template multi-blocs dist=8 par bloc → réussi ─────────────────────

def test_S21_reproduce_multiblock_dist8_per_block() -> None:
    res = fuzzy_extract(TMPL_2BLK)
    # Flip 8 bits dans chaque bloc (blocs distincts)
    noisy = bytearray(TMPL_2BLK)
    # Bloc 0 : bits 0→7
    for bit in range(8):
        noisy[bit // 8] ^= (1 << (bit % 8))
    # Bloc 1 : bits 0→7 dans le deuxième bloc
    offset = _BCH_DATA_BYTES  # début du bloc 1 en octets
    for bit in range(8):
        byte_idx = offset + bit // 8
        noisy[byte_idx] ^= (1 << (bit % 8))
    sec = fuzzy_reproduce(bytes(noisy), res.helper_data_hex)
    assert sec == res.secret_hex, "8 bits/bloc sur 2 blocs doit réussir"


# ─── S22 : template multi-blocs dist=9 sur bloc 0 → None ─────────────────────

def test_S22_reproduce_multiblock_dist9_bloc0_fail() -> None:
    res = fuzzy_extract(TMPL_2BLK)
    noisy = _flip_n_bits(TMPL_2BLK, 9, start_bit=0)  # 9 bits dans bloc 0
    sec = fuzzy_reproduce(noisy, res.helper_data_hex)
    assert sec is None, "9 bits sur bloc 0 → incorrigible → None"


# ─── S23 : unique_human_proven toujours False ─────────────────────────────────

def test_S23_unique_human_proven_always_false() -> None:
    res = fuzzy_extract(TMPL_1BLK)
    assert res.certified is False
    # FuzzyExtractorResult n'expose pas unique_human_proven directement
    # mais son note documente explicitement que FHE n'est pas implémenté
    assert "unique_human_proven=False" in res.note


# ─── S24 : algorithm v3 dans FuzzyExtractorResult ────────────────────────────

def test_S24_algorithm_name_v3() -> None:
    res = fuzzy_extract(TMPL_1BLK)
    assert "v3" in res.algorithm
    assert "BCH" in res.algorithm


# ─── S25 : noise_tolerance_bits = nb_blocs × BCH_T ───────────────────────────

def test_S25_noise_tolerance_calculation() -> None:
    # 1 bloc
    r1 = fuzzy_extract(b"x" * _BCH_DATA_BYTES)
    assert r1.noise_tolerance_bits == _BCH_T

    # 3 blocs
    r3 = fuzzy_extract(b"x" * (3 * _BCH_DATA_BYTES))
    assert r3.noise_tolerance_bits == 3 * _BCH_T


# ─── S26 : enroll_biometric — verification_policy v3 ─────────────────────────

def test_S26_enroll_verification_policy_v3() -> None:
    result, secret_hex, blinding_hex = enroll_biometric(TMPL_1BLK)
    rec = result.human_identity_record
    assert rec["verification_policy"] == "secure_sketch_hkdf_bch_v3"
    assert rec["unique_human_proven"] is False


# ─── S27 : enroll_biometric — bch_tolerance dans to_chain_record ──────────────

def test_S27_enroll_bch_fields_in_chain_record() -> None:
    result, _, _ = enroll_biometric(TMPL_1BLK)
    rec = result.human_identity_record
    assert "bch_tolerance_bits_per_block" in rec
    assert rec["bch_tolerance_bits_per_block"] == _BCH_T
    assert "bch_data_bytes_per_block" in rec
    assert rec["bch_data_bytes_per_block"] == _BCH_DATA_BYTES


# ─── S28 : fuzzy_extract — template vide → ValueError ────────────────────────

def test_S28_fuzzy_extract_empty_raises() -> None:
    with pytest.raises(ValueError, match="template_bytes vide"):
        fuzzy_extract(b"")


# ─── S29 : _bch_decode_template — ecc_size incompatible → None ───────────────

def test_S29_bch_decode_incompatible_ecc_size() -> None:
    _, ecc = _bch_encode_template(TMPL_1BLK)
    # Altérer l'octet ecc_size pour simuler des paramètres incompatibles
    bad_ecc = bytes([ecc[0], 7]) + ecc[2:]  # ecc_size=7 ≠ 8
    result = _bch_decode_template(TMPL_1BLK, bad_ecc)
    assert result is None, "ecc_size incompatible doit retourner None"


# ─── S30 : fuzzy_reproduce dist=8 sur chaque bloc d'un template 2-blocs ───────

def test_S30_reproduce_2blocs_dist8_each_independent() -> None:
    """Chaque bloc tolère indépendamment 8 bits — 16 bits au total sur 2 blocs."""
    tmpl = b"bloc_zero_23_bytes_exact" [:_BCH_DATA_BYTES].ljust(_BCH_DATA_BYTES, b"\x00")
    tmpl += b"bloc_one__23_bytes_exact"[:_BCH_DATA_BYTES].ljust(_BCH_DATA_BYTES, b"\x00")
    assert len(tmpl) == 2 * _BCH_DATA_BYTES

    res = fuzzy_extract(tmpl)
    assert res.noise_tolerance_bits == 2 * _BCH_T

    # Flip 8 bits dans bloc 0 seulement
    noisy_b0 = bytearray(tmpl)
    for bit in range(8):
        noisy_b0[bit // 8] ^= (1 << (bit % 8))
    s0 = fuzzy_reproduce(bytes(noisy_b0), res.helper_data_hex)
    assert s0 == res.secret_hex, "8 bits dans bloc 0 seulement → PASS"

    # Flip 8 bits dans bloc 1 seulement
    noisy_b1 = bytearray(tmpl)
    off = _BCH_DATA_BYTES
    for bit in range(8):
        noisy_b1[off + bit // 8] ^= (1 << (bit % 8))
    s1 = fuzzy_reproduce(bytes(noisy_b1), res.helper_data_hex)
    assert s1 == res.secret_hex, "8 bits dans bloc 1 seulement → PASS"
