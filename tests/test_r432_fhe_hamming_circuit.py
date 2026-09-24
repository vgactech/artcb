"""Tests R432 — FHE Hamming Circuit : vérification d'unicité biométrique via TFHE simulé.

Critères R432 (spec fournie) :
    A — FHE réel : check_uniqueness() exécute effectivement un calcul FHE
    B — Aucun template clair côté serveur (FheCiphertext opaque)
    C — Calcul de distance : D(A,B) = Σ XOR(A_i, B_i)
    D — Seuil : circuit retourne uniquement MATCH / NO_MATCH (anti-oracle)
    E — Tests complets : même, bruit, différent, limite exacte, seuil+1, ciphertext invalide
    F — Fail-closed : erreur cryptographique → UNKNOWN/ERROR → refus
    G — Invariants : unique_human_proven=False, certified=False dans tous les chemins

Périmètre :
    E01→E05  : FheHammingCircuit unitaire (circuit seul)
    I01→I08  : Intégration check_uniqueness() avec fhe_circuit
    F01→F06  : Fail-closed et anti-oracle
    G01→G04  : Invariants

MODE DEBUG actif. CERTIFIED_100=false.
"""

from __future__ import annotations

import base64
import os
from unittest.mock import patch

import pytest

from src.artcb.crypto.homomorphic import (
    FHE_CIRCUIT_PROTOCOL,
    FHE_SIMULATION_NOTE,
    FheCiphertext,
    FheHammingCircuit,
    FheUint,
    FheUniquenessResult,
)
from src.artcb.identity.biometric_onchain import (
    UniquenessCheckResult,
    _check_uniqueness_fhe,
    _extract_template_bytes_from_record,
    check_uniqueness,
)
from src.artcb.crypto.homomorphic import commit_biometric_template


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_record(human_id: str, template: bytes) -> dict:
    """Crée un enregistrement on-chain minimal avec template_bytes_b64."""
    return {
        "human_id": human_id,
        "template_bytes_b64": base64.b64encode(template).decode(),
        "template_hash": f"hash_{human_id}",
        "commitment": "aa" * 64,
    }


def _make_template(size: int = 32, seed: int = 0) -> bytes:
    """Génère un template de taille fixe (reproductible)."""
    return bytes((i + seed) % 256 for i in range(size))


def _flip_bits(template: bytes, n_bits: int) -> bytes:
    """Retourne une copie du template avec exactement n_bits flippés."""
    lst = bytearray(template)
    flipped = 0
    for byte_idx in range(len(lst)):
        for bit_pos in range(8):
            if flipped >= n_bits:
                break
            lst[byte_idx] ^= (1 << bit_pos)
            flipped += 1
        if flipped >= n_bits:
            break
    return bytes(lst)


# ═══════════════════════════════════════════════════════════════════════════════
# E — FheHammingCircuit unitaire
# ═══════════════════════════════════════════════════════════════════════════════

