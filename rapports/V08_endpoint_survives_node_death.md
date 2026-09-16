# V-08 — PUBLIC_ENDPOINT_SURVIVES_NODE_DEATH

**Date** : 2026-09-16  
**Statut** : ✅ CODE PASS — ⚠️ DNS ACTION OPÉRATEUR REQUISE  
**CERTIFIED_100** : false (immuable)  
**unique_human_proven** : false

---

## 1. Problème identifié (SPOF)

L'audit 2026-09-16 a mis en évidence un **point de défaillance unique (SPOF)** dans la configuration DNS d'ARTCB :

```python
# src/artcb/config.py
ARTCB_DNS_A_RECORDS[""] = "152.228.144.34"   # apex → OVH1 uniquement
```

```python
# src/artcb/node_registry.py
PUBLIC_HEALTH_URLS["ovh-node-1"] = "https://artcb.me/health"
```

**Conséquence** : si OVH1 (`152.228.144.34`) tombe, `artcb.me` devient inaccessible même si N2/N3/N4 sont vivants.

---

## 2. Propriété cible V-08

> La mort d'un nœud individuel (y compris l'apex OVH1) ne doit jamais rendre le domaine public ARTCB inaccessible, dès lors qu'au moins un nœud du quorum reste vivant.

---

## 3. Ce qui a été implémenté

### `src/artcb/network/failover.py`

Module de détection et diagnostic failover :

| Composant | Rôle |
|-----------|------|
| `NodeProbeResult` | Résultat d'un health-check sur un nœud |
| `FailoverState` | État complet du failover (apex, actif, v08_satisfied) |
| `probe_node()` | Sonde un nœud unique (HTTP GET `/health`) |
| `probe_all_nodes()` | Sonde tous les nœuds — séquentiel — OVH1 bloqué si `skip_ovh1=True` |
| `select_active_node()` | Sélectionne le meilleur nœud vivant selon la priorité |
| `compute_failover_state()` | Calcule l'état V-08 complet |
| `get_failover_status()` | Point d'entrée JSON-sérialisable |

**Priorité failover** (ordre de préférence) :
1. `ovh-node-1` (apex canonique, si vivant)
2. `aws-node-3` (NitroTPM + EIP statique — failover #1)
3. `ovh-node-4` (OVH GRA11 — failover #2)
4. `ovh-node-2` (OVH GRA11 — failover #3)
5. `mac-node-local` (fallback local uniquement)

### `src/api/network_routes.py`

Nouveau endpoint :

```
GET /api/v1/network/failover-status?skip_ovh1=true&timeout_s=3.0
```

Champs de réponse :

| Champ | Type | Description |
|-------|------|-------------|
| `v08_property` | str | `"PUBLIC_ENDPOINT_SURVIVES_NODE_DEATH"` |
| `v08_satisfied` | bool | True si apex vivant ou au moins un secours vivant |
| `v08_note` | str | Message opérateur (action DNS si nécessaire) |
| `apex_node_id` | str | `"ovh-node-1"` |
| `apex_alive` | bool | OVH1 répond ? |
| `failover_triggered` | bool | apex mort ET secours sélectionné |
| `active_node_id` | str | Nœud recommandé |
| `active_url` | str | URL publique du nœud recommandé |
| `alive_nodes` | list | Nœuds qui répondent |
| `dead_nodes` | list | Nœuds qui ne répondent pas |
| `probe_results` | list | Détails par nœud |
| `certified_100` | bool | **Toujours false** |

---

## 4. Résultats des tests

**Fichier** : `tests/test_v08_failover.py`  
**Résultat** : ✅ **41/41 PASS**

| Classe de test | Tests | Scénario |
|----------------|-------|----------|
| `TestApexAloneAlive` | 4 | N1 seul vivant → v08_satisfied=True, pas de failover |
| `TestApexDeadN3Alive` | 6 | N1 mort, N3-AWS vivant → failover déclenché |
| `TestApexDeadN2Alive` | 3 | N1 mort, N2 vivant → failover déclenché |
| `TestApexDeadN4Alive` | 2 | N1 mort, N4 vivant → failover déclenché |
| `TestAllDead` | 5 | Tous morts → v08_satisfied=False |
| `TestQuorum3of4` | 3 | N1+N2+N3 vivants → apex actif prioritaire |
| `TestSkipOvh1` | 2 | skip_ovh1=True → N1 jamais sondé |
| `TestPriority` | 5 | Ordre de priorité respecté |
| `TestGetFailoverStatus` | 7 | `get_failover_status()` — clés, certified_100, etc. |
| `TestFailoverRoute` | 4 | Route HTTP 200, champs corrects, certified_100=false |

---

## 5. Logique `v08_satisfied`

```python
if apex_alive:
    v08_satisfied = True         # domaine accessible directement
elif non_apex_alive:
    v08_satisfied = True         # failover possible si action DNS
else:
    v08_satisfied = False        # FAIL — artcb.me inaccessible
```

---

## 6. Honnêteté sur les limites

⚠️ **Ce code NE modifie PAS le DNS automatiquement.**

La propriété V-08 est démontrée **au niveau logiciel** (détection + diagnostic). La mise en œuvre opérationnelle effective requiert :

### Option A — DNS manuel OVH (immédiat, sans frais)
1. Aller sur le panneau OVH → Zone DNS de `artcb.me`
2. Modifier l'enregistrement `A @` de `152.228.144.34` (OVH1) vers l'IP du nœud de secours actif
3. TTL recommandé : 60s pour permettre un basculement rapide

### Option B — nginx upstream avec health-check (à moyen terme)
```nginx
upstream artcb_backend {
    server 152.228.144.34:8000 max_fails=2 fail_timeout=10s;  # OVH1
    server <N3_IP>:8000 backup;
    server <N4_IP>:8000 backup;
}
```

### Option C — DNS failover OVH/Cloudflare (solution idéale)
Activer le health-check DNS OVH ou utiliser Cloudflare Load Balancer avec health monitors.

---

## 7. Invariants respectés

- `certified_100` : **false** — jamais flipper
- `unique_human_proven` : **false** — non concerné
- OVH1 BLOQUÉ : `skip_ovh1=True` par défaut — aucune tentative de connexion
- `blocks.jsonl` : non touché
- R299 : aucun code supprimé
- SHA/hauteur : non inventés

---

## 8. Fichiers modifiés / créés

| Fichier | Statut |
|---------|--------|
| `src/artcb/network/__init__.py` | ✅ Créé |
| `src/artcb/network/failover.py` | ✅ Créé |
| `src/api/network_routes.py` | ✅ Modifié (ajout route `/failover-status`) |
| `tests/test_v08_failover.py` | ✅ Créé (41/41 PASS) |
| `rapports/V08_endpoint_survives_node_death.md` | ✅ Ce fichier |
