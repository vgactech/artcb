#!/usr/bin/env bash
# ARTCB — vérification locale après clone/install
set -Eeuo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

PYTHON="${ARTCB_PYTHON:-}"
if [ -z "$PYTHON" ]; then
  for candidate in \
    "$REPO_DIR/.venv/bin/python3" \
    "$REPO_DIR/.pythonlibs/bin/python3" \
    "$HOME/.pythonlibs/bin/python3" \
    "$(command -v python3 2>/dev/null || true)"; do
    if [ -x "$candidate" ]; then
      PYTHON="$candidate"
      break
    fi
  done
fi
[ -n "$PYTHON" ] && [ -x "$PYTHON" ] || { echo "ERROR: Python not found" >&2; exit 1; }

"$PYTHON" - <<'PY'
from src.api.main import app
import cryptography
import fastapi
import nacl
import pydantic
import pypdf
import uvicorn

print("API import OK")
print(
    "versions:"
    f" fastapi={fastapi.__version__}"
    f" pydantic={pydantic.__version__}"
    f" uvicorn={uvicorn.__version__}"
    f" cryptography={cryptography.__version__}"
    f" PyNaCl={nacl.__version__}"
    f" pypdf={pypdf.__version__}"
)
PY

if [ -f frontend/package-lock.json ]; then
  (cd frontend && npm ci --no-audit --no-fund --ignore-scripts)
fi
if [ -f frontend/package.json ]; then
  (cd frontend && npm run build)
fi

if [ -f src/c/libartcb_chain.so ]; then
  nm -D src/c/libartcb_chain.so 2>/dev/null | grep -q artcb_sha256_hex \
    || { echo "ERROR: native chain library has no expected symbol" >&2; exit 1; }
  echo "Native chain library OK"
else
  echo "Native chain library absent; Python fallback remains enabled"
fi

echo "ARTCB installation verification complete."