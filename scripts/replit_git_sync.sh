#!/usr/bin/env bash
# Autoscale git_sync: stay on the named branch tip. Never rewind to PIN.
# Never unshallow: log 20260901T112644Z spent ~17s on fetch --unshallow,
# Autoscale SIGTERM'd, then started a second copy (restart loop).
#
# Depth-1 clone of the branch tip is enough. PIN is a health check, not a
# checkout target. If merge-base cannot prove ancestry, KEEP THE TIP.

artcb_replit_git_sync() {
  local REPL_DIR="${REPL_DIR:-$(pwd)}"
  local ARTCB_REPLIT_BRANCH="${ARTCB_REPLIT_BRANCH:-cursor/replit-sync-ready-16d8}"
  local ARTCB_REPLIT_REMOTE="${ARTCB_REPLIT_REMOTE:-https://github.com/vgactech/artcb.git}"
  local ARTCB_REPLIT_PIN_SHA="${ARTCB_REPLIT_PIN_SHA:-}"
  local _TIP=""

  git config --global --add safe.directory "$REPL_DIR" 2>/dev/null || true
  git -C "$REPL_DIR" fetch --depth 1 origin "$ARTCB_REPLIT_BRANCH" 2>/dev/null \
    || git fetch --depth 1 origin "$ARTCB_REPLIT_BRANCH" 2>/dev/null || true

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
  git -C "$REPL_DIR" checkout --detach "$_TIP" || true
  _log "checkout tip=$_TIP"
  if [ -n "$ARTCB_REPLIT_PIN_SHA" ]; then
    if git -C "$REPL_DIR" merge-base --is-ancestor "$ARTCB_REPLIT_PIN_SHA" "$_TIP" 2>/dev/null; then
      : # PIN is ancestor or equal — integrity can be ok if PIN==tip
    else
      _log "WARN keep_tip ancestry_unknown pin=$ARTCB_REPLIT_PIN_SHA tip=$_TIP"
    fi
  fi
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  set -Eeuo pipefail
  _log() { printf '[%s] [step=git_sync] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
  REPL_DIR="${REPL_DIR:-$(pwd)}"
  artcb_replit_git_sync
fi
