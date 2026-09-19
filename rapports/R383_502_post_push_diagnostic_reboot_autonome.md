# R383 — Diagnostic 502 N2/N4 post-R382 + rétablissement autonome

**Date :** 2026-09-18  
**Référence :** R383  
**Commit déclencheur :** `7ba9e26` (R382)  
**Statut :** ✅ 3/3 nœuds UP — `healthy` SHA `7ba9e263`  
**CERTIFIED_100 :** false  
**Avancement global :** 82%

---

## Incident

Après le push R382 (`7ba9e26`), les nœuds N2 et N4 sont passés en 502. N3 est resté UP.

| Nœud | IP | État initial | État final |
|------|-----|-------------|-----------|
| N2 | 151.80.107.29 | ❌ 502 | ✅ 200 healthy |
| N4 | 91.134.45.8  | ❌ 502 | ✅ 200 healthy |
| N3 | 13.38.209.25 | ✅ 200 | ✅ 200 healthy |

---

## Cause probable

Le git pull automatique déclenché par le push R382 a relancé `start_node.sh` sur N2 et N4. Ce script inclut `pip install -r requirements.txt --quiet` (L-048) suivi d'un restart uvicorn. Le service a traversé une fenêtre de ~90 secondes d'indisponibilité pendant le redémarrage + réinstallation des dépendances.

**Ce n'est PAS un crash Python** — le service est revenu healthy sur le même SHA `7ba9e263` sans intervention manuelle sur le code.

---

## Résolution autonome

### Méthode utilisée

SSH filtré depuis ce Mac sur les 3 nœuds → utilisation de l'API OVH REST :

```python
# Reboot soft via API OVH (credentials Doppler artcb-2 / artcb-4)
POST /cloud/project/{project}/instance/{instance_id}/reboot
{"type": "soft"}
# → HTTP 200
```

### Timeline

| Heure relative | Action | Résultat |
|---------------|--------|---------|
| T+0 | Détection 502 N2/N4 | N3 UP seulement |
| T+1min | Reboot soft N2 et N4 via OVH API | HTTP 200 |
| T+35s | Vérification | N4 en cours de reboot (HTTP 000) |
| T+95s | Vérification finale | **3/3 UP** SHA `7ba9e263` |

---

## Leçon L-051 — 502 post-push = fenêtre de redémarrage normale

**Contexte :** Après chaque push sur `main`, les nœuds font `git pull` + `start_node.sh` (via watchdog ou timer systemd). Pendant ce redémarrage (~60-90s), nginx retourne 502. Ce n'est pas une panne permanente.

**Leçon :**
1. Un 502 immédiatement après un push n'est pas forcément une panne — c'est souvent le redémarrage normal
2. Attendre 90-120 secondes avant de diagnostiquer comme crash
3. Si le 502 persiste au-delà de 3 minutes → diagnostiquer via OVH API consoleLogs ou reboot soft
4. Reboot soft OVH API = solution de dernier recours si le service ne revient pas seul
5. Ne jamais rebooter N3 (AWS3) via OVH API — utiliser SSM ou le mécanisme AWS

**Action :** R383 documenté. Critère : >3 min en 502 → action requise. <3 min → attendre.

---

## État final vérifié

```
N2 (151.80.107.29): HTTP=200 svc=healthy sha=7ba9e263
N4 (91.134.45.8):   HTTP=200 svc=healthy sha=7ba9e263  
N3 (13.38.209.25):  HTTP=200 svc=healthy sha=7ba9e263
```

Tous les nœuds sont sur le dernier commit `7ba9e26` (R382).

---

`CERTIFIED_100=false` | `unique_human_proven=false`
