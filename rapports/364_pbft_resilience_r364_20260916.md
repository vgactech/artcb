# Rapport 364 — Résilience PBFT sans dépendance nœud unique + chain integrity

**Date** : 2026-09-16  
**Commit** : `1e8bf60` (main)  
**Déployé sur** : OVH2 ✅ · AWS3 ✅ · OVH4 ✅

---

## 1. Problème résolu

Le réseau ARTCB ne doit pas être bloqué par la mort d'un seul nœud.
Avec N=4, F=1, Q=3, la panne d'OVH1 ne doit pas arrêter OVH2+AWS3+OVH4.

**3 bugs corrigés dans ce commit.**

---

## 2. BUG1 — `coordinate_public_finality` fail-closed sur primary mort

### Avant (bug)
```python
if primary not in hosts and engine.node_id != primary:
    return {"ok": False, "reason": "primary_unreachable_transport"}  # ← BLOQUÉ
```
OVH2/AWS3/OVH4 ne pouvaient pas continuer PBFT si OVH1 (primary de la view 0) était mort.

### Après (fix)
```python
if primary not in hosts and engine.node_id != primary:
    plan = next_reachable_view(view)
    if plan.get("ok"):
        engine.pbft_log.emit_view_change(chain, view=target_view, ...)
        # fan-out VIEW-CHANGE aux 3 nœuds reachables
    return {..., "auto_view_change": True, "target_view": target_view}
```
Le VIEW-CHANGE est automatiquement émis et propagé. OVH2 devient primary (view 1).

---

## 3. BUG1b — `pbft_reachable_http_map()` incluait les nœuds morts

### Avant (bug)
La fonction retournait systématiquement les 4 IPs fixes sans vérifier leur disponibilité.
OVH1 mort restait dans le map → `primary_of(view=0) = ovh-node-1` ∈ hosts → pas de VIEW-CHANGE.

### Après (fix)
```python
def pbft_reachable_http_map(*, probe_timeout=2.0, skip_probe=False):
    # probe HTTP chaque nœud, exclut les unreachable
    # fallback: jamais vide
    # ARTCB_PBFT_SKIP_PROBE=1 pour legacy
```
OVH1 mort → exclu du map → `primary not in hosts` → auto VIEW-CHANGE déclenché.

---

## 4. BUG2 — Watchdog stall_sec = 900s (15 min) trop lent

### Avant
```python
stall_sec = float(os.environ.get("ARTCB_PUBLIC_TIP_STALL_SEC") or "900")
```
→ 15 minutes d'attente avant détection de stall et VIEW-CHANGE.

### Après
```python
stall_sec = float(os.environ.get("ARTCB_PUBLIC_TIP_STALL_SEC") or "120")
```
→ **2 minutes** maximum. Override `ARTCB_PUBLIC_TIP_STALL_SEC` conservé.

---

## 5. BUG3 — Pas de vérification d'intégrité de la chaîne au démarrage

### Avant
Aucune vérification que `prev_hash[n] == hash[n-1]` ni que les index sont séquentiels.

### Après : `ChainManager.verify_chain_integrity()`
```python
def verify_chain_integrity(self) -> dict:
    # Vérifie: index séquentiel (gaps + duplicates)
    # Vérifie: prev_hash linkage complet
    # Retourne: {ok, height, first_bad, reason, gaps, duplicates}
    # Jamais de raise (fail-safe)
```
Exposé dans `/api/v1/health` → champ `chain_integrity`.

---

## 6. Tests unitaires (17 PASS)

| Groupe | Tests |
|--------|-------|
| `TestWatchdogStallThreshold` | stall=120, env override, 900 absent |
| `TestVerifyChainIntegrity` | empty, genesis, valid, broken prev_hash, gap, dup, no-raise, health |
| `TestPbftReachableProbe` | skip_probe, env, excludes unreachable, fallback, auto-vc triggered, auto-vc info |

---

## 7. Déploiement live

| Nœud | SHA déployé | `chain_integrity.ok` | `height` |
|------|-------------|----------------------|----------|
| OVH2 `151.80.107.29` | `1e8bf604` ✅ | `True` ✅ | 1142 |
| AWS3 `13.38.209.25` | `1e8bf604` ✅ | `True` ✅ | 1142 |
| OVH4 `91.134.45.8` | `1e8bf604` ✅ | `True` ✅ | 1142 |

---

## 8. Comportement attendu désormais

| Scénario | Résultat |
|----------|---------|
| 4/4 nœuds disponibles | PBFT normal view 0 |
| OVH1 mort (view 0 primary) | Auto VIEW-CHANGE → view 1, OVH2 primary |
| OVH2 mort | Auto VIEW-CHANGE → view 2, AWS3 primary |
| AWS3 mort | Auto VIEW-CHANGE → view 3, OVH4 primary |
| OVH4 mort | Auto VIEW-CHANGE → view 4, ... |
| 3/4 disponibles | Finalité possible Q=3 |
| 2/4 disponibles | Aucune finalité, aucun fork |
| Chaîne corrompue au restart | `chain_integrity.ok=False` visible dans `/health` |

---

## 9. État CERTIFIED_100

`CERTIFIED_100 = false`

| Critère | État |
|---------|------|
| TEST DOMAIN live 3 nœuds (27/27) | ✅ rapport 363 |
| PBFT résilient sans OVH1 (code) | ✅ **ce commit** |
| chain_integrity vérifiée live | ✅ **ce commit** |
| VIEW-CHANGE prouvé en live distribué | ⏳ à tester live |
| Persistance après reboot réel | ⏳ à tester |
| OVH1 | ❌ hors périmètre |

Estimation : **~80%** vers CERTIFIED_100.
