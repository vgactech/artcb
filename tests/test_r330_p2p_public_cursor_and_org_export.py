"""R330 — P2P public sync cursor ignores private suffix; domain export/import hash."""

from __future__ import annotations

import json
from pathlib import Path

from artcb.authz.genesis import GenesisStore
from artcb.authz.registry import DomainRegistry, build_export_bundle, verify_export_bundle
from artcb.chain.manager import ChainManager, GENESIS_PREV_HASH
from artcb.p2p.sync import decide_public_import, public_sync_cursor


def test_public_sync_cursor_ignores_private_suffix(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARTCB_SPLIT_LEDGER", "1")
    blocks = tmp_path / "blocks.jsonl"
    rows = [
        {
            "index": 10,
            "timestamp": "2026-09-12T00:00:00Z",
            "prev_hash": GENESIS_PREV_HASH,
            "hash": "a" * 64,
            "visibility": "public",
            "signature": "ed25519:" + ("ab" * 32),
            "graph_root": "g" * 64,
            "merkle_root": "g" * 64,
            "pol_score": 0.1,
            "graph_id": "p10",
        }
    ]
    for i in range(50):
        rows.append(
            {
                "index": 100 + i,
                "timestamp": "2026-09-12T00:01:00Z",
                "prev_hash": "x" * 64,
                "hash": f"{i:064x}",
                "visibility": "private",
                "signature": "ed25519:" + ("cd" * 32),
                "graph_root": "p" * 64,
                "merkle_root": "p" * 64,
                "pol_score": 0.1,
                "graph_id": f"priv{i}",
            }
        )
    blocks.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    mgr = ChainManager(blocks, key_path=tmp_path / "k", enable_security=False)
    next_idx, tip, hashes = public_sync_cursor(mgr)
    assert next_idx == 11
    assert tip == "a" * 64
    assert "a" * 64 in hashes
    # decide next public
    nxt = {
        "index": 11,
        "visibility": "public",
        "hash": "b" * 64,
        "prev_hash": "a" * 64,
        "signature": "ed25519:" + ("ab" * 32),
        "graph_root": "g" * 64,
        "merkle_root": "g" * 64,
        "pol_score": 0.1,
        "timestamp": "2026-09-12T00:02:00Z",
        "graph_id": "p11",
    }
    # structure_ok false → reject hash; we only check index/prev path
    d = decide_public_import(
        nxt,
        local_len=next_idx,
        local_tip=tip,
        local_hashes=hashes,
        structure_ok=True,
        check_signature_envelope=False,
    )
    assert d.action in ("append", "reject")  # signature may fail
    assert d.reason != "wrong_index"
    assert d.reason != "wrong_prev_hash"


def test_org_export_import_preserves_content_hash(tmp_path: Path) -> None:
    orgs_path = tmp_path / "authz" / "orgs.json"
    orgs_path.parent.mkdir(parents=True, exist_ok=True)
    genesis = GenesisStore(orgs_path)
    org = genesis.create_org(name="ORG-EXPORT", founder_address="artcb1founderxxxxxxxxxxxxxxxxxxxx")
    # Simulate transfer to another node store
    other = GenesisStore(tmp_path / "authz2" / "orgs.json")
    imported = other.import_org(org.to_dict())
    assert imported.content_hash == org.content_hash
    assert imported.organization_id == org.organization_id
    assert other.get_org(org.organization_id) is not None

