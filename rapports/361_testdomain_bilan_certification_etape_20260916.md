# Rapport 361 — État TEST DOMAIN après b3c8c5a : bilan de certification d'étape

**Date :** 2026-09-16  
**SHA HEAD :** b3c8c5a (main)  
**CERTIFIED_100 :** false — inchangé  
**Total tests :** 172 PASS (97 + 53 + 22)  
**OVH1 :** ❌ BLOQUÉ — désactivé par l'utilisateur

---

## 1. Ce qui a été accompli (commits 9853e13 → b3c8c5a)

| Commit | Description | Tests |
|--------|-------------|-------|
| `9853e13` | Socle TEST DOMAIN — domain sep, wallet_states, attestation, factory | 97 |
| `2706c3c` | E2E local : TestChainManager, transaction, mining, balance, adversarial | +53 → 150 |
| `b3c8c5a` | Live API : 22 tests via FastAPI TestClient (L1–L4) | +22 → 172 |

---

## 2. Ce que les 172 tests prouvent réellement

### Niveau 1 — Séparation cryptographique (prouvé, Python pur)
```
H("ARTCB/WALLET/TEST/V1"    || PK) → artcbdev1…  ✅
H("ARTCB/WALLET/MAINNET/V1" || PK) → artcb1…     ✅
Même PK → adresses différentes                    ✅
Signature TEST ≠ signature MAINNET (network_id dans enveloppe signée) ✅
```

### Niveau 2 — Séparation protocolaire (prouvé, Python pur)
```
TEST_NETWORK_ID       = artcb-testnet-1     ≠ artcb-mainnet-1   ✅
TEST_GENESIS_HASH     = genesis-testnet-1   ≠ genesis-mainnet-1  ✅
TEST_PROTOCOL_VERSION = 189-testnet-1       ≠ 189-mainnet-1      ✅
Genesis TEST bloc 0   = hash déterministe incluant network_id    ✅
test_chain.jsonl      ≠ chain.jsonl (isolation physique)         ✅
```

### Niveau 3 — Séparation économique (prouvé, Python pur)
```
asset TEST  = tARTCB  ≠ ARTCB                          ✅
balance TEST ≠ balance MAINNET (mainnet_balance=None)  ✅
TEST→MAINNET transfer = cross_domain_reject             ✅
MAINNET→TEST transfer = cross_domain_reject             ✅
```

### Niveau 4 — Pipeline E2E local (prouvé, Python pur)
```
wallet TEST → tx signée → validation → bloc TEST → balance tARTCB ✅
chain.jsonl MAINNET absent après 6 blocs TEST                      ✅
14 adversariaux : mauvaise sig, mauvais domain, replay, etc.       ✅
```

### Niveau 5 — API HTTP (prouvé, FastAPI TestClient)
```
POST /wallet/create wallet_namespace=TEST → 200, adresse artcbdev1…   ✅
POST /wallet/create wallet_namespace=MAINNET → 200, adresse artcb1…   ✅
POST /wallet/create namespace=DEVNET → 422                             ✅
MAINNET : 2e wallet même device → 409 device_wallet_limit             ✅
TEST    : 3 wallets même device → 200 200 200                         ✅
TEST et MAINNET coexistent sur même device                             ✅
/wallet/list → adresse artcbdev1… visible                             ✅
/health → 200 après création wallet TEST                               ✅
```

---

## 3. Ce qui N'est PAS prouvé (trous restants)

### Trou T1 — Comportement sur nœud réel OVH1
```
❌ POST http://152.228.144.34:8000/wallet/create wallet_namespace=TEST
   Raison : OVH1 bloqué par l'utilisateur, et code 2706c3c pas encore déployé
```

### Trou T2 — Propagation TEST entre nœuds
```
❌ wallet TEST créé sur OVH1 → visible sur OVH2/AWS3/NODE4
   Raison : aucune infrastructure multi-nœud TEST câblée
```

