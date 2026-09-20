# R382 — NetworkEligibilityGate : éligibilité réseau des nœuds ARTCB

**Date :** 2026-09-19  
**Session :** Bob IDE — suite `continue`  
**HEAD avant :** 4f07918  
**CERTIFIED_100 :** false  
**Tests :** 30/30 PASS (T01→T30) | Non-régression : 78/78 PASS  
**Mode DEBUG :** actif

---

## Problème adressé

Le rapport expert (2026-09-19) identifie que bloquer simplement « Wi-Fi public/entreprise » est une mauvaise règle. La vraie question est :

> **La machine peut-elle réellement satisfaire les exigences opérationnelles du protocole ARTCB dans ses conditions réseau actuelles ?**

Un Wi-Fi domestique derrière CGNAT peut bloquer les connexions entrantes, tandis qu'un VPS sur Wi-Fi public peut être parfaitement joignable. Le critère doit être la **capacité réseau mesurée**, pas le type de réseau.

---

## Architecture : séparation stricte NetworkState / EconomicState

```
NetworkState (ce module)         EconomicState (economics/human_binding.py)
UNKNOWN                          ACTIVE
TESTING                          GRACE
DIRECT          ←─ séparé ─→     OFFLINE
RELAYABLE                        TRANSFERRED
DEGRADED                         RETIRED
SUSPENDED                        COMPROMISED
INDETERMINATE
```

**Invariant de sécurité :** `economic_impact = "none"` dans TOUS les résultats de ce module. `NetworkEligibilityGate` ne modifie JAMAIS `MachineRecord.status`. Seul `EpochCoordinator` gère les transitions économiques.

---

## Fichiers créés

| Fichier | Lignes | Description |
|---------|--------|-------------|
| `src/artcb/network/eligibility_gate.py` | 490 | Module principal (MODULE_VERSION 1.0.0) |
| `tests/test_r382_network_eligibility_gate.py` | 295 | Suite complète 30 tests |

---

## AVANT → APRÈS

**Fichier :** `src/artcb/network/` (ajout)

| AVANT | APRÈS |
|-------|-------|
| Seul `failover.py` (V-08) — gestion des pannes nœuds serveurs | + `eligibility_gate.py` — éligibilité réseau des nœuds utilisateurs |
| Aucune distinction NetworkState / EconomicState | Séparation stricte — NetworkState sans impact économique direct |
| Pas de test inbound / probe externe | `assess_network_capability()` — outbound TCP + inbound listen + external probe |
| Pas de classifieur DIRECT/RELAYABLE/DEGRADED/SUSPENDED | `classify_network_state()` — 6 états distincts |
| Pas de fenêtre de grâce réseau | `DEGRADED_GRACE_S = 300s` — anti-suspension abusive |
| Pas d'anti-flap | `MIN_PASS_STREAK = 2` — évite oscillations SUSPENDED↔DIRECT |

---

## Logique de classification (§28 rapport expert)

```
outbound TCP fail OU captive_portal      → SUSPENDED
external_reachable + probe_ok > 0        → DIRECT
nat=NONE + inbound_listen                → DIRECT
outbound ok + relay disponible           → RELAYABLE
outbound ok + aucune probe externe       → INDETERMINATE (ne pas suspendre injustement)
outbound ok + inbound fail + pas relay   → DEGRADED (→ SUSPENDED après grâce)
```

---

## Scénarios validés (T01→T30)

| Tests | Scénario |
|-------|---------|
| T01–T05 | NetworkCapability construction + injections de test |
| T06 | Wi-Fi domestique + probe externe → DIRECT |
| T07 | VPS cloud (IP publique) + écoute locale → DIRECT |
| T08 | Wi-Fi public + relay disponible → RELAYABLE |
| T09 | Wi-Fi public + relay absent, première fois → DEGRADED |
| T10 | Captive portal (hôtel, aéroport) → SUSPENDED |
| T11 | Réseau coupé total → SUSPENDED |
| T12 | Probe ARTCB indisponible → INDETERMINATE (pas de faux SUSPENDED) |
| T13 | DEGRADED depuis 10s (grâce non expirée) → reste DEGRADED |
| T14 | DEGRADED grâce expirée → SUSPENDED |
| T15 | Retour DIRECT → grâce réinitialisée |
| T16 | SUSPENDED → economic_impact = "none" (INVARIANT) |
| T17–T19 | Anti-flap MIN_PASS_STREAK |
| T20 | Pas d'anti-flap depuis UNKNOWN |
| T21–T25 | Cycle de vie NetworkEligibilityGate |
| T26 | economic_impact = "none" dans TOUS les états |
| T27 | _economic_state_unchanged = True dans tous les résultats |
| T28 | node_id préservé à travers les transitions |
| T29 | SUSPENDED ne supprime pas l'historique |
| T30 | EligibilityResult.to_dict() complet |

---

## Bug corrigé pendant les tests

**T17** a révélé un bug : `self._current_state` était mis à `TESTING` (ligne 575) avant la comparaison anti-flap (ligne 598), rendant la condition `prev_state == SUSPENDED` toujours fausse.

**Fix :** `prev_state = self._current_state` sauvegardé avant `TESTING`, utilisé dans la comparaison anti-flap.

```python
# AVANT (bugué)
self._current_state = NetworkState.TESTING
if self._current_state == NetworkState.SUSPENDED:  # toujours False !

# APRÈS (corrigé)
prev_state = self._current_state
self._current_state = NetworkState.TESTING
if prev_state == NetworkState.SUSPENDED:  # correct
```

---

## Limites honnêtes

- `_probe_inbound_listen()` teste uniquement `127.0.0.1:p2p_port` — preuve locale, pas externe.
- `external_reachable` doit être fourni par les probes ARTCB tiers (équivalent AutoNAT libp2p).
- `nat_class` = heuristique IP privée/publique — pas de STUN/TURN réel.
- Tests outbound sur `127.0.0.254:19998` = toujours fail en local (comportement intentionnel pour les tests).
- Calibrage sur vrais réseaux (DEGRADED_GRACE_S, MIN_PASS_STREAK) = non mesuré en conditions réelles.

---

*Rapport généré : 2026-09-19 | CERTIFIED_100=false | MODE DEBUG actif*
