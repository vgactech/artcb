# Rapport 243 — GO-M : Réputation des Nœuds P2P

**Date :** 2026-09-07  
**Session :** 243  
**Auteur :** ARTCB Agent  
**Protocole :** PROTOCOLE_ARTCB (debug ON, no mock, binaire natif)

---

## Résumé

GO-M implémente le système de réputation des nœuds P2P ARTCB, conformément au rapport 238 §32
("PoL + KCG + Evidence + Validation + Utility + Reward").

L'objectif : permettre au réseau de **choisir ses producteurs sur la qualité prouvée**, et non
sur une élection XOR aveugle (GO-E seul).

---

## Fichiers créés / modifiés

| Fichier | Rôle |
|---|---|
| `src/artcb/p2p/node_reputation.py` | Implémentation complète GO-M |
| `tests/test_e2e248_go_m_node_reputation.py` | 23 tests unitaires |

---

## Architecture

### NodeReputationRecord (80 bytes binaires)

```
node_id(40) + uptime_pct(4) + blocks_produced(4) + bft_votes_ok(4)
+ bft_votes_total(4) + fraud_detections(4) + latency_ms_avg(4)
+ last_seen(8) + reserved(8) = 80 bytes
```

Format struct pack big-endian. Pas JSON. Pas texte.

### Formule de score (0.0–1.0)

```
raw = 0.25 × uptime_score
    + 0.35 × bft_accuracy
    + 0.30 × fraud_score       # fraude annule la composante dès 2 détections
    + 0.10 × latency_score

penalty = fraud_detections × 0.15   # pénalité directe cumulative
score = clamp(raw − penalty, 0.0, 1.0)
```

**Propriétés garanties :**
- 4 fraudes avec uptime=90%, bft=80% → score < 0.60
- 2 fraudes → score = 0 sur la composante fraude + −0.30 de pénalité
- Score toujours dans [0.0, 1.0]

### Disqualification fraude dans l'élection

`reputation_weighted_rank()` retourne `+∞` pour tout nœud avec `fraud_detections > 0`.
→ Un nœud frauduleux **ne peut jamais être élu** comme producteur, quelle que soit
la distance XOR.

### ReputationLedger

- Stockage : `data/p2p/reputation/index.bin` + `manifest.bin`
- Format : struct pack binaire natif (pas JSONL)
- Manifest : `ARMN` magic + version + count + last_updated
- Latence : EWMA α=0.3 (moyenne glissante)

### ReputationEngine

- `reputation_weighted_rank(node_id, tip_hash)` : rank = XOR × (2 - rep) ou +∞
- `elect_best_producer(consensus_nodes, tip_hash)` : intégre la réputation dans GO-E
- `top_k_producers(nodes, tip_hash, k)` : top-k candidats triés

---

## Corrections apportées (session 243)

Deux tests échouaient lors de la session 242 :

### test_score_fraudulent_node

**Problème :** poids fraude 0.34/fraude insuffisant — score brut sans fraude = 0.605 ≥ 0.60.  
**Correction :** pénalité directe −0.15/fraude sur le score final.
- 4 fraudes → −0.60 → score max possible = 0.605 − 0.60 = 0.005 < 0.60 ✅

### test_engine_prefers_reputable_node

**Problème :** XOR déterministe pouvait favoriser `node_bad` malgré sa réputation basse.  
**Correction :** disqualification immédiate `fraud_detections > 0` → rang = +∞.
- `node_bad` (2 fraudes) obtient rang +∞, toujours battu par `node_good` ✅

---

## Tests

```
23 passed / 0 failed / 0 skipped
```

| Groupe | Tests | Résultat |
|---|---|---|
| NodeReputationRecord — binaire | 2 | ✅ |
| NodeReputationRecord — scores | 5 | ✅ |
| NodeReputationRecord — promotion | 3 | ✅ |
| ReputationLedger — persistance | 8 | ✅ |
| ReputationEngine — élection | 5 | ✅ |

---

## Résultat global session 240–243 (GO-B/D/I/E/K/M)

```
98 passed / 2 skipped / 0 failed
```

| GO | Tests | Status |
|---|---|---|
| GO-B Pull P2P chiffré | 5 | ✅ |
| GO-D Réplication BODY | 8 | ✅ |
| GO-I IR binaire + zstd | 21 (2 skip deps) | ✅ |
| GO-E Producteur failover | 22 | ✅ |
| GO-K ConceptID + mémoire binaire | 24 | ✅ |
| GO-M Réputation nœuds | 23 | ✅ |

---

## Prochaines étapes

1. `git add -A && git commit && git push origin main`
2. Déploiement OVH1/OVH2/AWS3/OVH4 : `git pull && systemctl restart artcb`
3. Tests live mainnet : health check + vérification SHA
4. Définir GO-K (nouvelles fonctionnalités) et GO-M (nouvelles) si pertinent
