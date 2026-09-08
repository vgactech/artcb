"""R271 — overlay + honest N04/N06 marking. No live network."""

from __future__ import annotations

from artcb.consensus.pbft_certification_matrix import finalize, new_matrix

from scripts.run_live271_close_not_proven import THE_18, _mark, _overlay_r270


def test_eighteen_ids_match_r270_not_proven() -> None:
    assert len(THE_18) == 18
    assert "PBFT-X01" in THE_18
    assert "PBFT-N04" in THE_18
    assert "PBFT-C04" in THE_18


def test_overlay_keeps_r270_passes_and_leaves_the_18() -> None:
    matrix = new_matrix()
    info = _overlay_r270(matrix)
    assert info["copied"] >= 20
    leftover = {r["id"]: r["verdict"] for r in matrix["rows"] if r["id"] in THE_18}
    assert set(leftover) == set(THE_18)
    assert all(v == "NOT_PROVEN" for v in leftover.values())
    passed = [r for r in matrix["rows"] if r["verdict"] == "PASS"]
    assert all(r["id"] not in THE_18 for r in passed)


def test_n04_fail_without_1pct_liveness() -> None:
    matrix = new_matrix()
    _mark(matrix, "PBFT-N04", False, level="L5", proof="safety only, no 1% round")
    finalize(matrix)
    row = next(r for r in matrix["rows"] if r["id"] == "PBFT-N04")
    assert row["verdict"] == "FAIL"
    assert matrix["certified_100"] is False
