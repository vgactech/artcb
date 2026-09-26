"""R487 — Tests ConcreteHammingBackend (ARTCB-CONCRETE-FHE-HAMMING-v1).

Tests T01→T18 validant :
  - T01-T03 : compilation circuit + cache
  - T04-T06 : hamming_distance_concrete — valeurs exactes
  - T07-T08 : fail-closed (bytes vides / longueurs différentes)
  - T09-T10 : fhe_uniqueness_check — MATCH / NO_MATCH
  - T11-T12 : fhe_uniqueness_check — liste vide / new_template vide
  - T13      : intégration avec check_uniqueness() (routing fhe_circuit)
  - T14      : invariants (unique_human_proven=False, certified=False)
  - T15      : ConcreteHammingResult champs debug
  - T16      : duck-typing FheHammingCircuit interface
  - T17      : all_errors si toutes les paires sont invalides
  - T18      : cache module-level (deux instances partagent le même circuit)

CERTIFIED_100=false | unique_human_proven=False
"""
from __future__ import annotations

import logging

import pytest

logger = logging.getLogger("artcb.tests.r487")

# ─── Imports modules ─────────────────────────────────────────────────────────

from src.artcb.crypto.homomorphic import (
    CONCRETE_FHE_NOTE,
    ConcreteHammingBackend,
    ConcreteHammingResult,
    _build_concrete_hamming_byte_circuit,
    _CONCRETE_CIRCUIT_CACHE,
)


# ─── Fixture partagée (circuit compilé une seule fois pour tous les tests) ──

@pytest.fixture(scope="module")
def backend() -> ConcreteHammingBackend:
    """ConcreteHammingBackend partagé — compilation unique (cache)."""
    return ConcreteHammingBackend()


# ─── T01 : compilation circuit Concrete (module-level build) ─────────────────

def test_T01_build_circuit_returns_circuit():
    """T01 — _build_concrete_hamming_byte_circuit() retourne un objet non-None."""
    circuit = _build_concrete_hamming_byte_circuit()
    assert circuit is not None, "Le circuit Concrete ne doit pas être None"


def test_T02_circuit_cache_populated():
    """T02 — Après build, le cache _CONCRETE_CIRCUIT_CACHE est non-None."""
    import src.artcb.crypto.homomorphic as hom
    # S'assurer que le build a été appelé au moins une fois
    _build_concrete_hamming_byte_circuit()
    assert hom._CONCRETE_CIRCUIT_CACHE is not None, "Cache doit être non-None après build"


def test_T03_backend_instantiation(backend):
    """T03 — ConcreteHammingBackend s'instancie sans erreur et a session_id."""
    assert backend is not None
    assert hasattr(backend, "_session_id")
    assert len(backend._session_id) == 16


# ─── T04-T06 : hamming_distance_concrete — valeurs exactes ──────────────────

def test_T04_hamming_identical_templates(backend):
    """T04 — Distance Hamming de deux templates identiques = 0."""
    t = bytes([0xAB, 0xCD, 0xEF, 0x12])
    dist, err = backend.hamming_distance_concrete(t, t)
    assert not err, "Pas d'erreur sur templates identiques"
    assert dist == 0, f"Distance attendue=0, obtenu={dist}"


def test_T05_hamming_all_bits_flipped(backend):
    """T05 — Distance Hamming de template vs complément = 8 × nb_octets."""
    t = bytes([0x00, 0x00, 0x00, 0x00])  # 4 octets
    t_inv = bytes([0xFF, 0xFF, 0xFF, 0xFF])
    dist, err = backend.hamming_distance_concrete(t, t_inv)
    assert not err
    assert dist == 32, f"4 octets × 8 bits = 32, obtenu={dist}"


def test_T06_hamming_known_value(backend):
    """T06 — Distance Hamming de valeurs connues (0xCC vs 0xAA = 4 bits différents)."""
    # 0xCC = 11001100, 0xAA = 10101010 → XOR = 01100110 → 4 bits
    t_a = bytes([0xCC])
    t_b = bytes([0xAA])
    dist, err = backend.hamming_distance_concrete(t_a, t_b)
    assert not err
    assert dist == 4, f"0xCC XOR 0xAA = 0x66 = 4 bits, obtenu={dist}"