class TestFheCircuitUnit:
    """E01→E05 — Tests du circuit FHE Hamming seul."""

    def test_e01_encrypt_returns_ciphertext(self) -> None:
        """E01 — encrypt() retourne un FheCiphertext opaque (jamais les bytes clairs)."""
        circuit = FheHammingCircuit()
        template = _make_template(32)
        ct = circuit.encrypt(template)

        assert isinstance(ct, FheCiphertext)
        # Propriété : le repr ne révèle pas le template
        repr_str = repr(ct)
        assert "REDACTED" in repr_str
        assert template.hex() not in repr_str
        assert template.decode("latin-1") not in repr_str

    def test_e02_hamming_distance_zero_same_template(self) -> None:
        """E02 — D(A,A) = 0 (même template)."""
        circuit = FheHammingCircuit()
        t = _make_template(32)
        fhe_uint = circuit.fhe_hamming(t, t)

        assert not fhe_uint._error_flag
        assert fhe_uint._value == 0

    def test_e03_hamming_distance_exact_bits(self) -> None:
        """E03 — D(A,B) = n_bits pour exactement n_bits flippés."""
        circuit = FheHammingCircuit()
        t_a = _make_template(32)

        for n in [1, 8, 16, 32, 64]:
            t_b = _flip_bits(t_a, n)
            fhe_uint = circuit.fhe_hamming(t_a, t_b)
            assert not fhe_uint._error_flag, f"n={n}: error_flag inattendu"
            assert fhe_uint._value == n, f"n={n}: attendu {n}, obtenu {fhe_uint._value}"

    def test_e04_decrypt_match_only_returns_bool(self) -> None:
        """E04 — decrypt_match() retourne (bool, bool) — pas la distance brute (anti-oracle)."""
        circuit = FheHammingCircuit()
        t_a = _make_template(32)
        t_b = _flip_bits(t_a, 5)

        fhe_uint = circuit.fhe_hamming(t_a, t_b)
        result = circuit.decrypt_match(fhe_uint, threshold_bits=10)

        assert isinstance(result, tuple)
        assert len(result) == 2
        match, error = result
        assert isinstance(match, bool)
        assert isinstance(error, bool)
        # La distance n'est pas exposée
        assert match is True    # 5 ≤ 10
        assert error is False

    def test_e05_threshold_boundary(self) -> None:
        """E05 — Limite exacte du seuil : dist=T → MATCH, dist=T+1 → NO_MATCH."""
        circuit = FheHammingCircuit()
        t_a = _make_template(32)

        for threshold in [0, 5, 16, 32, 63]:
            t_exact = _flip_bits(t_a, threshold)
            t_over = _flip_bits(t_a, threshold + 1)

            uint_exact = circuit.fhe_hamming(t_a, t_exact)
            uint_over = circuit.fhe_hamming(t_a, t_over)

            match_exact, _ = circuit.decrypt_match(uint_exact, threshold_bits=threshold)
            match_over, _ = circuit.decrypt_match(uint_over, threshold_bits=threshold)

            assert match_exact is True, f"threshold={threshold}: dist=T doit être MATCH"
            assert match_over is False, f"threshold={threshold}: dist=T+1 doit être NO_MATCH"

    def test_e06_different_templates_no_match(self) -> None:
        """E06 — Deux templates très différents (>50% bits flippés) → NO_MATCH avec seuil 5%."""
        circuit = FheHammingCircuit()
        t_a = _make_template(32, seed=0)
        t_b = _make_template(32, seed=128)  # template complètement différent

        fhe_uint = circuit.fhe_hamming(t_a, t_b)
        threshold_bits = int(0.05 * 32 * 8)  # 5% de 256 bits = 12 bits
        match, error = circuit.decrypt_match(fhe_uint, threshold_bits=threshold_bits)

        assert error is False
        # Les templates seed=0 et seed=128 diffèrent sur ~50% des bits → no match à 5%
        assert match is False

    def test_e07_encrypt_empty_raises(self) -> None:
        """E07 — encrypt() sur template vide → ValueError (fail-closed)."""
        circuit = FheHammingCircuit()
        with pytest.raises(ValueError, match="vide"):
            circuit.encrypt(b"")

    def test_e08_fhe_uniqueness_check_no_match(self) -> None:
        """E08 — fhe_uniqueness_check() : nouveau template unique → match_found=False."""
        circuit = FheHammingCircuit()
        new_t = _make_template(32, seed=0)
        existing = [
            ("human-001", _make_template(32, seed=200)),
            ("human-002", _make_template(32, seed=201)),
        ]
        result = circuit.fhe_uniqueness_check(new_t, existing, threshold_bits=5)

        assert result.match_found is False
        assert result.error is False
        assert result.unique_human_proven is False
        assert result.certified is False
        assert result.match_method == "fhe_hamming"

    def test_e09_fhe_uniqueness_check_match_found(self) -> None:
        """E09 — fhe_uniqueness_check() : template quasi-identique → match_found=True."""
        circuit = FheHammingCircuit()
        new_t = _make_template(32, seed=0)
        stored_t = _flip_bits(new_t, 3)   # 3 bits de bruit
        existing = [("human-abc", stored_t)]

        result = circuit.fhe_uniqueness_check(new_t, existing, threshold_bits=10)

        assert result.match_found is True
        assert result.existing_human_id == "human-abc"
        assert result.error is False
        assert result.unique_human_proven is False


