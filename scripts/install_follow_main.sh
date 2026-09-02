#!/usr/bin/env bash
# Install automatic origin/main follow for this clone or official node.
# Called from install.sh so a new machine receives later main updates
# without the operator repeating the order.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"
chmod +x "$REPO_DIR/scripts/artcb_follow_main.sh" 2>/dev/null || true

_ok() { printf '  ✅ %s\n' "$*"; }
_warn() { printf '  ⚠️  %s\n' "$*"; }

is_official=0
if [[ "${ARTCB_FOLLOW_MODE:-}" == "official" ]] \
  || [[ -f /etc/artcb/official_node ]] \
  || { command -v systemctl >/dev/null 2>&1 && systemctl is-enabled artcb >/dev/null 2>&1; }; then
  is_official=1
fi

if [[ "$is_official" == "1" ]]; then
  if [[ -n "${ARTCB_NODE_ID:-}" ]] && [[ ! -f /etc/artcb/official_node ]]; then
    if sudo -n true >/dev/null 2>&1; then
      echo "${ARTCB_NODE_ID}" | sudo tee /etc/artcb/official_node >/dev/null
      sudo chmod 644 /etc/artcb/official_node
    fi
  fi
  if command -v systemctl >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
    sudo cp "$REPO_DIR/scripts/artcb-follow-main.service" /etc/systemd/system/artcb-follow-main.service
    sudo cp "$REPO_DIR/scripts/artcb-follow-main.timer" /etc/systemd/system/artcb-follow-main.timer
    sudo systemctl daemon-reload
    sudo systemctl enable --now artcb-follow-main.timer
    _ok "timer systemd officiel artcb-follow-main.timer (toutes les 5 min)"
  else
    _warn "systemd/sudo indisponible — posez le timer à la main : scripts/artcb-follow-main.timer"
  fi
  exit 0
fi

# Clone / developer / new server: follow only if on main and clean (ff-only).
if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  mkdir -p "$HOME/.config/systemd/user"
  cat > "$HOME/.config/systemd/user/artcb-follow-main.service" <<EOF
[Unit]
Description=ARTCB follow origin/main (clone ff-only)

[Service]
Type=oneshot
WorkingDirectory=$REPO_DIR
Environment=GIT_TERMINAL_PROMPT=0
ExecStart=$REPO_DIR/scripts/artcb_follow_main.sh
EOF
  cat > "$HOME/.config/systemd/user/artcb-follow-main.timer" <<EOF
[Unit]
Description=ARTCB follow origin/main every 15 minutes (clone)

[Timer]
OnBootSec=5min
OnUnitActiveSec=15min
Persistent=true
Unit=artcb-follow-main.service

[Install]
WantedBy=timers.target
EOF
  systemctl --user daemon-reload
  systemctl --user enable --now artcb-follow-main.timer >/dev/null 2>&1 || true
  _ok "timer utilisateur clone (ff-only, toutes les 15 min)"
  exit 0
fi

if command -v crontab >/dev/null 2>&1; then
  cron_line="*/15 * * * * GIT_TERMINAL_PROMPT=0 $REPO_DIR/scripts/artcb_follow_main.sh >> $REPO_DIR/data/follow_main/cron.log 2>&1"
  existing="$(crontab -l 2>/dev/null || true)"
  if echo "$existing" | grep -Fq "artcb_follow_main.sh"; then
    _ok "cron clone déjà présent"
  else
    { echo "$existing"; echo "$cron_line"; } | crontab -
    _ok "cron clone */15 (ff-only, pas de reset --hard)"
  fi
  exit 0
fi

_warn "ni systemd --user ni cron — lancez manuellement : bash scripts/artcb_follow_main.sh"
_warn "un clone sur main propre recevra origin/main en fast-forward"
