#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
#  ARTCB — Déploiement sur l'instance AWS (aws-node-3 / eu-west-3)
#
#  Usage :
#    bash scripts/deploy_aws.sh IP BRANCH
#
#  BRANCH obligatoire (ne pas déployer main par défaut).
#  Prérequis : clé SSH ~/.ssh/artcb_aws_node_3 et IP publique de l'instance.
#  Ne touche PAS au nœud OVH 1 (152.228.144.34).
# ══════════════════════════════════════════════════════════════════
set -Eeuo pipefail

SERVER_IP="${1:-}"
BRANCH="${2:-${ARTCB_DEPLOY_BRANCH:-}}"
SSH_USER="${AWS_DEPLOY_USER:-ubuntu}"
SSH_KEY="${ARTCB_AWS_SSH_KEY:-${HOME}/.ssh/artcb_aws_node_3}"
KNOWN_HOSTS="${ARTCB_AWS_KNOWN_HOSTS:-$(cd "$(dirname "$0")/.." && pwd)/deploy/aws_artcb_node_3.known_hosts}"

if [ -z "$SERVER_IP" ] || [ -z "$BRANCH" ]; then
  echo "Usage: bash scripts/deploy_aws.sh IP BRANCH"
  echo "Example: bash scripts/deploy_aws.sh 203.0.113.10 cursor/aws-node-3-doppler-e769"
  exit 1
fi
if [ ! -f "$SSH_KEY" ]; then
  echo "Missing SSH key $SSH_KEY — generate with ssh-keygen -t ed25519 -f ~/.ssh/artcb_aws_node_3"
  exit 1
fi

SSH_OPTS=(-o ConnectTimeout=20 -o IdentitiesOnly=yes -o BatchMode=yes -i "$SSH_KEY")
if [ -f "$KNOWN_HOSTS" ]; then
  SSH_OPTS+=(-o "UserKnownHostsFile=$KNOWN_HOSTS" -o StrictHostKeyChecking=yes)
else
  SSH_OPTS+=(-o StrictHostKeyChecking=accept-new)
fi

echo "── Déploiement ARTCB aws-node-3 → $SSH_USER@$SERVER_IP (branche $BRANCH)"

ssh "${SSH_OPTS[@]}" "$SSH_USER@$SERVER_IP" bash -s <<REMOTE
set -Eeuo pipefail
export ARTCB_NODE_ID=aws-node-3
if [ ! -d ~/artcb/.git ]; then
  git clone https://github.com/vgactech/artcb.git ~/artcb
fi
cd ~/artcb
git fetch origin "$BRANCH"
if git show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
  git checkout -B "$BRANCH" "origin/$BRANCH"
  git reset --hard "origin/$BRANCH"
else
  git checkout -B "$BRANCH" FETCH_HEAD
  git reset --hard FETCH_HEAD
fi
DEPLOYED_SHA=\$(git rev-parse HEAD)
DEPLOYED_BRANCH=\$(git rev-parse --abbrev-ref HEAD)
echo "── Commit déployé : \$(git log --oneline -1) sha=\$DEPLOYED_SHA"
mkdir -p /home/ubuntu/artcb
printf 'ARTCB_GIT_SHA=%s\nARTCB_GIT_BRANCH=%s\nARTCB_NODE_ID=aws-node-3\n' "\$DEPLOYED_SHA" "\$DEPLOYED_BRANCH" > /tmp/artcb_release.env
chmod 644 /tmp/artcb_release.env
sudo mkdir -p /etc/artcb
sudo cp /tmp/artcb_release.env /etc/artcb/release.env
sudo chmod 644 /etc/artcb/release.env
bash install.sh
if [ -f /etc/artcb/doppler.env ]; then
  echo "── Secrets via Doppler (token présent dans /etc/artcb/doppler.env)"
  rm -f .env
else
  if ! grep -q '^ARTCB_WALLET_PASSPHRASE=' .env 2>/dev/null; then
    echo "ARTCB_WALLET_PASSPHRASE=\$(openssl rand -base64 24 | tr -d '=/+')" >> .env
    chmod 600 .env
  fi
  sed -i 's|^ARTCB_HOST=.*|ARTCB_HOST=0.0.0.0|' .env
  grep -q '^ARTCB_NODE_ID=' .env || echo 'ARTCB_NODE_ID=aws-node-3' >> .env
fi
sudo cp scripts/artcb.service /etc/systemd/system/artcb.service
sudo systemctl daemon-reload
sudo systemctl enable artcb.service
sudo systemctl restart artcb.service
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf http://127.0.0.1:8000/health >/dev/null; then
    echo "── santé locale OK (tentative \$i)"
    break
  fi
  sleep 2
done
sudo systemctl --no-pager --lines=8 status artcb.service || true
curl -sf http://127.0.0.1:8000/api/v1/health | head -c 400 && echo
REMOTE

echo "── Vérification santé publique"
curl -sf "http://$SERVER_IP:8000/api/v1/health" | head -c 400 && echo
echo "── Déploiement aws-node-3 terminé : http://$SERVER_IP:8000"
echo "── OVH1 152.228.144.34 n'a PAS été modifié"
