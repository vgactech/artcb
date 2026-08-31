#!/usr/bin/env bash
# Initialize a fresh ARTCB node over SSH (localhost POST /setup/init-node).
# Saves seed to ~/.artcb/node_init.env on the remote (0600). Never prints seed.
# Usage: bash scripts/init_remote_node.sh USER@HOST SSH_KEY NODE_NAME PUBLIC_URL
set -Eeuo pipefail
TARGET="${1:-}"
SSH_KEY="${2:-}"
NODE_NAME="${3:-}"
PUBLIC_URL="${4:-}"
if [ -z "$TARGET" ] || [ -z "$SSH_KEY" ] || [ -z "$NODE_NAME" ] || [ -z "$PUBLIC_URL" ]; then
  echo "Usage: bash scripts/init_remote_node.sh USER@HOST SSH_KEY NODE_NAME PUBLIC_URL"
  exit 1
fi
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o IdentitiesOnly=yes -o BatchMode=yes \
  "$TARGET" env NODE_NAME="$NODE_NAME" PUBLIC_URL="$PUBLIC_URL" bash -s <<'REMOTE'
set -Eeuo pipefail
python3 - <<'PY'
import json, os, urllib.request
from pathlib import Path

def env_file(path: Path) -> dict[str, str]:
    out = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out

doppler = env_file(Path("/etc/artcb/doppler.env"))
password = doppler.get("ARTCB_WALLET_PASSPHRASE") or ""
if len(password) < 8:
    import secrets, string
    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for _ in range(32))
    Path("/tmp/artcb_wallet_pass").write_text("ARTCB_WALLET_PASSPHRASE=" + password + "\n", encoding="utf-8")
    os.chmod("/tmp/artcb_wallet_pass", 0o600)

payload = json.dumps({
    "node_name": os.environ["NODE_NAME"],
    "password": password,
    "public_url": os.environ["PUBLIC_URL"],
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8000/setup/init-node",
    data=payload,
    method="POST",
    headers={"Content-Type": "application/json", "Accept": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode())
        status = resp.status
except Exception as exc:
    print(json.dumps({"ok": False, "error": type(exc).__name__, "http": getattr(exc, "code", 0)}))
    raise SystemExit(2)

seed = body.pop("seed_hex", None)
home = Path.home() / ".artcb"
home.mkdir(mode=0o700, exist_ok=True)
init_path = home / "node_init.env"
lines = [
    f"NODE_NAME={os.environ['NODE_NAME']}",
    f"PUBLIC_URL={os.environ['PUBLIC_URL']}",
    f"ADDRESS={body.get('address') or ''}",
    f"HYBRID={body.get('hybrid')}",
]
if seed:
    lines.append("SEED_HEX=" + seed)
init_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
init_path.chmod(0o600)
print(json.dumps({
    "ok": True,
    "http": status,
    "status": body.get("status"),
    "address_prefix": (body.get("address") or "")[:12],
    "hybrid": body.get("hybrid"),
    "seed_saved": bool(seed),
    "seed_printed": False,
}))
PY
sudo systemctl restart artcb.service
for i in $(seq 1 20); do
  if curl -sf http://127.0.0.1:8000/health >/dev/null; then
    echo "local_health_ok attempt=$i"
    break
  fi
  sleep 2
done
curl -sf http://127.0.0.1:8000/health | python3 -c 'import sys,json; d=json.load(sys.stdin); print(json.dumps({k:d.get(k) for k in ("status","git_sha","git_branch","bootstrap_mode","network_id","protocol_version","pqc") if k in d or True}))'
REMOTE
