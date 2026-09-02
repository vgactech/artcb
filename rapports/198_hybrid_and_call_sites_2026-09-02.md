# Rapport 198 — Câblage `verify_hybrid_and` (AND = les DEUX signatures)

**Horodatage :** 2026-09-02T14:20:00Z  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false`)  
**Branche :** `cursor/hybrid-and-call-sites-198-16d8` (base `origin/cursor/hybrid-and-hw-196-16d8`)  
**Décision :** D-051 (implémente D-034 A aux call sites, fenêtre D-032 B conservée)

## Vocabulaire

| Terme | Sens simple |
|-------|-------------|
| **AND** | Les **DEUX** signatures doivent passer : Ed25519 **et** ML-DSA-65. Une seule ne suffit pas. |
| **Jambe** | Une des deux signatures dans `hybrid:ed25519:…\|mldsa65:…`. |
| **Fenêtre D-032 B** | Ed25519 **seule** encore autorisée jusqu’au **2026-12-31T00:00:00Z**. |
| **Call site** | Endroit du code qui vérifie une signature (chaîne, groupes, gouvernance). |

## Avancement

| Étape | % | Résultat |
|-------|---|----------|
| Bootstrap live | 10 | SHA `30a7696a45888133b04e0ff78bbff2a9473c102f`, branche live `cursor/dv01-tpm-wpp-chaos-16d8`, clé présente, token non affiché |
| `origin/main` | 20 | `aeb132ae5266cfb9dfdfa8e7eafd49268b726fe5` ≠ live → **pas de déploiement main** |
| Helper AND + fenêtre | 45 | `verify_hybrid_and_or_window` : enveloppe hybride → AND des DEUX jambes ; Ed25519 seule → seulement si fenêtre ouverte ; ML-DSA seule → refus |
| Câblage chain | 60 | `verify_block_signature` → helper. Ed25519 pendant la fenêtre **OK**. Hybride sans clé PQC locale → refus (AND impossible) |
| Câblage groups | 75 | `verify_join_signature` → helper. Hybride exige `pqc_public_key_hex` (déjà le cas) |
| Câblage governance | 85 | Rotations → helper. `pqc_public_key_hex` optionnel ajouté. Sans cette clé, enveloppe hybride **refusée** (honnête) |
| Tests + rapport | 95 | pytest ciblé **50 passed** (198+196+174+178+gouvernance). Certif **false** |
| PR | 100 | branche poussée ; compare URL ci-dessous |

## Live mesuré (bootstrap, pas une matrice 4 nœuds)

| Champ | Valeur mesurée |
|-------|----------------|
| URL | `https://152.228.144.34:8443` (health HTTP 200) |
| `git_sha` | `30a7696a45888133b04e0ff78bbff2a9473c102f` |
| `git_branch` | `cursor/dv01-tpm-wpp-chaos-16d8` |
| PQC policy live | `hybrid_verify_mode=AND`, fenêtre `2026-12-31T00:00:00Z` |
| `high_value_hybrid_enforced` live | **false** |
| `hybrid_and_function` live | **absent** (live = SHA D-045, pas ce SHA) |
| `hybrid_and_call_sites_wired` live | **absent** (non déployé) |
| `certified_distributed_mainnet` | **false** |

`git_sha` live ≠ `origin/main` ≠ SHA de cette branche (`c8f87c823aaa1c0975fd853956bdd94f8a00a19d`). **Aucun** `install.sh`, **aucun** deploy `main`, **aucun** `init-node`.

## Ce qui est branché (honnête)

Les trois call sites demandés appellent `verify_hybrid_and_or_window`, qui appelle `verify_hybrid_and` dès qu’il y a une enveloppe hybride **et** une clé publique ML-DSA :

1. **chain** `verify_block_signature` — clé PQC = clé locale du nœud.
2. **groups** `verify_join_signature` — clé PQC = `pqc_public_key_hex` de la join-request.
3. **governance** `creator_key_rotation` / `user_key_rotation` — clé PQC = `pqc_public_key_hex` optionnel (API + manager).

**AND = les DEUX jambes.** Une jambe seule (Ed25519 ou ML-DSA) n’est **pas** un hybride valide.

Fenêtre D-032 **non cassée** : Ed25519 seule passe encore jusqu’au 2026-12-31. Après cette date, les call sites refusent Ed25519 seule.

`high_value_hybrid_enforced` reste **false** : les messages high-value ne sont **pas** forcés hybride tant que la fenêtre est ouverte.

`verify_hybrid()` sans `require_and` accepte encore Ed25519 seule (API legacy, tests 196). Les call sites production ne l’utilisent plus.

## Ce qui n’est pas branché (ne pas mentir)

| Surface | Pourquoi |
|---------|----------|
| `p2p/handshake.py` `verify_ed25519` | Hors des 3 call sites demandés. Carte d’identité / `peer_handshake` = **une jambe Ed25519**. `HIGH_VALUE_MESSAGES` le liste, mais le câblage 198 ne le touche pas. |
| Settlement / `node_identity` hors handshake | Pas de `verify_hybrid` existant à remplacer. |
| Live OVH1 | SHA D-045. Ce câblage **n’est pas** en production. |

Gouvernance avant 198 passait `pqc_public_key=b""` : une enveloppe hybride **échouait déjà** (AND sans clé PQC). On n’a pas prétendu le contraire. On a ajouté le paramètre pour qu’AND soit **possible** quand l’appelant fournit la clé.

## Tests

- `tests/test_e2e198_hybrid_and_call_sites.py` — 8 tests : helper AND+fenêtre, chain, groups, governance, health, CORS, certif false.
- `tests/test_e2e196_hybrid_and_hw.py` — écart « call sites absents » retiré ; `verify_hybrid()` legacy toujours Ed25519-ok.
- Cible 198+196+174+178+gouvernance : **50 passed**.
- `test_groups.py::test_store_group_visibility_and_chain_filter` : échec **préexistant** (`libartcb_chain.so` absent ici), pas le câblage AND.
- Jambe ML-DSA **mockée** (liboqs absent sur cet agent). Combineur AND prouvé.

## Interdits respectés

- Pas de commande OVH / checkout 258100013 / bare metal
- Pas de brute-force login IONOS
- Pas d’URL Replit compte en dur (regex plateforme)
- Pas d’`init-node` / `install.sh` / deploy `main`
- `certified=true` **interdit** et **non posé**
- Pas de faux TPM ; token non affiché

## PR

ManagePullRequest absent de cet environnement. Compare :

https://github.com/vgactech/artcb/compare/main...cursor/hybrid-and-call-sites-198-16d8
