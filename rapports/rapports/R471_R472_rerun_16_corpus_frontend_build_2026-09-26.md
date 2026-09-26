# R471 / R472 — Re-run 16 corpus LexiconMapper R467 + Frontend build
**Date :** 2026-09-26  
**git HEAD :** `17c214f6a03d23e63079fcb83fd73bafcb8f97a4`  
**CERTIFIED_100 :** false  
**Auteur :** Bob IDE (ARTCB agent)

---

## 1. Contexte

### R471 — Validation post-correction R467 sur les 21.5M entrées
L'audit expert post-R467 avait identifié 5 points à vérifier :
1. `by_method` complet par langue (pas seulement résolu/UNK)
2. `pos_filtered` quantifié par langue (CORR-01)
3. Fermeture mathématique : `entries = resolved + unresolved`
4. 18 clés collision → N occurrences réelles (pas seulement nb clés)
5. Manifeste `git_sha = HEAD actuel` (L-053)

### R472 — Frontend build + corrections TypeScript
3 erreurs TypeScript bloquaient le build depuis R469 (introduction de ContactPro.tsx) :
- `ContactPro.tsx` : import `useTranslation` + variable `t` déclarée mais inutilisée
- `ReflexStatus.tsx` : `fetchReflexStatus` et `ReflexStatusResponse` supprimés de `client.ts` en R424, jamais mis à jour dans le composant
- `ReflexStatus.tsx` : `value` de `Object.entries()` → type `unknown` non assignable à `ReactNode`

---

## 2. Corrections TypeScript (avant/après)

### `frontend/src/pages/ContactPro.tsx`

**AVANT (ligne 1-2) :**
```tsx
import { useState } from "react";
import { useTranslation } from "../i18n/useTranslation";
```
**APRÈS :**
```tsx
import { useState } from "react";
```
Import `useTranslation` supprimé + variable `const { t } = useTranslation()` retirée (ligne 46 originale).

---

### `frontend/src/pages/ReflexStatus.tsx`

**AVANT (lignes 13-17) :**
```tsx
import { useCallback, useEffect, useState } from "react";
import {
  fetchReflexStatus,
  type ReflexStatusResponse,
} from "../api/client";
import axios from "axios";
```
**APRÈS :**
```tsx
import { useCallback, useEffect, useState } from "react";
import axios from "axios";

// R424 — fetchReflexStatus/ReflexStatusResponse supprimés de client.ts (backend-only).
interface ReflexStatusResponse {
  certified: boolean;
  unique_human_proven: boolean;
  current_priority: string;
  current_priority_name: string;
  triggers_detected: number;
  priorities: Record<string, number>;
  active_since: number | null;
  note: string;
  engine?: string;
  rules?: number;
  total_triggers?: number;
  activated_at?: number | null;
}

async function fetchReflexStatus(): Promise<ReflexStatusResponse> {
  const { data } = await axios.get<ReflexStatusResponse>("/api/v1/reflex/status");
  return data;
}
```

**Fix cast `unknown → String` (ligne 187 originale) :**
```tsx
// AVANT
{value}
// APRÈS
{String(value)}
```

---

## 3. Résultats R471 — Re-run 16 corpus

### Statistiques globales

| Métrique | Valeur |
|---|---|
| `git_sha` | `17c214f6a03d23e63079fcb83fd73bafcb8f97a4` ✅ (= HEAD) |
| Entrées totales | **21 484 106** |
| Résolues | **13 779** (0.064136%) |
| Non résolues (UNK) | 21 470 327 |
| POS filtrées (CORR-01) | **58 513** |
| Occurrences collisions (CORR-02) | **79** (sur 18 clés) |
| Fermeture mathématique | ✅ `13779 + 21470327 = 21484106` |
| `closure_all_ok` | **True** (16/16 profils) |
| Durée totale | 1172.7s (~19.5 min) |

### By_method global (résolus uniquement)

| Méthode | Occurrences |
|---|---|
| `exact_lemma` | 12 649 |
| `exact_surface` | 1 051 |
| `collision_object_over_modifier` | 79 |

### By_method_unresolved global

| Cause | Occurrences |
|---|---|
| `unresolved` | 21 411 814 |
| `pos_filtered` | 58 513 |

### Détail par langue

