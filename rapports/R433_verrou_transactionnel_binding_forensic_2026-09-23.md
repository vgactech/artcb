# R433 — Verrou transactionnel binding, élimination DELETE legacy, journal forensic enchaîné

**Date :** 2026-09-23  
**Module :** `src/artcb/security/wallet_device_binding.py` + `src/api/admin_device_binding_routes.py`  
**Tâche :** TASK-001-BIOMETRIE-SUITE — suite R432  
**Statut :** ✅ DONE — 38/38 tests PASS  
**CERTIFIED_100 :** false

---

## Contexte

R432 avait introduit l'écriture atomique (tmp + rename + flock sur le `.tmp`) mais laissait une fenêtre de **lost-update** : le `fcntl.LOCK_EX` était pris sur le fichier `.tmp`, relâché avant le `rename()`. Deux processus pouvaient donc exécuter READ en parallèle, puis écraser chacun le résultat de l'autre.

De plus, les trois méthodes `admin_revoke_*` R379 effectuaient encore une suppression physique directe, contournant le chemin R431/R432 (`revoke_with_history` + `purge_binding`). Le journal forensic `binding_purge_log.json` n'était pas cryptographiquement enchaîné.

---

## Chantiers réalisés

### R433-A — Verrou transactionnel (`_transactional_lock`)

**Avant (R432) :**
```python
# src/artcb/security/wallet_device_binding.py — _write_atomic()
tmp = target.with_suffix(".tmp")
with tmp.open("wb") as fh:
    fcntl.flock(fh, fcntl.LOCK_EX)   # verrou sur .tmp uniquement
    fh.write(payload)
    fh.flush()
    os.fsync(fh.fileno())
tmp.rename(target)   # ← verrou déjà relâché ici
```

**Après (R433) :**
```python
@staticmethod
@contextlib.contextmanager
def _transactional_lock(target: Path):
    """Verrou exclusif POSIX sur <target>.lock — couvre READ→CAS→WRITE."""
    lock_path = target.with_suffix(".lock")
    lock_fh = lock_path.open("a")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_fh, fcntl.LOCK_UN)
        lock_fh.close()
```

Les méthodes `check_and_bind`, `_check_and_bind_test`, `revoke_with_history` et `purge_binding` enveloppent maintenant la séquence complète READ→sélection→CAS→mutation→WRITE dans un bloc `with self._transactional_lock(registry_path)`.

**Garantie :** deux processus concurrents ne peuvent pas exécuter ces séquences simultanément sur le même registre.

---

### R433-B — Élimination des DELETE legacy (`BindingLegacyDeleteError`)

**Avant (R432) :**
```python
# admin_revoke_by_wallet() — suppression physique directe
records = self._read()
to_remove = next((r for r in records if r["wallet_name"] == wallet_name), None)
updated = [r for r in records if r["wallet_name"] != wallet_name]
self._write(updated)
return to_remove
```

**Après (R433) :**
```python
def admin_revoke_by_wallet(self, wallet_name: str) -> dict | None:
    raise BindingLegacyDeleteError(
        "admin_revoke_by_wallet() est éliminé (R433). "
        "Utiliser revoke_with_history() + purge_binding() à la place."
    )
```

Idem pour `admin_revoke_by_fingerprint()` et `admin_revoke_test_by_wallet()`.

---

### R433-C — Routes DELETE → HTTP 410 Gone

**Avant (R432) :**
```python
# DELETE /fingerprint/{fingerprint} — suppression réelle, HTTP 200
removed = store.admin_revoke_by_fingerprint(fingerprint)
return {"ok": True, "revoked": removed, ...}
```

**Après (R433) :**
```python
# DELETE /fingerprint/{fingerprint} — HTTP 410 Gone
try:
    store.admin_revoke_by_fingerprint(fingerprint)
except BindingLegacyDeleteError as exc:
    raise HTTPException(
        status_code=410,
        detail={"code": "legacy_delete_removed", "message": str(exc),
                "migration": "POST /api/v1/admin/device-binding/revoke"},
    ) from exc
```

Les trois endpoints DELETE retournent maintenant HTTP **410 Gone** avec un message de migration vers POST `/revoke`.

---

### R433-D — Journal forensic enchaîné (`hash_prev` + `entry_hash`)

**Avant (R432) :**
```python
# _append_purge_log() — pas de chaîne cryptographique
existing.append(entry)
self._write_atomic(log_path, existing)
```

