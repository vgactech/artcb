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
#  Ne crée PAS de VM OVH 2.
# ══════════════════════════════════════════════════════════════════
set -Eeuo pipefail

SERVER_IP="${1:-}"
BRANCH="${2:-${ARTCB_DEPLOY_BRANCH:-}}"
SSH_USER="${AWS_DEPLOY_USER:-ubuntu}"
SSH_KEY="${ARTCB_AWS_SSH_KEY:-${HOME}/.ssh/artcb_aws_node_3}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
KNOWN_HOSTS="${ARTCB_AWS_KNOWN_HOSTS:-$REPO/deploy/aws_artcb_node_3.known_hosts}"

if [ -z "$SERVER_IP" ] || [ -z "$BRANCH" ]; then
  echo "Usage: bash scripts/deploy_aws.sh IP BRANCH"
  echo "Example: bash scripts/deploy_aws.sh 203.0.113.10 cursor/aws-node-3-ec2-launch-16d8"
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

echo "── Attente SSH ubuntu@$SERVER_IP"
ok_ssh=0
for i in $(seq 1 36); do
  if ssh "${SSH_OPTS[@]}" "$SSH_USER@$SERVER_IP" 'echo ssh-ok' >/dev/null 2>&1; then
    ok_ssh=1
    echo "── SSH OK (tentative $i)"
    break
  fi
  sleep 5
done
if [ "$ok_ssh" != "1" ]; then
  echo "SSH timeout vers $SERVER_IP"
  exit 2
fi

echo "── Pose Doppler artcb3 (token jamais affiché)"
DOPPLER_TMP="$(mktemp)"
chmod 600 "$DOPPLER_TMP"
python3 - "$DOPPLER_TMP" "$REPO" <<'PY'
import os
import sys
from pathlib import Path

out = Path(sys.argv[1])
repo = Path(sys.argv[2])
sys.path.insert(0, str(repo / "src"))
from artcb.live import parse_env_file  # noqa: E402
from artcb.node_registry import local_env_path  # noqa: E402

lines: list[str] = []
token = (os.environ.get("KEY_API_ARTCB_DOPPLER_3") or "").strip()
if token:
    lines.append("DOPPLER_TOKEN=" + token)
lines.append("DOPPLER_PROJECT=artcb3")
lines.append("DOPPLER_CONFIG=dev")
lines.append("ARTCB_NODE_ID=aws-node-3")
local = parse_env_file(local_env_path("aws-node-3"))
pw = (local.get("ARTCB_WALLET_PASSPHRASE") or "").strip()
if pw:
    lines.append("ARTCB_WALLET_PASSPHRASE=" + pw)
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
out.chmod(0o600)
print("doppler.env prepared keys=" + str(len(lines)) + " (values not printed)")
PY
scp "${SSH_OPTS[@]}" "$DOPPLER_TMP" "$SSH_USER@$SERVER_IP:/tmp/artcb_doppler.env"
rm -f "$DOPPLER_TMP"

echo "── Déploiement ARTCB aws-node-3 → $SSH_USER@$SERVER_IP (branche $BRANCH)"

ssh "${SSH_OPTS[@]}" "$SSH_USER@$SERVER_IP" \
  env BRANCH="$BRANCH" SERVER_IP="$SERVER_IP" \
  bash -s <<'REMOTE'
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
export ARTCB_NODE_ID=aws-node-3
if command -v cloud-init >/dev/null; then
  sudo cloud-init status --wait || true
fi
sudo apt-get update -y
sudo apt-get install -y git curl python3 python3-venv python3-pip build-essential cmake libssl-dev nginx openssl
if ! command -v doppler >/dev/null; then
  curl -sLf --retry 3 --tlsv1.2 --proto "=https" 'https://cli.doppler.com/install.sh' | sudo sh
