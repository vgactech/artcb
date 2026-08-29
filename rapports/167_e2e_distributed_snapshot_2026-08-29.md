# Rapport 167 — Simulation distribuée : EconomicStateSnapshot + SettlementID

**Horodatage UTC :** 2026-08-29T19:20:00Z  
**Branche :** `cursor/e2e167-distributed-snapshot-475d`  
**Base :** `origin/main` = `46fdd234` (merge PR #35)  
**Code P0 :** `b365ab7` puis correctifs unicité WorkID / transfert  
**Simulation canonique :** `simulations/20260829T191632Z_e2e167_distributed_consolidated/`  
**Run échoué conservé :** `simulations/20260829T191605Z_e2e167_distributed_consolidated/` (preuve, pas inventé)  
**Pytest :** `logs/20260829_pytest_rapport167.txt` — **613 passed, 8 skipped, 0 fail**  
**Ne jamais écraser** 160–166.

**613 verts ≠ certification mainnet multi-nœuds.** Gossip = comparaison de tips, pas sync de blocs. V-01…V-07 **non gelés**.

---

## 0. Mission (audit post-166 / merge)

Ordre : partir de `main` réellement mergé, vérifier 166, lancer **Simulation 167** exécutée (pas inventée), identifier erreurs, proposer corrections, lister les paramètres à valider.

Expertises : Git, consensus, tokenomics, concurrence, snapshots économiques.

---

## 1. Git réel confirmé

```
46fdd234  Merge PR #35  cursor/ovh-deploy-stripe-secrets-475d
   └── 532b1e5  Merge PR #34  tokenomics-21m-hbp-owner-decay-3fcb
```

Les travaux 34 + 35 **sont dans main**. Cette branche part de `46fdd234`.

---

## 2. Ce que 166 a vraiment livré (inchangé)

Documenté dans 166, repris ici sans rejouer OVH :

- 607 pytest à l’époque ; Stripe create+cancel `mints=false` ; OVH economics 200.
- Secrets : `KEY_API_STRIPE`, Doppler `SSH_PRIVATE_KEY`, token serveur révoqué corrigé.

166 **n’est pas** une simu distribuée. 167 ne remplace pas 166.

---

## 3. Exécution réelle 167 (aucun chiffre inventé)

Dossier : `20260829T191632Z_e2e167_distributed_consolidated/`  
`18_summary.json` : `failures=[]`, `invented=false`, `certified_distributed_mainnet=false`

### Manifest (`00_manifest.json`)

| Champ | Valeur lue |
|-------|------------|
| commit_sha | `b365ab7f67a52a6ab6ece2328271b3c080f34e9e` |
| protocol_version | `167-distributed-snapshot` |
| random_seed | 167 |
| started_at / finished_at | 2026-08-29T19:16:32Z / 19:16:34Z |
| invented_results | false |

### Invariants (`16_invariants.json`) — tous `true`

| Invariant | Résultat |
|-----------|----------|
| M1=100 % | true (`p_m1=1.0`, N_A snapshot=4, P extras≈0.48025) |
| count(Settlement(WorkID-X))=1 | true — A ok ; B/C/D `REJECT_DOUBLE_SETTLEMENT` |
| Transfert ne change pas N avant epoch+1 | true |
| N diminue au snapshot suivant | true (4 → 3, log `N_economic=3` après transfer) |
| Offline compte encore | true |
| Stripe down ≠ bloc | true (`WorkID-stripe-down` ok) |
| Partition : re-settle WorkID-X rejeté | true |
| OracleUnavailable sans prix inventé | true |
| Quorum médian 1.0+1.2 = 1.1 | true |
| Provider absent : settle OK | true |
| Restart nœud B : hauteur conservée | true |
| Supply ≤ 21 M | true |

### WorkID-X concurrent (`11_consensus_events.json`)

- 1 succès : nœud **A**, `paid=5000000000` = `r_block`, EconomicRoot `672de758…`
- 3 rejets : B, C, D — même SettlementID `624c8f3a…`

### Supply (`14_supply.json`)

Nœud A : 20_000_000_000 satoshi (4 blocs × 50 ARTCB). B/C/D : 0 (rejets). Cap 21 M OK.

### Canonical tip

Nœud A, height 4, tip `df97b67cbfc141e6…`. Règle : plus longue chaîne, égalité → hash plus petit. **Pas** un sync P2P réel.

---

## 4. Erreur réelle du premier run (191605)

`17_failures.json` :

```
HumanBindingError: first machine of an owner cannot bind a third-party human
```

**Cause :** transfert de M4 vers B alors que B n’avait pas encore de M1. Le registre traite la machine transférée comme première machine de B → binding externe interdit.

**Correction :** enregistrer `MB1` pour B (100 % B) ; M4 transféré = extra de B, binding E autorisé. Run 191632 = 0 fail.

Le dossier 191605 est **conservé** (preuve d’erreur, pas écrasé).

Deuxième bug trouvé en route : `taken_at` différent par nœud → SettlementID distincts pour le même WorkID. **Correction :** horodatage aligné + unicité **WorkID** dans le ledger (pas seulement le SID).

---

## 5. Avant / après (fichiers)

### Nouveau

- `src/artcb/economics/economic_snapshot.py` — snapshot, SettlementID, ledger, EpochCoordinator  
- `src/artcb/economics/distributed.py` — 4 nœuds A/B/C/D  
- `scripts/run_sim167_distributed.py`  
- `tests/test_economic_snapshot_167.py`

### Modifié

- `human_binding.py` : `MachineRegistry.all()`  
- `hbp.py` : `hbp_rate_from_ratio` — **chemin live `hbp_rate` inchangé**  
- `oracle.py` : `oracle_median_or_unavailable`  
- `protocol.py` : `epoch_snapshot` + `settlement_ledger` optionnels  
- `.gitignore` : `simulations/**/work/` (clés de chaîne)

---

## 6. Paramètres à valider (ne pas choisir à ma place)

| ID | Recommandation implémentée | À trancher |
|----|----------------------------|------------|
| **V-01** | Snapshot au début d’epoch | Confirmer Solution A |
| **V-02** | Transfert effet = epoch suivant | Confirmer |
| **V-03** | Grace reconnect 24 h (1 s en sim) | 24 h vs 1 epoch |
| **V-04** | Retrait au prochain snapshot | Confirmer |
| **V-05** | Finalité N=2 confirmations | N vs quorum |
| **V-06** | H_adult_max = DemographicReference (pas gelé) | Source WPP datée + hash |
| **V-07** | HBP ratio `H/H_adult_max` (fonction ajoutée) | Seuils ; activer en live ? |

D-026 = ces défauts **provisoires**.

---

## 7. Ce que 167 n’est pas

- Pas un réseau libp2p 4 nœuds réels  
- Pas de réplication de blocs (tips seulement)  
- Pas de gel `H_adult_max`  
- Pas d’oracle multi-source live (quorum sur listes fournies)  
- Pas une protection `main` GitHub (hors code)

---

## 8. Avancement

| Couche | % |
|--------|---|
| P0 snapshot + SettlementID + sim 4 nœuds + manifest | **~90 %** (exécuté, V-* ouverts) |
| P1 transitions / Stripe isolation dans 167 | **partiel** (S7/S9 exercés) |
| P2 oracle live + freeze démographique | **non** |
| Protocole global | **~97.5 %** |

Compare : https://github.com/vgactech/artcb/compare/main...cursor/e2e167-distributed-snapshot-475d  
PR automatique : `must be a collaborator`.
