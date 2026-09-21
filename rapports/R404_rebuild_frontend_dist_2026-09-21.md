# R404 — Rebuild frontend dist/ : suppression AgentMemory/Network du bundle production

**Date :** 2026-09-21  
**SHA HEAD :** `28d0f61`  
**Statut :** ✅ DONE — commité + pushé  
**CERTIFIED_100 :** false  

---

## Contexte — Divergence identifiée

L'expert a détecté une divergence critique entre le code source `main` et le frontend
réellement servi par `artcb.me` :

```
GitHub main (0132ab1)     ← source propre : /agent-memory et /network ABSENTS
        ≠
frontend/dist/            ← bundle daté du 18 sept (commit 25d1e1e) : ANCIEN
        ≠
artcb.me                  ← servait encore /agent-memory et /network visible utilisateur
```

**Root cause :** le `frontend/dist/` est tracké dans git. Les suppressions de pages
(R379/R401/R402) avaient modifié les fichiers `.tsx` source mais le bundle Vite n'avait
jamais été régénéré. Le nœud servait donc l'ancien artefact `index-CssPbdoB.js`.

---

## AVANT / APRÈS

### AVANT (bundle `index-CssPbdoB.js` — commit 25d1e1e du 18/09)

```
frontend/dist/assets/index-CssPbdoB.js  — 228 kB
  ✅ contient routes : /agent-memory, /network
  ✅ contient composants : AgentMemory, AgentPanel
  ✅ contient page : Memorize
```

Vérification : `grep -c "agent-memory|AgentMemory" index-CssPbdoB.js` → **2 occurrences**

### APRÈS (bundle `index-lQDgNxDq.js` — commit 28d0f61 du 21/09)

```
frontend/dist/assets/index-lQDgNxDq.js  — 228.5 kB
  ❌ route /agent-memory → absente
  ❌ route /network      → absente
  ❌ composant AgentPanel → absent
  ❌ page Memorize       → absente
  ✅ chaîne i18n agent_memory conservée (dictionnaire backend — non une route)
```

Vérification : `grep -o '"/agent-memory"|"/network"|AgentMemory\b' index-lQDgNxDq.js` → **0 résultats**

---

## Fichiers modifiés

| Fichier | Changement |
|---|---|
| `frontend/dist/assets/index-CssPbdoB.js` | SUPPRIMÉ (ancien bundle) |
| `frontend/dist/assets/index-lQDgNxDq.js` | CRÉÉ (nouveau bundle propre) |
| `frontend/dist/index.html` | Mis à jour (pointeur vers nouveau JS) |

---

## Conformité source → dist (vérifiée)

| Élément source | Présent dans new dist ? | Correct |
|---|---|---|
| `App.tsx` — pas de route `/agent-memory` | ❌ absent | ✅ |
| `App.tsx` — pas de route `/network` | ❌ absent | ✅ |
| `DashboardLayout.tsx` — pas de lien agent-memory | ❌ absent | ✅ |
| 15 pages listées dans App.tsx | ✅ toutes présentes | ✅ |
| i18n `agent_memory` (dictionnaire) | ✅ présent (chaîne texte) | ✅ (pas une route) |

---

## Impact sur les nœuds live

Après `git pull` sur N2/N4/N3, le frontend servi sera le bundle R404.  
Les nœuds live rechargent le `frontend/dist/` statique via le serveur uvicorn —  
**aucune action pip ni restart service requis** (fichiers statiques uniquement).

⚠️ **L-048 rappel** : pas de nouvelle dépendance Python dans ce commit — pas de re-pip requis.

---

## Limite documentée

Les chaînes i18n `agent_memory` (`translations.ts`) restent dans le bundle car elles font
partie du dictionnaire de traduction (`nav_agent_memory: 'Agent Memory'` pour les langues).
Ces chaînes ne constituent pas des routes React — elles n'affectent pas la navigation.
Un nettoyage optionnel des clés i18n inutilisées pourrait être fait séparément.

---

## CERTIFIED_100=false