# ═══════════════════════════════════════════════════════════════════════════════
# I — Intégration check_uniqueness() avec fhe_circuit
# ═══════════════════════════════════════════════════════════════════════════════

class TestCheckUniquenessIntegration:
    """I01→I08 — check_uniqueness() avec fhe_circuit fourni (chemin priorité 0)."""

    def test_i01_fhe_path_used_when_circuit_provided(self) -> None:
        """I01 — Avec fhe_circuit fourni, match_method = 'fhe_hamming'."""
        circuit = FheHammingCircuit()
        new_t = _make_template(32, seed=0)
        commitment = commit_biometric_template(new_t)
        records = [_make_record("human-i01", _make_template(32, seed=200))]

        result = check_uniqueness(
            commitment,
            records,
            template_bytes_for_match=new_t,
            fhe_circuit=circuit,
        )

        assert result.match_method == "fhe_hamming"
        assert result.match_found is False
        assert result.unique_human_proven is False
        assert result.certified is False

    def test_i02_fhe_detects_duplicate(self) -> None:
        """I02 — fhe_circuit détecte un template quasi-identique comme doublon."""
        circuit = FheHammingCircuit()
        original = _make_template(32, seed=10)
        noisy = _flip_bits(original, 4)     # 4 bits de bruit
        commitment_noisy = commit_biometric_template(noisy)
        records = [_make_record("human-original", original)]

        result = check_uniqueness(
            commitment_noisy,
            records,
            template_bytes_for_match=noisy,
            threshold_bits=10,
            fhe_circuit=circuit,
        )

        assert result.match_found is True
        assert result.existing_human_id == "human-original"
        assert result.match_method == "fhe_hamming"
        assert result.unique_human_proven is False

    def test_i03_no_fhe_circuit_falls_back_to_hamming_direct(self) -> None:
        """I03 — Sans fhe_circuit, le routing tombe sur hamming_direct (non-régression R434)."""
        new_t = _make_template(32, seed=0)
        commitment = commit_biometric_template(new_t)
        records = [_make_record("human-i03", _make_template(32, seed=200))]

        result = check_uniqueness(
            commitment,
            records,
            template_bytes_for_match=new_t,
            fhe_circuit=None,  # explicitement None
        )

        assert result.match_method == "hamming_direct"
        assert result.match_found is False

    def test_i04_fhe_empty_records_no_match(self) -> None:
        """I04 — Registre vide avec fhe_circuit → match_found=False, error=False."""
        circuit = FheHammingCircuit()
        new_t = _make_template(32, seed=0)
        commitment = commit_biometric_template(new_t)

        result = check_uniqueness(
            commitment,
            [],  # registre vide
            template_bytes_for_match=new_t,
            fhe_circuit=circuit,
        )

        # Registre vide : pas de comparaison, pas de match
        # Peut utiliser fhe_hamming ou fallback, mais jamais match_found=True
        assert result.match_found is False
        assert result.unique_human_proven is False

    def test_i05_fhe_without_template_bytes_falls_back_to_exact_hash(self) -> None:
        """I05 — fhe_circuit fourni mais sans template_bytes → fallback exact_hash."""
        circuit = FheHammingCircuit()
        new_t = _make_template(32, seed=5)
        commitment = commit_biometric_template(new_t)
        # Records sans template_bytes — juste des hashes
        records = [{"human_id": "human-i05", "template_hash": "differenthash"}]

        result = check_uniqueness(
            commitment,
            records,
            template_bytes_for_match=None,  # pas de template bytes
            fhe_circuit=circuit,
        )

        assert result.match_method == "exact_hash"
        assert result.match_found is False

    def test_i06_fhe_threshold_bits_from_ratio(self) -> None:
        """I06 — threshold_bits calculé depuis threshold (1-threshold)*bits_len."""
        circuit = FheHammingCircuit()
        new_t = _make_template(32, seed=0)  # 256 bits
        # threshold=0.90 → threshold_bits = round(0.10 * 256) = 26 bits
        stored_with_25_bits_noise = _flip_bits(new_t, 25)
        commitment = commit_biometric_template(new_t)
        records = [_make_record("human-i06", stored_with_25_bits_noise)]

        result = check_uniqueness(
            commitment,
            records,
            template_bytes_for_match=new_t,
            threshold=0.90,        # threshold_bits sera calculé
            threshold_bits=None,   # laisser calculer
            fhe_circuit=circuit,
        )

        # 25 bits noise ≤ 26 bits threshold → MATCH
        assert result.match_found is True
        assert result.match_method == "fhe_hamming"

    def test_i07_fhe_result_has_correct_fields(self) -> None:
        """I07 — UniquenessCheckResult issu de FHE a les champs requis."""
        circuit = FheHammingCircuit()
        new_t = _make_template(32, seed=0)
        commitment = commit_biometric_template(new_t)
        records = [_make_record("human-i07", _make_template(32, seed=200))]

        result = check_uniqueness(
            commitment,
            records,
            template_bytes_for_match=new_t,
            fhe_circuit=circuit,
        )

        assert hasattr(result, "match_found")
        assert hasattr(result, "match_method")
        assert hasattr(result, "unique_human_proven")
        assert hasattr(result, "certified")
        assert result.unique_human_proven is False
        assert result.certified is False

    def test_i08_extract_template_bytes_from_record_b64(self) -> None:
        """I08 — _extract_template_bytes_from_record() lit template_bytes_b64 correctement."""
        template = _make_template(32)
        rec = _make_record("human-i08", template)
        extracted = _extract_template_bytes_from_record(rec)
        assert extracted == template

    def test_i09_extract_template_bytes_from_record_hex(self) -> None:
        """I09 — _extract_template_bytes_from_record() lit template_bytes_hex correctement."""
        template = _make_template(32)
        rec = {
            "human_id": "human-i09",
            "template_bytes_hex": template.hex(),
        }
        extracted = _extract_template_bytes_from_record(rec)
        assert extracted == template

    def test_i10_extract_returns_none_when_absent(self) -> None:
        """I10 — _extract_template_bytes_from_record() retourne None si aucun champ."""
        rec = {"human_id": "human-i10", "template_hash": "abc"}
        result = _extract_template_bytes_from_record(rec)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# F — Fail-closed et anti-oracle (critère R432-D, R432-F)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFheFailClosed:
    """F01→F06 — Fail-closed, anti-oracle, tailles invalides."""

    def test_f01_size_mismatch_returns_error(self) -> None:
        """F01 — Tailles incompatibles → FheUint.error_flag=True → fail-closed."""
        circuit = FheHammingCircuit()
        t_a = _make_template(32)
        t_b = _make_template(16)   # taille différente

        fhe_uint = circuit.fhe_hamming(t_a, t_b)
        assert fhe_uint._error_flag is True

        match, error = circuit.decrypt_match(fhe_uint, threshold_bits=10)
        assert error is True
        assert match is False  # fail-closed : jamais MATCH si error

    def test_f02_empty_template_returns_error(self) -> None:
        """F02 — Template vide dans fhe_hamming → error_flag=True."""
        circuit = FheHammingCircuit()
        fhe_uint = circuit.fhe_hamming(b"", _make_template(32))
        assert fhe_uint._error_flag is True

        match, error = circuit.decrypt_match(fhe_uint, threshold_bits=10)
        assert error is True
        assert match is False

    def test_f03_negative_threshold_returns_error(self) -> None:
        """F03 — Seuil négatif → decrypt_match retourne error=True."""
        circuit = FheHammingCircuit()
        t = _make_template(32)
        fhe_uint = circuit.fhe_hamming(t, t)

        match, error = circuit.decrypt_match(fhe_uint, threshold_bits=-1)
        assert error is True
        assert match is False

    def test_f04_no_template_in_existing_no_error(self) -> None:
        """F04 — fhe_uniqueness_check() avec templates existants sans bytes → no match, no error."""
        circuit = FheHammingCircuit()
        new_t = _make_template(32)
        # Pas de bytes dans les records
        result = circuit.fhe_uniqueness_check(new_t, [], threshold_bits=10)
        assert result.match_found is False
        assert result.error is False

    def test_f05_all_errors_produces_error_flag(self) -> None:
        """F05 — Si tous les calculs sont en erreur (tailles incompatibles), error=True."""
        circuit = FheHammingCircuit()
        new_t = _make_template(32)
        # Stored templates de taille différente → tous en erreur
        existing = [
            ("human-f05a", _make_template(16)),  # taille différente
            ("human-f05b", _make_template(64)),  # taille différente
        ]
        result = circuit.fhe_uniqueness_check(new_t, existing, threshold_bits=10)

        assert result.match_found is False
        assert result.error is True  # tous les calculs sont en erreur

    def test_f06_empty_new_template_returns_error(self) -> None:
        """F06 — new_template vide dans fhe_uniqueness_check → error=True (fail-closed)."""
        circuit = FheHammingCircuit()
        result = circuit.fhe_uniqueness_check(b"", [], threshold_bits=10)
        assert result.error is True
        assert result.match_found is False


