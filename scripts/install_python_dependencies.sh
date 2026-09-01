#!/usr/bin/env bash
# ARTCB — installation Python reproductible et non bloquante
#
# Le socle API est installé sans liboqs-python. liboqs-python compile liboqs
# depuis ses sources et ne doit jamais être mélangé au chemin critique de boot.
#
# Usage:
#   bash scripts/install_python_dependencies.sh
#   ARTCB_INSTALL_PQC=1 ARTCB_PQC_TIMEOUT=300 \
#     bash scripts/install_python_dependencies.sh
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

if [ -z "$PYTHON" ] || [ ! -x "$PYTHON" ]; then
  echo "ERROR: Python 3 executable not found" >&2
  exit 1
fi

PIP_TIMEOUT="${ARTCB_PIP_TIMEOUT:-180}"
PIP_NETWORK_TIMEOUT="${ARTCB_PIP_NETWORK_TIMEOUT:-30}"
PQC_TIMEOUT="${ARTCB_PQC_TIMEOUT:-300}"
export PIP_USER=false

PYTHON_USER_SITE="$("$PYTHON" -c 'import site; print(site.getusersitepackages())')"
PYTHON_PURELIB="$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
PIP_DEST_ARGS=()
if [[ "$PYTHON_PURELIB" == /nix/store/* ]] && [[ "$PYTHON_USER_SITE" == "$REPO_DIR/.pythonlibs/"* ]]; then
  # Replit's wrapped Nix Python cannot write /nix/store. Install into the
  # persistent project site-packages that is already on PYTHONPATH.
  mkdir -p "$PYTHON_USER_SITE"
  PIP_DEST_ARGS=(--target "$PYTHON_USER_SITE" --upgrade)
  echo "Using Replit user site: $PYTHON_USER_SITE"
else
  PIP_DEST_ARGS=(--no-user)
fi

run_bounded() {
  local seconds="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout --foreground --signal=TERM --kill-after=10s "${seconds}s" "$@"
  else
    "$@"
  fi
}

RUNTIME_REQUIREMENTS="$(mktemp "${TMPDIR:-/tmp}/artcb-runtime-requirements.XXXXXX")"
cleanup() {
  rm -f "$RUNTIME_REQUIREMENTS"
}
trap cleanup EXIT

# Keep requirements.txt as the protocol's complete dependency inventory, but
# remove the only source-build dependency from the API's critical path.
awk '!/^[[:space:]]*liboqs-python([<>=!~]|[[:space:]]|$)/' \
  requirements.txt > "$RUNTIME_REQUIREMENTS"

echo "ARTCB Python runtime: $PYTHON"
echo "Installing runtime dependencies (PQC source build excluded from critical path)..."
run_bounded "$PIP_TIMEOUT" "$PYTHON" -m pip install \
  "${PIP_DEST_ARGS[@]}" \
  --disable-pip-version-check \
  --retries 3 \
  --timeout "$PIP_NETWORK_TIMEOUT" \
  -r "$RUNTIME_REQUIREMENTS"

"$PYTHON" - <<'PY'
import fastapi
import nacl
import pydantic
import uvicorn

print(
    "Runtime imports OK:"
    f" fastapi={fastapi.__version__}"
    f" pydantic={pydantic.__version__}"
    f" uvicorn={uvicorn.__version__}"
)
PY

if [ "${ARTCB_INSTALL_PQC:-0}" = "1" ]; then
  echo "PQC optional install enabled (hard timeout: ${PQC_TIMEOUT}s)..."
  if run_bounded "$PQC_TIMEOUT" "$PYTHON" -m pip install \
      "${PIP_DEST_ARGS[@]}" \
      --disable-pip-version-check \
      --retries 2 \
      --timeout "$PIP_NETWORK_TIMEOUT" \
      --upgrade "liboqs-python>=0.14.0"; then
    echo "PQC Python binding installation finished."
  else
    echo "WARNING: optional liboqs-python install failed or timed out."
    echo "The node remains operational with the documented Ed25519/X25519 fallback."
  fi
else
  echo "PQC optional install skipped; no native compilation in the critical path."
fi

echo "Python dependency installation complete."