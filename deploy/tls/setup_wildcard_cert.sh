#!/bin/bash
# deploy/tls/setup_wildcard_cert.sh
# V-08 TLS FIX — 2026-09-16
#
# Lit ARTCB_TLS_CERT_WILDCARD + ARTCB_TLS_KEY_WILDCARD depuis l'environnement
# (fournis par doppler run) et configure nginx pour utiliser le certificat
# wildcard artcb.me/*.artcb.me à la place du sous-domaine spécifique.
#
# Usage (sur le nœud) :
#   doppler run --project artcb-4 --config prd -- bash deploy/tls/setup_wildcard_cert.sh
#
# Prérequis : nginx installé, doppler configuré, script lancé en root ou sudo.
#
# Ce script est idempotent : peut être relancé sans danger.

set -euo pipefail

CERT_DIR="/etc/nginx/certs/artcb-wildcard"
NGINX_TLS_CONF="/etc/nginx/conf.d/artcb-tls-wildcard.conf"
NODE_ID="${ARTCB_NODE_ID:-unknown}"
DOMAIN="artcb.me"

echo "[TLS-SETUP] node=$NODE_ID domain=$DOMAIN"
echo "[TLS-SETUP] $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ── 1. Vérifier que les variables sont présentes ─────────────────────────────
if [ -z "${ARTCB_TLS_CERT_WILDCARD:-}" ] || [ -z "${ARTCB_TLS_KEY_WILDCARD:-}" ]; then
    echo "[TLS-SETUP] ERREUR: ARTCB_TLS_CERT_WILDCARD ou ARTCB_TLS_KEY_WILDCARD manquant"
    exit 1
fi

# ── 2. Écrire les fichiers de certificat ─────────────────────────────────────
mkdir -p "$CERT_DIR"

printf '%s' "$ARTCB_TLS_CERT_WILDCARD" > "$CERT_DIR/fullchain.pem"
printf '%s' "$ARTCB_TLS_KEY_WILDCARD"  > "$CERT_DIR/privkey.pem"
chmod 644 "$CERT_DIR/fullchain.pem"
chmod 600 "$CERT_DIR/privkey.pem"
echo "[TLS-SETUP] Certificat écrit dans $CERT_DIR"

# ── 3. Créer/mettre à jour la config nginx TLS wildcard ─────────────────────
cat > "$NGINX_TLS_CONF" << NGINX_CONF
# ARTCB wildcard TLS — généré automatiquement par setup_wildcard_cert.sh
# Certificat : artcb.me + *.artcb.me (Let's Encrypt, expire 2026-12-15)
# NE PAS ÉDITER MANUELLEMENT — régénéré par doppler run + setup_wildcard_cert.sh

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name artcb.me www.artcb.me n1.artcb.me n2.artcb.me n3.artcb.me n4.artcb.me node.artcb.me _;

    ssl_certificate     $CERT_DIR/fullchain.pem;
    ssl_certificate_key $CERT_DIR/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache   shared:SSL:10m;

    # HSTS (6 mois)
    add_header Strict-Transport-Security "max-age=15768000; includeSubDomains" always;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Authorization \$http_authorization;
        proxy_pass_header Authorization;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 120s;
    }
}
NGINX_CONF

echo "[TLS-SETUP] Config nginx écrite dans $NGINX_TLS_CONF"

# ── 4. Désactiver l'ancien certificat sous-domaine si existant ───────────────
OLD_CERT_CONF_PATTERN="/etc/nginx/conf.d/artcb-tls.conf"
if [ -f "$OLD_CERT_CONF_PATTERN" ]; then
    # Commenter les blocs ssl_certificate pointant vers l'ancien cert
    if grep -q "n4.artcb.me\|n3.artcb.me\|n2.artcb.me" "$OLD_CERT_CONF_PATTERN" 2>/dev/null; then
        mv "$OLD_CERT_CONF_PATTERN" "${OLD_CERT_CONF_PATTERN}.bak-v08-$(date +%Y%m%d)"
        echo "[TLS-SETUP] Ancien cert conf sauvegardé (remplacé par wildcard)"
    fi
fi

# ── 5. Tester la config nginx ─────────────────────────────────────────────────
echo "[TLS-SETUP] Test nginx -t..."
nginx -t
echo "[TLS-SETUP] Test OK"

# ── 6. Recharger nginx ───────────────────────────────────────────────────────
systemctl reload nginx
echo "[TLS-SETUP] nginx rechargé ✅"
echo "[TLS-SETUP] Certificat wildcard artcb.me déployé — node=$NODE_ID"
