#!/usr/bin/env bash
# Replace nginx default "Welcome to nginx" with a reverse proxy to uvicorn :8000.
# Keep :8443 IP TLS (artcb-tls.conf). Never wipes the book. Never prints secrets.
# Optional: CERTBOT_NAMES="artcb.me www.artcb.me n1.artcb.me" for HTTP-01.
set -Eeuo pipefail

CONF_SRC="${ARTCB_NGINX_HTTP_CONF:-}"
if [ -z "$CONF_SRC" ]; then
  if [ -f /tmp/artcb-me-http.conf ]; then
    CONF_SRC=/tmp/artcb-me-http.conf
  elif [ -f "$(dirname "$0")/../deploy/nginx/artcb-me-http.conf" ]; then
    CONF_SRC="$(cd "$(dirname "$0")/.." && pwd)/deploy/nginx/artcb-me-http.conf"
  fi
fi
if [ -z "$CONF_SRC" ] || [ ! -f "$CONF_SRC" ]; then
  echo "missing artcb-me-http.conf" >&2
  exit 2
fi

if ! command -v nginx >/dev/null; then
  sudo apt-get update -y
  sudo apt-get install -y nginx
fi

sudo mkdir -p /etc/nginx/conf.d
sudo cp "$CONF_SRC" /etc/nginx/conf.d/artcb-me-http.conf
sudo chmod 644 /etc/nginx/conf.d/artcb-me-http.conf
# Default site owns :80 default_server — that is the Welcome page.
sudo rm -f /etc/nginx/sites-enabled/default
if [ -f /etc/nginx/sites-available/default ]; then
  sudo mv /etc/nginx/sites-available/default /etc/nginx/sites-available/default.disabled || true
fi
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl reload nginx || sudo systemctl restart nginx
echo "NGINX_HTTP_PROXY=1"
curl -sf --max-time 8 -H 'Host: artcb.me' http://127.0.0.1/health | head -c 220 || true
echo

if [ -n "${CERTBOT_NAMES:-}" ]; then
  if ! command -v certbot >/dev/null; then
    sudo apt-get update -y
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y certbot python3-certbot-nginx
  fi
  # No invented email. HTTP-01 needs :80 already proxying.
  set +e
  sudo certbot --nginx --non-interactive --agree-tos --register-unsafely-without-email \
    --keep-until-expiring --redirect \
    $(printf -- '-d %s ' $CERTBOT_NAMES)
  echo "CERTBOT_RC=$?"
  set -e
  sudo nginx -t
  sudo systemctl reload nginx || true
fi
echo "enable_artcb_me_nginx done"
