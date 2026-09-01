#!/usr/bin/env bash
# Autoscale boot — bind :5000 in seconds, never create a venv.
# The 178 path (`python3 -m venv`) took 11 minutes and Replit SIGTERM'd the
# process, then started another copy (death spiral). This script must stay small.
set -Eeuo pipefail
REPL_DIR="$(pwd)"
umask 077
STARTUP_TS="$(date -u +%Y%m%dT%H%M%SZ)"
STARTUP_ID="${STARTUP_TS}_$$"
export ARTCB_STARTUP_ID="$STARTUP_ID"
_log() { printf '[%s] [startup_id=%s] [step=%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$STARTUP_ID" "${CURRENT_STEP:-boot}" "$*"; }
trap '_log EXIT status=$?' EXIT
export ARTCB_PORT="${ARTCB_PORT:-5000}"
CURRENT_STEP="shim"
python3 "$REPL_DIR/scripts/replit_live_shim.py" &
SHIM_PID=$!
_log "live_shim pid=$SHIM_PID port=$ARTCB_PORT"

CURRENT_STEP="public_url"
if [ -z "${ARTCB_NODE_PUBLIC_URL:-}" ] && [ -n "${REPLIT_DOMAINS:-}" ]; then
  export ARTCB_NODE_PUBLIC_URL="https://$(echo "$REPLIT_DOMAINS" | cut -d',' -f1 | tr -d ' ')"
fi

CURRENT_STEP="git_sync"
ARTCB_REPLIT_BRANCH="${ARTCB_REPLIT_BRANCH:-cursor/replit-sync-ready-16d8}"
ARTCB_REPLIT_REMOTE="${ARTCB_REPLIT_REMOTE:-https://github.com/vgactech/artcb.git}"
# PIN is a supply-chain check, not a checkout target. Never default to 178:
# a shallow clone makes merge-base fail and 181 then rewound to 4cb2943.
ARTCB_REPLIT_PIN_SHA="${ARTCB_REPLIT_PIN_SHA:-}"
# shellcheck source=scripts/replit_git_sync.sh
. "$REPL_DIR/scripts/replit_git_sync.sh"
artcb_replit_git_sync
_SHA="$(git -C "$REPL_DIR" rev-parse HEAD 2>/dev/null || true)"
{
  echo "ARTCB_GIT_SHA=$_SHA"
  echo "ARTCB_GIT_BRANCH=$ARTCB_REPLIT_BRANCH"
} > "$REPL_DIR/.artcb_release"
export ARTCB_GIT_SHA="$_SHA"
export ARTCB_GIT_BRANCH="$ARTCB_REPLIT_BRANCH"
_log "release sha=${_SHA:-NONE}"

CURRENT_STEP="python"
PYTHONPATH="$REPL_DIR"
for d in \
  "$REPL_DIR/.pythonlibs/lib/python3.11/site-packages" \
  "$HOME/.pythonlibs/lib/python3.11/site-packages"; do
  [ -d "$d" ] && PYTHONPATH="$d:$PYTHONPATH"
done
export PYTHONPATH
PYTHON=""
for _candidate in \
  "$REPL_DIR/.pythonlibs/bin/python3" \
  "$HOME/.pythonlibs/bin/python3" \
  "$HOME/venv/bin/python3" \
  "$(command -v python3)"; do
  if [ -x "$_candidate" ] \
    && "$_candidate" -c "import fastapi, uvicorn" 2>/dev/null; then
    PYTHON="$_candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  PYTHON="$(command -v python3)"
fi
export OQS_INSTALL_PATH="${OQS_INSTALL_PATH:-$HOME/_oqs}"
export LD_LIBRARY_PATH="${OQS_INSTALL_PATH}/lib:${OQS_INSTALL_PATH}/lib64:${LD_LIBRARY_PATH:-}"
if ! "$PYTHON" -c "import fastapi, uvicorn" 2>/dev/null; then
  _log "ERROR fastapi/uvicorn missing on $PYTHON — shim stays"
  wait "$SHIM_PID" || true
  exit 1
fi

CURRENT_STEP="uvicorn"
if ! "$PYTHON" -c "from src.api.main import app" 2>/tmp/artcb_import.err; then
  _log "ERROR import failed"
  cat /tmp/artcb_import.err >&2 || true
  wait "$SHIM_PID" || true
  exit 1
fi
kill "$SHIM_PID" 2>/dev/null || true
wait "$SHIM_PID" 2>/dev/null || true
sleep 0.2
_log "launching uvicorn python=$PYTHON sha=$_SHA"
exec "$PYTHON" -m uvicorn src.api.main:app --host 0.0.0.0 --port "$ARTCB_PORT" --log-level info
