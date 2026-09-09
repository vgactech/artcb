#!/usr/bin/env python3
"""Write this machine's PUBLIC replica keys into official_replica_keys.json.

Never prints the private key or the full public material. For a cloned-user node.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.artcb.chain.manager import ChainManager  # noqa: E402
from src.artcb.consensus.live_bft import n_f_q  # noqa: E402
from src.artcb.consensus.tip_attest import producer_key_b64  # noqa: E402
from src.artcb.node_registry import (  # noqa: E402
    MAC_NODE_ID,
    REPLICA_KEYS_PATH,
    official_replica_id,
)


def main() -> int:
    node_id = official_replica_id() or MAC_NODE_ID
    data = ROOT / "data"
    chain = ChainManager(data / "blocks.jsonl", key_path=data / "chain.key", enable_security=False)
    ed, pqc = producer_key_b64(chain)
    if not ed:
        print(json.dumps({"ok": False, "reason": "no_local_ed25519_public"}))
        return 2
    payload = json.loads(REPLICA_KEYS_PATH.read_text(encoding="utf-8"))
    replicas = payload.setdefault("replicas", {})
    replicas[node_id] = {
        "ed25519_b64": ed,
        "pqc_b64": pqc,
        "activation_epoch": int((replicas.get(node_id) or {}).get("activation_epoch") or 0),
        "revoked": False,
    }
    n, f, q = n_f_q(len(replicas))
    payload["n"] = n
    payload["f"] = f
    payload["q"] = q
    REPLICA_KEYS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "node_id": node_id,
                "ed_prefix": ed[:12],
                "pqc_len": len(pqc or ""),
                "n": n,
                "f": f,
                "q": q,
                "replica_count": len(replicas),
                "private_printed": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
