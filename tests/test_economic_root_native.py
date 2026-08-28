"""Native C EconomicRoot v2 vs historic v1."""

from __future__ import annotations

from pathlib import Path

from src.artcb.chain import ffi
from src.artcb.chain.manager import ChainManager
from src.artcb.economics.economic_root import economic_root, native_economic_root_available
from src.artcb.economics.settlement import MachineContribution, settle_block
from src.artcb.tokenomics import SATOSHI_PER_ARTCB


def test_c_abi_reports_v2() -> None:
    assert native_economic_root_available() is True
    assert ffi.hash_abi_version() == 2
    assert ffi.has_economic_root_abi() is True


def test_v1_empty_root_equals_six_field_hash() -> None:
    a = ffi.build_block_hash(1, "ts", "p" * 64, "g" * 64, "m" * 64, 0.7)
    b = ffi.build_block_hash(1, "ts", "p" * 64, "g" * 64, "m" * 64, 0.7, economic_root=None)
    c = ffi.build_block_hash(1, "ts", "p" * 64, "g" * 64, "m" * 64, 0.7, economic_root="")
    assert a == b == c
    assert len(a) == 64


def test_v2_root_changes_hash() -> None:
    root_a = "a" * 64
    root_b = "b" * 64
    ha = ffi.build_block_hash(1, "ts", "p" * 64, "g" * 64, "m" * 64, 0.7, economic_root=root_a)
    hb = ffi.build_block_hash(1, "ts", "p" * 64, "g" * 64, "m" * 64, 0.7, economic_root=root_b)
    h0 = ffi.build_block_hash(1, "ts", "p" * 64, "g" * 64, "m" * 64, 0.7)
    assert ha != hb
    assert ha != h0


def test_chain_v1_block_still_verifies(tmp_path: Path) -> None:
    chain = ChainManager(tmp_path / "blocks.jsonl", key_path=tmp_path / "k", enable_security=False)
    block = chain.append_block(graph_id="g", graph_root="a" * 64, pol_score=0.81)
    assert block.hash_version == 1
    assert chain.verify()["valid"] is True


def test_chain_v2_settlement_verifies_and_detects_tamper(tmp_path: Path) -> None:
    chain = ChainManager(tmp_path / "blocks.jsonl", key_path=tmp_path / "k", enable_security=False)
    contributors = [
        {
            "address": "A",
            "owner_address": "A",
            "machine_index": 1,
            "machine_id": "M1",
            "pol_score": 0.9,
            "signature": "",
        }
    ]
    block = chain.append_block(
        graph_id="g",
        graph_root="b" * 64,
        pol_score=0.9,
        contributors=contributors,
        block_reward=50 * SATOSHI_PER_ARTCB,
        verified_humans=0,
    )
    assert block.hash_version == 2
    assert block.economics and block.economics["economic_root"]
    assert chain.verify()["valid"] is True
    lines = chain.blocks_path.read_text(encoding="utf-8").splitlines()
    tampered = lines[0].replace(block.economics["economic_root"], "c" * 64, 1)
    evil = tmp_path / "evil.jsonl"
    evil.write_text(tampered + "\n", encoding="utf-8")
    valid, message = ffi.verify_chain_file(evil)
    assert valid is False
    assert "hash mismatch" in message or "mismatch" in message.lower()


def test_python_economic_root_still_sensitive() -> None:
    r = 50 * SATOSHI_PER_ARTCB
    machines = [MachineContribution("A1", "A", 1, None, 1.0)]
    live = settle_block(r_block_satoshi=r, verified_humans=0, machines=machines)
    a = economic_root(live.economic_parts)
    b = economic_root({**live.economic_parts, "r_block_satoshi": r + 1})
    assert a != b