fi
sudo mkdir -p /etc/artcb
if [ -f /tmp/artcb_doppler.env ]; then
  sudo cp /tmp/artcb_doppler.env /etc/artcb/doppler.env
  sudo chmod 600 /etc/artcb/doppler.env
  sudo chown root:root /etc/artcb/doppler.env
  rm -f /tmp/artcb_doppler.env
fi
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
DEPLOYED_SHA=$(git rev-parse HEAD)
DEPLOYED_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "── Commit déployé : $(git log --oneline -1) sha=$DEPLOYED_SHA"
printf 'ARTCB_GIT_SHA=%s\nARTCB_GIT_BRANCH=%s\nARTCB_NODE_ID=aws-node-3\n' "$DEPLOYED_SHA" "$DEPLOYED_BRANCH" > /tmp/artcb_release.env
chmod 644 /tmp/artcb_release.env
sudo cp /tmp/artcb_release.env /etc/artcb/release.env
sudo chmod 644 /etc/artcb/release.env
bash install.sh
if [ -f /etc/artcb/doppler.env ]; then
  echo "── Secrets via Doppler (token présent dans /etc/artcb/doppler.env)"
  rm -f .env
else
  if ! grep -q '^ARTCB_WALLET_PASSPHRASE=' .env 2>/dev/null; then
    echo "ARTCB_WALLET_PASSPHRASE=$(openssl rand -base64 24 | tr -d '=/+')" >> .env
    chmod 600 .env
  fi
  sed -i 's|^ARTCB_HOST=.*|ARTCB_HOST=0.0.0.0|' .env
  grep -q '^ARTCB_NODE_ID=' .env || echo 'ARTCB_NODE_ID=aws-node-3' >> .env
fi
sudo cp scripts/artcb.service /etc/systemd/system/artcb.service
sudo systemctl daemon-reload
sudo systemctl enable artcb.service
sudo systemctl restart artcb.service
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if curl -sf http://127.0.0.1:8000/health >/dev/null; then
    echo "── santé locale OK (tentative $i)"
    break
  fi
  sleep 2
done
sudo systemctl --no-pager --lines=8 status artcb.service || true
curl -sf http://127.0.0.1:8000/api/v1/health | head -c 400 && echo

sudo mkdir -p /etc/artcb/tls
if [ ! -f /etc/artcb/tls/server.crt ]; then
  sudo openssl req -x509 -newkey rsa:2048 -sha256 -days 825 -nodes \
    -keyout /etc/artcb/tls/server.key \
    -out /etc/artcb/tls/server.crt \
    -subj "/CN=${SERVER_IP}/O=ARTCB/OU=aws-node-3" \
    -addext "subjectAltName=IP:${SERVER_IP}"
  sudo chmod 600 /etc/artcb/tls/server.key
  sudo chmod 644 /etc/artcb/tls/server.crt
fi
sudo mkdir -p /etc/nginx/conf.d
sudo tee /etc/nginx/conf.d/artcb-tls.conf >/dev/null <<NGX
server {
    listen 8443 ssl;
    listen [::]:8443 ssl;
    ssl_certificate     /etc/artcb/tls/server.crt;
    ssl_certificate_key /etc/artcb/tls/server.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Authorization \$http_authorization;
        proxy_pass_header Authorization;
    }
}
NGX
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl reload nginx || sudo systemctl restart nginx
curl -sk --max-time 10 https://127.0.0.1:8443/health | head -c 200 || true
echo
REMOTE

if [ ! -f "$KNOWN_HOSTS" ]; then
  ssh-keyscan -T 10 -H "$SERVER_IP" > "$KNOWN_HOSTS" 2>/dev/null || true
fi

echo "── Vérification santé publique"
curl -sf "http://$SERVER_IP:8000/api/v1/health" | head -c 400 && echo
curl -sk "https://$SERVER_IP:8443/health" | head -c 400 && echo
echo "── Déploiement aws-node-3 terminé : http://$SERVER_IP:8000"
echo "── OVH1 152.228.144.34 n'a PAS été modifié"
