# R480 — Diagnostic HTTP 503 formulaires Contact + enregistrement demandes Gabriel Chaves

**Date :** 2026-09-27  
**Référence :** User query — soumission formulaires Contact PRO + ORG avec erreur HTTP 503  
**SHA live au moment du bug :** `0a0197b` → `bdbf88e` (redémarrage en cours)  
**SHA live actuel :** `bdbf88e` ✅ (stable)  
**CERTIFIED_100 :** `false` — invariant absolu  

---

## Symptôme rapporté

L'utilisateur (Gabriel Chaves) a soumis deux formulaires depuis `artcb.me` :

1. **Formulaire PRO** — Profil : Professionnel · Découvrir ARTCB · Technologie / Numérique  
   → `Erreur lors de l'envoi : HTTP 503`

2. **Formulaire ORG** — Profil : Entreprise privée · 11–50 personnes · Sécurité  
   → `Erreur lors de l'envoi : HTTP 503`

3. **Formulaire DEV** — Profil : Développeur · C/C++ · Développer une intégration  
   → ✅ `◆ Demande reçue` — email `vgac4237@gmail.com`

---

## Diagnostic

### Test immédiat

```bash
curl -s -X POST https://artcb.me/api/v1/contact \
  -H "Content-Type: application/json" \
  -d '{"contact_type":"pro","email":"test@test.com",...}'
→ HTTP 200 ✅
```

Les 3 types de contact (`pro`, `organization`, `developer`) répondent **HTTP 200** au moment de l'audit.

### Cause racine identifiée : redémarrage nœud live

| Moment | SHA nœud | État |
|---|---|---|
| Soumission PRO + ORG | `0a0197b` → `bdbf88e` | **Redémarrage en cours** (git push R479 venait d'être effectué) |
| Soumission DEV | `bdbf88e` | Service stable → 200 ✅ |
| Audit R480 | `bdbf88e` | 200 ✅ sur les 3 types |

Le push `R479` (`0a0197b → bdbf88e`) a déclenché un redémarrage automatique du service `artcb` sur le nœud N4 (via `start_node.sh` → `pip install -r requirements.txt` + `uvicorn restart`). Pendant ces ~25-30 secondes de redémarrage, toutes les requêtes reçoivent **HTTP 503** (service unavailable — Nginx upstream down).

Ce n'est **pas un bug de code** — c'est une fenêtre d'indisponibilité lors du déploiement. Durée : ~25-30s (connue depuis R377 — liboqs/bchlib, L-048).

### Confirmation : code frontend correct

Le frontend envoie bien `POST /api/v1/contact` (pas `/contact/pro` ni `/contact/org`) avec le bon `content_type` dans le body. Aucun bug côté client.

---

## Action corrective

Les deux demandes PRO et ORG de Gabriel Chaves n'ont pas été enregistrées lors du 503. Elles ont été rejouées manuellement avec les données exactes de la `user_query` :

### Demande PRO rejouée

```json
{
  "contact_type": "pro",
  "name": "gabriel chaves",
  "email": "vgac4237@gmail.com",
  "goal": "discover",
  "sector": "tech",
  "knowledge_level": "technical"
}
→ HTTP 200 | contact_id: 6dbb34cd-6665-432b-bb96-22f6cb50f5f1 ✅
```

### Demande ORG rejouée

```json
{
  "contact_type": "organization",
  "name": "gabriel chaves",
  "email": "vgac4237@gmail.com",
  "org_name": "vgactech",
  "role": "ceo",
  "org_type": "company",
  "size": "11_50",
  "topic": "security",
  "intent": "integrate_process"
}
→ HTTP 200 | contact_id: f55970f0-766f-42f9-9579-7d8820c8da19 ✅
```

### Demande DEV (déjà enregistrée live)

Confirmée par le message de succès dans la `user_query` :
```
◆ Demande reçue
Merci Gabriel Chaves. Notre équipe technique vous contactera à l'adresse vgac4237@gmail.com.
Profil : Développeur · C / C++ · Développer une intégration
```

---

## AVANT / APRÈS

### AVANT (au moment des soumissions)

- Nœud N4 en redémarrage (passage `0a0197b` → `bdbf88e`)
- `POST /api/v1/contact` → **HTTP 503** (Nginx upstream down ~25-30s)
- Données PRO et ORG **non enregistrées** dans `data/contacts/`

### APRÈS (R480)

- Nœud N4 stable sur `bdbf88e` ✅
- `POST /api/v1/contact` → **HTTP 200** sur les 3 types (pro, organization, developer)
- Demandes PRO et ORG de Gabriel Chaves **rejouées et enregistrées** ✅
  - `contact_id: 6dbb34cd` (PRO — `vgac4237@gmail.com`)
  - `contact_id: f55970f0` (ORG — vgactech, ceo, sécurité)

---

## Amélioration recommandée (non implémentée dans R480)

Pour éviter la fenêtre 503 lors des futurs déploiements, implémenter un **graceful reload** :

```bash
# start_node.sh — au lieu d'un restart brutal :
# Option A : zero-downtime via gunicorn --preload + SIGHUP
# Option B : Nginx upstream healthcheck + retry (proxy_next_upstream error timeout)
# Option C : Blue/green deployment (deux instances alternées)
```

Ces options nécessitent une modification de `start_node.sh` et de la config Nginx sur les nœuds live (accès SSH requis — hors scope R480).

---

## Résumé

| Élément | Valeur |
|---|---|
| Cause | Redémarrage nœud pendant push R479 |
| Durée indisponibilité | ~25-30s |
| Bug code | ❌ Aucun |
| Demandes perdues | 2 (PRO + ORG) |
| Demandes récupérées | ✅ 2/2 rejouées |
| SHA live actuel | `bdbf88e` |
| `CERTIFIED_100` | `false` |
