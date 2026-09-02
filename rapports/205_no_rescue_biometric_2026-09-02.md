# Rapport 205 — Démarrage sans rescue + inscription biométrique www.artcb.me

**Horodatage :** 2026-09-02T19:25:00Z  
**Décision :** D-055  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false`, `OPERATOR_MAINNET_CERTIFICATION_GO=false`)

Aucun wipe. Aucun `install.sh`. Aucun disque rescue. PEM jamais collés ici.

## 1. Audit GitHub (mesuré)

| Affirmation | Réalité |
|-------------|---------|
| SHA `origin/main` au départ | `ad017bca05c2e3799c7dcd120ca1797968d499b6` |
| `certification_gate()` | AND DV-01…07 + BFT + V locked + GO opérateur ; **GO = False** |
| Tests `test_*.py` | **83** (+ `test_webauthn_biometric.py`, `test_e2e205_no_rescue_biometric.py`) |
| Rescue | **interdit** — `scripts/inject_ssh_no_rescue.py` (`FORBID_RESCUE`) |

## 2. SSH sans rescue (mesuré cette session)

`python3 scripts/load_node_ssh_keys.py` puis `python3 scripts/inject_ssh_no_rescue.py` :

| Nœud | SSH | Source PEM | Rescue |
|------|-----|------------|--------|
| OVH1 `152.228.144.34` | **oui** | env `OVH_SSH_PRIVATE_KEY` | non |
| OVH2 `151.80.107.29` | **oui** | Doppler `artcb-2` `SSH_PRIVATE_KEY` | non (`no_rescue_root=0`) |
| AWS3 `51.44.222.232` | **oui** | Doppler `artcb3` `SSH_PRIVATE_KEY` | non |
| OVH4 `91.134.45.8` | **non** | `KEY_API_ARTCB_DOPPLER_4` **absent** ; `ARTCB_OVH_NODE_4` = clé **publique** | n/a |

Password SSH OVH4 : `Permission denied (publickey)` uniquement. Hop OVH1→OVH4 : publickey denied. Console VNC OVH4 : impossible sans token Doppler `artcb-4`.

## 3. Live (mesuré, livre inchangé)

| Nœud | SHA live | branche | HTTPS |
|------|----------|---------|-------|
| OVH1 | `ad017bc` main | main | https://artcb.me/health 200 |
| OVH2 | `ad017bc` main | main | https://n2.artcb.me/health 200 |
| AWS3 | `ad017bc` main | main | https://n3.artcb.me/health 200 |
| OVH4 | `f284180` feature | `cursor/artcb-me-official-16d8` | n4 URLError ; :8000 200 |

`certified_distributed_mainnet=false` × 4. Cas B (4 SHA + TPS distribué) **toujours non**.

## 4. Biométrie (code, tests machine)

Sur `www.artcb.me` (après merge + keep-book de **cette** branche) :

- Bouton **S'inscrire par biométrie** (accueil, header, `/#/register`, page Wallets).
- **Empreinte** : WebAuthn `platform` + `userVerification=required` (capteur téléphone / Touch ID / Windows Hello).
- **Visage** : WebAuthn Face ID / déverrouillage visage OS ; à défaut caméra avant + liveness (handicap moteur).
- **Les deux** : empreinte d'abord, puis visage.
- **Aucune image brute** acceptée par l'API (`raw_biometric_rejected`). Pas d'empreinte/visage on-chain.

Tests : `tests/test_webauthn_biometric.py` (software authenticator, pas un téléphone réel).

## 5. Bloquant restant pour Cas B

Mettre dans Doppler **sans coller dans le chat** :

- secret Cursor `KEY_API_ARTCB_DOPPLER_4`
- projet `artcb-4` secret `SSH_PRIVATE_KEY` (PEM du nœud 4, **pas** la pubkey `ARTCB_OVH_NODE_4`)

Ensuite : `scripts/load_node_ssh_keys.py` + keep-book bundle (comme 203/204) + nginx `n4.artcb.me`. **Pas de rescue.**

Tant que ce n'est pas fait : **aucun TPS distribué officiel**, **aucune certif**.
