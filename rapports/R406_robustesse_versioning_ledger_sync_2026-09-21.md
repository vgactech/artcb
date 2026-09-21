# R406 — Robustesse versioning : Makefile install-hooks + Ledger v2.9 + sémantique git_head

**Date :** 2026-09-21  
**HEAD au moment de la rédaction :** `b9036a3` (R405 — TASK-VERSIONING)  
**Avancement global :** 84 %  
**CERTIFIED_100 :** false  

---

## 1. Contexte et objectif

R405 a livré le hook pre-commit `artcb_r405_precommit_hook.sh` qui auto-bumpe `MODULE_VERSION` dans les `.py` stagés à chaque `git commit`. L'audit expert post-R405 a identifié **trois questions ouvertes** :

| Question | Problème |
|----------|---------|
| Q1 | Comment garantir que R405 est présent après chaque nouveau clone ? |
| Q2 | Faut-il rester fail-open ou passer fail-closed ? |
| Q3 | Comment empêcher un commit quand le mécanisme est absent/défaillant ? |

R406 répond aux trois questions et synchronise le ledger sur le HEAD réel.

---

## 2. Travaux réalisés

### 2.1 Makefile — cibles `install-hooks` + `check-hooks`

**AVANT :**
```makefile
.PHONY: chain test api frontend demo demo-real \
        env-docker env-replit env-dev env-codespaces \
        docker-build docker-up docker-down docker-logs \
        ssh-setup test-fast deploy-check \
        node-start p2p-status p2p-connect test-p2p
```
*(pas de cible install-hooks)*

**APRÈS :**
```makefile
.PHONY: chain test api frontend demo demo-real \
        env-docker env-replit env-dev env-codespaces \
        docker-build docker-up docker-down docker-logs \
        ssh-setup test-fast deploy-check \
        node-start p2p-status p2p-connect test-p2p \
        install-hooks check-hooks

# ─── Hooks Git (R406) ─────────────────────────────────────────────────────────
# À exécuter après chaque nouveau clone : make install-hooks
# Installe le hook pre-commit R405 (auto-bump MODULE_VERSION) dans .git/hooks/
install-hooks:
	@echo "[R406] Installation du hook pre-commit R405 (auto-bump MODULE_VERSION)..."
	python3 scripts/artcb_r405_install_precommit_hook.py
	@echo "[R406] ✅ Hook installé. Vérification :"
	python3 scripts/artcb_r405_install_precommit_hook.py --check

check-hooks:
	@echo "[R406] Vérification de l'état du hook pre-commit R405..."
	python3 scripts/artcb_r405_install_precommit_hook.py --check
```

**Fichier modifié :** `Makefile`  
**Impact :** Tout nouveau clone peut installer le hook en une commande.

---

### 2.2 Décision fail-open / fail-closed (Q2 + Q3)

**Décision maintenue : FAIL-OPEN conservé.** Justifications :

1. `git commit --no-verify` contourne **toujours** un hook local — fail-closed local n'est pas une garantie absolue.
2. Fail-closed bloquerait les CI/CD automatisés et les merges de dépendances.
3. La vraie garantie devra venir d'une **CI GitHub Actions** (future R407) qui vérifie les `MODULE_VERSION` post-commit.

Responsabilité documentée dans le Makefile et dans le ledger :
```
make install-hooks  ← obligatoire après chaque nouveau clone
```

---

### 2.3 Sémantique `git_head` dans le ledger (Q auto-référence)

**Problème :** Le SHA du commit contenant `task_ledger.yaml` ne peut pas être connu avant que ce commit existe.

**Règle gravée dans `TASK-VERSIONING.git_head_semantics` du ledger :**
> `git_head` = HEAD connu **AVANT** le commit de sync du ledger.  
> C'est-à-dire : le SHA du commit *précédent* — vérifiable et non circulaire.

---

### 2.4 Sync ledger v2.7 → v2.9

