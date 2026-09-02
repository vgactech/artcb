#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
#  ARTCB — suivre origin/main automatiquement
#
#  Nœud officiel (/etc/artcb/official_node, artcb.service, ou
#  ARTCB_FOLLOW_MODE=official) :
#    fetch → checkout -B main → reset --hard → /etc/artcb/release.env
#    → restart artcb si le SHA a changé
#
#  Clone (machine perso / serveur nouvellement installé) :
#    fetch → pull --ff-only si on est sur main et le tree est propre
#    ARTCB_FOLLOW_MAIN=1 : reset keep-book (toujours sans wipe)
#
#  Interdits : wipe data/chain/blocks.jsonl, install.sh, genesis,
#  init-node, rescue, affichage de token / PEM.
#
#  Fetch GitHub (dépôt public) sans mot de passe :
#    1) git fetch origin (HTTP/1.1, credential.helper vide)
#    2) git fetch https://github.com/vgactech/artcb.git
#    3) nœud officiel seulement : SHA GitHub API + tarball overlay
#       (chemins protégés exclus) si le smart-HTTP répond 401
# ══════════════════════════════════════════════════════════════════
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

GITHUB_HTTPS="${ARTCB_GITHUB_URL:-https://github.com/vgactech/artcb.git}"
GITHUB_API_MAIN="${ARTCB_GITHUB_API_MAIN:-https://api.github.com/repos/vgactech/artcb/commits/main}"
GITHUB_TARBALL_FMT="${ARTCB_GITHUB_TARBALL_FMT:-https://codeload.github.com/vgactech/artcb/tar.gz/%s}"
LOG_DIR="${ARTCB_FOLLOW_LOG_DIR:-$REPO_DIR/data/follow_main}"
mkdir -p "$LOG_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/${STAMP}.log"

_log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG" >/dev/null; echo "$*"; }

_is_official() {
  if [[ "${ARTCB_FOLLOW_MODE:-}" == "official" ]]; then
    return 0
  fi
  if [[ -f /etc/artcb/official_node ]]; then
    return 0
  fi
  if command -v systemctl >/dev/null 2>&1 && systemctl is-enabled artcb >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

_book_guard() {
  local book="data/chain/blocks.jsonl"
  if [[ -f "$book" ]]; then
    _log "blocks.jsonl not emptied lines=$(wc -l < "$book" | tr -d ' ')"
  else
    _log "blocks.jsonl absent (clone without chain yet)"
  fi
  _log "install.sh not executed"
  _log "init_genesis.py not executed"
  _log "init-node not executed"
  _log "rescue not used"
}

_anon_git() {
  GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=true \
    git -c credential.helper= \
        -c http.extraHeader= \
        -c http.version=HTTP/1.1 \
        "$@"
}

_github_main_sha() {
  python3 - "$GITHUB_API_MAIN" <<'PY'
import json, sys, urllib.request
url = sys.argv[1]
req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "artcb-follow-main"})
with urllib.request.urlopen(req, timeout=20) as resp:
    payload = json.loads(resp.read().decode("utf-8"))
sha = payload.get("sha") or ""
if len(sha) != 40:
    raise SystemExit("github_api_sha_invalid")
print(sha)
PY
}

_tarball_overlay() {
  local sha="$1"
  local url
  # shellcheck disable=SC2059
  url="$(printf "$GITHUB_TARBALL_FMT" "$sha")"
  local tmp
  tmp="$(mktemp -d /tmp/artcb-main-XXXXXX)"
  _log "FETCH_METHOD=tarball sha=$sha"
  if ! curl -fsSL --retry 3 --retry-delay 2 -o "$tmp/main.tgz" "$url"; then
    rm -rf "$tmp"
    _log "tarball download failed"
    return 1
  fi
  mkdir -p "$tmp/src"
  tar -xzf "$tmp/main.tgz" -C "$tmp/src" --strip-components=1
  # Overlay code only. Never touch the book, local secrets, venv, or git objects.
  rsync -a --delete \
    --exclude '.git/' \
    --exclude 'data/' \
    --exclude '.env' \
    --exclude '.venv/' \
    --exclude 'frontend/node_modules/' \
    --exclude 'frontend/dist/' \
    --exclude '*.pem' \
    --exclude '*.key' \
    --exclude 'data/follow_main/' \
    "$tmp/src/" "$REPO_DIR/"
  rm -rf "$tmp"
  _log "tarball overlay applied (protected paths skipped)"
  return 0
}

