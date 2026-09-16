# Rapport 365 — Preuves live : VIEW-CHANGE + persistance + consensus gate

**Date** : 2026-09-16  
**Commit** : à venir sur `main`  
**Base** : `b0bec3b` (main)

---

## 1. FIX-A — `verify_chain_integrity()` upgradée + `consensus_gate()`

### Avant (R364)
- L1 seulement : structure (index, gaps, duplicates, prev_hash)
- Pas de vérification cryptographique
- Pas de gate PBFT

### Après (R365)
**3 couches** dans `verify_chain_integrity(verify_hashes=True)` :

| Couche | Vérifie | Bloque si |
|--------|---------|-----------|
| **L1** | Index séquentiel, no gaps, no dup, prev_hash linkage | Structure cassée |
| **L2** | `ffi.build_block_hash()` recalculé = hash stocké (blocs public) | Hash tampered |
| **L3** | `network_id` et `protocol_version` du Genesis = constantes config | Mauvais réseau |

**`consensus_gate()`** : gate dure appelée par `write_certified_block()`.
- Si `consensus_safe=False` → bloque l'écriture, log ERROR
- `ARTCB_PBFT_SKIP_INTEGRITY_GATE=1` pour tests/bootstrap
- Retourne `{allowed, reason, integrity}`

---

## 2. FIX-B — VIEW-CHANGE live prouvé (13/13)

OVH1 est **vraiment mort**. Tests exécutés sur les 3 nœuds réels.

| Preuve | Résultat |
|--------|---------|
| OVH1 `152.228.144.34` timeout/refused | ✅ |
| OVH1 absent du `pbft_reachable_http_map()` | ✅ |
| Nœuds reachables ≥ 3 (Q) | ✅ `[aws-node-3, ovh-node-2, ovh-node-4]` |
| View > 0 sur les 3 nœuds | ✅ **view=27** |
| Views cohérentes OVH2/AWS3/OVH4 | ✅ `{27}` |
| Primary cohérent 3 nœuds | ✅ `aws-node-3` |
| Primary ≠ OVH1 | ✅ |
| `chain_integrity` OVH2/AWS3/OVH4 | ✅ `True` |
| `consensus_safe` OVH2/AWS3/OVH4 | ✅ `True` |

**OVH1 mort → VIEW-CHANGE automatique → view=27, primary=aws-node-3.**
Le réseau ARTCB fonctionne à 3/4 sans OVH1.

---

## 3. FIX-C — Persistance après redémarrage service (21/21)

Protocole : snapshot AVANT → `systemctl restart artcb` → snapshot APRÈS.

| Critère | OVH2 | AWS3 | OVH4 |
|---------|------|------|------|
| SHA identique | ✅ `b0bec3b347a9` | ✅ | ✅ |
| Height identique | ✅ 1142 | ✅ 1142 | ✅ 1142 |
| `integrity_ok=True` | ✅ | ✅ | ✅ |
| View identique | ✅ 27 | ✅ 27 | ✅ 27 |
| Primary identique | ✅ `aws-node-3` | ✅ | ✅ |
| Wallets TEST présents | ✅ 4 | ✅ 3 | ✅ 2 |
| Adresses TEST conservées | ✅ | ✅ | ✅ |

**Après redémarrage : aucune régression. La chaîne, la view PBFT et les wallets TEST persistent.**

---

## 4. État CERTIFIED_100

`CERTIFIED_100 = false`

| Critère | État |
|---------|------|
| TEST DOMAIN live 27/27 (rapport 363) | ✅ |
| PBFT résilient R364 (3 bugs code) | ✅ |
| VIEW-CHANGE live prouvé (13/13) | ✅ **NEW** |
| Persistance redémarrage service (21/21) | ✅ **NEW** |
| consensus_gate() L1+L2+L3 | ✅ **NEW** |
| Reboot machine complète (OS) | ⏳ non testé |
| Finalité bloc après VIEW-CHANGE (nouveau bloc produit) | ⏳ non prouvé live |
| CERTIFIED_100 | ❌ |

Estimation : **~85%** vers CERTIFIED_100.

---

## 5. Fichiers modifiés

| Fichier | Modification |
|---------|-------------|
| `src/artcb/chain/manager.py` | `verify_chain_integrity()` L1+L2+L3 + `consensus_gate()` |
| `tests/test_r365_view_change_live.py` | 13 preuves VIEW-CHANGE live |
| `rapports/365_view_change_persistance_r365_20260916.md` | Ce rapport |