**AVANT :**
```yaml
meta:
  version: "2.7"
  git_head: "1ac7d22"   # stale depuis R398
  global_pct: 78
  sync_note: "v2.7 — sync HEAD c280a8a"
```

**APRÈS :**
```yaml
meta:
  version: "2.9"
  git_head: "b9036a3"   # HEAD réel R405
  global_pct: 84
  sync_note: "v2.9 — R402/R403/R404/R405/R406 intégrés. TASK-VERSIONING=DONE. Makefile install-hooks."
```

Nouvelles entrées dans `done` : R402, R403, R404, R405, R406, TASK-VERSIONING  
TASK-VERSIONING retiré de `open`  
Doublons R364/R365 hérités corrigés → `R364-initial` / `R365-initial`

---

## 3. Tests R406 — 15/15 PASS

| Test | Description | Résultat |
|------|-------------|---------|
| T01 | Makefile contient `install-hooks` | ✅ PASS |
| T02 | `make install-hooks` s'exécute sans erreur | ✅ PASS |
| T03 | Hook installé après `make install-hooks` | ✅ PASS |
| T04 | Marqueur R405 présent dans le hook | ✅ PASS |
| T05 | Hook absent dans un repo git tmp vide | ✅ PASS |
| T06 | `make install-hooks` est idempotent (×2) | ✅ PASS |
| T07 | `--check` retourne 0 si hook installé | ✅ PASS |
| T08 | Commit passe sans hook (fail-open simulé) | ✅ PASS |
| T09 | Hook bash contient `exit 0` fail-open + WARN | ✅ PASS |
| T10 | `sync_note` contient un SHA (sémantique documentée) | ✅ PASS |
| T11 | R402/R403/R404/R405 présents dans `done` | ✅ PASS |
| T12 | `global_pct >= 84` | ✅ PASS |
| T13 | `git_head` ledger = HEAD réel (b9036a3) | ✅ PASS |
| T14 | `TASK-VERSIONING` présent dans `done` ou `open` | ✅ PASS |
| T15 | Aucun doublon d'id dans done+open | ✅ PASS |

**Total : 15/15 PASS en 6.41s**

---

## 4. État OPEN restant après R406

| ID | Titre | Priorité |
|----|-------|---------|
| R365 | aws-node-3 surveillance PBFT + décision opérateur | HIGH |
| TASK-001-BIOMETRIE-SUITE | FAR/FRR + FHE + SDK iOS/Android | MEDIUM |
| TASK-005 | Genesis transfer — authz | LOW |
| TASK-006-LIVE-VALIDATION | Validation live panne/retrait aws-node-3 | LOW |
| TASK-007 | PoL / KnowledgeID / UsageID | LOW |

---

## 5. Limites honnêtes

- **make install-hooks** n'est pas automatique — un développeur qui oublie de le lancer n'a pas de protection.
- **Fail-open** = pas de garantie d'intégrité forte sur chaque commit.
- **R407 (future)** : CI GitHub Actions vérifiant `MODULE_VERSION` post-push = vraie garantie opposable.
- `CERTIFIED_100 = false` — invariant permanent.

---

## 6. Avant / Après — résumé

| Domaine | AVANT (R405) | APRÈS (R406) |
|---------|-------------|-------------|
| Nouveau clone | Hook absent, aucune doc | `make install-hooks` documenté |
| Fail-open | Décidé mais non documenté | Justification formelle dans ledger |
| Ledger git_head | `1ac7d22` (stale) | `b9036a3` (HEAD réel) |
| Ledger version | 2.7 | 2.9 |
| Ledger global_pct | 78 % | 84 % |
| TASK-VERSIONING | OPEN | DONE |
| Doublons R364/R365 | Présents | Corrigés (suffixe `-initial`) |
| Tests R406 | — | 15/15 PASS |

**CERTIFIED_100 = false | DEBUG MODE | R406**
