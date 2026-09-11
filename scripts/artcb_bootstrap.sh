#!/usr/bin/env bash
# ARTCB — bootstrap zero-touch pour clone GitHub (R322 2026-09-11T21:40:00Z)
#
# Usage (utilisateur futur) :
#   git clone https://github.com/vgactech/artcb.git && cd artcb && bash scripts/artcb_bootstrap.sh
#
# Installe les dépendances OS manquantes (si droits), puis délègue à install.sh
# (venv, pip, frontend, lib C, .env, follow-main). Idempotent.
#
# Variables :
#   ARTCB_BOOTSTRAP_SKIP_OS=1   — ne tente pas apt/brew
#   ARTCB_INSTALL_PQC=1         — tente liboqs (optionnel, borné)
#   ARTCB_BOOTSTRAP_VERIFY=0    — saute verify_installation.sh
set -Eeuo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

_ok()   { printf '\033[32m  ✅ %s\033[0m\n' "$*"; }
_warn() { printf '\033[33m  ⚠️  %s\033[0m\n' "$*"; }
_err()  { printf '\033[31m  ❌ %s\033[0m\n' "$*"; }
_step() { printf '\n\033[1m[%s] %s\033[0m\n' "$1" "$2"; }

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║     ARTCB — Bootstrap clone (OS + runtime)              ║"
echo "╚══════════════════════════════════════════════════════════╝"

need_cmd() { command -v "$1" >/dev/null 2>&1; }

_sudo() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  elif need_cmd sudo; then
    sudo -n "$@" 2>/dev/null || sudo "$@"
  else
    return 1
  fi
}

_step "0/3" "Dépendances système (idempotent)"
if [ "${ARTCB_BOOTSTRAP_SKIP_OS:-0}" = "1" ]; then
  _warn "ARTCB_BOOTSTRAP_SKIP_OS=1 — étape OS ignorée"
else
  OS="$(uname -s 2>/dev/null || echo unknown)"
  case "$OS" in
    Darwin)
      if ! need_cmd brew; then
        _warn "Homebrew absent — installez https://brew.sh puis relancez pour node/cmake"
      else
        MISSING=()
        need_cmd python3 || MISSING+=(python3)
        need_cmd node || MISSING+=(node)
        need_cmd npm || MISSING+=(node)
        need_cmd cmake || MISSING+=(cmake)
        need_cmd pkg-config || MISSING+=(pkg-config)
        need_cmd openssl || MISSING+=(openssl@3)
        if [ "${#MISSING[@]}" -gt 0 ]; then
          # uniq
          uniq=()
          for p in "${MISSING[@]}"; do
            skip=0
            for u in "${uniq[@]:-}"; do [ "$u" = "$p" ] && skip=1 && break; done
            [ "$skip" -eq 0 ] && uniq+=("$p")
          done
          _ok "brew install ${uniq[*]}"
          brew install "${uniq[@]}" || _warn "brew install partiel — poursuite"
        else
          _ok "Outils macOS déjà présents"
        fi
      fi
      ;;
    Linux)
      if need_cmd apt-get; then
        PKGS=()
        need_cmd python3 || PKGS+=(python3)
        dpkg -s python3-venv >/dev/null 2>&1 || PKGS+=(python3-venv)
        dpkg -s python3-pip >/dev/null 2>&1 || PKGS+=(python3-pip)
        need_cmd node || PKGS+=(nodejs)
        need_cmd npm || PKGS+=(npm)
        need_cmd gcc || PKGS+=(build-essential)
        need_cmd cmake || PKGS+=(cmake)
        need_cmd pkg-config || PKGS+=(pkg-config)
        dpkg -s libssl-dev >/dev/null 2>&1 || PKGS+=(libssl-dev)
        if [ "${#PKGS[@]}" -gt 0 ]; then
          if _sudo apt-get update -y && _sudo apt-get install -y "${PKGS[@]}"; then
            _ok "apt install ${PKGS[*]}"
          else
            _warn "apt non disponible (sudo) — installez manuellement : ${PKGS[*]}"
          fi
        else
          _ok "Paquets Debian/Ubuntu déjà présents"
        fi
      elif need_cmd dnf; then
        PKGS=()
        need_cmd python3 || PKGS+=(python3)
        need_cmd gcc || PKGS+=(gcc gcc-c++ make)
        need_cmd cmake || PKGS+=(cmake)
        need_cmd node || PKGS+=(nodejs)
        if [ "${#PKGS[@]}" -gt 0 ]; then
          _sudo dnf install -y "${PKGS[@]}" || _warn "dnf install partiel"
        fi
      else
        _warn "Gestionnaire de paquets non détecté — vérifiez python3/node/gcc manuellement"
      fi
      ;;
    *)
      _warn "OS=$OS non géré pour auto-OS — python3 + pip + node recommandés"
      ;;
  esac
fi

if ! need_cmd python3; then
  _err "python3 toujours introuvable après bootstrap OS"
  exit 1
fi
_ok "python3 : $(python3 --version 2>&1)"

_step "1/3" "install.sh (venv + pip + frontend + C + .env + follow-main)"
bash "$REPO_DIR/install.sh"

_step "2/3" "Vérification"
if [ "${ARTCB_BOOTSTRAP_VERIFY:-1}" != "0" ] && [ -x "$REPO_DIR/scripts/verify_installation.sh" ]; then
  bash "$REPO_DIR/scripts/verify_installation.sh" || _warn "verify_installation a signalé des écarts (non bloquant si fallback Python)"
else
  _warn "verify sauté"
fi

_step "3/3" "Suite utilisateur"
echo ""
echo "  Démarrer :"
echo "    source .venv/bin/activate"
echo "    PYTHONPATH=src uvicorn src.api.main:app --host 0.0.0.0 --port 8000"
echo ""
echo "  Joindre le réseau public (catch-up) :"
echo "    PYTHONPATH=src:scripts python3 scripts/artcb_doctor.py"
echo "    # jamais wipe blocks.jsonl ; trou seed 716 = STOP honnête si pas d'enfant"
echo ""
echo "  PQC optionnel : ARTCB_INSTALL_PQC=1 bash scripts/artcb_bootstrap.sh"
echo "  swtpm (tests TPM logiciels) : install OS-spécifique — doctor signale l'écart"
echo ""
_ok "Bootstrap terminé"
