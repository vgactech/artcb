# Rapport 204 — Nœud 4 : expliquer les 2 secrets (pas les coller)

**Horodatage UTC :** 2026-09-02T19:45:00Z  
**Branche :** `cursor/explain-ovh4-secrets-8124`  
**Live OVH1 `/health.git_sha` :** `ad017bca05c2e3799c7dcd120ca1797968d499b6` = `origin/main`  
**Certification :** **NOT MAINNET CERTIFIED**

Aucun token, PEM, Application Secret, Consumer Key n’est reproduit ici.

---

## Pourquoi ce rapport

L’opérateur a mis à jour Doppler `artcb-4` (clés OVH) comme demandé, puis a
répondu qu’il **ne comprenait pas** d’où sortent `KEY_API_ARTCB_DOPPLER_4` et
`SSH_PRIVATE_KEY` — l’agent précédent les exigeait sans dire **qui les
fabrique**. Le pavé wallet / MetaMask collé dans le même message n’aidait pas.

Guide utilisateur : `docs/NOEUD_4_LES_2_SECRETS.md`.  
Règle agent : `.cursor/rules/ovh-node-4.mdc`.

---

## Mesures (cette session)

| Check | Résultat |
|-------|----------|
| Bootstrap OVH1 | health 200, key_id `kid_abad2468682059ef`, PQC ML-DSA-65 |
| `origin/main` | `ad017bca05c2e3799c7dcd120ca1797968d499b6` |
| OVH4 `http://91.134.45.8:8000/health` | **200**, `git_sha=f28418084d84e00d3d5290ceefb846b30af527de`, branch `cursor/artcb-me-official-16d8` |
| `KEY_API_ARTCB_DOPPLER_4` dans l’env agent | **absent** (pas dans `CLOUD_AGENT_ALL_SECRET_NAMES`) |
| `KEY_API_ARTCB_DOPPLER_2` / `_3` | présents ; `/v3/me` 200 (`artcb2` / `ARTCB NODE 3`) |
| `DOPPLER_TOKEN` → `artcb-4` | HTTP **400** pas d’accès |
| `_2` → `artcb-4` | HTTP **400** |
| `_3` → `artcb-4` | HTTP **400** |
| Cursor `OVH_*` `/me` | HTTP **403** « This credential does not exist » |
| Cursor `ARTCB_OVH_NODE_4` | clé **publique** = `deploy/artcb_ovh_node_4.pub` (empreinte `SHA256:LGMsEgc8sgimQVmwvPUCC7je8AT6ft4vC9lmJWcmXcc`) |
| SSH `ubuntu@91.134.45.8` clé OVH1 | `Permission denied (publickey)` |
| SSH même hôte clé Doppler `artcb-2` | `Permission denied (publickey)` (empreinte nœud 2 `SHA256:7ehKF2XDI/OayZtfi3mxO6NiHq4WIhrDjt1z6MbGNsY`) |
| PEM nœud 4 sur OVH1 `~/.ssh` | **absent** |

`artcb-2` contient maintenant un `SSH_PRIVATE_KEY` (noms listés, valeur non
imprimée). Ça n’ouvre **pas** OVH4.

---

## Qui fabrique quoi

| Nom | Qui le crée | Où il va | L’agent peut-il le donner ? |
|-----|-------------|----------|------------------------------|
| `KEY_API_ARTCB_DOPPLER_4` | **Opérateur** dans Doppler Access → Generate (`dp.st.…`) | Secrets Cursor (même tableau que `_2` / `_3`) | **Non** |
| `SSH_PRIVATE_KEY` nœud 4 | Agent **après** le token Cursor, ou déjà dans Doppler | Doppler `artcb-4` / `dev` | **Non** (jamais le chat) |
| `OVH_APPLICATION_*` / `OVH_CONSUMER_KEY` | Opérateur page OVH createToken (déjà fait) | Doppler `artcb-4` seulement | Non |

---

## Ce que cette PR ne fait pas

- Pas de SSH réussi sur OVH4 (badge Cursor toujours absent).
- Pas de keep-book `origin/main` sur `91.134.45.8`.
- Pas de rotation des clés OVH Cursor 403.
- Pas de déploiement OVH1.

Dès que l’opérateur écrit « token Cursor collé » (sans coller le token), un
agent suivant ouvre `artcb-4` et enchaîne SSH / keep-book **sans rescue**.
