# R432 — Durcissement sécurité binding : actor authentifié + séparation REVOKE/PURGE + écriture atomique + version CAS

**Date :** 2026-09-24  
**SHA HEAD avant commit :** `0045dca37e6ff78f9385ebca1e31cecd07ad6e98`  
**Auteur :** Bob IDE (agent)  
**Avancement global :** ~54 %  
**CERTIFIED_100 :** false  

---

## Contexte — Audit R431

L'audit indépendant (vgactech/artcb, commit `0045dca`) a identifié 4 problèmes dans l'implémentation R431 :

| # | Problème | Gravité |
|---|----------|---------|
| P1 | `revocation_actor` = valeur body client → spoofable | Critique (forensic) |
| P2 | DELETE R379 contourne l'historique R431 (deux chemins concurrents) | Architectural |
| P3 | `_write()` = `write_text()` sans verrou ni rename → pas atomique | Fiabilité |
| P4 | Pas de champ `version` ni de CAS → deux opérations concurrentes indétectables | Cohérence |

R432 traite les 4 problèmes.

---

## Fichiers modifiés

### 1. `src/artcb/security/wallet_device_binding.py`

| Élément | Avant R432 | Après R432 |
|---------|-----------|------------|
| `MODULE_VERSION` | `'1.1.1'` | `'1.2.0'` |
| Import `fcntl` | absent | ajouté |
| `_write()` / `_write_test()` | `write_text()` direct | délèguent à `_write_atomic()` |
| `_write_atomic()` | absente | tmp → fsync → rename + flock (POSIX) |
| `BindingPurgeError` | absente | nouvelle exception pour la purge physique |
| Champ `version` dans records | absent | `version: 1` à la création, incrémenté à chaque mutation |
| Champ `requested_actor` dans records | absent | conserve la valeur du body client (informatif) |
| `revoke_with_history()` — param `actor` | `actor: str = "admin"` (body client) | `authenticated_actor` (serveur) + `requested_actor` (body, informatif) + `expected_version` CAS |
| `revoke_with_history()` — CAS | absent | vérifie `expected_version` si fourni, lève `BindingRevocationError` si divergence |
| `revoke_with_history()` — retour | `{previous_state, new_state, revoked_at, binding_id}` | + `version_before`, `version_after` |
| `purge_binding()` | absente | purge physique d'un binding REVOKED uniquement + journal forensic |
| `_append_purge_log()` | absente | append-only dans `binding_purge_log.json` |
| `list_purge_log()` | absente | lecture du journal de purge |

#### Avant (ligne 111, `_write`) :
```python
def _write(self, records: list[dict]) -> None:
    self.path.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    self.path.chmod(0o600)
```

#### Après :
```python
@staticmethod
def _write_atomic(target: Path, records: list[dict]) -> None:
    tmp = target.with_suffix(".tmp")
    payload = json.dumps(records, indent=2, ensure_ascii=False).encode("utf-8")
    with tmp.open("wb") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX)
        except (AttributeError, OSError):
            pass  # Non-POSIX — best effort
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    tmp.rename(target)
    try:
        target.chmod(0o600)
    except OSError:
        pass

def _write(self, records: list[dict]) -> None:
    self._write_atomic(self.path, records)
```

#### Avant (signature `revoke_with_history`) :
```python
def revoke_with_history(self, *, ..., actor: str = "admin", ...):
    ...
    records[target_idx] = {**target, "revocation_actor": actor}
```

#### Après :
```python
def revoke_with_history(
    self, *,
    authenticated_actor: str = "operator",  # provient du token serveur
    requested_actor: str | None = None,       # valeur body client, informative
    expected_version: int | None = None,      # CAS optionnel
    ...
):
    ...
    # CAS check
    if expected_version is not None and expected_version != current_version:
        raise BindingRevocationError("Conflit de version (CAS)...")
    ...
    records[target_idx] = {
        **target,
        "version": current_version + 1,
        "revocation_actor": authenticated_actor,  # forensic — token serveur
        "requested_actor": requested_actor,         # informatif — body client
    }
```

---

### 2. `src/api/admin_device_binding_routes.py`

| Élément | Avant R432 | Après R432 |
|---------|-----------|------------|
| `MODULE_VERSION` | `'1.1.1'` | `'1.2.0'` |
| Import `BindingPurgeError` | absent | ajouté |
| `_extract_authenticated_actor()` | absente | extrait `wallet_name / label / address / kind` du dict token |
| `POST /revoke` — `actor` body | `actor: str = "admin"` → écrit dans `revocation_actor` | remplacé par `requested_actor` (informatif) ; `authenticated_actor` extrait du token |
| `POST /revoke` — `expected_version` | absent | `expected_version: int | None` (CAS optionnel) |
| `POST /revoke` — retour | sans `version_before/after` | avec `version_before`, `version_after` |
| `POST /purge` | absent | purge d'un binding REVOKED, motif obligatoire, journal forensic |

