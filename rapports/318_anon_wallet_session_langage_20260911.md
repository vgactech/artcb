# R318 — Session anonyme ≠ wallet privé + lexique véhicule

**UTC :** 2026-09-11T19:45:00Z  
**CERTIFIED_100 :** `false`

## Incident (screenshot artcb.me/#/wallets)

Observation : « Wallet actif » `artcb10pj2gty9u02hl5xwpa2wkhfdyass6fq8kdp3q0` + bouton déconnexion + sélecteur **PRIVE**, sans login.

### Preuve live anonyme (avant fix)

| Endpoint | Résultat |
|----------|----------|
| `GET /auth/me` | `authenticated=false`, `address=null` — **pas** de faille Principal |
| `GET /wallet/list` | **200**, 14 wallets dont `artcb10pj…` — **fuite P1** |
| `GET /wallet/balance/{addr}` | **200** anonyme |

### Causes UX (pas « magie » backend)

1. `ARTCB_WALLET_LIST_PUBLIC` défaut **1** → liste d’adresses aux anonymes  
2. Frontend auto-`setActorAddress(w[0])` (Memorize/Groups) → **1er wallet = « actif »**  
3. Import adresse → `setActorAddress` sans session  
4. `DashboardContext` défaut `visibility="private"` → UI **PRIVE** pour tout le monde  
5. `sessionHeaders` lisait `localStorage` alors que login écrit `sessionStorage`

**Réseau PRIVE ≠ compte privé authentifié** — c’était le sélecteur UI par défaut.

## Correctifs

| Couche | Fix |
|--------|-----|
| Backend | défaut `ARTCB_WALLET_LIST_PUBLIC=0` (401 anonyme) |
| Frontend | `authMe()` au load ; « Wallet actif » seulement si `sessionToken` |
| Frontend | défaut réseau **public** ; plus d’auto-acteur ; import ≠ login |
| Frontend | `sessionHeaders` → sessionStorage (+ migration localStorage) |
| Langage IA | `voiture`/`car`/`coche` → `C2` ; matching **mot entier** (évite `car` ⊂ `verificar`) |

## Tests

- wallet list anonyme 401 + opt-in public : PASS  
- probe FR/EN/ES : PASS  
- `test_encoder_voiture_car_coche_overlap` : PASS  

## Suite

- Rebuild/deploy frontend assets sur seeds (tsc local absent ici — follow-main code API immédiat ; UI build CI/node)  
- Sessions distribuées (mémoire process) = chantier séparé  
- Langage IA **pas** 100 % (E2E A→B / ledger encore NOT_PROVEN)

**CERTIFIED_100=false**
