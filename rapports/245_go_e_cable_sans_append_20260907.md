# Rapport 245 — GO reçu : câblage GO-E, **aucun bloc produit**

**Date :** 2026-09-07  
**GO opérateur :** le mot `GO` (session 244, après attente explicite).  
**Ce n’est pas une D-0xx.** Je n’écris pas dans `DECISIONS_UTILISATEUR_ARTCB`.  
**Contact :** `official@artcb.space`

---

## Interprétation (dite, pas élargie)

```text
GO
=
câbler ProducerMonitor + le rendre visible
≠
D-0xx
≠
append un bloc public
≠
V-01-B producteur exécuté
≠
redéployer les 4 nœuds
≠
ARTCB_PRODUCER_FAILOVER_PRODUCE=true sur le live
```

Si tu voulais **produire** sur le mainnet, il faut encore : `GO-E produce` + un seul nœud backup + keep-book. Le mot seul ne lance pas deux élus.

---

## Interrupteurs

| Variable | Défaut | Effet |
|---|---|---|
| `ARTCB_PRODUCER_FAILOVER_LIVE` | false | Instancie le moniteur (observe) |
| `ARTCB_PRODUCER_FAILOVER_PRODUCE` | false | Arme un futur append ; **ignoré** tant que `append_implemented=false` |

`maybe_produce()` rend toujours `appended=false`. Même les deux variables à true.

---

## Live (inchangé)

4 officiels toujours `2696f2e` au bootstrap de cette session. Tip 5 blocs `27350024…`. Ce commit n’y est pas. Je n’ai pas SSH.

---

## Fichiers

- `src/artcb/p2p/producer_runtime.py`
- `src/api/deps.py` (`AppState.producer_failover`)
- `GET /p2p/status` → `producer_failover`
- `/health` → `producer_failover_live` / `producer_failover_will_append`
- `tests/test_e2e249_go_e_runtime.py`

XOR sans BFT d’élection : rappel 244. Toujours vrai.