_fetch_main() {
  local err
  err="$(mktemp)"
  if _anon_git fetch --prune origin "+refs/heads/main:refs/remotes/origin/main" 2>"$err"; then
    rm -f "$err"
    _log "FETCH_METHOD=origin"
    return 0
  fi
  _log "origin fetch failed: $(tr '\n' ' ' < "$err" | tail -c 240)"
  if _anon_git fetch --prune "$GITHUB_HTTPS" "+refs/heads/main:refs/remotes/origin/main" 2>"$err"; then
    rm -f "$err"
    _log "FETCH_METHOD=https_direct"
    return 0
  fi
  _log "https_direct fetch failed: $(tr '\n' ' ' < "$err" | tail -c 240)"
  rm -f "$err"
  return 1
}

_write_release() {
  local sha="$1" br="$2"
  if [[ ! -d /etc/artcb ]] && ! sudo -n true >/dev/null 2>&1; then
    _log "release.env skipped (no /etc/artcb and no sudo)"
    return 0
  fi
  printf 'ARTCB_GIT_SHA=%s\nARTCB_GIT_BRANCH=%s\n' "$sha" "$br" > /tmp/artcb_release.env
  sudo mkdir -p /etc/artcb
  sudo cp /tmp/artcb_release.env /etc/artcb/release.env
  sudo chmod 644 /etc/artcb/release.env
  rm -f /tmp/artcb_release.env
  _log "release.env sha=$sha branch=$br"
}

_restart_if_needed() {
  local before="$1" after="$2"
  if [[ "$before" == "$after" ]]; then
    _log "no restart (sha unchanged)"
    return 0
  fi
  if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files artcb.service >/dev/null 2>&1; then
    sudo systemctl restart artcb
    _log "artcb restarted old=$before new=$after"
  else
    _log "artcb.service absent — restart skipped"
  fi
}

BEFORE_SHA="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
BEFORE_BR="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
_log "follow-main start repo=$REPO_DIR before=$BEFORE_SHA branch=$BEFORE_BR"

MODE="clone"
if _is_official; then
  MODE="official"
fi
if [[ "${ARTCB_FOLLOW_MAIN:-}" == "1" && "$MODE" != "official" ]]; then
  MODE="forced"
fi
_log "MODE=$MODE"

FETCH_OK=0
if _fetch_main; then
  FETCH_OK=1
fi

TARGET_SHA=""
if [[ "$FETCH_OK" == "1" ]] && git show-ref --verify --quiet refs/remotes/origin/main; then
  TARGET_SHA="$(git rev-parse refs/remotes/origin/main)"
  _log "target origin/main=$TARGET_SHA"
fi

if [[ -z "$TARGET_SHA" ]]; then
  if [[ "$MODE" == "official" || "$MODE" == "forced" ]]; then
    if TARGET_SHA="$(_github_main_sha)"; then
      if [[ "$TARGET_SHA" != "$BEFORE_SHA" ]]; then
        _tarball_overlay "$TARGET_SHA" || { _book_guard; exit 2; }
      else
        _log "tarball skipped (already $TARGET_SHA)"
      fi
    else
      _log "cannot resolve GitHub main SHA"
      _book_guard
      exit 3
    fi
  else
    _log "clone mode: git fetch failed; leave working tree untouched"
    _book_guard
    exit 4
  fi
elif [[ "$MODE" == "official" || "$MODE" == "forced" ]]; then
  git checkout -f -B main origin/main
  git reset --hard origin/main
  TARGET_SHA="$(git rev-parse HEAD)"
  _log "keep-book reset --hard $TARGET_SHA"
elif [[ "$MODE" == "clone" ]]; then
  CUR_BR="$(git rev-parse --abbrev-ref HEAD)"
  if [[ "$CUR_BR" != "main" ]]; then
    _log "clone on branch $CUR_BR — no checkout (will not destroy local work)"
    _book_guard
    exit 0
  fi
  if [[ -n "$(git status --porcelain)" ]]; then
    _log "clone tree dirty — skip ff-only (ARTCB_FOLLOW_MAIN=1 to force)"
    _book_guard
    exit 0
  fi
  git merge --ff-only origin/main
  TARGET_SHA="$(git rev-parse HEAD)"
  _log "clone ff-only $TARGET_SHA"
fi

AFTER_SHA="$(git rev-parse HEAD 2>/dev/null || echo "$TARGET_SHA")"
AFTER_BR="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
# Tarball path: working tree matches GitHub but git objects may be stale.
if [[ "$FETCH_OK" != "1" && -n "$TARGET_SHA" ]]; then
  AFTER_SHA="$TARGET_SHA"
  AFTER_BR="main"
fi

if [[ "$MODE" == "official" || "$MODE" == "forced" ]]; then
  _write_release "$AFTER_SHA" "$AFTER_BR"
  _restart_if_needed "$BEFORE_SHA" "$AFTER_SHA"
fi

_book_guard
_log "DEPLOYED_SHA=$AFTER_SHA"
_log "DEPLOYED_BRANCH=$AFTER_BR"
_log "follow-main done"
