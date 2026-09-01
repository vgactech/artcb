#!/usr/bin/env bash
# Pick a Python that already has FastAPI. Never create a venv.
#
# Replit workflow: /home/runner/venv/bin/python3 (packages already there).
# Autoscale Nix `python3` on PATH often has no fastapi. Prefer Replit
# interpreters first; fall back to PATH python3 only if it can import.

artcb_python_serves() {
  local py="$1"
  [ -n "$py" ] && [ -x "$py" ] || return 1
  "$py" -c "import fastapi, uvicorn" 2>/dev/null
}

artcb_pick_python() {
  local REPL_DIR="${REPL_DIR:-$(pwd)}"
  local cand=""
  PYTHON=""
  for cand in \
    "${ARTCB_PYTHON:-}" \
    "${HOME}/venv/bin/python3" \
    "${REPL_DIR}/.pythonlibs/bin/python3" \
    "${HOME}/.pythonlibs/bin/python3" \
    "$(command -v python3 2>/dev/null || true)"
  do
    if artcb_python_serves "$cand"; then
      PYTHON="$cand"
      break
    fi
  done
  if [ -z "$PYTHON" ]; then
    _log "ERROR fastapi/uvicorn missing — shim stays (no venv)"
    return 1
  fi
  export PYTHON
  export PATH="$(dirname "$PYTHON"):${PATH:-}"
  _log "python=$PYTHON"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  set -Eeuo pipefail
  _log() { printf '[%s] [step=python] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
  REPL_DIR="${REPL_DIR:-$(pwd)}"
  artcb_pick_python
  printf '%s\n' "$PYTHON"
fi
