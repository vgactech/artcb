# Rapport 363 — TEST DOMAIN LIVE validé sur OVH2, AWS3, OVH4

**Date** : 2026-09-16  
**Commit base** : `acc8676` (main)  
**Nœuds testés** : OVH2 (151.80.107.29) · AWS3 (13.38.209.25) · OVH4 (91.134.45.8)  
**OVH1** : ❌ hors périmètre (désactivé par décision utilisateur)

---

## 1. Résultats

### Score global : 27/27 PASS — 100%

| Test | OVH2 | AWS3 | OVH4 |
|------|------|------|------|
| T1 health + SHA=acc8676 | ✅ | ✅ | ✅ |
| T2 create wallet TEST → artcbdev1… | ✅ | ✅ | ✅ |
| T3 prefix artcbdev1 confirmé | ✅ | ✅ | ✅ |
| T4 address_v2 artcb2t… (V-PQC-2) | ✅ | ✅ | ✅ |
| T5 liste = TEST wallets + MAINNET wallets | ✅ | ✅ | ✅ |
| T6 zéro pollution cross-namespace | ✅ | ✅ | ✅ |
| T7 séparation PQC artcb2t ≠ artcb2 | ✅ | ✅ | ✅ |
| T8 wallet_namespace="TEST" stocké | ✅ | ✅ | ✅ |
| T9 wallet_namespace MAINNET compatible | ✅ | ✅ | ✅ |

### Wallets TEST créés (preuves live)

| Nœud | address (Ed25519 TEST) | address_v2 (PQC TEST) |
|------|------------------------|------------------------|
| OVH2 | `artcbdev1t8nh3e3gj6u9dqzmm9g…` | `artcb2t1pmshccnmfkfgrdndsxn6…` |
| AWS3 | `artcbdev1qmnsqz6wlfl3rvwcd5x…` | `artcb2t13cdqekp4jyd30uec3tx7…` |
| OVH4 | `artcbdev1599cxucqagva9wuyxxj…` | `artcb2t1yg9s8qem2pldurq4aqas…` |

---

## 2. Ce qui a été validé en conditions réelles

### Séparation cryptographique TEST DOMAIN

- Les wallets TEST ont `address = artcbdev1…` (domain-separated Ed25519)
- Les wallets TEST ont `address_v2 = artcb2t…` (domain-separated PQC hybride ML-DSA-65)
- Aucun wallet TEST n'a par erreur un prefix `artcb1…` ou `artcb2…` (mainnet)
- Aucun wallet MAINNET n'a par erreur un prefix `artcbdev1…` ou `artcb2t…` (test)
- `wallet_namespace = "TEST"` correctement stocké dans le metadata JSON

### V-PQC-2 load_wallet() fix (rapport 362) validé live

- Les wallets TEST créés via l'API ont bien `artcb2t…` en address_v2
- Le fix `load_wallet()` (lecture `wallet_namespace` depuis `.json`) est actif sur les 3 nœuds

### Infrastructure

- OVH2 : SHA `acc8676` ✅ — 1142 blocs — port 8000 actif
- AWS3 : SHA `acc8676` ✅ — 1142 blocs — redémarré via SSH (ancien process OOM tué)
- OVH4 : SHA `acc8676` ✅ — 1142 blocs — port 8000 actif

---

## 3. Observation : wallet_namespace manquant sur wallets legacy MAINNET

Les wallets MAINNET existants (créés avant l'implémentation TEST DOMAIN) n'ont pas de champ
`wallet_namespace` dans leur metadata (`"?"` retourné). C'est le comportement attendu par
le fallback `stored_ns = "MAINNET"` dans `load_wallet()` — compatibilité descendante OK.

---

## 4. État CERTIFIED_100

`CERTIFIED_100 = false`

| Critère | État |
|---------|------|
| TEST DOMAIN local (202 tests) | ✅ |
| TEST DOMAIN live OVH2/AWS3/OVH4 (27/27) | ✅ **NEW** |
| V-PQC-2 artcb2t | ✅ |
| Fix load_wallet() namespace | ✅ |
| OVH1 live | ❌ hors périmètre |
| PBFT distribué 4 nœuds prouvé | ❌ |
| Persistance après redémarrage nœud | ❌ |

Estimation : **~75%** vers CERTIFIED_100.

---

## 5. Fichiers

| Fichier | Rôle |
|---------|------|
| `rapports/363_testdomain_live_3noeuds_20260916.md` | Ce rapport |
