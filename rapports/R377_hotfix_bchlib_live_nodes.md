# R377 — Hotfix live : bchlib manquant sur N2/N4/N3 — artcb.me DOWN→UP

**Date :** 2026-09-18  
**Durée panne :** inconnue (découverte lors de ce diagnostic)  
**Résolution :** ~20 minutes après identification  
**Commit déclencher la panne :** `d81b130` (R374 — ajout de `bchlib>=2.1.3` à requirements.txt)  
**Statut :** ✅ RÉSOLU — 4/4 nœuds `healthy` sur `e039cdaf`  
**CERTIFIED_100 :** false  

---

## 1. Symptôme

```
https://artcb.me/health → 502 Bad Gateway
N2 (151.80.107.29):443 → 502
N4 (91.134.45.8):443 → 502
N3 (13.38.209.25) n3.artcb.me → 502
```

Nginx répond → TLS OK → FastAPI mort derrière.

---

## 2. Diagnostic

### Étape 1 — DNS

```
$ dig +short artcb.me A
151.80.107.29   (N2/OVH2)
91.134.45.8     (N4/OVH4)
```

DNS multi-A OK. Nginx sur les deux nœuds répond (502 ≠ timeout/refus).

### Étape 2 — Port 8000 direct

```
N2 :8000 → (aucune réponse)
N4 :8000 → (aucune réponse)
N3 :8000 → Connection refused
```

FastAPI uvicorn mort sur les 3 nœuds.

### Étape 3 — Journalctl OVH2 (SSH)

```
Sep 18 14:18:00 start_node.sh[3591986]:   File "/home/ubuntu/artcb/src/artcb/identity/biometric_onchain.py", line 95, in <module>
Sep 18 14:18:00 start_node.sh[3591986]:     import bchlib
Sep 18 14:18:00 start_node.sh[3591986]: ModuleNotFoundError: No module named 'bchlib'
```

**Cause racine confirmée :** `bchlib` ajouté à `requirements.txt` en R374 (commit `d81b130`) mais **jamais installé dans le venv des nœuds live**.

Le service était en boucle `activating (auto-restart)` → crash → restart → crash.

---

## 3. Cause racine détaillée

| Élément | État |
|---------|------|
| `requirements.txt` | ✅ `bchlib>=2.1.3` présent depuis commit `d81b130` |
| Venv OVH2 | ❌ `bchlib` absent (jamais `pip install -r requirements.txt` relancé après R374) |
| Venv OVH4 | ❌ même problème |
| Venv AWS3 | ❌ même problème |
| Git sur N2/N4 | ✅ `e039cdaf` (à jour) |
| `start_node.sh` | ✅ n'installe pas automatiquement les nouvelles dépendances |

**Leçon principale :** Un commit ajoutant une nouvelle dépendance dans `requirements.txt` **ne déclenche pas automatiquement `pip install`** sur les nœuds live. Le déploiement des dépendances est une étape séparée du déploiement du code.

---

## 4. Correction appliquée

### OVH2 (151.80.107.29) — SSH direct

```bash
cd ~/artcb
.venv/bin/pip install 'bchlib>=2.1.3' --quiet
sudo systemctl restart artcb
```

Résultat : `BCHLIB_OK` → service `active` → health `e039cdaf / healthy`

### OVH4 (91.134.45.8) — SSH direct

```bash
cd ~/artcb
.venv/bin/pip install 'bchlib>=2.1.3' --quiet
sudo systemctl restart artcb
```

Résultat : `BCHLIB_OVH4_OK` → service `active` → health `e039cdaf / healthy`

### AWS3 (13.38.209.25) — SSM via boto3

```python
ssm.send_command(...)
# commande :
cd /home/ubuntu/artcb
.venv/bin/pip install 'bchlib>=2.1.3' --quiet
sudo systemctl restart artcb.service
```

Résultat : `BCHLIB_OK` → service `active` → health `e039cdaf / healthy`

---

## 5. Résultat final mesuré

| Nœud | IP | git_sha | status | bootstrap_mode |
|------|----|---------|--------|----------------|
| artcb.me | DNS → N2/N4 | `e039cdaf03cc` | healthy | False |
| N2/OVH2 | 151.80.107.29 | `e039cdaf03cc` | healthy | False |
| N4/OVH4 | 91.134.45.8 | `e039cdaf03cc` | healthy | False |
| N3/AWS3 | 13.38.209.25 | `e039cdaf03cc` | healthy | False |

**4/4 nœuds `healthy`.**

---

## 6. Avant / Après

### Avant (panne)

```
artcb.me → 502 Bad Gateway (nginx/1.24.0)
N2 :8000 → no response (uvicorn mort)
N4 :8000 → no response (uvicorn mort)
N3 :8000 → Connection refused (uvicorn mort)
Logs N2 : ModuleNotFoundError: No module named 'bchlib'
```

### Après (résolu)

```
artcb.me → {"status":"healthy","git_sha":"e039cdaf..."}
N2 → healthy / e039cdaf / bootstrap=False
N4 → healthy / e039cdaf / bootstrap=False
N3 → healthy / e039cdaf / bootstrap=False
```

---

## 7. Leçon L-048 (à ajouter)

> **L-048 — Nouvelle dépendance = re-pip obligatoire sur tous les nœuds live**
>
> L'ajout d'une dépendance dans `requirements.txt` ne déclenche pas automatiquement
> son installation sur les nœuds live. Si `start_node.sh` ne fait pas `pip install -r requirements.txt`
> à chaque démarrage, tout commit introduisant une nouvelle lib crée une panne silencieuse
> au prochain restart du service. Action : soit `start_node.sh` installe les dépendances à
> chaque boot, soit le script de hotfix/deploy doit inclure `pip install` explicitement.

---

## 8. Action recommandée

Modifier [`scripts/start_node.sh`](scripts/start_node.sh) ou [`scripts/hotfix_pull_restart.sh`](scripts/hotfix_pull_restart.sh) pour inclure :

```bash
pip install -r requirements.txt --quiet --no-deps-update
```

avant le lancement d'uvicorn, pour que les nouvelles dépendances soient toujours installées.

---

*CERTIFIED_100=false | OVH1 152.228.144.34 non touché*