# ═══════════════════════════════════════════════════════════════════════════════
# G — Invariants absolus (critère R432-G)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFheInvariants:
    """G01→G04 — unique_human_proven=False, certified=False dans tous les cas."""

    def test_g01_fhe_uniqueness_result_invariants_no_match(self) -> None:
        """G01 — FheUniquenessResult.unique_human_proven=False et certified=False (no match)."""
        circuit = FheHammingCircuit()
        t = _make_template(32, seed=0)
        existing = [("human-g01", _make_template(32, seed=200))]
        result = circuit.fhe_uniqueness_check(t, existing, threshold_bits=5)

        assert result.unique_human_proven is False
        assert result.certified is False
        assert result.match_method == "fhe_hamming"

    def test_g02_fhe_uniqueness_result_invariants_match(self) -> None:
        """G02 — FheUniquenessResult.unique_human_proven=False même si match_found=True."""
        circuit = FheHammingCircuit()
        t = _make_template(32, seed=0)
        stored = _flip_bits(t, 2)
        result = circuit.fhe_uniqueness_check(t, [("human-g02", stored)], threshold_bits=10)

        assert result.match_found is True
        assert result.unique_human_proven is False
        assert result.certified is False

    def test_g03_check_uniqueness_fhe_path_invariants(self) -> None:
        """G03 — UniquenessCheckResult issu du chemin fhe_hamming maintient les invariants."""
        circuit = FheHammingCircuit()
        new_t = _make_template(32, seed=0)
        commitment = commit_biometric_template(new_t)
        records = [_make_record("human-g03", _make_template(32, seed=200))]

        result = check_uniqueness(
            commitment,
            records,
            template_bytes_for_match=new_t,
            fhe_circuit=circuit,
        )

        assert result.unique_human_proven is False
        assert result.certified is False
        assert result.match_method == "fhe_hamming"

    def test_g04_module_version_is_r432(self) -> None:
        """G04 — MODULE_VERSION de homomorphic.py est 1.1.1 (R432 auto-versioning)."""
        import src.artcb.crypto.homomorphic as hom
        assert hom.MODULE_VERSION == "1.1.1", (
            f"Attendu 1.1.1, obtenu {hom.MODULE_VERSION}"
        )

    def test_g05_protocol_constant(self) -> None:
        """G05 — FHE_CIRCUIT_PROTOCOL = 'ARTCB-FHE-HAMMING-v1'."""
        assert FHE_CIRCUIT_PROTOCOL == "ARTCB-FHE-HAMMING-v1"

    def test_g06_simulation_note_present(self) -> None:
        """G06 — FHE_SIMULATION_NOTE mentionne la nature simulée (honnêteté ARTCB)."""
        assert "SIMULATION" in FHE_SIMULATION_NOTE
        assert "Concrete" in FHE_SIMULATION_NOTE
