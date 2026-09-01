# Ticket 179 — liboqs dans l’image Autoscale publique

**Statut :** OUVERT — **ne pas exécuter maintenant**  
**Décision liée :** D-039 (pas d’init-wallet). D-036 (pas de redéploiement OVH1).  
**PIN Git déjà cloné :** `4cb2943d4190def4efabf16b12369d91ebad7e8f`

---

## Ce qui est fini vs ce qui ne l’est pas

| Travail | État |
|---------|------|
| Sync Git Architecture A (PIN) | **Terminé** dans le log `startup_id=20260831T230052Z_21` : `clone_pin_ok` + `release_written` + `pin=` identiques |
| FastAPI sur l’URL publique | **Pas démontré** au 2026-08-31T23:20Z : `/live` encore `phase=replit_shim` |
| liboqs 0.16 **local** (session Repl / `$HOME/_oqs`) | Peut être vrai **sur le disque interactif** |
| liboqs 0.16 **Autoscale public** | **Non** — le build local **ne se copie pas** dans l’instance publique |

Deux chambres d’hôtel : tu as peint la chambre **atelier** (Repl interactif). La chambre **publique** (Autoscale) est un **autre disque**, souvent sans `.git` et sans `$HOME/_oqs`.

---

## Pourquoi le build local ne se propage pas

1. Autoscale démarre un **conteneur neuf** (souvent sans `.git`).
2. `$HOME/_oqs` et `$HOME/src/liboqs` vivent sur le **filesystem du Repl interactif**, pas dans l’image de déploiement.
3. `replit.nix` n’embarque **pas** `pkgs.liboqs` (commentaire : absent / trop vieux sur le canal). Un Nix 0.13 serait d’ailleurs le **piège ABI** déjà noté (`847c264`, `.agents/memory/liboqs-replit-runtime.md`) : binding Python 0.16 + natif 0.13 → ML-DSA-65 OFF.
4. `replit_start.sh` compile le natif **en arrière-plan après** uvicorn. Même si cmake réussit, le `.so` **disparaît au cold start** suivant.

Donc : `pip show liboqs-python` = binding. **Pas** = natif 0.16 chargé sur l’URL publique.

---

## Procédure de suivi (à exécuter **plus tard**, pas maintenant)

Choisir **une** voie. Ne pas les mélanger.

### Voie A — Cuire le natif dans l’image / snapshot Autoscale (préférée)

1. Sur une machine de build (Repl interactif ou CI) : `scripts/install_native_liboqs_replit.sh` tag **0.16.0**.
2. Vérifier `liboqs.so` + `oqs.get_enabled_sig_mechanisms()` contient `ML-DSA-65`.
3. Inclure `$OQS_INSTALL_PATH` dans le **snapshot de déploiement** (ou artefact monté au même chemin).
4. Dans Autoscale, **avant** uvicorn :  
   `OQS_INSTALL_PATH` + `LD_LIBRARY_PATH` pointent vers **ce** `.so`, **avant** le liboqs Nix 0.13.
5. Redeploy. Mesurer **l’URL publique**, pas le shell local.

### Voie B — Nix `pkgs.liboqs` seulement si version **0.16.x**

Si le canal Nix fournit 0.13 : **refuser**. Revenir à A.

### Voie C — Compiler à chaque cold start Autoscale (dégradé)

Laisser `install_native_liboqs_replit.sh` tourner **avant** uvicorn (après le shim `/live`).  
Acceptable seulement si cmake/gcc sont **dans l’image Autoscale** et si le timeout healthcheck reste `/` = 200.  
Le `.so` n’est **pas** persistant : chaque cold start = 2–5 min.

---

## Critères d’acceptation (quand on l’exécutera)

Mesurés sur `https://artcb--vgac42.replit.app` :

1. `/live` **sans** `phase=replit_shim`
2. `/api/v1/health` FastAPI : `git_sha` = PIN, `release_integrity=ok`
3. `pqc.available=true`, algorithm `ML-DSA-65`
4. Natif **0.16** (pas seulement `liboqs-python` 0.16)
5. `availability_is_not_enforcement=true` reste affiché (D-032 / D-039)
6. Un **second** cold start Autoscale garde (A) ou refait (C) le natif 0.16

## Interdit tant que ce ticket n’est pas clos

- `POST /setup/init-node` (V-R05)
- Dire « plus de fallback Ed25519 »
- Dire « DV-04 PASS »
- Redéployer `152.228.144.34`
- Coller des secrets / seeds

## Qui fait quoi plus tard

| Rôle | Action |
|------|--------|
| Agent Replit | Ne compile **pas** maintenant. Si GO : voie A ou C, rapport SHA + versions natives, **sans** seed |
| Cursor | Ne change **pas** OVH1. Si GO : câbler snapshot / `replit.nix` **seulement** si liboqs Nix = 0.16 |
| Opérateur | GO explicite avant toute cuisson d’image |
