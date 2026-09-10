#!/bin/bash
# Launchd entry for mac-node-local. Never prints secret values.
# 2026-09-10T14:50:00Z — `doppler run` without a filter fails closed when
# artcb-1/prd contains a restricted secret (MAC_SUDO_PASSWORD, R301b).
# Fetch names only, skip restricted names, then run uvicorn.
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"
unset DOPPLER_TOKEN
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ONLY="$(/usr/bin/python3 - <<'PY'
import json
import os
import subprocess

env = os.environ.copy()
env.pop("DOPPLER_TOKEN", None)
raw = subprocess.check_output(
    [
        "/usr/local/bin/doppler",
        "secrets",
        "--project",
        "artcb-1",
        "--config",
        "prd",
        "--only-names",
        "--json",
    ],
    env=env,
)
data = json.loads(raw)
names = list(data) if isinstance(data, dict) else list(data)
skip = {"MAC_SUDO_PASSWORD"}
keep = [n for n in names if n and n not in skip]
print(",".join(keep))
PY
)"
# ~~2026-09-10T14:50:00Z~~ previous launchd argv was `doppler run --project artcb-1 --config prd -- uvicorn …` (all secrets).
exec /usr/local/bin/doppler run --project artcb-1 --config prd --only-secrets "$ONLY" -- \
  "$ROOT/.venv/bin/python" -m uvicorn src.api.main:app \
  --host 0.0.0.0 --port 8001 --limit-concurrency 16 --timeout-keep-alive 5
