#!/bin/bash
# Script de démarrage API ARTCB avec venv
# Usage: bash scripts/start_api.sh

set -e

cd "$(dirname "$0")/.."

echo "=== Démarrage API ARTCB ==="

# Vérifier venv
if [ ! -d "venv" ]; then
    echo "FAIL venv manquant - création..."
    python3 -m venv venv
    ARTCB_PYTHON="$PWD/venv/bin/python3" \
      ARTCB_INSTALL_PQC=0 bash scripts/install_python_dependencies.sh
    echo "OK venv créé et dépendances installées"
fi

# Tuer processus existants
pkill -f "uvicorn.*8000" 2>/dev/null || true
sleep 1

# Démarrer API
echo "OK Lancement uvicorn sur http://localhost:8000"
venv/bin/uvicorn api.main:app \
    --app-dir src \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level info

# Note: Ce script reste en foreground (pas de &)
# Pour background: bash scripts/start_api.sh > logs/api.log 2>&1 &

# Made with Bob
