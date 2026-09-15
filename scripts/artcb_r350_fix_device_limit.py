#!/usr/bin/env python3
"""R350 — Fix device_wallet_limit + USER↔NODE association (exécuté une seule fois sur chaque nœud).

Ce script est déployé via artcb_follow_main sur OVH2/OVH4.
À supprimer après exécution.
"""
from __future__ import annotations
import hashlib, json, os, requests, sys, time
from pathlib import Path

try:
    from nacl import signing as nacl_signing
except ImportError:
    sys.path.insert(0, '/home/ubuntu/artcb/src')
    from nacl import signing as nacl_signing

# ── Config ──────────────────────────────────────────────────────────────────
SEED_HEX = os.getenv("ARTCB_USER_WALLET_SEED_HEX", "")
PASSWORD  = "12345678"
PROTOCOL  = "r348-user-node-association-v1"
DATA_DIR  = Path(os.getenv("ARTCB_DATA_DIR", "/home/ubuntu/artcb/data"))
SELF_BASE = os.getenv("ARTCB_NODE_BASE_URL", "http://localhost:8000")

if not SEED_HEX:
    print("ARTCB_USER_WALLET_SEED_HEX not set — aborting")
    sys.exit(0)

sk      = nacl_signing.SigningKey(bytes.fromhex(SEED_HEX))
pub_hex = sk.verify_key.encode().hex()

# ── 1. Supprimer les fichiers device_limit ──────────────────────────────────
DEVICE_FILES = [
    DATA_DIR / "wallet_device_bindings.json",
    DATA_DIR / "node_device.json",
    DATA_DIR / "economics" / "devices.json",
]
for f in DEVICE_FILES:
    if f.exists():
        f.unlink()
        print(f"[fix] deleted {f}")

# ── 2. Supprimer vgactech2 (wallet corrompu) ──────────────────────────────
for ext in (".json", ".key", ".pqc"):
    wf = DATA_DIR / "wallets" / f"vgactech2{ext}"
    if wf.exists():
        wf.unlink()
        print(f"[fix] deleted {wf}")

time.sleep(2)

# ── 3. Recréer vgactech2 avec password 12345678 ──────────────────────────
kw = dict(timeout=15)
rc = requests.post(SELF_BASE + "/api/v1/wallet/create",
     json={"name": "vgactech2", "password": PASSWORD,
           "seed_hex": SEED_HEX, "allow_multi": True}, **kw)
print(f"[fix] wallet/create: {rc.status_code}")
if rc.status_code not in (200, 201):
    print(f"[fix] FAIL: {rc.text[:200]}")
    sys.exit(1)
wallet_addr = rc.json().get("address", "")
print(f"[fix] addr: {wallet_addr}")

# ── 4. Login + challenge/verify + USER↔NODE association ──────────────────
rl = requests.post(SELF_BASE + "/api/v1/auth/login",
     json={"name": "vgactech2", "password": PASSWORD}, **kw)
print(f"[fix] login: {rl.status_code}")
if rl.status_code != 200:
    print(f"[fix] FAIL: {rl.text[:100]}")
    sys.exit(1)

H = {"Authorization": "Bearer " + rl.json()["session_token"]}
wallet_addr = rl.json().get("address", wallet_addr)

ch  = requests.get(SELF_BASE + "/api/v1/auth/challenge", **kw).json()["challenge"]
sig = sk.sign(bytes.fromhex(ch)).signature.hex()
rv  = requests.post(SELF_BASE + "/api/v1/auth/verify",
      json={"address": wallet_addr, "challenge": ch, "signature": sig}, **kw)
print(f"[fix] verify: {rv.status_code}")
if rv.status_code == 200:
    H = {"Authorization": "Bearer " + rv.json()["session_token"]}

rn  = requests.get(SELF_BASE + "/api/v1/identity/user-node/challenge", headers=H, **kw)
cn  = rn.json()
nid = cn.get("node_id", "")
nw  = cn.get("node_wallet_address", "") or ""
chu = cn.get("challenge", "")
print(f"[fix] node_id: {nid[:30]}")

msg  = "|".join([PROTOCOL, chu.strip(), nid.strip(), nw.strip(),
                 wallet_addr.strip(), "client"])
sig2 = sk.sign(msg.encode("utf-8")).signature.hex()

ra = requests.post(SELF_BASE + "/api/v1/identity/user-node/associate",
     json={"user_address": wallet_addr, "user_public_key_hex": pub_hex,
           "challenge": chu, "signature_hex": sig2, "role": "client"},
     headers=H, **kw)
print(f"[fix] associate: {ra.status_code}")
if ra.status_code == 200:
    a = ra.json().get("association", {})
    print(f"[fix] ✅ USER↔NODE PASS")
    print(f"[fix]    user={a.get('user_address','?')[:30]}")
    print(f"[fix]    node={a.get('node_id','?')[:30]}")
    print(f"[fix]    persistence={a.get('persistence','?')}")
    # Écrire le résultat dans un fichier trace
    trace = DATA_DIR / "identity" / "r350_fix_result.json"
    trace.parent.mkdir(parents=True, exist_ok=True)
    trace.write_text(json.dumps({
        "ts": time.time(), "result": "PASS",
        "user_address": wallet_addr, "node_id": nid,
    }))
else:
    print(f"[fix] ❌ FAIL: {ra.text[:200]}")
    sys.exit(1)