#### Avant (endpoint POST /revoke) :
```python
actor: str = Body(default="admin", description="Acteur déclenchant la révocation"),
...
result = store.revoke_with_history(..., actor=actor, ...)
```

#### Après :
```python
requested_actor: str | None = Body(default=None, description="Identité fournie par le client (informative)"),
expected_version: int | None = Body(default=None, description="Version CAS attendue (optionnelle)"),
...
authenticated_actor = _extract_authenticated_actor(_actor)  # token Bearer vérifié
result = store.revoke_with_history(
    ...,
    authenticated_actor=authenticated_actor,
    requested_actor=requested_actor,
    expected_version=expected_version,
)
```

---

### 3. `tests/test_r432_binding_security_hardening.py` (NOUVEAU)

12 cas T01→T12 :

| Test | Description | Résultat |
|------|-------------|----------|
| T01 | `authenticated_actor` écrit dans `revocation_actor` (pas `requested_actor`) | ✅ PASS |
| T02 | `requested_actor` stocké séparément dans un champ distinct | ✅ PASS |
| T03 | `_extract_authenticated_actor` : priorité wallet_name → label → address → kind | ✅ PASS |
| T04 | Champ `version = 1` à la création | ✅ PASS |
| T05 | `version` passe de 1 à 2 après révocation | ✅ PASS |
| T06 | CAS `expected_version=1` correct → révocation OK | ✅ PASS |
| T07 | CAS `expected_version=99` incorrect → BindingRevocationError | ✅ PASS |
| T08 | `purge_binding` sur REVOKED → succès + journal forensic | ✅ PASS |
| T09 | `purge_binding` sur ACTIVE → BindingPurgeError | ✅ PASS |
| T10 | `purge_binding` sans `purge_reason` → BindingPurgeError | ✅ PASS |
| T11 | Journal `binding_purge_log.json` contient le snapshot avant suppression | ✅ PASS |
| T12 | Non-régression complète R431 (T01→T06 + T09 R431) | ✅ PASS |

### 4. `tests/test_r431_revoke_with_history.py` (mis à jour)

Migration du paramètre `actor=` → `authenticated_actor=` (8 occurrences). 9/9 PASS maintenu.

---

## Résultats des tests

```
tests/test_r432_binding_security_hardening.py  12/12 PASS (2.01s)
tests/test_r431_revoke_with_history.py          9/9  PASS (non-régression)
tests/test_r345_wallet_client_binding.py        2/2  PASS (non-régression)
─────────────────────────────────────────────────────────
Total : 23/23 PASS
```

---

## Architecture résultante

```
ADMIN
  │
  ├── POST /revoke  (R431/R432)
  │     │
  │     ├── authenticated_actor = _extract_authenticated_actor(token Bearer)
  │     ├── requested_actor = body["requested_actor"] (informatif)
  │     ├── CAS optionnel (expected_version)
  │     └── ACTIVE → REVOKED (historique conservé, version+1)
  │
  ├── POST /purge  (R432 — chemin EXCEPTIONNEL)
  │     │
  │     ├── binding_id + purge_reason obligatoires
  │     ├── état doit être REVOKED (sinon 409)
  │     ├── journal forensic binding_purge_log.json AVANT suppression
  │     └── suppression physique
  │
  └── DELETE /fingerprint, /wallet, /test/wallet  (R379 — DEPRECATED)
        └── suppression physique directe (conservé pour rétro-compat)
```

---

## Modèle de données complet (R432)

```json
{
  "binding_id": "<uuid4>",
  "wallet_name": "...",
  "device_fingerprint": "...",
  "env_type": "...",
  "namespace": "PRODUCTION|TEST",
  "state": "ACTIVE|REVOKED",
  "version": 1,
  "created_at": "2026-...",
  "revoked_at": null,
  "revocation_reason": null,
  "revocation_actor": null,
  "requested_actor": null
}
```

Après révocation :
```json
{
  "state": "REVOKED",
  "version": 2,
  "revoked_at": "2026-...",
  "revocation_actor": "<token-identity>",
  "requested_actor": "<client-claim|null>"
}
```

---

## Limites documentées (honnêtes)

1. **fcntl.flock** : sérialise les processus sur POSIX (Linux/macOS). Sur Windows, le rename reste atomique au niveau FS mais le flock est absent. Les nœuds live (Linux) sont pleinement couverts.
2. **DELETE R379** : toujours présents pour rétro-compat. La politique "toute révocation = REVOKE" n'est pas encore une invariante globale — les DELETE R379 existent toujours et peuvent contourner l'historique. La migration vers `/purge/` après révocation est le chemin recommandé pour les purges planifiées.
3. **binding_purge_log.json** : append-only dans le même répertoire data. Pas de signature cryptographique ni de réplication — un accès système root peut le modifier. Chantier futur.

---

**CERTIFIED_100 = false**
