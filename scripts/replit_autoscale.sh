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
export ARTCB_FAST_BOOT=1
python3 "$REPL_DIR/scripts/replit_live_shim.py" &
SHIM_PID=$!
_log "live_shim pid=$SHIM_PID port=$ARTCB_PORT"
for _i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  if curl -sf "http://127.0.0.1:${ARTCB_PORT}/live" >/dev/null 2>&1; then
    _log "shim_ready /live=200"
    break
  fi
  sleep 0.1
done

CURRENT_STEP="public_url"
_artcb_https_from_host() {
  local d="$1"
  d="${d#https://}"
  d="${d#http://}"
  d="${d%%/*}"
  d="${d%%,*}"
  d="$(echo "$d" | tr -d ' ')"
  [ -n "$d" ] && echo "https://${d}"
}
if [ -z "${ARTCB_NODE_PUBLIC_URL:-}" ]; then
  if [ -n "${REPLIT_DEV_DOMAIN:-}" ]; then
    export ARTCB_NODE_PUBLIC_URL="$(_artcb_https_from_host "$REPLIT_DEV_DOMAIN")"
  elif [ -n "${REPLIT_INTERNAL_APP_DOMAIN:-}" ]; then
    export ARTCB_NODE_PUBLIC_URL="$(_artcb_https_from_host "$REPLIT_INTERNAL_APP_DOMAIN")"
  elif [ -n "${REPLIT_DOMAINS:-}" ]; then
    export ARTCB_NODE_PUBLIC_URL="$(_artcb_https_from_host "$REPLIT_DOMAINS")"
  elif [ -n "${REPL_SLUG:-}" ] && [ -n "${REPL_OWNER:-}" ]; then
    export ARTCB_NODE_PUBLIC_URL="https://${REPL_SLUG}--${REPL_OWNER}.replit.app"
  fi
fi

CURRENT_STEP="git_sync"
ARTCB_REPLIT_BRANCH="${ARTCB_REPLIT_BRANCH:-main}"
ARTCB_REPLIT_REMOTE="${ARTCB_REPLIT_REMOTE:-https://github.com/vgactech/artcb.git}"
# PIN is a supply-chain check, not a checkout target. Never default to 178:
# a shallow clone makes merge-base fail and 181 then rewound to 4cb2943.
ARTCB_REPLIT_PIN_SHA="${ARTCB_REPLIT_PIN_SHA:-}"
# shellcheck source=scripts/replit_git_sync.sh
. "$REPL_DIR/scripts/replit_git_sync.sh"
artcb_replit_git_sync
_SHA="$(git -C "$REPL_DIR" rev-parse HEAD 2>/dev/null || true)"
if [ -z "$_SHA" ]; then
  _SHA="${ARTCB_REPLIT_PIN_SHA:-}"
fi
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
  "$REPL_DIR"/.pythonlibs/lib/python*/site-packages \
  "$HOME"/.pythonlibs/lib/python*/site-packages; do
  [ -d "$d" ] && PYTHONPATH="$d:$PYTHONPATH"
done
export PYTHONPATH
# Replit venv / .pythonlibs before Nix python3. Never `python3 -m venv`.
# shellcheck source=scripts/replit_pick_python.sh
. "$REPL_DIR/scripts/replit_pick_python.sh"
if ! artcb_pick_python; then
  wait "$SHIM_PID" || true
  exit 1
fi
export OQS_INSTALL_PATH="${OQS_INSTALL_PATH:-$HOME/_oqs}"
export LD_LIBRARY_PATH="${OQS_INSTALL_PATH}/lib:${OQS_INSTALL_PATH}/lib64:${LD_LIBRARY_PATH:-}"

CURRENT_STEP="uvicorn"
export ARTCB_SHIM_PID="$SHIM_PID"
_log "launching uvicorn python=$PYTHON sha=$_SHA same-process-import"
exec "$PYTHON" "$REPL_DIR/scripts/replit_serve.py"
