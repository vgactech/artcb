# V-PQC-2 — Certification ML-DSA-65 ×3 nœuds
**Date** : 2026-09-17T09:05:38Z  
**Script** : `scripts/certif_vpqc2_x4.py` v2  
**Résultat** : ✅ PASS — 3/3 nœuds certifiés (OVH1 bloqué par règle opérateur)

---

## Résumé

| Nœud | IP | Wallet | sig_len | algo | dur_ms | statut |
|------|----|--------|---------|------|--------|--------|
| ovh-node-4 | 91.134.45.8 | pqc-certif-n4 | 3309 | ML-DSA-65 | 282 | ✅ FULL_CERT |
| aws-node-3 | 13.38.209.25 | pqc-test-aws3 | 3309 | ML-DSA-65 | 3923 | ✅ FULL_CERT |
| ovh-node-2 | 151.80.107.29 | ovh-node-2 | 3309 | ML-DSA-65 | 251 | ✅ FULL_CERT |
| ovh-node-1 | 152.228.144.34 | — | — | — | — | SKIP (opérateur bloqué) |

## Adresses wallet certifiées

| Nœud | Adresse |
|------|---------|
| ovh-node-4 | `artcb1q758se70hfzs6z5r2yanfa7meld3crcuz20343` |
| aws-node-3 | `artcb1vqtms9rnhmxu4y7u932tf5j0as45c23gcxhmxv` |
| ovh-node-2 | `artcb1ykchmlksgnt6qmgez7u6pfecgwl5mn96xmsr9z` |

## Critères vérifiés

| Critère | Résultat |
|---------|----------|
| `vpqc2_pass = True` | ✅ sur 3/3 nœuds |
| `algorithm = "ML-DSA-65"` | ✅ sur 3/3 nœuds |
| `signature_len = 3309` | ✅ sur 3/3 nœuds |
| `pqc_public_key_len = 1952` | ✅ sur 3/3 nœuds |
| challenge unique par appel | ✅ (challenge hex 64 chars) |
| TLS HTTPS validé | ✅ (cert wildcard artcb.me) |

## Limites honnêtes (CERTIFIED_100 = false)

- Les 3 nœuds utilisent des wallets **distincts** — la clé ML-DSA-65 de chaque nœud est indépendante.
- Cela prouve que chaque nœud **contrôle localement** une clé privée ML-DSA-65.
- Cela ne prouve **pas** que les nœuds partagent une clé PQC commune.
- `unique_human_proven = false` — non pertinent pour cette vérification réseau.
- `CERTIFIED_100 = false` — règle permanente.

## Protocole de vérification

```
POST /api/v1/ops/pqc-challenge
  → challenge (hex 64 chars) + algorithm=ML-DSA-65

POST /api/v1/ops/pqc-verify
  body: { challenge, wallet_name, user_password }
  → vpqc2_pass=True + sig (3309 bytes) + pub_key (1952 bytes)
```

## Commande de reproduction

```bash
python3 scripts/certif_vpqc2_x4.py --output results.json
```

Prérequis : Doppler CLI authentifié avec accès aux projets `artcb3` et `artcb-2`.
