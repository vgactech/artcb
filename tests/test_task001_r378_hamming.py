"""Tests R378 — Matching Hamming direct sur template_bytes.

Suite complète (T01→T28) :

  Primitives Hamming :
  T01 : hamming_distance_bits — templates identiques → 0
  T02 : hamming_distance_bits — templates opposés → 8×len
  T03 : hamming_distance_bits — 1 bit flip → 1
  T04 : hamming_distance_bits — 8 bits flip → 8
  T05 : hamming_distance_bits — longueurs différentes (padding 0x00)
  T06 : hamming_similarity — identiques → 1.0
  T07 : hamming_similarity — opposés → 0.0
  T08 : hamming_similarity — indépendants → ~0.5 (propriété statistique)

  hamming_uniqueness_check — correspondances :
  T09 : même template → match_found=True (seuil défaut 5%)
  T10 : templates très différents → match_found=False
  T11 : threshold_bits=0 → tout matche (seuil = dist=0 seulement si identique)
  T12 : threshold_bits=256 → tout matche (seuil très permissif)
  T13 : threshold_ratio=0.0 → seuil 1 bit → seul exact match
  T14 : threshold_ratio=1.0 → tout matche

  Invariants absolus :
  T15 : unique_human_proven=False — match trouvé
  T16 : unique_human_proven=False — no match
  T17 : certified=False — match trouvé
  T18 : certified=False — no match
  T19 : match_method = "hamming_direct" dans tous les cas

  Records sans template_bytes → ignorés :
  T20 : record sans template_bytes_b64 ni template_bytes_hex → ignoré

  existing_human_id :
  T21 : existing_human_id présent dans match
  T22 : existing_human_id = None si no match

  HammingMatchResult — champs :
  T23 : hamming_distance dans le résultat match
  T24 : hamming_similarity dans le résultat match
  T25 : threshold_bits dans le résultat
  T26 : template_len_bytes dans le résultat

  Matrice FAR/FRR simulée (R378 benchmark) :
  T27 : matrice distances 0,1,2,4,8,9,16,32,64,128,256 bits — comportement au seuil
  T28 : séparation même humain / humains différents (propriété ~0.5 dist indépendante)
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from artcb.identity.biometric_onchain import (
    HammingMatchResult,
    hamming_distance_bits,
    hamming_similarity,
    hamming_uniqueness_check,
)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _flip_bits(data: bytes, n_bits: int) -> bytes:
    """Retourne `data` avec exactement n_bits bits flippés (positions consécutives)."""
    result = bytearray(data)
    for i in range(n_bits):
        byte_idx = i // 8
        bit_idx = i % 8
        result[byte_idx] ^= (1 << bit_idx)
    return bytes(result)


def _make_record(template_bytes: bytes, human_id: str, use_hex: bool = False) -> dict:
    """Crée un record simulé avec template_bytes_b64 ou template_bytes_hex."""
    if use_hex:
        return {"human_id": human_id, "template_bytes_hex": template_bytes.hex()}
    return {"human_id": human_id, "template_bytes_b64": base64.b64encode(template_bytes).decode()}


TEMPLATE_32 = b"\xab\xcd\xef\x01\x23\x45\x67\x89" * 4   # 32 octets


# ─── T01 : identiques → 0 ────────────────────────────────────────────────────

def test_T01_hamming_distance_identical():
    assert hamming_distance_bits(TEMPLATE_32, TEMPLATE_32) == 0


# ─── T02 : opposés → 8×len ───────────────────────────────────────────────────

def test_T02_hamming_distance_opposite():
    a = b"\x00" * 32
    b = b"\xff" * 32
    assert hamming_distance_bits(a, b) == 256


# ─── T03 : 1 bit flip → 1 ────────────────────────────────────────────────────

def test_T03_hamming_distance_one_bit():
    noisy = _flip_bits(TEMPLATE_32, 1)
    assert hamming_distance_bits(TEMPLATE_32, noisy) == 1


# ─── T04 : 8 bits flip → 8 ───────────────────────────────────────────────────

def test_T04_hamming_distance_eight_bits():
    noisy = _flip_bits(TEMPLATE_32, 8)
    assert hamming_distance_bits(TEMPLATE_32, noisy) == 8


# ─── T05 : longueurs différentes → padding 0x00 ──────────────────────────────

def test_T05_hamming_distance_different_lengths():
    a = b"\x00" * 4
    b = b"\x00" * 4 + b"\xff" * 4  # 4 octets supplémentaires tous 1
    # dist = 0 (sur les 4 premiers) + 32 (sur les 4 suivants, padding = 0x00)
    assert hamming_distance_bits(a, b) == 32


# ─── T06 : similarity identiques → 1.0 ──────────────────────────────────────

def test_T06_hamming_similarity_identical():
    assert hamming_similarity(TEMPLATE_32, TEMPLATE_32) == 1.0


# ─── T07 : similarity opposés → 0.0 ─────────────────────────────────────────

def test_T07_hamming_similarity_opposite():
    a = b"\x00" * 32
    b = b"\xff" * 32
    assert hamming_similarity(a, b) == 0.0


# ─── T08 : similarity indépendants → ~0.5 ────────────────────────────────────

def test_T08_hamming_similarity_independent_near_half():
    """Deux templates pseudo-aléatoires indépendants → similarity ≈ 0.5 (±10%)."""
    import hashlib
    # Templates déterministes mais "indépendants"
    a = hashlib.sha256(b"person-alice-fingerprint").digest() * 2  # 64 octets
    b = hashlib.sha256(b"person-bob-fingerprint").digest() * 2    # 64 octets
    sim = hamming_similarity(a, b)
    # Propriété statistique : bit-strings indépendants → ~50% bits différents
    assert 0.35 <= sim <= 0.65, f"similarity={sim:.4f} devrait être proche de 0.5"


# ─── T09 : même template → match_found=True (seuil défaut 5%) ────────────────

def test_T09_exact_match_default_threshold():
    rec = _make_record(TEMPLATE_32, "human-alice")
    result = hamming_uniqueness_check(TEMPLATE_32, [rec])
    assert result.match_found is True
    assert result.hamming_distance == 0
    assert result.hamming_similarity == 1.0


# ─── T10 : templates très différents → match_found=False ─────────────────────

def test_T10_no_match_different_templates():
    import hashlib
    a = hashlib.sha256(b"alice").digest()
    b = hashlib.sha256(b"bob__").digest()
    rec = _make_record(a, "human-alice")
    result = hamming_uniqueness_check(b, [rec], threshold_bits=8)
    # distance Hamming entre deux SHA-256 indépendants >> 8 bits
    assert result.match_found is False


# ─── T11 : threshold_bits=0 → seulement les templates identiques matchent ────

def test_T11_threshold_zero_only_identical():
    rec = _make_record(TEMPLATE_32, "human-alice")
    # Template légèrement différent
    noisy = _flip_bits(TEMPLATE_32, 1)
    result_exact = hamming_uniqueness_check(TEMPLATE_32, [rec], threshold_bits=0)
    result_noisy = hamming_uniqueness_check(noisy, [rec], threshold_bits=0)
    assert result_exact.match_found is True   # dist=0 ≤ 0 → match
    assert result_noisy.match_found is False  # dist=1 > 0 → no match


# ─── T12 : threshold_bits=256 → tout matche ──────────────────────────────────

def test_T12_high_threshold_everything_matches():
    import hashlib
    a = hashlib.sha256(b"alice").digest()
    b = hashlib.sha256(b"bob__").digest()
    rec = _make_record(a, "human-alice")
    result = hamming_uniqueness_check(b, [rec], threshold_bits=256)
    assert result.match_found is True


# ─── T13 : threshold_ratio=0.0 → seuil 1 bit ─────────────────────────────────

def test_T13_threshold_ratio_zero():
    rec = _make_record(TEMPLATE_32, "human-alice")
    noisy_1bit = _flip_bits(TEMPLATE_32, 1)
    # threshold_ratio=0.0 → max(1, int(0.0 * 256)) = 1
    result = hamming_uniqueness_check(noisy_1bit, [rec], threshold_ratio=0.0)
    # dist=1, threshold=1 → dist ≤ threshold → MATCH
    assert result.match_found is True
    assert result.hamming_distance == 1


# ─── T14 : threshold_ratio=1.0 → tout matche ─────────────────────────────────

def test_T14_threshold_ratio_one():
    import hashlib
    a = hashlib.sha256(b"alice").digest()
    b = hashlib.sha256(b"bob__").digest()
    rec = _make_record(a, "human-alice")
    result = hamming_uniqueness_check(b, [rec], threshold_ratio=1.0)
    assert result.match_found is True


# ─── T15 : unique_human_proven=False — match ─────────────────────────────────

def test_T15_unique_human_proven_false_match():
    rec = _make_record(TEMPLATE_32, "human-alice")
    result = hamming_uniqueness_check(TEMPLATE_32, [rec])
    assert result.unique_human_proven is False


# ─── T16 : unique_human_proven=False — no match ──────────────────────────────

def test_T16_unique_human_proven_false_no_match():
    result = hamming_uniqueness_check(TEMPLATE_32, [])
    assert result.unique_human_proven is False


# ─── T17 : certified=False — match ───────────────────────────────────────────

def test_T17_certified_false_match():
    rec = _make_record(TEMPLATE_32, "human-alice")
    result = hamming_uniqueness_check(TEMPLATE_32, [rec])
    assert result.certified is False


# ─── T18 : certified=False — no match ────────────────────────────────────────

def test_T18_certified_false_no_match():
    result = hamming_uniqueness_check(TEMPLATE_32, [])
    assert result.certified is False


# ─── T19 : match_method = "hamming_direct" ───────────────────────────────────

def test_T19_match_method_hamming_direct():
    rec = _make_record(TEMPLATE_32, "human-alice")
    result_match = hamming_uniqueness_check(TEMPLATE_32, [rec])
    result_no = hamming_uniqueness_check(TEMPLATE_32, [])
    assert result_match.match_method == "hamming_direct"
    assert result_no.match_method == "hamming_direct"


# ─── T20 : record sans template_bytes → ignoré ───────────────────────────────

def test_T20_record_without_template_bytes_ignored():
    records = [
        {"human_id": "ghost"},
        {"human_id": "empty", "template_bytes_b64": ""},
        {"human_id": "none_hex", "template_bytes_hex": None},
    ]
    result = hamming_uniqueness_check(TEMPLATE_32, records)
    assert result.match_found is False


# ─── T21 : existing_human_id dans match ──────────────────────────────────────

def test_T21_existing_human_id_in_match():
    rec = _make_record(TEMPLATE_32, "human-42")
    result = hamming_uniqueness_check(TEMPLATE_32, [rec])
    assert result.existing_human_id == "human-42"


# ─── T22 : existing_human_id None si no match ────────────────────────────────

def test_T22_existing_human_id_none_if_no_match():
    result = hamming_uniqueness_check(TEMPLATE_32, [])
    assert result.existing_human_id is None


# ─── T23 : hamming_distance dans le résultat ─────────────────────────────────

def test_T23_hamming_distance_in_result():
    noisy = _flip_bits(TEMPLATE_32, 4)
    rec = _make_record(TEMPLATE_32, "human-alice")
    result = hamming_uniqueness_check(noisy, [rec], threshold_bits=8)
    assert result.hamming_distance == 4


# ─── T24 : hamming_similarity dans le résultat ───────────────────────────────

def test_T24_hamming_similarity_in_result():
    rec = _make_record(TEMPLATE_32, "human-alice")
    result = hamming_uniqueness_check(TEMPLATE_32, [rec])
    assert result.hamming_similarity == 1.0


# ─── T25 : threshold_bits dans le résultat ───────────────────────────────────

def test_T25_threshold_bits_in_result():
    rec = _make_record(TEMPLATE_32, "human-alice")
    result = hamming_uniqueness_check(TEMPLATE_32, [rec], threshold_bits=42)
    assert result.threshold_bits == 42


# ─── T26 : template_len_bytes dans le résultat ───────────────────────────────

def test_T26_template_len_bytes_in_result():
    rec = _make_record(TEMPLATE_32, "human-alice")
    result = hamming_uniqueness_check(TEMPLATE_32, [rec])
    assert result.template_len_bytes == 32


# ─── T27 : matrice FAR/FRR simulée ───────────────────────────────────────────

def test_T27_far_frr_matrix():
    """Matrice complète : comportement au seuil pour distances 0→256 bits.

    Pour chaque distance N bits :
      - intra-classe (même personne, bruit N bits) : si N ≤ threshold → MATCH (bon)
      - inter-classe (personne différente, par définition > threshold) : → NO_MATCH (bon)

    NOTE honnête :
        Ces tests vérifient le comportement algorithmique du seuil,
        PAS les FAR/FRR réels sur capteurs.
        Un seuil à T bits = 100% match pour dist ≤ T, 0% pour dist > T.
        En biométrie réelle, les distributions intra/inter se chevauchent.
        CERTIFIED_100=false.
    """
    rec = _make_record(TEMPLATE_32, "human-alice")
    max_bits = len(TEMPLATE_32) * 8  # 256 bits

    # Matrice de distances à tester
    test_distances = [0, 1, 2, 4, 8, 9, 16, 32, 64, 128, 200, 256]
    threshold = 8  # seuil fixe pour la matrice

    results = []
    for dist in test_distances:
        if dist > max_bits:
            # Distance impossible sur 32 octets — skip
            continue
        noisy = _flip_bits(TEMPLATE_32, dist)
        actual_dist = hamming_distance_bits(TEMPLATE_32, noisy)
        assert actual_dist == dist, f"flip_bits({dist}) produit dist={actual_dist}"

        result = hamming_uniqueness_check(noisy, [rec], threshold_bits=threshold)

        # Vérification comportement au seuil
        if dist <= threshold:
            assert result.match_found is True, (
                f"dist={dist} bits ≤ threshold={threshold} → doit matcher"
            )
        else:
            assert result.match_found is False, (
                f"dist={dist} bits > threshold={threshold} → ne doit pas matcher"
            )

        results.append((dist, result.match_found, result.hamming_distance))

    # Invariants dans tous les cas
    for dist, match, measured_dist in results:
        assert measured_dist >= 0 or not match  # dist=-1 sentinel = no template_bytes only

    # Rapport de la matrice (visible dans pytest -v)
    print("\n=== MATRICE FAR/FRR SIMULÉE (threshold=8 bits sur 256 bits) ===")
    print(f"{'Distance (bits)':<20} {'Match':<10} {'Verdict'}")
    print("-" * 50)
    for dist, match, _ in results:
        verdict = "TP (intra, bruit ≤ seuil)" if match else "TN (intra, bruit > seuil)"
        print(f"{dist:<20} {str(match):<10} {verdict}")
    print(f"\nNote : FAR/FRR réels non mesurés (CERTIFIED_100=false)")


# ─── T28 : séparation intra/inter-classe ─────────────────────────────────────

def test_T28_intra_vs_inter_class_separation():
    """Démontre la séparation statistique intra-classe vs inter-classe.

    Intra-classe (même personne, bruit faible) : distance faible → match attendu
    Inter-classe (personnes différentes) : distance ~50% → no-match attendu

    NOTE honnête :
        En pratique, la séparation dépend entièrement du pipeline de capture.
        Un capteur mal calibré peut produire des templates intra-classe avec
        une distance > threshold. Ce test utilise des vecteurs synthétiques
        qui SIMULENT le comportement attendu — pas des vraies empreintes.
        FAR/FRR réels = NON MESURÉS. CERTIFIED_100=false.
    """
    import hashlib

    # Simuler un template "Alice" avec 3 captures (bruit 0, 2, 6 bits)
    alice_enrolled = hashlib.sha256(b"alice-enroll-00").digest()
    alice_capture1 = _flip_bits(alice_enrolled, 2)  # bruit faible : 2 bits
    alice_capture2 = _flip_bits(alice_enrolled, 6)  # bruit modéré : 6 bits

    # Simuler un template "Bob" (indépendant — ~50% de bits différents)
    bob_template = hashlib.sha256(b"bob-different-person").digest()

    rec_alice = _make_record(alice_enrolled, "human-alice")

    threshold = 8  # 8 bits = BCH_T de R374

    # Intra-classe Alice : les deux captures matchent (bruit ≤ threshold)
    r1 = hamming_uniqueness_check(alice_capture1, [rec_alice], threshold_bits=threshold)
    r2 = hamming_uniqueness_check(alice_capture2, [rec_alice], threshold_bits=threshold)
    assert r1.match_found is True, (
        f"Alice capture1 (dist={r1.hamming_distance}) devrait matcher avec threshold={threshold}"
    )
    assert r2.match_found is True, (
        f"Alice capture2 (dist={r2.hamming_distance}) devrait matcher avec threshold={threshold}"
    )

    # Inter-classe Bob : ne matche pas Alice
    r3 = hamming_uniqueness_check(bob_template, [rec_alice], threshold_bits=threshold)
    assert r3.match_found is False, (
        f"Bob (dist={r3.hamming_distance}) ne devrait pas matcher Alice avec threshold={threshold}"
    )

    # Vérification : la distance inter-classe est effectivement >> threshold
    inter_dist = hamming_distance_bits(bob_template, alice_enrolled)
    assert inter_dist > threshold * 4, (
        f"Distance inter-classe={inter_dist} devrait être >> {threshold}"
    )

    # Invariants
    for r in [r1, r2, r3]:
        assert r.unique_human_proven is False
        assert r.certified is False
        assert r.match_method == "hamming_direct"

    # Rapport
    print(f"\n=== SÉPARATION INTRA/INTER-CLASSE (threshold={threshold} bits) ===")
    print(f"Alice intra (capture1) : dist={r1.hamming_distance} bits → match={r1.match_found}")
    print(f"Alice intra (capture2) : dist={r2.hamming_distance} bits → match={r2.match_found}")
    print(f"Bob inter-classe       : dist={r3.hamming_distance} bits → match={r3.match_found}")
    print(f"Séparation inter/intra : {inter_dist}/{max(r1.hamming_distance, r2.hamming_distance)} bits")
    print(f"unique_human_proven=False dans tous les cas (invariant absolu)")
    print(f"CERTIFIED_100=false — distances sur vecteurs synthétiques, pas capteurs réels")
