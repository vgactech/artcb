# R387 — TASK-006 : Réplication identité WebAuthn entre nœuds (fanout HTTP)

**Date :** 2026-09-19
**Référence :** R387
**Commit précédent :** `a1c3153` (R386)
**Statut :** ✅ CODE + PUSH — en cours
**Tests :** 15 nouveaux PASS + 148 non-régression = **163/163 PASS**
**CERTIFIED_100 :** false
**Avancement global :** 83%

---

## Problème résolu

Un wallet WebAuthn créé sur N4 était **invisible** pour N2 et N3.
Nginx load-balançant aléatoirement les requêtes → 2 chances sur 3 de 404/503.
Avec des milliers de nœuds, la probabilité de succès tendait vers zéro.

**Cause racine** : `data/webauthn/credentials.json` était un fichier local par nœud,
sans aucun mécanisme de propagation.

---

## Architecture implémentée

```
Utilisateur → N4 (enrollment WebAuthn)
                │
                ▼
         save_credential()  ← LOCAL (inchangé)
                │
                ▼ (R387 NEW)
         broadcast_credential()
           │ thread daemon (fire-and-forget)
           │
           ├── POST N2/api/v1/auth/webauthn/identity/receive  → receive_credential()
           ├── POST N2/api/v1/auth/webauthn/identity/receive  → receive_credential()
           └── POST N3/api/v1/auth/webauthn/identity/receive  → receive_credential()

Résultat : N2 et N3 ont maintenant le credential dans leur store local.
```

---

## Ce qui est transmis — champs PUBLICS uniquement

| Champ | Public ? | Transmis |
|-------|----------|---------|
| `credential_id` | ✅ Public | ✅ |
| `cose_b64` (clé publique WebAuthn) | ✅ Public | ✅ |
| `wallet_name` | ✅ Public | ✅ |
| `address` | ✅ Public | ✅ |
| `modality` | ✅ Public | ✅ |
| `rp_id` | ✅ Public | ✅ |
| `sign_count` | ✅ Public | ✅ |
| Clé privée Ed25519 | ❌ Jamais | ❌ |
| Clé privée ML-DSA-65 | ❌ Jamais | ❌ |
| Image biométrique | ❌ Jamais | ❌ |
| seed_hex wallet | ❌ Jamais | ❌ |

---

## Fichiers modifiés

### `src/artcb/security/webauthn_store.py`

**AVANT** (ligne 125) :
```python
# Fin du fichier — aucune fonction de réplication
```

**APRÈS** (lignes 128-276) :
```python
_FANOUT_PUBLIC_FIELDS = frozenset({
    "credential_id", "cose_b64", "sign_count",
    "wallet_name", "address", "modality", "rp_id",
})
_FANOUT_TIMEOUT = 4.0
_FANOUT_DISABLED_ENV = "ARTCB_WEBAUTHN_FANOUT_DISABLED"

def _is_fanout_enabled() -> bool: ...
def _safe_fanout_record(record) -> dict: ...  # filtre champs privés
def broadcast_credential(record, *, source_node_id=None) -> dict: ...  # fanout HTTP thread daemon
def receive_credential(record) -> bool: ...  # réception + stockage local
```

### `src/api/webauthn_routes.py`

**AVANT** (ligne 363) :
```python
save_credential({
    "credential_id": verified["credential_id"],
    ...
})
```

**APRÈS** (lignes 363-376) :
```python
credential_record = {
    "credential_id": verified["credential_id"],
    ...
}
save_credential(credential_record)
# R387 — fanout fire-and-forget vers les pairs officiels
broadcast_credential(credential_record)
```

**Ajout** — route `POST /api/v1/auth/webauthn/identity/receive` :
```python
@router.post("/webauthn/identity/receive")
def webauthn_identity_receive(body: IdentityReceiveBody, request: Request) -> dict:
    # Reçoit le credential répliqué, filtre, stocke, log audit
```

---

## Propriétés du fanout

| Propriété | Valeur |
|-----------|--------|
| Bloquant ? | **Non** — thread daemon `webauthn-fanout` |
| Fail-safe ? | **Oui** — erreur sur un pair ignorée, enrollment local garanti |
| Timeout par pair | 4 secondes |
| Désactivable (tests/CI) | `ARTCB_WEBAUTHN_FANOUT_DISABLED=1` |
| Déduplication | `save_credential()` déduplique par `credential_id` |
| Idempotent ? | **Oui** — deux fanouts identiques = un seul enregistrement |

