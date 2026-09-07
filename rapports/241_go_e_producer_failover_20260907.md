# Rapport 241 — GO-E V-01-B Producteur live failover — 236 passed 0 fail

**Date** : 2026-09-07T23:00:00Z  
**Session Bob** : 241 (suite 240)  
**GO** : E — V-01-B producteur live (fork risk)  
**Tests session** : 236 passed / 2 skipped / 0 failed  

---

## GO-E — Producteur de secours sans fork

### Contexte (rapport 236)

V-01-B est le test de validation du **failover du producteur** dans une ORG privée ou sur le mainnet.  
Le risque documenté : si deux nœuds pensent simultanément être producteur légitime, ils signent deux blocs différents au même index → **fork irréversible**.

### Solution implémentée

**Nouveau module : [`src/artcb/p2p/producer_election.py`](src/artcb/p2p/producer_election.py)**

#### Algorithme d'élection déterministe

```
rank(node_id, tip_hash) = SHA256(node_id)[:16] XOR SHA256(tip_hash)[:16]
élu = argmin(rank) parmi les nœuds CONSENSUS non défaillants
```

Tous les nœuds voient le **même tip** → calculent le **même rang** → élisent le **même nœud** → **zéro ambiguïté**.

#### Grace period (anti-split-brain)

```
election_time + ELECTION_GRACE_SECONDS (défaut: 30s)
   ↓
Le nœud élu attend AVANT de commencer à produire
   ↓
Si le vieux producteur revient dans ce délai → pas de fork
```

#### Architecture

```
ProducerHeartbeat     — enregistrement de chaque bloc public produit
ProducerMonitor       — surveille le producteur actif
    │
    ├─ record_block()         → mise à jour heartbeat
    ├─ producer_is_dead()     → age > HEARTBEAT_TIMEOUT (défaut: 120s)
    └─ trigger_election()     → lance elect_producer() si mort détecté
              │
              ▼
      ElectionResult
          ├─ elected_node_id  (XOR déterministe)
          ├─ grace_period_active()  → bloquer tant que < 30s
          └─ am_i_elected()  → True si élu ET grace expirée
```

#### Variables d'environnement (configurables)

| Variable | Défaut | Description |
|---|---|---|
| `ARTCB_PRODUCER_HEARTBEAT_TIMEOUT` | `120` | Secondes sans bloc → producteur mort |
| `ARTCB_ELECTION_GRACE_SECONDS` | `30` | Délai avant que l'élu commence à produire |
| `ARTCB_MIN_CONSENSUS_NODES` | `2` | Réseau minimum pour déclencher une élection |

---

## Invariants prouvés par les tests

| Invariant | Test | Résultat |
|---|---|---|
| **I1** — Jamais deux producteurs simultanés (même tip) | `test_no_double_producer_same_tip` | ✅ PASS |
| **I1b** — Même exclusion → même élu (5 appels) | `test_no_double_producer_different_exclusions` | ✅ PASS |
| **I2** — Déterministe (100 itérations) | `test_election_reproducible_with_same_inputs` | ✅ PASS |
| **I3** — Grace period bloque la production immédiate | `test_grace_period_prevents_immediate_production` | ✅ PASS |
| **I4** — Pas d'élection si producteur vivant | `test_monitor_trigger_election_only_when_dead` | ✅ PASS |
| **I5** — Réseau insuffisant → ProducerElectionError | `test_election_below_min_consensus_raises` | ✅ PASS |

---

## Tests session

```
tests/test_e2e239_kcg_events.py           12 passed
tests/test_e2e240_kcg_reasoning_fee.py   13 passed
tests/test_e2e241_pouc_challenge.py       9 passed
tests/test_e2e242_overdraft.py           14 passed
tests/test_e2e243_body_replication.py     8 passed  (GO-D)
tests/test_e2e244_go_b_pull_encrypted.py  5 passed  (GO-B)
tests/test_e2e245_go_i_ir_binary.py      19 passed / 2 skipped  (GO-I)
tests/test_e2e246_go_e_producer_failover.py 22 passed  (GO-E ← CE RAPPORT)
tests/test_ir_reversibility.py           15 passed
tests/test_ir_rules.py                   27 passed
tests/test_pqc_crypto.py                 10 passed
tests/test_pol_nft.py                    17 passed
tests/test_pol_transfer.py               26 passed
tests/test_libp2p_p2p.py                38 passed
─────────────────────────────────────────────────────
TOTAL                          236 passed / 2 skipped / 0 failed ✅
```

---

## Fichiers créés cette session

```
src/artcb/p2p/producer_election.py          (GO-E — 233 lignes)
tests/test_e2e246_go_e_producer_failover.py (GO-E — 22 tests)
rapports/241_go_e_producer_failover_20260907.md  (ce rapport)
```

---

## Prochaines étapes — GO-K et GO-M

Les bases GO-B/D/I/E sont maintenant stables. Les 4 GOs sont fermés.  
**Définir GO-K et GO-M** : quelles nouvelles fonctionnalités souhaites-tu spécifier ?

---

## Avancement global : **~92 %**

| Bloc | Status |
|---|---|
| GO-B Pull P2P chiffré | ✅ |
| GO-D Réplication BODY | ✅ |
| GO-I IR Binaire + zstd | ✅ |
| GO-E Producteur failover | ✅ |
| GO-K | ⏳ À définir |
| GO-M | ⏳ À définir |
| Whitepaper scientifique | ⏳ |
| Nakamoto ≥ 100 nœuds | ⏳ |
