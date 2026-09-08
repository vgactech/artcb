"""R270 certification matrix unit tests — no live network."""

from __future__ import annotations

from artcb.consensus.live_bft import n_f_q
from artcb.consensus.pbft_certification_matrix import (
    CRITICAL_IDS,
    REQUIRED,
    apply_result,
    finalize,
    independent_safety,
    new_matrix,
)


def test_n_f_q_four() -> None:
    n, f, q = n_f_q(4)
    assert (n, f, q) == (4, 1, 3)


def test_matrix_covers_required_and_critical() -> None:
    matrix = new_matrix()
    ids = [r["id"] for r in matrix["rows"]]
    assert ids == [s["id"] for s in REQUIRED]
    assert set(CRITICAL_IDS) <= set(ids)
    assert matrix["certified_100"] is False
    assert matrix["global_verdict"] == "NOT_PROVEN"


def test_one_missing_critical_blocks_certified_100() -> None:
    matrix = new_matrix()
    for row in matrix["rows"]:
        apply_result(matrix, row["id"], verdict="PASS", result="PASS", live_wan="PASS", level="L6")
    apply_result(matrix, "PBFT-N04", verdict="NOT_PROVEN", result="NOT_PROVEN", live_wan="NOT_EXECUTED")
    finalize(matrix)
    assert matrix["certified_100"] is False
    assert matrix["global_verdict"] == "PARTIALLY_VERIFIED"


def test_fail_is_not_certified() -> None:
    matrix = new_matrix()
    for row in matrix["rows"]:
        apply_result(matrix, row["id"], verdict="PASS", result="PASS")
    apply_result(matrix, "PBFT-S01", verdict="FAIL", result="FAIL")
    apply_result(matrix, "PBFT-X01", verdict="PASS", result="PASS")
    apply_result(matrix, "PBFT-X02", verdict="PASS", result="PASS")
    finalize(matrix)
    assert matrix["certified_100"] is False
    assert matrix["global_verdict"] == "NOT_CERTIFIED"
    assert matrix["bft_settlement"] == "PASS"
    assert matrix["bft_block_consensus"] == "PARTIAL"


def test_independent_safety_detects_divergence() -> None:
    snap = {
        "ovh-node-1": {"height": 10, "last_hash": "aa", "view": 1, "git_sha": "x"},
        "ovh-node-2": {"height": 10, "last_hash": "bb", "view": 1, "git_sha": "x"},
        "aws-node-3": {"height": 10, "last_hash": "aa", "view": 1, "git_sha": "x"},
        "ovh-node-4": {"height": 10, "last_hash": "aa", "view": 1, "git_sha": "x"},
    }
    got = independent_safety(snap)
    assert got["converged"] is False
    assert got["hash_unique"] == 2
