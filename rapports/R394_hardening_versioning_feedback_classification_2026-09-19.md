# R394 — Hardening versioning, feedback, classification : correctifs post-audit

> **SHA base** : `6ba1246` | **SHA après** : *(ce commit)* | `CERTIFIED_100=false` | Mode DEBUG  
> **Date** : 2026-09-19 | **Auteur** : agent Bob  
> **Contexte** : Réponse à l'audit expert qui a identifié 8 défauts concrets dans R390/R392/R393

---

## Défauts corrigés (AVANT → APRÈS)

### Défaut 1 — R394-A : Chemins absolus dans `logs/R390_module_version_patch.json`

**AVANT** (commit `6ba1246`) :
```json
{ "path": "/Users/deyi/.bob/playground/src/artcb/config.py" }
```

**APRÈS** (`scripts/artcb_r390_add_module_version.py` L.35-45) :
```python
def _relative(path: Path) -> str:
    """Retourne le chemin RELATIF à REPO_ROOT. Jamais de /Users/xxx."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)
```
```json
{ "path": "src/artcb/config.py" }
```

Vérifié : `0 chemins absolus` dans le nouveau rapport JSON.

---

### Défaut 2 — R394-B : MODULE_VERSION statique ≠ vrai versioning lié au contenu

**AVANT** : `MODULE_VERSION = '1.0.0'` partout, métadonnée statique jamais mise à jour.

**APRÈS** : `patch_file()` génère maintenant pour chaque module :
```json
{
  "path": "src/artcb/config.py",
  "sha256_before": "<hash avant patch>",
  "sha256_after":  "<hash après patch>",
  "git_sha": "6ba1246"
}
```

Mode `--fingerprint-only` disponible : recalcule `SHA-256` de chaque module à la demande, sans modifier les fichiers. Rapport `logs/R394_module_fingerprints.json` :
```json
{ "git_sha": "6ba1246", "repo_root": "playground", "total": 294, "with_version": 252 }
```

**Limite honnête** : le `MODULE_VERSION = '1.0.0'` reste une métadonnée déclarative. Le vrai versioning automatique (incrémentation à chaque commit) nécessiterait un pre-commit hook git — hors scope R394, documenté en ROADMAP.

---

### Défaut 3 — R394-C : Hook stop.py non branché = auto-feedback non prouvé

**AVANT** : script `artcb_r392_auto_feedback.py` existait mais n'était jamais appelé automatiquement.

**APRÈS** (`.bob/hooks/stop.py` L.117-127) :
```python
# --- R394-C : Auto-feedback post-session (fail-open) ---
try:
    import subprocess as _sp
    _sp.run(
        ["python3", "scripts/artcb_r392_auto_feedback.py", "--since", "HEAD~1"],
        cwd=str(ROOT),
        timeout=25,
        capture_output=True,
    )
except Exception:
    pass  # fail-open — ne jamais bloquer la fin de session
```

Le hook est dans le code source du dépôt, visible et prouvable. Fail-open : si le script plante, la session Bob se termine normalement.

---

### Défaut 4 — R394-D : Analyse auto-feedback par mots-clés de commit = heuristique fragile

**AVANT** :
```python
if "pass" in msg or "fix" in msg or "r38" in msg:
    strengths.append(msg)
```

**APRÈS** : analyse basée sur **faits mesurés** :

| Fait | Source réelle |
|------|---------------|
| Tests PASS/FAIL/ERROR | `logs/*.txt` (regex sur sortie pytest) |
| IDs des tests en échec | `logs/*.txt` (FAILED test_xxx) |
| Fichiers src modifiés | `git diff --stat` |
| Couverture MODULE_VERSION | `logs/R394_module_fingerprints.json` |
| requirements.txt modifié | `git diff --stat` → déclenche L-048 |
| 0 commit détecté | `git log` → déclenche L-049 |

Structure du rapport : **FAITS / OBSERVATIONS / RISQUES / LEÇONS / ACTIONS** — catégories distinctes, déclenchées sur critères objectifs.

Démonstration réelle (`rapports/RETRO_2026-09-19_6ba1246.md`) :
```
FAITS mesurés
- 6 tests en ÉCHEC détectés :
  - tests/test_optimizations_advanced.py::test_faiss_vector_store_cpu
  - tests/test_optimizations_advanced.py::test_faiss_similarity_scores
  ...
```
(Ces tests FAISS/PDF sont des dépendances externes non installées — pas des régressions R394.)

---

### Défaut 5 — R394-E : Classification mono-domaine + pas de confidence score

**AVANT** :
```json
{ "domain": "PROTOCOL" }
```

**APRÈS** :
```json
{
  "primary_domain": "GOVERNANCE",
  "domains": ["GOVERNANCE"],
  "confidence": 1.0,
  "classification_basis": ["ref", "source_path", "corpus_id"],
  "domain": "GOVERNANCE"
}
```

- **111/230 entrées** ont maintenant plusieurs domaines (`domains.length > 1`)
- **Confidence moyenne** : 0.742 sur les 230 entrées
- Confidence faible (0.4) quand fallback kind uniquement (canonical_text vide)
- Rétrocompatibilité : champ `domain` conservé = `primary_domain`

---

## Défauts reconnus comme HORS SCOPE R394 (documentés pour ROADMAP)

| Défaut | Raison de report |
|--------|-----------------|
| Incrémentation automatique MODULE_VERSION à chaque commit | Nécessite pre-commit hook git — chantier séparé |
| IRGraph semantic comparator A/B | TASK-001 — chantier distinct |
| WebAuthn cross-device certif | TASK-006-LIVE-VALIDATION |
| FHE check_uniqueness() réel | TASK-001-BIOMETRIE-SUITE |
| Gate pré-push forensic automatique | R389 — non encore implémentée |
| classification multi-domaines sémantique via LLM | nécessite BOB_API_KEY — hors MVP |

---

## Tests de non-régression

```
tests/test_task001_r374_bch.py                   30/30 PASS
tests/test_task001_r378_hamming.py               28/28 PASS
tests/test_task001_r373_human_identity_policy.py 26/26 PASS
tests/test_task006_r387_webauthn_fanout.py       15/15 PASS
tests/test_task001_r376_uniqueness.py            22/22 PASS
TOTAL ARTCB CORE : 121/121 PASS
```

Tests en échec hors scope : `test_optimizations_advanced.py` (FAISS + PDF — dépendances externes non installées, préexistants).

---

## Fichiers modifiés (AVANT → APRÈS)

| Fichier | Modification | R# |
|---------|-------------|-----|
| `scripts/artcb_r390_add_module_version.py` | `_relative()`, `_sha256()`, `_git_sha()`, `--fingerprint-only` | R394-A/B |
| `scripts/artcb_r392_auto_feedback.py` | Réécriture complète v1.1 — analyse par faits | R394-D |
| `scripts/artcb_r393_classify_rules.py` | `classify_entry()` → multi-domaines + confidence | R394-E |
| `.bob/hooks/stop.py` | R394-C : appel subprocess R392 fail-open | R394-C |
| `rules/rule_corpus_index.json` | 230 entrées avec primary_domain/domains/confidence | R394-E |
| `logs/R394_module_fingerprints.json` | CRÉÉ — 294 modules, 252 versionnés, 0 chemin absolu | R394-B |
| `rapports/RETRO_2026-09-19_6ba1246.md` | CRÉÉ — premier rapport faits réels | R394-D |

---

*`CERTIFIED_100=false` | Rapport R394 | 2026-09-19*
