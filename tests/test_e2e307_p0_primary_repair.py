"""R307 — P0 repair: primary_of(16/17) and repair script contract."""

from __future__ import annotations

from pathlib import Path

from artcb.consensus.pbft_view import primary_of
from artcb.node_registry import official_pbft_replica_ids


def test_primary_of_view16_is_ovh2_under_n5() -> None:
    ids = official_pbft_replica_ids()
    assert len(ids) == 5
    assert primary_of(16) == "ovh-node-2"
    assert primary_of(17) == "aws-node-3"
    assert ids[16 % 5] == "ovh-node-2"


def test_307_script_canonical_primary_of_no_wipe() -> None:
    text = (Path(__file__).resolve().parents[1] / "scripts" / "run_live307_p0_primary_repair.py").read_text(
        encoding="utf-8"
    )
    assert "primary_of(view)" in text
    assert "certified_100" in text.lower() or "CERTIFIED_100" in text
    assert "wipe" in text.lower()
    assert "False" in text or "false" in text
    assert "view-change" in text
