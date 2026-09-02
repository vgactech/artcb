#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
#  ARTCB — Installation complète en une seule commande
#  Usage :
#    git clone https://github.com/vgactech/artcb.git && cd artcb && bash install.sh
#  Ou sur une installation existante :
#    bash install.sh
#
#  Ce script installe TOUT ce qui est nécessaire au runtime :
#    - venv Python isolé
#    - dépendances Python runtime depuis requirements.txt
#    - liboqs-python en option, avec timeout (jamais dans le chemin critique)
#    - frontend React (npm install + build)
#    - bibliothèque native C libartcb_chain.so
#    - configure .env à partir de .env.example (si absent)
#    - installe le suivi automatique de GitHub origin/main (timer / cron)
#    - NE démarre PAS le serveur — utilisez `bash scripts/replit_start.sh`
#      ou `uvicorn src.api.main:app --port 8000` après
# ══════════════════════════════════════════════════════════════════
set -Eeuo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

_ok()   { printf '\033[32m  ✅ %s\033[0m\n' "$*"; }
_warn() { printf '\033[33m  ⚠️  %s\033[0m\n' "$*"; }
_err()  { printf '\033[31m  ❌ %s\033[0m\n' "$*"; }
_step() { printf '\n\033[1m[%s] %s\033[0m\n' "$1" "$2"; }

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║         ARTCB — Installation complète                   ║"
echo "║  https://github.com/vgactech/artcb                      ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── 1. Python ─────────────────────────────────────────────────────
_step "1/8" "Environnement Python"
if ! command -v python3 &>/dev/null; then
  _err "python3 introuvable. Installez-le avant de relancer."
  _err "  Ubuntu/Debian : sudo apt install python3 python3-venv"
  _err "  macOS         : brew install python3"
  exit 1
fi
PY_VER=$(python3 --version 2>&1)
_ok "Python : $PY_VER"

VENV="$REPO_DIR/.venv"
if [ ! -f "$VENV/bin/python3" ]; then
  python3 -m venv "$VENV"
  _ok "venv créé : $VENV"
else
  _ok "venv existant : $VENV"
fi
PYTHON="$VENV/bin/python3"
PIP="$VENV/bin/pip"
export PATH="$VENV/bin:$PATH"
export PIP_USER=false

# ── 2. Dépendances Python runtime ─────────────────────────────────
_step "2/8" "Dépendances Python"
ARTCB_PYTHON="$PYTHON" bash "$REPO_DIR/scripts/install_python_dependencies.sh"
_ok "Dépendances Python installées"

# ── 3. Statut PQC (sans compilation dans le chemin critique) ─────
_step "3/8" "Vérification PQC (liboqs)"
if "$PYTHON" -c "import ctypes.util; exit(0 if ctypes.util.find_library('oqs') or ctypes.util.find_library('liboqs') else 1)" 2>/dev/null; then
  _ok "liboqs natif : présent — ML-DSA-65 + ML-KEM-768 potentiellement disponibles"
else
  _warn "liboqs natif absent — fallback Ed25519/X25519 actif"
  _warn "PQC optionnel borné : ARTCB_INSTALL_PQC=1 ARTCB_PQC_TIMEOUT=300 bash install.sh"
fi

# ── 4. Frontend React ─────────────────────────────────────────────
_step "4/8" "Frontend React (npm)"
if ! command -v node &>/dev/null || ! command -v npm &>/dev/null; then
  _warn "node/npm introuvables — frontend ne sera pas buildé"
  _warn "  Ubuntu : sudo apt install nodejs npm"
  _warn "  macOS  : brew install node"
else
  NODE_VER=$(node --version 2>&1)
  _ok "Node.js : $NODE_VER"
  cd "$REPO_DIR/frontend"
  if [ -f package-lock.json ]; then
    npm ci --no-audit --no-fund --silent
  else
    npm install --no-audit --no-fund --silent
  fi
  npm run build --silent
  cd "$REPO_DIR"
  _ok "Frontend buildé dans frontend/dist/"
fi

# ── 5. Bibliothèque C native ──────────────────────────────────────
_step "5/8" "Bibliothèque C libartcb_chain.so"
# NB : toujours recompiler via le Makefile C (source de vérité).
# L'ancienne commande cc inline avec -I"$(pkg-config --cflags ...)" produisait
# une .so SANS symboles quand pkg-config renvoyait une chaîne vide (le -I nu
# consommait le fichier source) — 26 tests échouaient avec
# « undefined symbol: artcb_sha256_hex ».
if command -v cc &>/dev/null || command -v gcc &>/dev/null; then
   if timeout --foreground --signal=TERM --kill-after=10s "${ARTCB_C_BUILD_TIMEOUT:-120}s" \
      make -C src/c clean all >/dev/null 2>&1 \
     && nm -D src/c/libartcb_chain.so 2>/dev/null | grep -q artcb_sha256_hex; then
    _ok "libartcb_chain.so compilé (symboles artcb_* vérifiés)"
  else
    rm -f src/c/libartcb_chain.so
    _warn "libartcb_chain.so : compilation échouée — fallback Python actif"
  fi
else
  _warn "Compilateur C absent — libartcb_chain.so ignoré (fallback Python)"
fi

# ── 6. Configuration .env ─────────────────────────────────────────
_step "6/8" "Configuration .env"
if [ ! -f ".env" ]; then
  cp .env.example .env
  _ok ".env créé depuis .env.example"
  _warn "IMPORTANT : éditez .env et renseignez au minimum :"
  _warn "  ARTCB_WALLET_PASSPHRASE=<un mot de passe fort>"
  _warn "  ARTCB_NODE_WALLET_ADDRESS sera créé via POST /setup/init-node"
else
  _ok ".env existant conservé"
fi

# ── 7. Suivi automatique de origin/main ───────────────────────────
_step "7/8" "Suivi automatique de GitHub origin/main"
bash "$REPO_DIR/scripts/install_follow_main.sh" || _warn "install_follow_main.sh non bloquant"
_ok "Un clone sur main propre recevra les mises à jour (ff-only)"
_ok "Un nœud officiel reset --hard keep-book (livre / .env / .venv intacts)"

# ── 8. Résumé ─────────────────────────────────────────────────────
_step "8/8" "Résumé"
echo ""
  echo "  Installation terminée (socle runtime installé, PQC optionnel non bloquant)."
echo ""
echo "  Pour démarrer le nœud :"
  echo "    bash scripts/verify_installation.sh"
  echo "    bash scripts/replit_start.sh      (Replit)"
echo "    source .venv/bin/activate && uvicorn src.api.main:app --host 0.0.0.0 --port 8000   (local)"
echo ""
echo "  Première utilisation :"
echo "    1. Ouvrir http://localhost:8000"
echo "    2. Le nœud démarre en mode bootstrap"
echo "    3. POST /setup/init-node {node_name, password} → sauvegarder seed_hex"
echo "    4. Redémarrer → toutes les routes sont actives"
echo ""
echo "  Mises à jour : bash scripts/artcb_follow_main.sh   (ou le timer installé ci-dessus)"
echo "  Statut PQC : GET /health → pqc.available"
echo ""