**Après (R433) :**
```python
# hash_prev = entry_hash de l'entrée précédente (ou "genesis")
hash_prev = existing[-1].get("entry_hash", "genesis") if existing else "genesis"

entry_with_chain = {**entry, "hash_prev": hash_prev}
entry_raw = json.dumps(entry_with_chain, sort_keys=True, ...)
entry_hash = hashlib.sha256(entry_raw.encode("utf-8")).hexdigest()
entry_with_chain["entry_hash"] = entry_hash
```

**Invariant :** `entry[n].hash_prev == entry[n-1].entry_hash` — toute altération rétroactive rompt la chaîne.

L'appel `_append_purge_log` est lui-même sous `_transactional_lock(log_path)`.

---

## Fichiers modifiés

| Fichier | Nature | Avant | Après |
|---------|--------|-------|-------|
| `src/artcb/security/wallet_device_binding.py` | Code | `MODULE_VERSION='1.2.x'` | `MODULE_VERSION='1.3.0'` |
| `src/api/admin_device_binding_routes.py` | API | `MODULE_VERSION='1.2.1'` | `MODULE_VERSION='1.3.0'` |
| `tests/test_r433_transactional_binding.py` | Tests | ❌ absent | ✅ 15 tests |
| `tests/test_r431_revoke_with_history.py` | Tests | T09 testait DELETE R379 | T09 teste BindingLegacyDeleteError |
| `tests/test_r432_binding_security_hardening.py` | Tests | T12 testait DELETE R379 | T12 teste BindingLegacyDeleteError |

---

## Résultats des tests

### Nouveaux tests R433 — 15/15 PASS

| Test | Description | Résultat |
|------|-------------|---------|
| T-LOCK-01 | `_transactional_lock()` acquiert et relâche sans deadlock | ✅ |
| T-LOCK-02 | Deux registres distincts — verrous indépendants | ✅ |
| T-CAS-01 | Bind concurrent (2 processus, même fp) → 1 seul ACTIVE | ✅ |
| T-CAS-02 | Révocation concurrente → premier gagne, second BindingRevocationError | ✅ |
| T-CAS-03 | Purge concurrente → un seul purge_id, l'autre erreur | ✅ |
| T-CAS-04 | 5 processus bind même (wallet, fp) → idempotent, 1 enregistrement | ✅ |
| T-CAS-05 | CAS expected_version=1 sous contention → conflit détecté | ✅ |
| T-LEGACY-01 | `admin_revoke_by_fingerprint()` → `BindingLegacyDeleteError` | ✅ |
| T-LEGACY-02 | `admin_revoke_by_wallet()` → `BindingLegacyDeleteError` | ✅ |
| T-LEGACY-03 | `admin_revoke_test_by_wallet()` → `BindingLegacyDeleteError` | ✅ |
| T-FORENSIC-01 | Première entrée → `hash_prev="genesis"` + `entry_hash` valide | ✅ |
| T-FORENSIC-02 | `entry[1].hash_prev == entry[0].entry_hash` | ✅ |
| T-FORENSIC-03 | Altération entrée[0] → hash_prev rompt la chaîne | ✅ |
| T-FORENSIC-04 | `entry_hash` reproductible depuis le contenu | ✅ |
| T-FORENSIC-05 | `list_purge_log()` expose `hash_prev` et `entry_hash` | ✅ |

### Non-régression — 23/23 PASS

| Suite | Tests | Résultat |
|-------|-------|---------|
| `test_r431_revoke_with_history.py` | 9/9 | ✅ |
| `test_r432_binding_security_hardening.py` | 12/12 | ✅ |
| `test_r345_wallet_client_binding.py` | 2/2 | ✅ |

**Total : 38/38 PASS**

---

## Limites documentées

- `_transactional_lock` utilise `fcntl.flock` — POSIX uniquement (Linux/macOS). Sur Windows : best-effort (pas de verrou, mais le `rename` reste atomique au niveau FS).
- La chaîne forensic est append-only logiquement — rien n'empêche un attaquant avec accès FS de réécrire le fichier JSON entièrement. Pour une garantie forte, il faudrait un journal en append physique ou un stockage immuable.
- Les tests de concurrence T-CAS-01→04 utilisent `multiprocessing` avec des timeouts de 10s — suffisants pour des tests unitaires locaux mais pas une garantie sous charge réelle.
- `CERTIFIED_100=false` — les validations DV-* live restent à jouer.

---

## Chantiers suivants

- **R434** : `reasoning.py` G4 (ARTCD)
- **FAR/FRR** sur vrais capteurs biométriques
- **anti-Sybil multi-appareil** (wallet_per_human_limit)
- **TASK-006-LIVE-VALIDATION**
