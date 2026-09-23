#!/usr/bin/env bash
# artcb_r425_reset_device_binding.sh — Reset opérateur d'un binding appareil ARTCB
#
# Usage :
#   ./scripts/artcb_r425_reset_device_binding.sh <FINGERPRINT> [BASE_URL] [BEARER_TOKEN]
#
# Exemple (dev local) :
#   ./scripts/artcb_r425_reset_device_binding.sh 97a0b6403ecb4932 http://localhost:8000 <your_token>
#
# Exemple (nœud live) :
#   ./scripts/artcb_r425_reset_device_binding.sh 97a0b6403ecb4932 https://artcb.me <your_token>
#
# Ce script exécute :
#   1. GET  /api/v1/admin/device-binding/list  → vérifie que le fingerprint existe
#   2. DELETE /api/v1/admin/device-binding/fingerprint/<FINGERPRINT>  → révoque le binding
#   3. Affiche la réponse JSON complète
#
# PROTOCOLE ARTCB — mode DEBUG — logs horodatés sur stdout.
# Jamais de suppression silencieuse : chaque opération est confirmée.
# Ce script ne supprime PAS la credential WebAuthn côté navigateur.
# Pour repartir à zéro complètement, l'utilisateur doit aussi supprimer sa
# credential WebAuthn dans les paramètres de sécurité du navigateur.
#
# CERTIFIED_100=false

set -euo pipefail

FINGERPRINT="${1:-}"
BASE_URL="${2:-http://localhost:8000}"
BEARER_TOKEN="${3:-}"

TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

if [[ -z "$FINGERPRINT" ]]; then
    echo "[ERROR] Usage: $0 <FINGERPRINT> [BASE_URL] [BEARER_TOKEN]"
    echo "  Fingerprint = les 16+ premiers caractères hex de l'empreinte appareil"
    echo "  Exemple: $0 97a0b6403ecb4932 https://artcb.me <token>"
    exit 1
fi

if [[ -z "$BEARER_TOKEN" ]]; then
    # Tenter de lire depuis l'environnement
    BEARER_TOKEN="${ARTCB_OPERATOR_TOKEN:-}"
    if [[ -z "$BEARER_TOKEN" ]]; then
        echo "[ERROR] Token opérateur requis. Passer en \$3 ou définir ARTCB_OPERATOR_TOKEN."
        echo "  Exemple: ARTCB_OPERATOR_TOKEN=<token> $0 $FINGERPRINT $BASE_URL"
        exit 1
    fi
fi

echo "[$TS] [R425] Reset device binding ARTCB"
echo "  Fingerprint : $FINGERPRINT"
echo "  Nœud cible  : $BASE_URL"
echo ""

# ── Étape 1 : Vérifier que le binding existe ──────────────────────────────────
echo "[$TS] [STEP 1] Lecture liste des bindings..."
LIST_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
    -H "Authorization: Bearer $BEARER_TOKEN" \
    -H "Content-Type: application/json" \
    "$BASE_URL/api/v1/admin/device-binding/list" 2>&1)

HTTP_STATUS=$(echo "$LIST_RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
LIST_BODY=$(echo "$LIST_RESPONSE" | grep -v "HTTP_STATUS:")

if [[ "$HTTP_STATUS" != "200" ]]; then
    echo "[ERROR] GET /api/v1/admin/device-binding/list → HTTP $HTTP_STATUS"
    echo "  Réponse : $LIST_BODY"
    echo ""
    echo "[HINT] Vérifier :"
    echo "  - Le token Bearer est valide (wallet opérateur avec droits write)"
    echo "  - Le nœud répond : curl $BASE_URL/api/v1/health"
    exit 2
fi

echo "  → HTTP $HTTP_STATUS OK"
echo "  Bindings existants :"
echo "$LIST_BODY" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    bindings = d.get('production', [])
    if not bindings:
        print('  (aucun binding PRODUCTION)')
    for b in bindings:
        fp = b.get('device_fingerprint','?')
        wn = b.get('wallet_name','?')
        ts = b.get('created_at','?')
        print(f'  FP={fp[:16]}… wallet={wn} created={ts}')
except Exception as e:
    print(f'  (parse JSON failed: {e})')
    print(sys.stdin.read()[:500])
" 2>/dev/null || echo "$LIST_BODY" | head -20
echo ""

# ── Étape 2 : Révoquer le binding ────────────────────────────────────────────
echo "[$TS] [STEP 2] Révocation binding fingerprint=$FINGERPRINT..."
DEL_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
    -X DELETE \
    -H "Authorization: Bearer $BEARER_TOKEN" \
    -H "Content-Type: application/json" \
    "$BASE_URL/api/v1/admin/device-binding/fingerprint/$FINGERPRINT" 2>&1)

HTTP_STATUS_DEL=$(echo "$DEL_RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
DEL_BODY=$(echo "$DEL_RESPONSE" | grep -v "HTTP_STATUS:")

echo "  → HTTP $HTTP_STATUS_DEL"
echo "  Réponse : $DEL_BODY" | python3 -m json.tool 2>/dev/null || echo "  Réponse : $DEL_BODY"
echo ""

if [[ "$HTTP_STATUS_DEL" == "200" ]]; then
    echo "[$TS] [R425] ✅ Binding RÉVOQUÉ avec succès."
    echo ""
    echo "  PROCHAINES ÉTAPES pour l'utilisateur :"
    echo "  1. Sur le navigateur/appareil concerné :"
    echo "     → Ouvrir les paramètres de sécurité du navigateur"
    echo "     → Supprimer la credential WebAuthn associée à artcb.me"
    echo "     → (Chrome : chrome://settings/securityKeys)"
    echo "     → (Safari : Préférences → Mots de passe → Passkeys)"
    echo "  2. Retourner sur l'interface ARTCB → /register"
    echo "     → Créer un nouveau wallet avec un nouveau WebAuthn"
    echo ""
    echo "  ⚠️  IMPORTANT : seed_hex de l'ancien wallet toujours valide."
    echo "     Si l'utilisateur veut récupérer l'ANCIEN wallet, utiliser seed_hex."
    echo "     Ce reset permet de créer un NOUVEAU wallet sur cet appareil."
elif [[ "$HTTP_STATUS_DEL" == "404" ]]; then
    echo "[WARN] Fingerprint non trouvé dans les bindings PRODUCTION."
    echo "  Vérifier que le fingerprint est exact (16+ hex chars)."
    echo "  Le binding a peut-être déjà été supprimé."
else
    echo "[ERROR] Suppression échouée — HTTP $HTTP_STATUS_DEL"
    echo "  Réponse : $DEL_BODY"
    exit 3
fi

echo "[$TS] [R425] Terminé."