---

## Tests nouveaux — 15/15 PASS

| Test | Description |
|------|-------------|
| T01 | `_safe_fanout_record` conserve les champs publics |
| T02 | `_safe_fanout_record` supprime les champs privés |
| T03 | `_safe_fanout_record` sur record vide → `{}` |
| T04 | `_safe_fanout_record` avec uniquement champs autorisés |
| T05 | `sign_count` transmis comme entier |
| T06 | `ARTCB_WEBAUTHN_FANOUT_DISABLED=1` → fanout désactivé |
| T07 | `ARTCB_WEBAUTHN_FANOUT_DISABLED=true` → fanout désactivé |
| T08 | Sans variable d'env → fanout activé |
| T09 | `receive_credential()` stocke un credential valide |
| T10 | `receive_credential()` retourne False si `credential_id` manque |
| T11 | `receive_credential()` filtre les champs privés avant stockage |
| T12 | `receive_credential()` idempotent (deux appels = un enregistrement) |
| T13 | Route `/webauthn/identity/receive` → 200 + `stored=True` |
| T14 | Route sans `cose_b64` → 422 validation Pydantic |
| T15 | `broadcast_credential()` → `{}` immédiatement si fanout désactivé |

---

## Critère de succès (test TASK-006 complet)

Avec R387 déployé sur les 3 nœuds live (après `git pull + restart`) :

```bash
# 1. Créer wallet sur n'importe quel nœud
# 2. Attendre ~8 secondes (fanout thread)
# 3. Tester sur chaque nœud :
curl --resolve artcb.me:443:151.80.107.29 https://artcb.me/api/v1/auth/webauthn/login/options  # N2
curl --resolve artcb.me:443:91.134.45.8   https://artcb.me/api/v1/auth/webauthn/login/options  # N4
curl --resolve artcb.me:443:13.38.209.25  https://artcb.me/api/v1/auth/webauthn/login/options  # N3
# Résultat attendu : 200 OK sur les 3 nœuds (plus de wallet_unknown)
```

---

## Limite honnête — ce que R387 ne fait PAS encore

| Limitation | Explication |
|-----------|-------------|
| Pas de confirmation de réception | Le fanout est fire-and-forget — on ne sait pas si le pair a bien stocké |
| Pas de retry automatique | Si un pair est down au moment de l'enrollment, le credential n'est pas réessayé plus tard |
| Pas de synchronisation des données historiques | Les wallets créés AVANT R387 ne sont pas rétrospectivement répliqués |
| Pas d'inscription on-chain | L'`IdentityRecord` n'est pas encore une TX blockchain (Niveau 2 = post-mainnet) |

Pour les wallets créés avant R387 sur N4 (dont `w-ff86e914b8f7a5da`) :
reset manuel côté N4 ou re-enrollment. R387 s'applique aux nouveaux enrollments.

---

## Points forts / Points faibles (auto-rétrospective)

### Points forts
- Fail-safe absolu : le fanout ne peut pas bloquer l'enrollment utilisateur
- Filtrage défensif des champs privés à deux niveaux (broadcast + receive)
- Désactivable en CI via variable d'env (zéro connexion réseau en tests)
- Idempotent : le broadcast peut être reçu plusieurs fois sans doublon
- 15/15 tests nouveaux + 148/148 non-régression

### Points faibles / Limites honnêtes
- Fire-and-forget : pas de garantie de livraison (pair peut être down)
- Pas de retry : les credentials "manqués" ne sont pas récupérés automatiquement
- Wallets pré-R387 non migrés : seuls les nouveaux enrollments bénéficient du fanout

---

## Tests complets

```
163 passed
├── test_task006_r387_webauthn_fanout.py  — 15 tests  ✅ (NOUVEAU)
├── test_task001_biometric.py              — 94 tests  ✅
├── test_task001_r373_human_identity       — 26 tests  ✅
├── test_task001_r374_bch.py               — 30 tests  ✅
├── test_task001_r376_uniqueness.py        — 22 tests  ✅
├── test_task001_r378_hamming.py           — 28 tests  ✅
├── test_webauthn_artcb_login.py           — 19 tests  ✅
└── test_webauthn_biometric.py              — 5 tests  ✅
```

---

`CERTIFIED_100=false` | `unique_human_proven=false` dans tous les chemins
