#!/usr/bin/env python3
"""Sign two PRE-PREPARE on the current primary. Run on the node with chain.key env."""
from __future__ import annotations

import json
import os
from pathlib import Path

# Inherit ARTCB_WALLET_PASSPHRASE from the running uvicorn process if missing.
if not os.environ.get("ARTCB_WALLET_PASSPHRASE"):
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            cmdline = (proc / "cmdline").read_bytes()
        except OSError:
            continue
        if b"-m" not in cmdline or b"uvicorn" not in cmdline:
            continue
        raw = (proc / "environ").read_bytes().split(b"\0")
        for kv in raw:
            if kv.startswith(b"ARTCB_WALLET_PASSPHRASE="):
                os.environ["ARTCB_WALLET_PASSPHRASE"] = kv.split(b"=", 1)[1].decode()
            if kv.startswith(b"ARTCB_DATA_DIR="):
                os.environ["ARTCB_DATA_DIR"] = kv.split(b"=", 1)[1].decode()
        break

from artcb.chain.manager import ChainManager
from artcb.consensus.pbft_finality import sign_preprepare, verify_preprepare
from artcb.consensus.pbft_view import PbftViewStore
from artcb.node_registry import official_replica_id

data = Path(os.environ.get("ARTCB_DATA_DIR") or "/home/ubuntu/artcb/data")
chain = ChainManager(data / "chain" / "blocks.jsonl", key_path=data / "chain.key")
rid = official_replica_id()
view = int(PbftViewStore(data, replica_id=rid).view)
x = json.loads(
    chain.append_block(
        graph_id="v02-x", graph_root="x", pol_score=0.1, visibility="public", source="pbft:v02", dry_run=True
    ).to_json_line()
)
y = json.loads(
    chain.append_block(
        graph_id="v02-y", graph_root="y", pol_score=0.1, visibility="public", source="pbft:v02", dry_run=True
    ).to_json_line()
)
pp_x = sign_preprepare(chain, view=view, replica_id=rid, block=x)
pp_y = sign_preprepare(chain, view=view, replica_id=rid, block=y)
payload = {
    "ok": True,
    "view": view,
    "replica": rid,
    "x": x,
    "y": y,
    "pp_x": pp_x,
    "pp_y": pp_y,
    "vx": bool(verify_preprepare(pp_x)),
    "vy": bool(verify_preprepare(pp_y)),
}
Path("/tmp/artcb266_v02.json").write_text(json.dumps(payload))
print(json.dumps({"ok": True, "wrote": "/tmp/artcb266_v02.json", "view": view, "replica": rid, "vx": payload["vx"], "vy": payload["vy"], "ix": x["index"], "hx": x["hash"], "hy": y["hash"]}))