| Langue | Entrées | Résolus | pos_filtered | Collisions | Rate % |
|---|---|---|---|---|---|
| ar | 1 373 037 | 449 | 3 440 | 0 | 0.0327 |
| de | 1 733 696 | 791 | 2 821 | 4 | 0.0456 |
| en | 2 360 112 | **563** | **12 257** | **18** | 0.0239 |
| es | 1 992 273 | 1 553 | 2 797 | 13 | 0.0780 |
| fr | 784 019 | 446 | 2 620 | 18 | 0.0569 |
| id | 79 949 | 61 | 1 068 | 0 | 0.0763 |
| it | 1 363 559 | 83 | 2 309 | 5 | 0.0061 |
| ja | 1 048 878 | 743 | 3 674 | 0 | 0.0708 |
| ko | 463 834 | 84 | 1 730 | 0 | 0.0181 |
| pl | 1 885 859 | 1 114 | 4 203 | 1 | 0.0591 |
| pt | 909 945 | 613 | 2 654 | 10 | 0.0674 |
| ru | 1 935 993 | 286 | 7 507 | 4 | 0.0148 |
| tr | 2 891 601 | **6 377** | 1 500 | 0 | **0.2205** |
| zh | 472 921 | 70 | 3 893 | 2 | 0.0148 |
| la | 2 042 686 | 516 | 6 040 | 3 | 0.0253 |
| pt-BR | 145 744 | 30 | 0 | 1 | 0.0206 |

### Observations notables

- **`en` : 12 257 pos_filtered** — langue avec le plus de filtrages POS grammaticaux (auxiliaires, conjonctions, prépositions). Normal pour un corpus anglais dense.
- **`ru` : 7 507 pos_filtered** — russophone riche en particules et prépositions.
- **`tr` : taux 0.22%** — turc reste la langue avec le meilleur taux de résolution (agglutination → plus de matchs `exact_lemma`).
- **`en` : 18 collisions** — toutes les 18 clés collision détectées (`car`, `cars`, `voiture`…) ont matché dans le corpus anglais.
- **Manifeste cohérent** : `git_sha = 17c214f` = HEAD local ✅ (L-053 respecté).

### Comparaison R466b → R471

| Métrique | R466b (f7cbfbd) | R471 (17c214f) | Delta |
|---|---|---|---|
| `git_sha` cohérent | ❌ f7cbfbd ≠ HEAD | ✅ 17c214f = HEAD | +L-053 |
| pos_filtered tracé | ❌ non | ✅ 58 513 exposés | +CORR-01 |
| collisions occurrences | ❌ non (nb clés seulement) | ✅ 79 occurrences | +CORR-02 |
| `by_method` complet | ❌ null | ✅ exact_lemma/surface/collision | +A-03 |
| fermeture vérifiée | ❌ non vérifiée | ✅ True 16/16 | +audit |
| fr résolu | 448 | **446** | -2 (faux positifs éliminés CORR-01) |
| en résolu | 615 | **563** | -52 (POS grammaticaux filtrés) |

---

## 4. Frontend build

### Output `npm run build`
```
✓ 123 modules transformed.
dist/index.html                      0.78 kB │ gzip:   0.43 kB
dist/assets/index-BaQ-WNEh.css      13.25 kB │ gzip:   3.41 kB
dist/assets/axios-DhXgJQ-f.js       46.09 kB │ gzip:  17.77 kB
dist/assets/vendor-C8w-UNLI.js     141.74 kB │ gzip:  45.48 kB
dist/assets/index-Cgk88agn.js      302.50 kB │ gzip:  82.67 kB
dist/assets/cytoscape-DTSO7Bv0.js  443.72 kB │ gzip: 142.36 kB
✓ built in 12.79s
```
**Résultat : BUILD SUCCESS** — 0 erreur TypeScript, 0 warning.

Les pages Contact (R469) et le bandeau Pro/Dev/Org (R470) sont maintenant inclus dans `frontend/dist/`.

---

## 5. Fichiers modifiés

| Fichier | Type | Action |
|---|---|---|
| `frontend/src/pages/ContactPro.tsx` | TypeScript | Import useTranslation supprimé |
| `frontend/src/pages/ReflexStatus.tsx` | TypeScript | Interface + fetch locaux, cast String() |
| `frontend/dist/` | Build artifact | Rebuild complet (ContactPro/ReflexStatus inclus) |
| `logs/R471_mapping_stats.json` | Artefact | Nouveau — manifeste 16 profils R471 |
| `scripts/artcb_r471_rerun_16_lexiconmapper_r467.py` | Script | Nouveau — runner R471 |

---

## 6. Points en attente

- **Déploiement live N2/N3/N4** : `git pull` + `systemctl restart artcb` requis pour servir le nouveau `frontend/dist/`
- **TASK-001 FHE** : `check_uniqueness()` via Hamming direct (R378) est en place ; FHE Concrete réel reste à brancher
- **CERTIFIED_100** : toujours `false` — invariant maintenu

---

*Rapport produit automatiquement par Bob IDE (ARTCB agent) — session 2026-09-26*
