#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
#  ARTCB — Lanceur du nœud (utilisé par systemd artcb.service)
#
#  Deux modes, sans secret en clair sur le disque :
#    1. Doppler (recommandé) : si DOPPLER_TOKEN est défini (via
#       EnvironmentFile root-only /etc/artcb/doppler.env), les secrets
#       sont injectés par `doppler run` — aucun .env nécessaire.
#    2. Fallback .env : sans token Doppler, l'application charge
#       le .env local (python-dotenv) comme avant.
# ══════════════════════════════════════════════════════════════════
set -Eeuo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

export ARTCB_GIT_SHA="${ARTCB_GIT_SHA:-$(git rev-parse HEAD 2>/dev/null || true)}"
export ARTCB_GIT_BRANCH="${ARTCB_GIT_BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)}"
echo "── git ${ARTCB_GIT_BRANCH:-?}@${ARTCB_GIT_SHA:-unknown}"

UVICORN=(.venv/bin/python -m uvicorn src.api.main:app --host 0.0.0.0 --port "${ARTCB_PORT:-8000}")

if [ -n "${DOPPLER_TOKEN:-}" ] && command -v doppler &>/dev/null; then
  echo "── Démarrage via Doppler (secrets distants, aucun .env requis)"
  exec doppler run -- "${UVICORN[@]}"
else
  echo "── Démarrage via .env local (DOPPLER_TOKEN absent)"
  exec "${UVICORN[@]}"
fi
