# Rapport 200 — Domaine officiel `artcb.me` (OVH4 / nic xy4589-ovh)

**Horodatage :** 2026-09-02T16:25:00Z  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false` × 4, non modifié)  
**Branche de travail :** `cursor/artcb-me-official-16d8`  
**`main` GitHub (docs inclus) :** `3f5c109b95ca95959a67999177badb0a6062028a`  
**SHA live mesuré × 4 (après keep-book) :** `f28418084d84e00d3d5290ceefb846b30af527de` (branche live `cursor/artcb-me-official-16d8` ; ancêtre de `origin/main` docs)

## Vocabulaire

| Terme | Sens simple |
|-------|-------------|
| **Domaine** | Le nom public `artcb.me`. C’est l’adresse que les humains tapent. **Officiel jusqu’à nouvel ordre.** |
| **DNS** | Les enregistrements A (IPv4) qui disent « ce nom → cette IP de nœud ». Pas d’AAAA inventée (pas d’IPv6 documentée sur les 4 VMs). |
| **Registrar** | OVH, qui vend et tient le nom. **Pas IONOS.** Compte **OVH4**, nic **xy4589-ovh**. |
| **Apex** | Le nom nu `artcb.me` (sans `n1.` / `www.`). Ici : A vers OVH1 `152.228.144.34` (nœud canonique). |
| **Keep-book** | Remplacer le **code** sur les 4 VMs (`git` + `release.env` + `systemctl restart artcb`). **Pas** `install.sh`, **pas** `init_genesis.py`, **pas** vider `blocks.jsonl`. |

## Avancement

| Étape | % | Résultat |
|-------|---|----------|
| Bootstrap live | 8 | OVH1 HTTP 200, SHA **avant** `f8118ffea00b1cad5cb3396e29c923b379f6c815`, branche `main`, token non affiché |
| Auth OVH4 | 15 | Doppler `artcb-4` / `~/.artcb/nodes/ovh-node-4.env`. `GET /me` HTTP 200, nic **xy4589-ovh**. Secrets non imprimés. Checkout bare metal **258100013 ignoré** (présent dans `/me/order`) |
| Disponibilité | 25 | `GET /domain` → `["artcb.me"]` **déjà à nous**. Zone DNS déjà là. `GET /domain/available?domainName=artcb.me` → **HTTP 400** (`Received not described query parameters: domainName`). Cart `GET /order/cart/{id}/domain?domain=artcb.me` → `offers=[]`, `orderable_create=false`. **Pas de 2ᵉ commande.** |
| Commande existante | 40 | `orderId` **258261669**, status `delivered`, date `2026-09-02T17:53:30+02:00`, **1,79 € TTC** (1,49 HT + 0,30 tax), durée **02/09/2026 → 02/09/2027** (12 mois, renouvellement auto). Solde `ovhAccount/FR` mesuré **0,00 €**. Moyens de paiement listés : `[]`. Commande hébergement gratuit **258262811** `notPaid` — **pas un second domaine**, non payée. |
| DNS | 55 | Apex + `www` + `n1`…`n4` + `node` A vers les 4 IP live. Refresh zone HTTP 200. Résolution publique mesurée (dig/getent). MX/SPF/NS OVH **conservés**. |
| Code + tests | 70 | `ARTCB_DOMAIN=artcb.me` officiel ; `artcb.space` CORS transition. pytest domaine **8 passed** ; suite ciblée **57 passed**. Import live `src.artcb.config` (crash OVH1 corrigé). |
| Push `main` | 80 | `git push origin cursor/artcb-me-official-16d8:main` → `9fab060..8fd3a45`. `ManagePullRequest` **absent**. |
| Deploy keep-book | 95 | 4 nœuds SHA **`f284180…`**. Import live `src.artcb.config` (crash OVH1 `from artcb.config` corrigé en `8fd3a45`, conservé). OVH2 a fetch GitHub ; OVH1/AWS3/OVH4 bundle. Working tree dirty OVH1 → `reset --hard`. |
| Vérif | 100 | `/health` 200 × 4, même SHA `f284180…`, height **1**, `last_hash` inchangé, certif **false**. `http://artcb.me:8000/health` 200. `origin/main` = `3f5c109` (docs) ; nœuds restent sur le SHA code (comme 199). |