def test_T06b_hamming_multi_bytes_exact(backend):
    """T06b — Distance sur plusieurs octets = somme des distances par octet."""
    import random
    rng = random.Random(0xAB)
    template_a = bytes([rng.randint(0, 255) for _ in range(32)])
    template_b = bytes([rng.randint(0, 255) for _ in range(32)])
    dist_concrete, err = backend.hamming_distance_concrete(template_a, template_b)
    # Calcul de référence
    expected = sum(bin(a ^ b).count('1') for a, b in zip(template_a, template_b))
    assert not err
    assert dist_concrete == expected, f"Distance Concrete={dist_concrete} != attendu={expected}"


# ─── T07-T08 : fail-closed ────────────────────────────────────────────────────

def test_T07_fail_closed_empty_template(backend):
    """T07 — Template vide → error=True, distance=None (fail-closed)."""
    dist, err = backend.hamming_distance_concrete(b"", bytes([0x00, 0x01]))
    assert err, "Template vide doit produire error=True"
    assert dist is None


def test_T08_fail_closed_different_lengths(backend):
    """T08 — Longueurs différentes → error=True, distance=None (fail-closed)."""
    dist, err = backend.hamming_distance_concrete(bytes(4), bytes(8))
    assert err, "Longueurs différentes doivent produire error=True"
    assert dist is None


# ─── T09-T10 : fhe_uniqueness_check — MATCH / NO_MATCH ──────────────────────

def test_T09_uniqueness_match_found(backend):
    """T09 — Template quasi-identique (dist=2) sous seuil (threshold=10) → match_found=True."""
    new_t = bytes([0x41, 0x42, 0x43, 0x44] * 8)  # 32 octets
    # Template légèrement différent : 2 bits flippés au total
    stored = bytearray(new_t)
    stored[0] ^= 0x01  # 1 bit flip
    stored[1] ^= 0x02  # 1 bit flip
    stored_bytes = bytes(stored)

    result = backend.fhe_uniqueness_check(
        new_t,
        [("human-001", stored_bytes)],
        threshold_bits=10,
    )
    assert isinstance(result, ConcreteHammingResult)
    assert result.match_found is True, "dist=2 ≤ threshold=10 → match attendu"
    assert result.existing_human_id == "human-001"
    assert result.error is False
    assert result.unique_human_proven is False   # invariant absolu


def test_T10_uniqueness_no_match(backend):
    """T10 — Templates très différents (dist>>threshold) → match_found=False."""
    new_t = bytes([0x00] * 32)
    stored_t = bytes([0xFF] * 32)  # dist = 256 bits

    result = backend.fhe_uniqueness_check(
        new_t,
        [("human-002", stored_t)],
        threshold_bits=20,
    )
    assert result.match_found is False, "dist=256 > threshold=20 → no match"
    assert result.error is False
    assert result.unique_human_proven is False


# ─── T11-T12 : cas limites liste ────────────────────────────────────────────

def test_T11_uniqueness_empty_list(backend):
    """T11 — Liste vide → match_found=False, error=False (nouvelle identité autorisée)."""
    result = backend.fhe_uniqueness_check(
        bytes(32),
        [],
        threshold_bits=10,
    )
    assert result.match_found is False
    assert result.error is False  # liste vide = pas d'erreur


def test_T12_uniqueness_empty_new_template(backend):
    """T12 — new_template vide → error=True immédiatement (fail-closed)."""
    result = backend.fhe_uniqueness_check(
        b"",
        [("human-003", bytes(32))],
        threshold_bits=10,
    )
    assert result.error is True
    assert result.match_found is False


# ─── T13 : intégration check_uniqueness() routing FHE ───────────────────────

def test_T13_check_uniqueness_routing_concrete_fhe(backend):
    """T13 — check_uniqueness() avec fhe_circuit=ConcreteHammingBackend utilise le chemin FHE."""
    import base64
    from src.artcb.identity.biometric_onchain import (
        BiometricCommitment,
        check_uniqueness,
    )

    new_t = bytes([0xAB] * 32)
    stored_t = bytes([0xCD] * 32)  # dist > 0

    # BiometricCommitment minimal (template hash fictif)
    import hashlib
    commit = BiometricCommitment(
        commitment_hex="aa" * 32,
        blinding_hex="bb" * 32,
        template_hash_hex=hashlib.sha256(new_t).hexdigest(),
    )

    # Record existant avec template_bytes_b64
    existing = [{
        "human_id": "human-999",
        "template_bytes_b64": base64.b64encode(stored_t).decode(),
        "template_hash": hashlib.sha256(stored_t).hexdigest(),
    }]

    result = check_uniqueness(
        commit,
        existing,
        template_bytes_for_match=new_t,
        fhe_circuit=backend,
        threshold_bits=200,   # seuil très large → doit matcher
    )
    # match_method doit être "fhe_hamming"
    assert result.match_method == "fhe_hamming", (
        f"match_method attendu='fhe_hamming', obtenu='{result.match_method}'"
    )
    # templates différents → match_found dépend du seuil (200 bits > dist réel ?)
    dist_expected = sum(bin(a ^ b).count('1') for a, b in zip(new_t, stored_t))
    if dist_expected <= 200:
        assert result.match_found is True
    else:
        assert result.match_found is False
    assert result.unique_human_proven is False
    assert result.certified is False


