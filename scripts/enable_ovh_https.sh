#!/usr/bin/env bash
# TLS on the EXISTING OVH node only (no new machine).
# Self-signed cert with IP SAN — Let's Encrypt needs a DNS name we do not have.
# Serves https://152.228.144.34:8443 → proxy to 127.0.0.1:8000
set -Eeuo pipefail
SERVER_IP="${1:-152.228.144.34}"
SSH_USER="${OVH_DEPLOY_USER:-ubuntu}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
KNOWN_HOSTS="$REPO/deploy/ovh_artcb_node_1.known_hosts"
SSH_OPTS=(-o ConnectTimeout=15 -o IdentitiesOnly=yes -o BatchMode=yes)
if [ -f "${HOME}/.ssh/artcb_ovh_deploy" ]; then
  SSH_OPTS+=(-i "${HOME}/.ssh/artcb_ovh_deploy")
fi
if [ -f "$KNOWN_HOSTS" ]; then
  SSH_OPTS+=(-o "UserKnownHostsFile=$KNOWN_HOSTS" -o StrictHostKeyChecking=yes)
else
  SSH_OPTS+=(-o StrictHostKeyChecking=accept-new)
fi

ssh "${SSH_OPTS[@]}" "$SSH_USER@$SERVER_IP" bash -s <<'REMOTE'
set -Eeuo pipefail
sudo mkdir -p /etc/artcb/tls /etc/nginx/conf.d
if [ ! -f /etc/artcb/tls/server.crt ]; then
  sudo openssl req -x509 -newkey rsa:2048 -sha256 -days 825 -nodes \
    -keyout /etc/artcb/tls/server.key \
    -out /etc/artcb/tls/server.crt \
    -subj "/CN=152.228.144.34/O=ARTCB/OU=artcb-node-1" \
    -addext "subjectAltName=IP:152.228.144.34"
  sudo chmod 600 /etc/artcb/tls/server.key
  sudo chmod 644 /etc/artcb/tls/server.crt
fi
if ! command -v nginx >/dev/null; then
  sudo apt-get update -y
  sudo apt-get install -y nginx
fi
sudo tee /etc/nginx/conf.d/artcb-tls.conf >/dev/null <<'NGX'
server {
    listen 8443 ssl;
    listen [::]:8443 ssl;
    ssl_certificate     /etc/artcb/tls/server.crt;
    ssl_certificate_key /etc/artcb/tls/server.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Authorization $http_authorization;
        proxy_pass_header Authorization;
    }
}
NGX
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl reload nginx || sudo systemctl restart nginx
echo "── TLS local probe"
curl -sk --max-time 10 https://127.0.0.1:8443/health | head -c 200 || true
echo
REMOTE

echo "── copy public cert (not the key)"
mkdir -p "$REPO/deploy"
scp "${SSH_OPTS[@]}" "$SSH_USER@$SERVER_IP:/etc/artcb/tls/server.crt" "$REPO/deploy/ovh_artcb_node_1.crt"
echo "── public HTTPS probe"
curl -sk --max-time 10 "https://$SERVER_IP:8443/health" | head -c 300 || true
echo
echo "── done https://$SERVER_IP:8443"
