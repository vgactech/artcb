# Rapport 260 — Nœud actif contradictoire (V-XX), pas un second 259

**Date :** 2026-09-08  
**Contact :** `official@artcb.space`  
**259 reste le référentiel opérationnel.** On ne relance pas l’arrêt OVH4.  
**Pas de wipe.** Pas de `install.sh` / genesis / rescue. GO-E produce **off**.  
**Pas un PASS BFT. Pas production-ready.**

---

## Verdict 259 verrouillé (audit intégré)

| Propriété | Après 259 |
|---|---|
| 4 nœuds, même hauteur, même tip, réplication | PASS live |
| Arrêt volontaire + production pendant l’arrêt + catch-up | **PASS live** |
| Historique conservé (1077 → 1078, `wc -l` ×4 = 1078) | **PASS observé** |
| Consensus BFT / nœud Byzantine / double proposition / partition réseau | **NON** |
| Failover automatique complet | partiel |
| Certification production-ready globale | **NON** |

Vocabulaire : **PASS résilience à la perte temporaire d’un nœud + catch-up**.  
Pas ~~PASS BFT~~.

Preuve live 259 (mesurée, non inventée) : OVH4 `systemctl stop` → height **1078** hash `93c8b7c1dde1e79afa8f277f10f1705298c0beda5e9a7f3e5281a1f2d6cc51be` → OVH2/AWS3 replica → OVH4 restart keep-book → catch-up → **1078 × 4**. SHA live au moment du 259 : `8e2be0b4…` puis docs `8105efa7…`.

---

## Ce que 260 implémente

Un nœud **absent** (259) n’est pas un nœud **Byzantine**. V-XX = pair **accessible** qui envoie volontairement des payloads contradictoires.

```
Client / probe  ──offers──►  OVH1 / OVH2 / AWS3  (honnêtes)
                    │
                    └── from_node_id=ovh-node-4  (identité *déclarée*)
```

OVH4 **n’est pas arrêté**. On n’écrit pas un fork sur son `blocks.jsonl`.  
Le menteur de la batterie locale / du probe est l’**offre**, pas un rewrite du livre officiel.

### Huit contrôles (tests `tests/test_e2e260_byzantine_active.py`)

| # | Question audit | Test | Résultat local |
|---|---|---|---|
| 1 | Les honnêtes convergent encore ? | `test_1_honest_nodes_still_converge` | PASS |
| 2 | Bloc invalide rejeté ? | `test_2_invalid_block_rejected` | PASS |
| 3 | Signature incorrecte rejetée ? | `test_3` + `test_3b` (clé embarquée) | PASS |
| 4 | Hash incohérent rejeté ? | `test_4_inconsistent_hash_rejected` | PASS |
| 5 | Deux propositions contradictoires détectées ? | `test_5` + `test_decide_equivocation` | PASS |
| 6 | Le fautif peut-il bloquer indéfiniment ? | `test_6` flood 12 + append honnête | PASS |
| 7 | Après « restauration », resync propre ? | `test_7` diverge = **pas de wipe** ; `test_7b` retard = catch-up 259 | PASS |
| 8 | Preuve exploitable ? | JSONL `data/consensus/byzantine_evidence.jsonl` + `GET /consensus/byzantine/evidence` | PASS |

`pytest` 260+222+251+258 : **34 passed**.

### Code

| Chemin | Rôle |
|---|---|
| `src/artcb/consensus/byzantine_guard.py` | Enveloppe `ed25519:` / `hybrid:` ; vérif si clé producteur embarquée |
| `src/artcb/consensus/byzantine_evidence.py` | Preuve append-only ; `record_fraud` réputation sur equivocation / hash / sig |
| `src/artcb/p2p/sync.py` `decide_public_import` | Après hash : **equivocation** (même index, autre hash) puis signature |
| `ChainManager.import_extending_block` | Même garde ; jamais d’overwrite |
| `POST /api/v1/p2p/blocks/offer` | Offre publique, mêmes verdicts que receive/pull |
| `GET /api/v1/consensus/byzantine/evidence` | Liste + summary |

`wrong_index` / `wrong_prev_hash` restent des rejets **normaux** (catch-up). Ils ne remplissent pas le journal de fraude.

### Ce que 260 n’est pas

- Pas de view-change PBFT, pas de 2f+1 signatures de bloc.
- Pas un nœud officiel qui **produit** deux tips signés sur disque.
- Pas une partition réseau (perte de paquets).
- Pas un PASS ConceptID / PoL / ORG / anti-Sybil / perf.
- Le CI docs 259 n’est pas une preuve réseau. Le live 259 l’est, pour la **panne**.

Nœud divergé : le replica **refuse** d’écraser (`equivocation`). Le rattrapage 259 (simple retard) continue de fonctionner. Un wipe automatique serait l’anti-preuve.

---

## Live (mesuré 2026-09-08T01:00:55Z) — SHA encore `8105efa7…`

Matrice **inchangée** avant/après probe : height **1078**, tip `93c8b7c1dde1e79afa8f277f10f1705298c0beda5e9a7f3e5281a1f2d6cc51be`, `chain_valid=true` ×4. OVH4 **up**. Aucun wipe. `appended_from_byzantine_offer=false`.

| Appel | HTTP | Lecture |
|---|---|---|
| `POST /p2p/blocks/offer` ×3 | **405** Method Not Allowed | route 260 **absente** sur ce SHA |
| `GET /consensus/byzantine/evidence` | **404** | idem |
| `POST /p2p/blocks/receive` enveloppe poubelle | **400** | rejeté, livre intact |
| `POST /p2p/replica/push` enveloppe poubelle | **400** `replica_decrypt_failed:KEMError` | nginx `:8443` voit un peer allowlist (loopback XFF) puis KEM refuse ; **pas d’append** |

Les 8 contrôles V-XX sont **PASS locaux**. Ils ne sont **pas** encore PASS live sur les 4 compute — il manque le follow-main de ce SHA. Le CI de la branche 259 docs-only n’est toujours pas une preuve réseau.

Déployer 260 exige un **GO follow-main** explicite. Pas exécuté ici.

---

## Interdit (rappel)

Relancer l’arrêt OVH4 « pour voir ». Wipe `blocks.jsonl`. Transformer 259 ou 260 en PASS BFT. Inventer un hash / une hauteur. Afficher le token. Mélanger Doppler.
