#!/usr/bin/env bash
# Pick a Python that already has FastAPI. Never create a venv.
#
# Autoscale log 20260901T114712Z: $HOME/venv import (faiss AVX probes)
# delayed pick by ~2 minutes. Prefer .pythonlibs first. Time-box imports.

artcb_python_serves() {
  local py="$1"
  [ -n "$py" ] && [ -x "$py" ] || return 1
  if command -v timeout >/dev/null 2>&1; then
    timeout 8 "$py" -c "import fastapi, uvicorn" 2>/dev/null
  else
    "$py" -c "import fastapi, uvicorn" 2>/dev/null
  fi
}

artcb_pick_python() {
  local REPL_DIR="${REPL_DIR:-$(pwd)}"
  local cand=""
  PYTHON=""
  for cand in \
    "${ARTCB_PYTHON:-}" \
    "${REPL_DIR}/.pythonlibs/bin/python3" \
    "${HOME}/.pythonlibs/bin/python3" \
    "${HOME}/venv/bin/python3" \
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
