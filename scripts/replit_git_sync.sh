#!/usr/bin/env bash
# Autoscale git_sync: stay on the published snapshot. Never rewind to PIN.
#
# Log 20260901T114712Z: clone GitHub at 11:47:14, Autoscale SIGTERM at
# 11:47:30 (~16s). Then checkout 184 instead of 185. Do not clone unless
# ARTCB_REPLIT_FORCE_CLONE=1 (Nix workspace pull).

artcb_replit_git_sync() {
  local REPL_DIR="${REPL_DIR:-$(pwd)}"
  local ARTCB_REPLIT_BRANCH="${ARTCB_REPLIT_BRANCH:-main}"
  local ARTCB_REPLIT_REMOTE="${ARTCB_REPLIT_REMOTE:-https://github.com/vgactech/artcb.git}"
  local ARTCB_REPLIT_PIN_SHA="${ARTCB_REPLIT_PIN_SHA:-}"
  local _TIP=""

  git config --global --add safe.directory "$REPL_DIR" 2>/dev/null || true

  if [ "${ARTCB_REPLIT_FORCE_CLONE:-}" != "1" ] \
    && [ -f "$REPL_DIR/scripts/replit_autoscale.sh" ] \
    && [ ! -d "$REPL_DIR/.git" ]; then
    _log "keep snapshot no_clone"
    return 0
  fi

  if [ "${ARTCB_REPLIT_SNAPSHOT_ONLY:-0}" = "1" ] \
    && [ "${ARTCB_REPLIT_FORCE_SYNC:-0}" != "1" ]; then
    _log "keep snapshot snapshot_only"
    return 0
  fi

  if [ -d "$REPL_DIR/.git" ]; then
    if git -C "$REPL_DIR" rev-parse --is-shallow-repository 2>/dev/null | grep -qx true; then
      git -C "$REPL_DIR" fetch --unshallow origin "$ARTCB_REPLIT_BRANCH" 2>/dev/null \
        || git -C "$REPL_DIR" fetch --update-shallow origin "$ARTCB_REPLIT_BRANCH" 2>/dev/null \
        || true
    else
      git -C "$REPL_DIR" fetch origin "$ARTCB_REPLIT_BRANCH" 2>/dev/null || true
    fi
  fi


  if [ ! -d "$REPL_DIR/.git" ]; then
    git clone --depth 1 --branch "$ARTCB_REPLIT_BRANCH" "$ARTCB_REPLIT_REMOTE" /tmp/artcb-src-$$ \
      && cp -a /tmp/artcb-src-$$/. "$REPL_DIR/" && rm -rf /tmp/artcb-src-$$ \
      || { _log "WARN clone failed — snapshot files"; return 0; }
  fi

  if ! git -C "$REPL_DIR" rev-parse --verify "origin/$ARTCB_REPLIT_BRANCH" >/dev/null 2>&1; then
    _log "WARN no origin/$ARTCB_REPLIT_BRANCH — keeping snapshot"
    return 0
  fi

  # Never overwrite a user's dependency edits or local protocol work. A dirty
  # workspace is a valid local snapshot; checkout would fail noisily and could
  # leave release metadata claiming a different source than the running code.
  if [ -n "$(git -C "$REPL_DIR" status --porcelain --untracked-files=all 2>/dev/null)" ]; then
    _log "WARN dirty_worktree — keeping snapshot; no checkout"
    return 0
  fi

  _TIP="$(git -C "$REPL_DIR" rev-parse "origin/$ARTCB_REPLIT_BRANCH")"
  git -C "$REPL_DIR" checkout --detach "$_TIP" || true
  _log "checkout tip=$_TIP"
  if [ -n "$ARTCB_REPLIT_PIN_SHA" ]; then
    if git -C "$REPL_DIR" merge-base --is-ancestor "$ARTCB_REPLIT_PIN_SHA" "$_TIP" 2>/dev/null; then
      :
    else
      _log "WARN keep_tip ancestry_unknown pin_set=1"
    fi
  fi
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  set -Eeuo pipefail
  _log() { printf '[%s] [step=git_sync] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
  REPL_DIR="${REPL_DIR:-$(pwd)}"
  artcb_replit_git_sync
fi
