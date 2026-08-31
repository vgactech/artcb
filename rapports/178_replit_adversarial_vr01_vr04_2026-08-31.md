# Rapport 178 — Audit adversarial Replit (V-R01…V-R04)

**OVH1 non touché.** Mesuré au bootstrap : SHA `5b4b24ae692ac2bb8255a4a5a3ca941b4365db29`, branche `main`, PQC ML-DSA-65. D-036 + D-038 + **D-039**.

Décision : **ne pas créer le wallet** tant que V-R01–V-R04 ne sont pas verts. `/health` `pqc.available=true` n’est **pas** une preuve d’usage obligatoire.

---

## Ce que l’expert a raison de séparer

| Affirmation | Statut |
|-------------|--------|
| Environnement Replit peut compiler du natif | Rapport Replit — **non re-prouvé ici** |
| `pqc.available=true` / ML-DSA-65 dans `/health` | **Disponibilité** seulement |
| Toutes les signatures critiques = hybrid AND | **Non démontré** — et le code dit le contraire |
| Plus de fallback Ed25519 seul | **Faux** jusqu’au `2026-12-31T00:00:00Z` (D-032) |
| Wallet auto-créé | **Non** — conforme |
| 503 = bootstrap, pas 500 | **Oui**, maintenant explicite (`wallet_initialization_required`) |
| Git sync sûr | **Non** avant 178 (Architecture B). **Durci** en A (PIN) |

---

## Sonde live Cursor (2026-08-31, après le rapport Replit)

`https://artcb--vgac42.replit.app` répondait encore le **shim** :

- `/live` 200 `phase=replit_shim`
- `/api/v1/health` 200 `status=alive`, **pas** de `git_sha`, **pas** de bloc PQC FastAPI
- `/ready` 200 (bug 177 : le shim mentait « ready »)
- `/api/v1/chain/verify` 404

Donc le commit `3fd7aad` **annoncé installé** et le health PQC **annoncé** ne sont **pas** ce que cette URL publique servait au moment de la sonde. Deux processus possibles (session interactive vs Autoscale), ou uvicorn pas encore lié. **V-R01 public = FAIL** jusqu’à ce que `/health` FastAPI expose `git_sha` + `release_integrity`.

---

## V-R01 — Commit exécuté

`release_identity()` compare env / `.artcb_release` / `git rev-parse HEAD` et le PIN `ARTCB_REPLIT_PIN_SHA`.

- `release_integrity=ok` si les sources désignent le même commit
- `source_mismatch` si env et fichier se contredisent
- `pin_mismatch` si le SHA affiché ≠ PIN opérateur

Le SHA dans `/health` **peut encore mentir** si on forge `ARTCB_GIT_SHA`. Le PIN opérateur (secret Replit, pas le tip GitHub) est la contre-mesure.

## V-R02 — Test PQC négatif

Résultat **actuel** (D-032, volontaire) :

```text
liboqs absent
    → nœud démarre
    → /ready 503 (si mode normal + SHA connu)
    → chemins wallet/chain acceptent encore Ed25519
```

Ce n’est **pas** « démarrage sécurisé refusé » au sens crash-the-process. Refuser tout le process casserait l’UI bootstrap et la fenêtre D-032. On **refuse `/ready`** et on **avoue** dans `/health` :

- `availability_is_not_enforcement: true`
- `high_value_hybrid_enforced: false`
- `ed25519_only_still_accepted: true` (tant que la fenêtre est ouverte)

`HIGH_VALUE_MESSAGES` est documenté, **pas branché** sur sign/verify.

## V-R03 — Hybride réel

`verify_hybrid()` :

- signature `hybrid:` + jambe ML-DSA invalide → **False** (AND)
- signature `ed25519:` seule → **True** (legacy D-032)

Donc : AND est réel **quand** le payload est hybride. Ed25519 seul **passe encore**.

## V-R04 — Bootstrap

- Pas de wallet / seed à `create_app()` sans `ARTCB_NODE_WALLET_ADDRESS`
- `init-node` seul crée le wallet ; `seed_hex` est dans la **réponse HTTP**, pas dans le `logger.warning` (adresse + URL seulement)
- 503 catch-all :

```json
{
  "status": "bootstrap_required",
  "wallet_initialized": false,
  "chain_available": false,
  "mining_available": false,
  "reason": "wallet_initialization_required"
}
```

## Git — Architecture A

`scripts/replit_start.sh` :

- Fetch autorisé
- `git reset --hard origin/$BRANCH` **refusé** si `ARTCB_REPLIT_PIN_SHA` est vide
- Checkout uniquement du SHA épinglé (secret Replit)

Le shim `/ready` est désormais **503** (plus un 200 menteur). `/` et `/live` restent 200 pour Autoscale.

---

## Ce qui n’est pas fait (volontaire)

- **V-R05** init-wallet — **bloqué** jusqu’à V-R01 public vert (SHA + integrity sur l’URL Autoscale)
- **V-R06** P2P Replit ↔ OVH2/AWS3/OVH4
- **V-R07** comparaison `/health` vs signatures réelles sur un wallet live
- Enforcement `HIGH_VALUE_MESSAGES` (changerait D-032)
- Redéploiement OVH1
- DV-04 PASS

## Tests

`pytest tests/test_e2e177_replit_ready.py tests/test_e2e178_replit_adversarial.py`
