"""Phase 222 — deterministic public-tip import (T-E48 / V-01-C..F).

Receive and pull must return the same verdict for the same block.
V-01 is not a certification of the whole network.
"""

from __future__ import annotations

from pathlib import Path

from artcb.authz.anchor import anchor_public_commitment, commitment_public_symbols
from artcb.chain import ffi
from artcb.chain.ffi import HASH_VERSION_V1
from artcb.chain.manager import ChainManager
from artcb.p2p.public_archive import PublicBlockArchive
from artcb.p2p.sync import P2PSyncService, decide_public_import


def _rehash(block: dict) -> dict:
    row = dict(block)
    version = int(row.get("hash_version") or HASH_VERSION_V1)
    eco = None
    if version >= 2:
        eco = str(row.get("economic_root") or (row.get("economics") or {}).get("economic_root") or "")
    row["hash"] = ffi.build_block_hash(
        int(row["index"]),
        str(row["timestamp"]),
        str(row["prev_hash"]),
        str(row["graph_root"]),
        str(row.get("merkle_root") or row["graph_root"]),
        float(row["pol_score"]),
        economic_root=eco,
    )
    return row


def _svc(chain: ChainManager, tmp: Path) -> P2PSyncService:
    svc = object.__new__(P2PSyncService)
    svc.chain = chain
    svc.archive = PublicBlockArchive(tmp)
    svc.symbol_sync = None
    svc.last_import_decisions = []
    return svc


def _pair(tmp_path: Path) -> tuple[ChainManager, ChainManager, Path]:
    key = tmp_path / "chain.key"
    path_a = tmp_path / "a" / "blocks.jsonl"
    path_b = tmp_path / "b" / "blocks.jsonl"
    chain_a = ChainManager(path_a, key_path=key, enable_security=False)
    chain_a.append_block(
        graph_id="genesis",
        graph_root="root0",
        pol_score=0.0,
        visibility="public",
        block_reward=0,
        source="authz_commitment",
    )
    path_b.parent.mkdir(parents=True)
    path_b.write_text(path_a.read_text(encoding="utf-8"), encoding="utf-8")
    chain_b = ChainManager(path_b, key_path=key, enable_security=False)
    return chain_a, chain_b, key


def _commitment(chain: ChainManager, domain_id: str, content_hash: str | None = None) -> dict:
    digest = content_hash or (domain_id.encode().hex().ljust(64, "0")[:64])
    symbols = commitment_public_symbols(
        kind="org",
        domain_id=domain_id,
        content_hash=digest,
        parent_id="ARTCB",
        issuer="artcb1alicexxxxxxxxxxxxxxxx",
        issued_at="2026-09-05T00:00:00Z",
    )
    anchor_public_commitment(chain, symbols=symbols)
    return chain.list_blocks(visibility="public")[-1]


def test_receive_and_pull_same_verdict_for_same_block(tmp_path: Path) -> None:
    chain_a, chain_b, _ = _pair(tmp_path)
    block = _commitment(chain_a, "domain_same")
    local = chain_b._read_all_blocks()
    kwargs = dict(
        local_len=len(local),
        local_tip=chain_b.last_hash(),
        local_hashes={str(r.get("hash") or "") for r in local},
        structure_ok=P2PSyncService.verify_block_structure(block),
    )
    via_receive = decide_public_import(block, **kwargs)
    via_pull = decide_public_import(block, **kwargs)
    assert via_receive == via_pull
    assert via_receive.action == "append"


def test_g_duplicate_does_not_append_twice(tmp_path: Path) -> None:
    chain_a, chain_b, _ = _pair(tmp_path)
    block = _commitment(chain_a, "domain_dup")
    svc = _svc(chain_b, tmp_path / "b")
    first = svc.import_public_blocks([block], from_node_id="ovh1")
    tip = chain_b.last_hash()
    height = len(chain_b._read_all_blocks())
    second = svc.import_public_blocks([block, block], from_node_id="ovh1")
    assert first >= 1
    assert chain_b.last_hash() == tip
    assert len(chain_b._read_all_blocks()) == height
    assert any(d.action == "duplicate" for d in svc.last_import_decisions)


def test_h_wrong_prev_hash_rejected(tmp_path: Path) -> None:
    chain_a, chain_b, _ = _pair(tmp_path)
    block = _rehash({**_commitment(chain_a, "domain_prev"), "prev_hash": "00" * 32})
    svc = _svc(chain_b, tmp_path / "b")
    before = chain_b.last_hash()
    svc.import_public_blocks([block], from_node_id="evil")
    assert chain_b.last_hash() == before
    assert any(d.reason == "wrong_prev_hash" for d in svc.last_import_decisions)


def test_i_wrong_index_rejected(tmp_path: Path) -> None:
    chain_a, chain_b, _ = _pair(tmp_path)
    block = _commitment(chain_a, "domain_idx")
    # B is at height 1; skip to index 7
    forged = _rehash({**block, "index": 7})
    svc = _svc(chain_b, tmp_path / "b")
    before = len(chain_b._read_all_blocks())
    svc.import_public_blocks([forged], from_node_id="evil")
    assert len(chain_b._read_all_blocks()) == before
    reasons = {d.reason for d in svc.last_import_decisions}
    assert "wrong_index" in reasons or "hash_mismatch" in reasons


def test_j_forged_hash_rejected(tmp_path: Path) -> None:
    chain_a, chain_b, _ = _pair(tmp_path)
    block = dict(_commitment(chain_a, "domain_hash"))
    block["hash"] = "ff" * 32
    svc = _svc(chain_b, tmp_path / "b")
    before = chain_b.last_hash()
    svc.import_public_blocks([block], from_node_id="evil")
    assert chain_b.last_hash() == before
    assert svc.last_import_decisions[-1].action == "reject"
    assert svc.last_import_decisions[-1].reason == "hash_mismatch"


def test_k_arbitrary_event_does_not_extend_tip(tmp_path: Path) -> None:
    chain_a, chain_b, _ = _pair(tmp_path)
    legit = _commitment(chain_a, "domain_k")
    fake = dict(legit)
    fake["public_symbols"] = {
        **(legit.get("public_symbols") or {}),
        "artcb_event": "I_AM_A_MINER_NOW",
    }
    svc = _svc(chain_b, tmp_path / "b")
    before = chain_b.last_hash()
    svc.import_public_blocks([fake], from_node_id="evil")
    assert chain_b.last_hash() == before
    assert svc.last_import_decisions[-1].action == "archive_only"
    assert svc.last_import_decisions[-1].reason == "not_converging_event"


def test_m_concurrent_producers_do_not_silently_merge(tmp_path: Path) -> None:
    chain_a, chain_b, _ = _pair(tmp_path)
    _commitment(chain_a, "org_x")
    _commitment(chain_b, "org_y")
    assert chain_a.last_hash() != chain_b.last_hash()
    svc_a = _svc(chain_a, tmp_path / "aa")
    before_a = chain_a.last_hash()
    height_a = len(chain_a._read_all_blocks())
    svc_a.import_public_blocks(chain_b.list_blocks(visibility="public"), from_node_id="ovh2")
    assert chain_a.last_hash() == before_a
    assert len(chain_a._read_all_blocks()) == height_a
    reasons = {d.reason for d in svc_a.last_import_decisions}
    assert "wrong_index" in reasons or "wrong_prev_hash" in reasons or "already_on_chain" in reasons
