#!/usr/bin/env bash
# Autoscale git_sync: stay on the named branch tip. Never rewind to PIN.
#
# 181 cloned `--depth 1`, then `merge-base --is-ancestor $PIN $TIP` failed
# because PIN 4cb2943 is not in the shallow history. The else-branch checked
# out that PIN, wiped 181 from disk, and `import src.api.main` loaded the
# 178 tree (~5 minutes). Autoscale SIGTERM → restart loop.
#
# Rules:
# 1. Clone/fetch the named branch tip (not main).
# 2. If ancestry is unknown, unshallow / fetch the PIN, recompute tip, retry.
# 3. If PIN is an ancestor of tip (or unset): checkout tip.
# 4. If still unknown, or PIN is proven not an ancestor: KEEP TIP.
# 5. Never `git checkout --detach "$ARTCB_REPLIT_PIN_SHA"`.

artcb_replit_git_sync() {
  local REPL_DIR="${REPL_DIR:-$(pwd)}"
  local ARTCB_REPLIT_BRANCH="${ARTCB_REPLIT_BRANCH:-cursor/replit-sync-ready-16d8}"
  local ARTCB_REPLIT_REMOTE="${ARTCB_REPLIT_REMOTE:-https://github.com/vgactech/artcb.git}"
  local ARTCB_REPLIT_PIN_SHA="${ARTCB_REPLIT_PIN_SHA:-}"
  local _TIP=""

  git config --global --add safe.directory "$REPL_DIR" 2>/dev/null || true
  git -C "$REPL_DIR" fetch origin "$ARTCB_REPLIT_BRANCH" 2>/dev/null \
    || git fetch origin "$ARTCB_REPLIT_BRANCH" 2>/dev/null || true

  if [ ! -d "$REPL_DIR/.git" ]; then
    git clone --depth 1 --branch "$ARTCB_REPLIT_BRANCH" "$ARTCB_REPLIT_REMOTE" /tmp/artcb-src-$$ \
      && cp -a /tmp/artcb-src-$$/. "$REPL_DIR/" && rm -rf /tmp/artcb-src-$$ \
      || { _log "WARN clone failed — snapshot files"; return 0; }
  fi

  if ! git -C "$REPL_DIR" rev-parse --verify "origin/$ARTCB_REPLIT_BRANCH" >/dev/null 2>&1; then
    _log "WARN no origin/$ARTCB_REPLIT_BRANCH — keeping snapshot"
    return 0
  fi

  _TIP="$(git -C "$REPL_DIR" rev-parse "origin/$ARTCB_REPLIT_BRANCH")"

  _artcb_pin_is_ancestor() {
    [ -z "$ARTCB_REPLIT_PIN_SHA" ] && return 0
    git -C "$REPL_DIR" merge-base --is-ancestor "$ARTCB_REPLIT_PIN_SHA" "$1" 2>/dev/null
  }

  if ! _artcb_pin_is_ancestor "$_TIP"; then
    _log "ancestry unknown — unshallow + fetch pin then retry"
    git -C "$REPL_DIR" fetch --unshallow origin "$ARTCB_REPLIT_BRANCH" 2>/dev/null \
      || git -C "$REPL_DIR" fetch --unshallow 2>/dev/null \
      || git -C "$REPL_DIR" fetch origin "$ARTCB_REPLIT_BRANCH" 2>/dev/null \
      || true
    if [ -n "$ARTCB_REPLIT_PIN_SHA" ]; then
      git -C "$REPL_DIR" fetch origin "$ARTCB_REPLIT_PIN_SHA" 2>/dev/null || true
    fi
    if git -C "$REPL_DIR" rev-parse --verify "origin/$ARTCB_REPLIT_BRANCH" >/dev/null 2>&1; then
      _TIP="$(git -C "$REPL_DIR" rev-parse "origin/$ARTCB_REPLIT_BRANCH")"
    fi
  fi

  git -C "$REPL_DIR" checkout --detach "$_TIP" || true
  if _artcb_pin_is_ancestor "$_TIP"; then
    _log "checkout tip=$_TIP"
  else
    _log "WARN keep_tip ancestry_unknown pin=${ARTCB_REPLIT_PIN_SHA:-none} tip=$_TIP"
    _log "checkout tip=$_TIP"
  fi
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  set -Eeuo pipefail
  _log() { printf '[%s] [step=git_sync] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
  REPL_DIR="${REPL_DIR:-$(pwd)}"
  artcb_replit_git_sync
fi
