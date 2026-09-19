# R382 — Reset device binding via Doppler + SSH résolu autonome

**Date :** 2026-09-18  
**Référence :** R382  
**Commit R381 :** `3492000`  
**Statut :** ✅ RESET EFFECTUÉ — binding supprimé sur N4  
**CERTIFIED_100 :** false  
**Avancement global :** 81%

---

## Contexte

L'utilisateur a signalé que le reset du device binding aurait dû être géré **de manière autonome via Doppler**, sans demander d'action à l'utilisateur. Ce rapport documente le processus complet d'auto-résolution.

---

## Problème initial

Le binding `97a0b6403ecb4932` → `w-55fe5464a470b6ed` n'avait pas été supprimé dans R381 car :
1. SSH port 22 timeout depuis ce Mac vers tous les nœuds (port filtré)
2. Port 8000 direct filtré également
3. DNS local cassé (`artcb.me` → `172.24.16.51` IP privée)
4. L'ARTCB_API_KEY du projet local n'était pas celle du nœud hébergeant le binding

## Solution appliquée (autonome via Doppler)

### Étape 1 — Identifier le bon nœud via l'API

```
N2 (151.80.107.29) : 2 bindings PROD — fingerprint 97a0b... ABSENT
N4 (91.134.45.8)   : 5 bindings PROD — fingerprint 97a0b... PRÉSENT ✅
N3 (13.38.209.25)  : 2 bindings PROD — fingerprint 97a0b... ABSENT
```

### Étape 2 — Récupérer la clé N4 via Doppler

```bash
doppler secrets get ARTCB_API_KEY --project artcb-4 --config prd --plain
# → artcb_8cfe19fbca37448ae4b3570e0185150e056f1ea78e5b...
```

### Étape 3 — Contourner le DNS local cassé avec `--resolve`

```bash
curl -sk --resolve "artcb.me:443:91.134.45.8" \
  -X DELETE "https://artcb.me/api/v1/admin/device-binding/fingerprint/97a0b6403ecb49329c594eaad225aafd" \
  -H "Authorization: Bearer artcb_8cfe19fbca37448ae4b3570e0185150e056f1ea78e5b..."
```

### Résultat

```json
{
  "ok": true,
  "revoked": {
    "wallet_name": "w-55fe5464a470b6ed",
    "device_fingerprint": "97a0b6403ecb49329c594eaad225aafd",
    "env_type": "client_ua_device_id_anon",
    "namespace": "PRODUCTION",
    "created_at": "2026-09-17T20:41:31Z"
  },
  "message": "Binding PRODUCTION supprimé. L'appareil peut maintenant créer un nouveau wallet.",
  "certified_100": false
}
```

**HTTP 200 ✅ — Binding supprimé.**

---

## État après reset

| Nœud | Bindings PROD restants | Cible supprimée |
|------|------------------------|-----------------|
| N2 (151.80.107.29) | 2 (vgactech2, pqc-test-ovh2) | ✅ absente |
| **N4 (91.134.45.8)** | **4** (vgactech2, pqc-test-ovh4, pqc-certif-n4, vgactech0) | **✅ supprimée** |
| N3 (13.38.209.25) | 2 (vgactech2, pqc-test-aws3) | ✅ absente |

L'utilisateur peut maintenant se réinscrire sur son appareil depuis `artcb.me`.

---

## Leçon L-050 — Méthode de reset autonome via Doppler

**Contexte :** Le reset du device binding requiert :
1. La bonne clé API (celle du nœud hébergeant le binding, pas la clé locale)
2. Le bon nœud (le binding n'est pas répliqué entre nœuds — chaque nœud a son propre fichier)
3. Contournement DNS si `artcb.me` ne résout pas correctement : `curl --resolve "artcb.me:443:<IP>"`

**Leçon :**
1. Les secrets par nœud sont dans Doppler sous `artcb-2/prd`, `artcb3/prd`, `artcb-4/prd`
2. Toujours scanner les 3 nœuds (LIST) avant de tenter le DELETE — le binding peut être sur n'importe lequel
3. SSH port 22 peut être filtré depuis le Mac → utiliser HTTPS port 443 avec `--resolve` comme fallback
4. Ne jamais demander à l'utilisateur de faire un reset qu'on peut faire soi-même via Doppler + API
5. La clé locale (`artcb-blockchain/dev`) ≠ la clé de nœud (`artcb-{N}/prd`)

**Action :** R382 — reset autonome réalisé. Méthode documentée pour les prochains resets.

---

## Procédure réutilisable (à appliquer systématiquement)

```python
# Pattern autonome de reset device binding
import subprocess

NODES = [
    ("N2", "151.80.107.29", "artcb-2"),
    ("N4", "91.134.45.8",   "artcb-4"),
    ("N3", "13.38.209.25",  "artcb3"),
]

for name, ip, project in NODES:
    key = subprocess.check_output(
        f"doppler secrets get ARTCB_API_KEY --project {project} --config prd --plain",
        shell=True, text=True
    ).strip()
    # 1. LIST pour trouver le binding
    # 2. DELETE si présent
    # 3. Utiliser --resolve "artcb.me:443:{ip}" pour contourner DNS
```

---

`CERTIFIED_100=false` | `unique_human_proven=false`
