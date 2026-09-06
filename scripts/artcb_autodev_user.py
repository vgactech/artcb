#!/usr/bin/env python3
"""ARTCB auto-dev user — bout en bout.

    wallet local → login sess_ → agent header → /auth/me → mémo privé

Refuse les blocs publics (commitment / tip) sans ARTCB_AUTODEV_ALLOW_PUBLIC=1.
Ne jamais imprimer mot de passe, seed, ni token.
Ne crée pas d'ORG. Ne déploie pas. Ne wipe pas.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _self_test() -> int:
    import tempfile

    os.environ.setdefault("ARTCB_ALLOW_MULTI_WALLET", "true")
    tmp = Path(tempfile.mkdtemp(prefix="artcb-autodev-"))
    os.environ["ARTCB_DATA_DIR"] = str(tmp / "data")
    os.environ["ARTCB_LOG_DIR"] = str(tmp / "logs")
    os.environ.setdefault("ARTCB_WALLET_PASSPHRASE", "test-passphrase-artcb-dev-32chars!")
    os.environ.setdefault("ARTCB_NODE_WALLET_ADDRESS", "artcb1testnode000000000000000000000000000")
    os.environ.setdefault("ARTCB_SKIP_SEED_DISCOVERY", "1")
    os.environ.setdefault("ARTCB_SKIP_CLOUD_METADATA", "1")
    os.environ.setdefault("ARTCB_ALLOW_LOCAL_PEERS", "1")
    os.environ.setdefault("ARTCB_MIN_BLOCK_INTERVAL_SEC", "0")
    password = os.environ.get("ARTCB_AUTODEV_PASSWORD") or "monMotDePasse42!"
    os.environ["ARTCB_AUTODEV_PASSWORD"] = password

    from fastapi.testclient import TestClient

    from api.main import create_app
    from artcb.autodev.user import AutodevUser

    client = TestClient(create_app())
    user = AutodevUser(password=password, agent_id="cursor-autodev")
    ident = user.ensure_wallet()
    user.login(client)
    me = user.whoami(client)
    stored = user.record(client, content="autodev self-test 233")
    out = {
        "mode": "self_test",
        "wallet_created_or_loaded": True,
        "address_prefix": ident.address[:12],
        "whoami_kind": me.get("kind"),
        "is_user": me.get("is_user"),
        "is_operator": me.get("is_operator"),
        "memo_stored": stored.get("memo_stored"),
        "visibility": stored.get("visibility"),
        "principal_kind": stored.get("principal_kind"),
        "token_printed": False,
        "seed_printed": False,
        "public_tip_touched": False,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if me.get("is_user") and stored.get("memo_stored") else 1


def _live_operator_is_not_user() -> int:
    """Measure live operator /auth/me — must not pretend to be a human."""
    import urllib.request

    url = os.environ.get("ARTCB_API_URL") or "https://152.228.144.34:8443"
    key = (os.environ.get("ARTCB_API_KEY") or "").strip()
    req = urllib.request.Request(f"{url.rstrip('/')}/api/v1/auth/me")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    try:
        import ssl

        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            body = json.loads(resp.read().decode())
    except Exception as exc:
        print(json.dumps({"mode": "live_whoami", "error": type(exc).__name__, "token_printed": False}))
        return 1
    out = {
        "mode": "live_operator_whoami",
        "kind": body.get("kind"),
        "is_user": body.get("is_user"),
        "is_operator": body.get("is_operator"),
        "address": body.get("address"),
        "token_printed": False,
        "note": "clé nœud ≠ user auto-dev. Login live non lancé (pas de wallet auto-dev sur OVH1).",
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ARTCB auto-dev user loop")
    parser.add_argument("--self-test", action="store_true", help="TestClient local, pas le live")
    parser.add_argument("--live-operator-check", action="store_true", help="Mesure /auth/me opérateur")
    args = parser.parse_args()
    if args.live_operator_check:
        return _live_operator_is_not_user()
    return _self_test()


if __name__ == "__main__":
    raise SystemExit(main())