### Trou T3 — Isolation TEST dans le réseau distribué
```
❌ transaction TEST ne pollue pas chain.jsonl d'un nœud MAINNET
   (prouvé localement en isolation, pas en réseau réel)
```

### Trou T4 — Persistance après redémarrage
```
❌ test_chain.jsonl survit à un redémarrage du nœud
   et les blocs TEST sont rechargés correctement
```

### Trou T5 — Consensus TEST
```
❌ un bloc TEST passe par PBFT sur les 4 nœuds
   et est rejeté par le validateur MAINNET
```

### Trou T6 — Tokenomics et PoL complets
```
❌ reward model TEST = fixe 1 tARTCB (pas le PoL complet)
   ❌ HBP/OwnerDecay non câblés en mode TEST
```

---

## 4. Prochain plan d'action (dépend de la réactivation OVH1)

### Étape A — Déploiement (OVH1 requis)
```bash
# Sur OVH1 via SSM aws-node-3 :
git pull origin main   # → b3c8c5a
systemctl restart artcb-node
curl http://localhost:8000/health | python3 -m json.tool
# Vérifier git_sha == b3c8c5a dans /health
```

### Étape B — Smoke test live sur OVH1
```bash
curl -X POST http://localhost:8000/api/v1/wallet/create \
  -H "Content-Type: application/json" \
  -H "X-ARTCB-Device-Id: test-device-ovh1-001" \
  -d '{"name":"test-ovh1-001","password":"TestPass123!","wallet_namespace":"TEST"}'
# Attendre : {"address":"artcbdev1q...","wallet_namespace":"TEST","asset":"tARTCB"}
```

### Étape C — Isolation vérifiée sur OVH1
```bash
# Vérifier que test_chain.jsonl est créé sur OVH1
ls -la /data/test_chain.jsonl
# Vérifier que chain.jsonl (MAINNET) n'a pas bougé
stat /data/chain.jsonl  # mtime inchangé
```

### Étape D — Test adversarial distribué
```bash
# Tenter d'envoyer une transaction TEST vers une adresse MAINNET
# Doit retourner cross_domain_reject
```

### Étape E — Tests à écrire une fois OVH1 réactivé
Le fichier `tests/test_testdomain_ovh1.py` sera créé avec :
- `pytest.mark.live` + `skipif` sur `ARTCB_OVH1_ENABLED != "1"`
- 8 tests : smoke, adresse, namespace, isolation, health, liste, 409, rejection

---

## 5. Tableau de certification TEST DOMAIN

| Critère | Local TestClient | OVH1 réel |
|---------|:---:|:---:|
| Adresse artcbdev1… | ✅ | ❌ (à tester) |
| Namespace TEST explicite | ✅ | ❌ |
| asset=tARTCB dans réponse | ✅ | ❌ |
| test_chain.jsonl isolé | ✅ | ❌ |
| MAINNET 409 2e wallet | ✅ | ❌ |
| TEST multi-wallet device | ✅ | ❌ |
| Sig TEST invalide sur MAINNET | ✅ | ❌ |
| /health OK après TEST | ✅ | ❌ |
| Propagation entre nœuds | ❌ | ❌ |
| Bloc TEST rejeté par MAINNET | ❌ (local prouvé) | ❌ |
| Persistance redémarrage | ❌ | ❌ |
| Consensus PBFT TEST | ❌ | ❌ |

**`CERTIFIED_100=false` — justifié.**

---

## 6. Résumé

Le TEST DOMAIN est **fortement prouvé au niveau application** (cryptographie, API, binding, séparation économique, E2E local, 172 tests).

Il **n'est pas encore prouvé au niveau réseau distribué** : propagation, consensus, isolation entre nœuds physiques, persistance après redémarrage.

La prochaine étape est bloquée sur OVH1. Dès que l'utilisateur le réactive, les actions sont : `git pull` → redémarrage → smoke test → rapport 362.