# ─── T14 : invariants absolus ────────────────────────────────────────────────

def test_T14_invariants_always_false(backend):
    """T14 — unique_human_proven et certified toujours False dans ConcreteHammingResult."""
    result = ConcreteHammingResult(match_found=False)
    assert result.unique_human_proven is False, "unique_human_proven DOIT être False"
    assert result.certified is False, "certified DOIT être False"

    result2 = ConcreteHammingResult(match_found=True)
    assert result2.unique_human_proven is False
    assert result2.certified is False


# ─── T15 : champs debug ConcreteHammingResult ────────────────────────────────

def test_T15_concrete_result_debug_fields(backend):
    """T15 — ConcreteHammingResult expose les champs debug sans les divulguer dans repr."""
    new_t = bytes([0x10] * 16)
    stored_t = bytearray(new_t)
    stored_t[0] ^= 0x03   # 2 bits
    result = backend.fhe_uniqueness_check(
        new_t,
        [("human-debug", bytes(stored_t))],
        threshold_bits=5,
    )
    assert result._debug_hamming_distance is not None
    assert result._debug_threshold_bits == 5
    assert result._debug_total_bytes == 16
    # repr ne doit pas exposer la distance (champ repr=False)
    r = repr(result)
    assert "_debug_hamming_distance" not in r


# ─── T16 : duck-typing FheHammingCircuit ─────────────────────────────────────

def test_T16_duck_typing_fhe_hamming_circuit(backend):
    """T16 — ConcreteHammingBackend expose fhe_uniqueness_check() compatible FheHammingCircuit."""
    # Vérification de l'interface par inspection (duck-typing)
    assert callable(getattr(backend, "fhe_uniqueness_check", None)), (
        "fhe_uniqueness_check doit être callable"
    )
    assert callable(getattr(backend, "hamming_distance_concrete", None)), (
        "hamming_distance_concrete doit être callable"
    )


# ─── T17 : all_errors ────────────────────────────────────────────────────────

def test_T17_all_errors_if_all_invalid(backend):
    """T17 — Si toutes les paires sont invalides (longueurs différentes) → error=True."""
    new_t = bytes(32)
    existing = [
        ("human-X", bytes(16)),  # longueur différente → error
        ("human-Y", bytes(8)),   # longueur différente → error
    ]
    result = backend.fhe_uniqueness_check(new_t, existing, threshold_bits=10)
    assert result.error is True, "Toutes erreurs → error=True"
    assert result.match_found is False


# ─── T18 : cache partagé entre instances ─────────────────────────────────────

def test_T18_circuit_cache_shared_between_instances():
    """T18 — Deux instances ConcreteHammingBackend partagent le même circuit compilé."""
    b1 = ConcreteHammingBackend()
    b2 = ConcreteHammingBackend()
    assert b1._circuit is b2._circuit, (
        "Le cache module-level doit garantir un seul circuit compilé"
    )


# ─── T19 : note contient CONCRETE_FHE_NOTE ───────────────────────────────────

def test_T19_result_note_contains_concrete_note(backend):
    """T19 — Le champ note de ConcreteHammingResult contient CONCRETE_FHE_NOTE."""
    result = backend.fhe_uniqueness_check(bytes(4), [], threshold_bits=10)
    assert CONCRETE_FHE_NOTE in result.note, (
        f"note doit contenir CONCRETE_FHE_NOTE, obtenu: {result.note!r}"
    )


# ─── T20 : version MODULE_VERSION ────────────────────────────────────────────

def test_T20_module_version():
    """T20 — MODULE_VERSION de homomorphic.py est 1.3.0 (R487)."""
    from src.artcb.crypto.homomorphic import MODULE_VERSION
    assert MODULE_VERSION == "1.3.0", f"Attendu '1.3.0', obtenu '{MODULE_VERSION}'"