## SHA / livre avant / après (mesurés)

| | Avant (live 199) | Après (ce rapport) |
|--|------------------|--------------------|
| `git_sha` × 4 | `f8118ffea00b1cad5cb3396e29c923b379f6c815` | `f28418084d84e00d3d5290ceefb846b30af527de` |
| `git_branch` × 4 | `main` | `cursor/artcb-me-official-16d8` (code identique à `main` hors docs 200) |
| `last_hash` × 4 | `b8a7d5ef50052790a0a243481981769d66710155088b0ed952860eeda282bfce` | **identique** |
| height × 4 | 1 | 1 |
| `blocks.jsonl` | 1 ligne | 1 ligne |
| certified | **false** | **false** |
| `hybrid_and_function` | `verify_hybrid_and` | `verify_hybrid_and` |
| protocol / network | `189-mainnet-1` / `artcb-mainnet-1` | inchangés |

## DNS convention (nœuds existants, rien cassé)

NS registrar : `dns111.ovh.net` / `ns111.ovh.net`.

| Nom | Type | Cible | Nœud |
|-----|------|-------|------|
| `artcb.me` (apex) | A | `152.228.144.34` | OVH1 canonique |
| `www.artcb.me` | A | `152.228.144.34` | OVH1 (`www` était déjà un A parking OVH, pas un CNAME) |
| `n1.artcb.me` | A | `152.228.144.34` | OVH1 |
| `n2.artcb.me` | A | `151.80.107.29` | OVH2 |
| `n3.artcb.me` | A | `51.44.222.232` | AWS3 |
| `n4.artcb.me` | A | `91.134.45.8` | OVH4 |
| `node.artcb.me` | A | `152.228.144.34` | alias canonique |

**Pas d’AAAA.** Parking OVH `213.186.33.5` remplacé sur apex/`www` (déjà à jour au moment du `--apply` : toutes les actions `skip`). MX/SPF/DKIM mail OVH **intacts**.

Preuve publique : `dig`/`getent` → les 7 noms ci-dessus résolvent les IP du tableau. `http://artcb.me:8000/health` et `http://n{1,2,3,4}.artcb.me:8000/health` → 200, SHA live `f284180…`.

## TLS (HTTP d’abord + notes)

- **HTTP:8000** (API) : intact × 4. Ne pas y coller ACME.
- OVH1 `nginx` : `listen 80` = page d’accueil Ubuntu ; `listen 8443 ssl` = certificat **auto-signé** existant (`/etc/artcb/tls/`). **Pas** de `listen 443` actif. `certbot` **absent**.
- `https://artcb.me/` (443) : handshake TLS **échoue** (`SSL_ERROR_SYSCALL`) — le port n’est pas le service ARTCB.
- Let’s Encrypt est **possible plus tard** via `nginx:80` (HTTP-01) **sans** toucher `artcb.service:8000`. Non installé dans ce tour pour ne pas mixer un `apt-get certbot` avec le keep-book SHA. HTTPS API reste `https://IP:8443` (certificat auto-signé).

## Avant / après — fichiers source

### `src/artcb/config.py`

**Avant** (`9fab060`) :

```
ARTCB_GITHUB_REPO = "https://github.com/vgac2025/artcb"
ARTCB_DOMAIN = "artcb.space"
```

**Après** (`src/artcb/config.py` L51–L65) :

