# R403 — Audit cohérence wallet multi-nœuds ARTCB

**Date :** 2026-09-21  
**SHA HEAD local :** `107d21b`  
**Statut :** ✅ DONE — commité + pushé  
**CERTIFIED_100 :** false  

---

## Contexte et motivation

L'expert a identifié une anomalie architecturale importante dans le rapport précédent :
le `WalletManager` stocke les fichiers wallet (`.key`, `.json`, `.pqc`) **localement**
sur chaque nœud dans `data_dir/wallets/`. De même, `WalletDeviceBindingStore` stocke
les bindings dans `data/wallet_device_bindings.json` **local au nœud**.

Conséquence : si une création de wallet est traitée par N2, le wallet n'est **pas répliqué**
sur N4 et N3. Une requête d'authentification subséquente routée vers N4 renverrait
`wallet_not_found` — expliquant le comportement transitoire observé par l'utilisateur.

R403 implémente le script d'audit de cohérence pour diagnostiquer cet état.

---

## Architecture du problème (confirmée sur HEAD)

```
src/artcb/wallet/manager.py:95
    self.wallet_dir = wallet_dir or (settings.data_dir / "wallets")

src/artcb/security/wallet_device_binding.py:84
    self.path = Path(data_dir) / "wallet_device_bindings.json"
```

**Aucune réplication P2P des fichiers wallet n'existe dans le code actuel.**

Les trois couches ont des niveaux de synchronisation différents :

| Couche | Réplication | Vérité |
|---|---|---|
| Code (git SHA) | ✅ git push + systemd | Synchronisé |
| Blockchain (blocs) | ✅ protocole PBFT | Répliqué |
| Wallet files (`.key`/`.json`) | ❌ local au nœud | STATE_LOCAL |
| Device bindings (`.json`) | ❌ local au nœud | STATE_LOCAL |
| Sessions auth | ❌ local au nœud | STATE_LOCAL |

---

## Fichiers créés

### AVANT (avant R403)

| Fichier | État |
|---|---|
| `scripts/artcb_r403_wallet_consistency_audit.py` | N'existait pas |
| `tests/test_r403_wallet_consistency_audit.py` | N'existait pas |

### APRÈS (R403)

| Fichier | Description | Lignes |
|---|---|---|
| `scripts/artcb_r403_wallet_consistency_audit.py` | Script d'audit — sonde 5 aspects par nœud | ~340 |
| `tests/test_r403_wallet_consistency_audit.py` | 19/19 PASS T01→T19 | ~265 |

---

## Fonctionnement du script R403

```
python3 scripts/artcb_r403_wallet_consistency_audit.py --wallet <nom>
python3 scripts/artcb_r403_wallet_consistency_audit.py --wallet <nom> --session-token <tok>
python3 scripts/artcb_r403_wallet_consistency_audit.py --wallet <nom> --device-fp <fp>
```

### Sondes par nœud

| Sonde | Endpoint | Ce qui est vérifié |
|---|---|---|
| `probe_wallet_exists()` | `/api/v1/wallet/list` | Wallet présent dans la liste du nœud |
| `probe_auth_me()` | `/auth/me` + Bearer | Session reconnue sur ce nœud |
| `probe_chain_tip()` | `/api/v1/chain/status` | Hauteur + last_hash blockchain |
| `probe_device_binding_admin()` | `/api/v1/admin/device-bindings/<fp>` | Binding appareil présent (admin) |

### Verdicts détectés

| Verdict | Description |
|---|---|
| `WALLET_STATE_LOCAL` | Wallet présent sur N2 seulement → problème réplication |
| `SESSION_INCONSISTENT` | Session valide sur N2, invalide sur N4/N3 |
| `CHAIN_FORK` | Hashes blockchain distincts entre nœuds |
| `CHAIN_LAG` | Spread de hauteur > 5 blocs |
| `WALLET_ADDRESS_MISMATCH` | Même nom de wallet mais adresses différentes |

---

## Résultats des tests

```
tests/test_r403_wallet_consistency_audit.py — 19/19 PASS (0.87s)

T01–T04 : probe_wallet_list / probe_wallet_exists ✅
T05–T07 : probe_auth_me ✅
T08–T09 : probe_chain_tip ✅
T10–T11 : probe_device_binding_admin ✅
T12–T15 : analyze_consistency (cohérence, WALLET_STATE_LOCAL, CHAIN_FORK, SESSION_INCONSISTENT) ✅
T16–T17 : run_audit intégration + log forensic ✅
T18–T19 : main() exit codes (0=CONSISTENT, 1=INCONSISTENT) ✅
```

---

## Validation live (sonde 2026-09-21T09:35:59Z)

Fichier log : `logs/R403_consistency_all_1789983359680226000.json`

| Nœud | IP | Tip height | last_hash | Cohérence |
|---|---|---|---|---|
| N2 / OVH2 | 151.80.107.29 | 1142 | 32a80547 | ✅ |
| N4 / OVH4 | 91.134.45.8 | 1142 | 32a80547 | ✅ |
| N3 / AWS3 | 13.38.209.25 | 1142 | 32a80547 | ✅ |

**VERDICT : CONSISTENT — blockchain 3/3 cohérente.**

Note : `/api/v1/wallet/list` répond 401 (authentification requise — attendu en production).
Pour auditer la cohérence des wallets, fournir `--session-token` avec un token admin valide.

---

## Recommandation architecture (hors scope R403 — non modifié)

Pour résoudre le `WALLET_STATE_LOCAL` structurel, trois options :

1. **Sticky sessions DNS** — forcer un client à toujours atteindre le même nœud
   (simple, mais fragile si le nœud tombe)
2. **Réplication wallet metadata** — partager les `.json` (adresse + public_key) via P2P
   (ne jamais répliquer `.key` — clé privée chiffrée reste locale)
3. **Wallet lookup on-chain** — enregistrer l'adresse wallet dans un bloc Genesis/TX lors
   de la création (conforme à l'architecture blockchain décentralisée)

La décision architecturale revient à l'opérateur. R403 documente le diagnostic, pas la solution.

---

## Limites documentées

- Sans `--session-token` admin, `wallet/list` répond 401 → audit wallet incomplet
- `probe_device_binding_admin` nécessite un endpoint admin non encore implémenté (HTTP 404)
- FAR/FRR biométriques (TASK-001) et DV-01/06/07 bloqués (matériel/SSH live)

---

## CERTIFIED_100=false
