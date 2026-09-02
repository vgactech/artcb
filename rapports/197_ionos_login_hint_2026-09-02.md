# Rapport 197 — Email de connexion IONOS pour artcb.space

**Horodatage :** 2026-09-02T14:10:00Z  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet` non modifié)  
**Branche :** `cursor/ionos-login-hint-16d8`  
**Interdits respectés :** pas de checkout OVH / `--order` / dedicated ; pas d’affichage de mot de passe / token / API key ; pas d’`install.sh` / deploy `main` / init-node Replit ; pas d’URL Replit compte en dur.

## Vocabulaire

| Terme | Sens simple |
|-------|-------------|
| **Login IONOS** | L’adresse e-mail avec laquelle on ouvre le compte client IONOS (DNS / domaine). |
| **Proxy WHOIS** | Adresse IONOS de protection RGPD, **pas** le mail du client. |
| **`--only-names`** | Liste Doppler des **noms** de clés, sans les valeurs. |

## Avancement

| Étape | % | Résultat |
|-------|---|----------|
| Bootstrap live | 15 | SHA mesuré ci-dessous ; clé présente ; token non affiché |
| Repo + git history | 40 | Pas d’email IONOS ; seulement placeholder `IONOS_API_KEY` |
| `~/.artcb` + Cursor `IONOS_*` | 55 | Aucune clé IONOS |
| Doppler 4 projets | 80 | Aucune clé `IONOS_*` |
| WHOIS / DNS public | 95 | Registrar IONOS confirmé ; mail client **redacté** |
| Docs AUTO_PROMPT 195/196 + ce rapport | 100 | Annexes ajoutées ; certif **false** |

## Live mesuré (une fois)

| Champ | Valeur |
|-------|--------|
| Health | HTTP 200 `http://152.228.144.34:8000/health` |
| API | `https://152.228.144.34:8443` |
| `git_sha` live | `30a7696a45888133b04e0ff78bbff2a9473c102f` |
| `git_branch` live | `cursor/dv01-tpm-wpp-chaos-16d8` |
| `origin/main` (fetch) | `aeb132ae5266cfb9dfdfa8e7eafd49268b726fe5` |
| SHA live == `origin/main` | **non** (pas de deploy) |
| PQC | ML-DSA-65 |
| `certified_distributed_mainnet` | **false** (non touché) |

## Email IONOS : **non trouvé**

Aucun `IONOS_EMAIL`, `IONOS_LOGIN`, `IONOS_USER` nulle part.

`IONOS_API_KEY` et `IONOS_PASSWORD` : **absents** des coffres (pas « présent »).

### Où c’est cherché (fichiers / noms de clés seulement)

| Source | Noms trouvés liés IONOS / email | Email login IONOS |
|--------|--------------------------------|-------------------|
| `.env.example` | commentaire `IONOS_API_KEY` (placeholder) | non |
| `src/artcb/config.py` | champ `ionos_api_key` ← env `IONOS_API_KEY` | non |
| `.gitignore` | `api_key_ionos.json` (fichier jamais dans git) | non |
| Commit `961d605` « rapport 116 » | DNS `artcb.space` + placeholder clé API ; **fichier rapport 116 absent** | non |
| `src/artcb/node_registry.py` | pas IONOS (emails **OVH** seulement) | non |
| `~/.artcb/nodes/ovh-node-2.env` | clés OVH / wallet (noms) — **0** IONOS | non |
| `~/.artcb/nodes/aws-node-3.env` | clés AWS — **0** IONOS | non |
| `~/.artcb/nodes/ovh-node-4.env` | clés OVH / Doppler — **0** IONOS | non |
| `~/.artcb/cursor_agent.env` | **fichier absent** | non |
| Cursor secrets | **0** `IONOS_*` (liste : `ARTCB_API_KEY`, `AWS_API_*`, `DOPPLER_TOKEN`, `KEY_API_ARTCB_DOPPLER_2`, `KEY_API_ARTCB_DOPPLER_3`, `KEY_API_STRIPE`, `OVH_*`) | non |
| Doppler `artcb-blockchain` / `dev` | **0** IONOS ; emails nommés : `GIT_USER_EMAIL`, `KAGGLE_EMAIL` | non |
| Doppler `artcb-2` / `dev` | **0** IONOS ; `OVH_CONTACT_EMAIL` | non |
| Doppler `artcb3` / `dev` | **0** IONOS | non |
| Doppler `artcb-4` / `dev` | **0** IONOS | non |

### DNS / WHOIS public (pas un coffre)

Preuve que le **registrar** est IONOS, pas l’email client :

- Registrar : **IONOS SE** (IANA 83)
- NS : `ns1089.ui-dns.com`, `ns1023.ui-dns.de`, `ns1119.ui-dns.org`, `ns1072.ui-dns.biz`
- SOA : `hostmaster.1und1.com` (contact technique IONOS, pas le client)
- SPF : `include:_spf-eu.ionos.com`
- MX : `mx00.ionos.fr` / `mx01.ionos.fr` (compte vraisemblablement **ionos.fr**)
- WHOIS registrant : **REDACTED FOR PRIVACY** ; email publié `dataprivacyprotected@ionos.de` = **proxy RGPD**, pas un login
- Pays registrant : FR ; subdivision : 75
- Expiration registre : 2027-08-07

### Emails opérateurs **non étiquetés IONOS** (ne pas les traiter comme login IONOS)

Déjà publics dans le dépôt ou le run Cursor ; **aucune** preuve qu’un de ces mails ouvre IONOS :

- `vgacofficiel@gmail.com` — owner Cursor de ce run + contact licence
- `vgac42@gmail.com` — nic OVH4 dans `node_registry.py`
- `vgac4237@gmail.com` — nic OVH2 dans `node_registry.py`
- `vgaciaofficiel@gmail.com` — `KAGGLE_EMAIL` cité rapport 105
- `artcb-mvp@hackathon.raise2026` — `GIT_USER_EMAIL` Doppler (nom de clé seulement lu ; valeur = identité git, pas IONOS)
- `contact@artcb.io` — docs / gouvernance

## Travail autonome possible sans fournisseur

Fait ici : inventaire coffres, preuve registrar, annexes AUTO_PROMPT 195/196, ce rapport, placeholder `IONOS_EMAIL` dans `.env.example`.

**Impossible sans l’opérateur :** se connecter à IONOS, lire le mail client derrière le proxy RGPD, créer `IONOS_API_KEY`, changer le DNS. L’agent n’a pas la clé API (absente).

**Pas fait (interdit) :** commande bare metal OVH, deploy `main`, `certified=true`.

## Suite opérateur

1. Essayer les Gmail ci-dessus sur [login.ionos.fr](https://login.ionos.fr) (MX `.fr`).
2. « Mot de passe oublié » IONOS si un mail est reconnu.
3. Une fois reconnecté : créer une clé sur https://developer.hosting.ionos.com/keys et poser **seulement** `IONOS_EMAIL` (et la clé API) dans Doppler — **ne pas** committer les valeurs.
