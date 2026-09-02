# PROMPT — Agent Replit ARTCB (201)

Copie-colle ce bloc. **Branche officielle = `main`.** Le PIN de `cursor/replit-sync-ready-16d8` / SHA 200 **ne marche plus**.

## Secrets (panneau 🔒)

| Secret | Valeur |
|--------|--------|
| `ARTCB_REPLIT_BRANCH` | `main` |
| `ARTCB_REPLIT_PIN_SHA` | SHA **complet 40 hex** de `origin/main` (rapport 201, section mesurée). **Pas** un SHA court. |
| `SESSION_SECRET` | garder |
| `DOPPLER_TOKEN` | garder |

Ne mets **jamais** le PIN dans `.replit`.

## Après avoir collé le PIN

1. **Publish / Redeploy** Autoscale (le snapshot doit être ce SHA).
2. `ARTCB_REPLIT_SNAPSHOT_ONLY=1` est normal au boot : pas de `git clone` à chaque start.
3. Replit reste **bootstrap** : pas de wallet, pas de `init-node`.
4. Si `release_integrity=pin_mismatch` : le snapshot n’est pas descendant du PIN → Republish, ou vérifie que le PIN est bien le SHA `main` actuel (ou un **ancêtre**).

## Interdits

- Ne pas pointer `cursor/replit-sync-ready-16d8`
- Ne pas `git reset --hard` sans PIN
- Ne pas inverser `certified_distributed_mainnet`
- Ne pas coller de clés / tokens dans le chat
