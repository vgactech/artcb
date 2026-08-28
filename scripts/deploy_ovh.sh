#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
#  ARTCB — Déploiement / redéploiement sur l'instance OVH
#
#  Usage (depuis une machine ayant un accès SSH à l'instance) :
#    bash scripts/deploy_ovh.sh [IP] [BRANCHE]
#
#  Défauts : IP=152.228.144.34 (artcb-node-1, GRA11). BRANCHE obligatoire
#  (ne pas déployer main par défaut). ARTCB_DEPLOY_BRANCH peut la fournir.
#  Prérequis : clé SSH autorisée pour l'utilisateur ubuntu.
#  Variables : ARTCB_SSH_KEY=~/.ssh/xxx pour forcer une clé.
#
#  Premier déploiement : le script installe tout (install.sh) puis
#  enregistre le service systemd artcb.service. Les déploiements
#  suivants font git pull + install.sh + restart.
# ══════════════════════════════════════════════════════════════════
set -Eeuo pipefail

SERVER_IP="${1:-${OVH_SERVER_IP:-152.228.144.34}}"
BRANCH="${2:-${ARTCB_DEPLOY_BRANCH:-}}"
SSH_USER="${OVH_SERVER_USER:-ubuntu}"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10)
[ -n "${ARTCB_SSH_KEY:-}" ] && SSH_OPTS+=(-i "$ARTCB_SSH_KEY")

if [ -z "$BRANCH" ]; then
  echo "Usage: bash scripts/deploy_ovh.sh [IP] BRANCH"
  echo "BRANCH is required (do not silently deploy main)."
  echo "Example: bash scripts/deploy_ovh.sh 152.228.144.34 cursor/tokenomics-21m-hbp-owner-decay-3fcb"
  exit 1
fi

echo "── Déploiement ARTCB → $SSH_USER@$SERVER_IP (branche $BRANCH)"

ssh "${SSH_OPTS[@]}" "$SSH_USER@$SERVER_IP" bash -s <<REMOTE
set -Eeuo pipefail

# 1. Code
if [ ! -d ~/artcb/.git ]; then
  git clone https://github.com/vgactech/artcb.git ~/artcb
fi
cd ~/artcb
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"
DEPLOYED_SHA=\$(git rev-parse HEAD)
DEPLOYED_BRANCH=\$(git rev-parse --abbrev-ref HEAD)
echo "── Commit déployé : \$(git log --oneline -1) sha=\$DEPLOYED_SHA"
mkdir -p /home/ubuntu/artcb
printf 'ARTCB_GIT_SHA=%s\nARTCB_GIT_BRANCH=%s\n' "\$DEPLOYED_SHA" "\$DEPLOYED_BRANCH" > /tmp/artcb_release.env
chmod 644 /tmp/artcb_release.env
sudo mkdir -p /etc/artcb
sudo cp /tmp/artcb_release.env /etc/artcb/release.env
sudo chmod 644 /etc/artcb/release.env

# 2. Installation (idempotente)
bash install.sh

# 3. Secrets : Doppler (recommandé) ou .env fallback
if [ -f /etc/artcb/doppler.env ]; then
  echo "── Secrets via Doppler (token présent dans /etc/artcb/doppler.env)"
  rm -f .env
else
  if ! grep -q '^ARTCB_WALLET_PASSPHRASE=' .env 2>/dev/null; then
    echo "ARTCB_WALLET_PASSPHRASE=\$(openssl rand -base64 24 | tr -d '=/+')" >> .env
    chmod 600 .env
    echo "── Passphrase wallet générée dans .env (à migrer vers Doppler)"
  fi
  sed -i 's|^ARTCB_HOST=.*|ARTCB_HOST=0.0.0.0|' .env
fi

# 4. Service systemd
sudo cp scripts/artcb.service /etc/systemd/system/artcb.service
sudo systemctl daemon-reload
sudo systemctl enable artcb.service
sudo systemctl restart artcb.service
sleep 5
sudo systemctl --no-pager --lines=5 status artcb.service || true

# 5. Vérification santé locale
curl -sf http://127.0.0.1:8000/api/v1/health | head -c 400 && echo
REMOTE

echo "── Vérification santé publique"
curl -sf "http://$SERVER_IP:8000/api/v1/health" | head -c 400 && echo
echo "── Déploiement terminé : http://$SERVER_IP:8000"