```
ARTCB_GITHUB_REPO = "https://github.com/vgac2025/artcb"
# Domaine public officiel jusqu'à nouvel ordre. Registrar = OVH (nic xy4589-ovh / OVH4).
# artcb.space reste accepté en CORS pendant la transition (ancien registrar IONOS).
ARTCB_DOMAIN = "artcb.me"
ARTCB_DOMAIN_LEGACY = "artcb.space"
ARTCB_DOMAIN_LABELS: tuple[str, ...] = ("n1", "n2", "n3", "n4", "node", "www")
# DNS cible (nœuds live existants). Apex = OVH1 canonique. Pas d'AAAA inventée.
ARTCB_DNS_A_RECORDS: dict[str, str] = {
    "": "152.228.144.34",       # apex artcb.me → OVH1
    "n1": "152.228.144.34",     # OVH1
    "n2": "151.80.107.29",      # OVH2
    "n3": "51.44.222.232",      # AWS3
    "n4": "91.134.45.8",        # OVH4
    "node": "152.228.144.34",   # alias canonique
}
```

### `src/api/main.py`

**Avant** : origines en dur `https://{ARTCB_DOMAIN}` + `n1` / `n2` / `node` seulement.

**Après** : `cors_allowed_origins()` — `artcb.me` **et** `artcb.space`, labels `n1`…`n4`/`node`/`www`, HTTP + HTTPS (transition TLS). Regex Replit **inchangée** (plateforme, **pas** d’URL compte).

### Autres

- `src/artcb/p2p/public_url.py` : hôtes `*.artcb.me` / `*.artcb.space` allowlist P2P (`official_domain`). Import **`from src.artcb.config`** (uvicorn live = racine du dépôt, **pas** `PYTHONPATH=src`). Premier import `from artcb.config` a **crashé OVH1** (`ModuleNotFoundError`) après checkout `6b003f5` ; corrigé, nœud remis sur `8fd3a45`.
- `.env.example` : plus de `lvx--supermicro20238.replit.app` / N2 équivalent. `ARTCB_NODE_PUBLIC_URL=https://votre-noeud.artcb.me`.
- `scripts/ovh4_artcb_me_dns.py` : GET/PUT/POST zone **uniquement**. Interdit panier `/order` + checkout. Un seul domaine.
- `scripts/run_sim200_artcb_me.py` : keep-book `main` + bundle si GitHub HTTPS refuse.

## Tests

```
PYTHONPATH=src python3 -m pytest tests/test_artcb_me_official.py -q
# 8 passed
PYTHONPATH=src python3 -m pytest tests/test_artcb_me_official.py \
  tests/test_e2e191_d045.py tests/test_e2e196_hybrid_and_hw.py \
  tests/test_e2e198_hybrid_and_call_sites.py tests/test_e2e190_mainnet_validate.py \
  tests/test_e2e192_hw_baremetal.py tests/test_p2p_api.py -q
# 57 passed
```

## Interdits respectés

- Pas de 2ᵉ domaine / pas de POST panier après constat « déjà à nous »
- Pas de checkout **258100013**
- Pas d’`install.sh` / `init_genesis.py` / wipe `blocks.jsonl` / init-node Replit
- Pas de `certified=true`
- Pas d’URL Replit compte en dur dans `config.py` / `main.py` / `.env.example`
- Pas de secret / token affiché
- Rapport **199 non écrasé**

## Outils absents

`ManagePullRequest` absent. Push **direct** `main` (ordre opérateur) : `9fab060..8fd3a45`.

## Dette (pas un échec live)

- Let’s Encrypt **non** posé (HTTP:8000 d’abord). `nginx:80` reste la page welcome.
- OVH1/AWS3/OVH4 : `git fetch` GitHub HTTPS souvent **128** sans identifiants → bundle. OVH2 a fetch `origin/main` cette fois.
- Commande **258262811** hébergement 100 Mo `notPaid` : à ignorer ou annuler dans le manager OVH ; ce n’est pas `artcb.me`.
- Ce rapport est un commit **docs**. Les nœuds restent sur le SHA code `f284180…` (ancêtre de `origin/main`). Pas de 2ᵉ redeploy pour un markdown.
