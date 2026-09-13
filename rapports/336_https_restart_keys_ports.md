# R336 — Clés / ports / restart HTTPS (2026-09-13T18:39:35Z)

## Réponses directes

### 1. Clés synchronisées / renouvelées / révoquées ?

**Partiel — pas « une bonne fois pour toutes » encore.**

| Étape | Fait ? |
|-------|--------|
| Doppler `artcb-2`/`artcb3`/`artcb-4` avaient `ARTCB_API_KEY` | **Oui** (étaient vides → provisionnés R335) |
| Alignement **prd = dev** (VMs = `DOPPLER_CONFIG=dev`) | **Oui** ce tour |
| Cache local `~/.artcb/nodes/*.env` | **Oui** (mode 0600) |
| VMs chargent la nouvelle clé en mémoire | **NON prouvé** (Bearer direct encore 401 après follow-main) |
| Révocation des anciennes | **NON** — règle : ne révoquer qu’après test non-bloquant ; anciennes inconnues sans SSH |

Cause probable restante : token Doppler **sur la VM** (`/etc/artcb/doppler.env`) invalide / mauvais projet, ou fallback `.env` sans la clé. Invisible sans console.

### 2. Pourquoi pas « une porte libre » à la place de :22 ?

Mesure LAN ce tour :

```
ovh1/2/aws3/ovh4 : OPEN = [80, 443] seulement
:22 :2222 :8000 :8443 :8022 … = CLOSED
```

Une « porte libre » **n’écoute pas toute seule**. Pour SSH sur :2222 il faudrait déjà : ouvrir firewall + démarrer `sshd` sur ce port = **accès console/SSH** (cercle).  
Les ports **occupés et utiles** sont **:80/:443** → d’où R336 : redémarrage **via HTTPS** (`/api/v1/ops/peer-restart`, `/fanout-restart`), même modèle que peer-ingest.

`:8000`/`:8443` timeout depuis LAN — filtrés, pas « disponibles ».

### 3. « Raisonnement rapide / langage rapide »

Pas un produit nommé ainsi. Dans le tour précédent je parlais de **deux chantiers parallèles** :

1. **ReasoningID** (R333→R334) — identité structurelle du raisonnement (multiset, prémisses≠conclusions)
2. **Langage IA** (C2-D / lexique) — résolution de concepts multi-hôte

« Rapide » = estimation d’avancement (~58 %) et exécution en parallèle, **pas** une couche « reasoning rapide » séparée.

### 4. Audit ChatGPT R334 collé

**D’accord** avec le verdict : R334 PASS sur fan-out / ACL chemin / ancre 1167 ; `CERTIFIED_100=false` ; 401 direct ≠ échec fan-out.

## Code R336

- `src/api/ops_routes.py` — fingerprint + self-restart + peer-restart + fanout-restart
- `scripts/artcb_r336_https_restart.py`

## Ce que tu peux me fournir pour débloquer définitivement

**Option A (recommandée, 5 min/console OVH+AWS)** — sur **chaque** VM n2/n3/n4 :

1. Confirmer `/etc/artcb/doppler.env` contient `DOPPLER_TOKEN` valide + `DOPPLER_PROJECT=artcb-2|artcb3|artcb-4` + `DOPPLER_CONFIG=dev`
2. `sudo systemctl restart artcb` (ou équivalent)
3. Me dire seulement : « restart done » (pas les secrets)

**Option B** — dans Cursor secrets d’environnement, coller les **service tokens** Doppler (noms seulement déjà connus) :
`KEY_API_ARTCB_DOPPLER_2`, `_3`, `_4` — pour que l’agent puisse re-provisionner sans CLI personal.

**Option C** — ouvrir **SSH :22** (ou :443 reverse tunnel) depuis ton LAN / security group, une fois.

**Ne pas** coller les valeurs `ARTCB_API_KEY` / `dp.st…` dans le chat.

`CERTIFIED_100=false`

## Remesure live post-deploy (`b8da76e`) — 2026-09-13T18:47:23Z

| Nœud | fingerprint match | `doppler` | publish direct |
|------|-------------------|-----------|----------------|
| ovh-node-2 | **true** sha `55fc2f1f…` | artcb-2/dev | **OK** |
| aws-node-3 | **true** sha `2f014064…` | artcb3/dev | **OK** |
| ovh-node-4 | **true** sha `6c8b8097…` | artcb-4/dev | **OK** |

`POST /api/v1/ops/fanout-restart` : n2+n3 accepted 200 (n4 était en 502 mid-deploy puis rattrapé).

`/api/v1/api-keys/me` reste 401 pour une clé **env-only** (pas dans `api_keys.json`) — **attendu**, ce n’est pas le chemin write.

**Révocation** : les projets n2–n4 étaient **vides** avant provision — pas d’ancienne `ARTCB_API_KEY` Doppler à révoquer. Ne **pas** toucher `artcb-blockchain` (clé ovh1/opérateur partagée).

HTTPS restart = la « porte » déjà ouverte (:443), pas un port inventé.
