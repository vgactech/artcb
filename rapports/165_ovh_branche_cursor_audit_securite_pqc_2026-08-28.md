# Rapport 165 — Déploiement OVH depuis la branche Cursor + audit sécurité / PQC / Provider / Stripe

**Horodatage UTC :** 2026-08-28T22:12:00Z  
**Branche :** `cursor/tokenomics-21m-hbp-owner-decay-3fcb`  
**HEAD au moment du rapport :** `fc993da940f33d5ec6efda6666174aec2e10000f` (chmod scripts ; docs `ea6a173` ; code `77a5560` / `42df315`).  
**Base de départ :** `8e783631571cd853321663a43b9044123ab84d5b`  
**PR #34 :** **OUVERTE**, **non fusionnée**. Compare : https://github.com/vgactech/artcb/compare/main...cursor/tokenomics-21m-hbp-owner-decay-3fcb  
**Simulation canonique :** `simulations/20260828T220852Z_e2e165/` (`failures: []`)  
**Pytest :** `logs/20260828_pytest_rapport165_full.txt` — **606 passed, 9 skipped, 0 fail**  
**Langue :** rapport FR, code EN. DEBUG ON.  
**Ne jamais écraser** 160, 161, 162, 163, 164. Dossier 164 `simulations/20260828T200518Z_e2e164/` **conservé**.

**606 verts ≠ protocole complet. Pas d’oracle production-secure. Pas de résistance Sybil totale. Pas de certification multi-nœuds.**

---

## 0. Mission utilisateur (2026-08-28 21:54 UTC)

1. Pousser **cette** branche et mettre à jour OVH **sans** merger `main` ni PR #34.  
2. Traiter l’audit ChatGPT (A–I) **sur cette branche**.

Aucun merge `origin/main`. Aucun force-push.

---

## 1. Git / PR #34 — toujours ouverte

| Élément | Valeur |
|---------|--------|
| Branche | `cursor/tokenomics-21m-hbp-owner-decay-3fcb` |
| `main` | `0edabb66…` (inchangé, non mergé) |
| PR | https://github.com/vgactech/artcb/pull/34 — **OPEN**, `isDraft=false` |
| Compare | https://github.com/vgactech/artcb/compare/main...cursor/tokenomics-21m-hbp-owner-decay-3fcb |

**Mise à jour du body PR #34 :** l’outil `ManagePullRequest` / `update_pr` **n’est pas disponible** dans ce runtime. `gh` est **lecture seule** pour les PR. Body non modifié ici. URL compare ci-dessus.

---

## 2. OVH — résultat réel (cette branche n’est PAS live)

Public : `http://152.228.144.34:8000`  
Preuves : `logs/20260828_ovh_live_predeploy.txt`, `logs/20260828_ovh_live_postattempt.txt`

### 2.1 Push git

`git push origin cursor/tokenomics-21m-hbp-owner-decay-3fcb` — OK (plusieurs commits 165).

### 2.2 Tentatives de déploiement (ordre demandé)

| # | Action | Résultat |
|---|--------|----------|
| 1 | `git push` | OK |
| 2 | `scripts/deploy_ovh.sh 152.228.144.34 cursor/tokenomics-21m-hbp-owner-decay-3fcb` | SSH **Permission denied (publickey)** |
| 3 | SSH `ubuntu@152.228.144.34` | Port 22 ouvert (`OpenSSH_9.6p1`) ; **aucune clé privée** dans `~/.ssh` (seulement `known_hosts`) |
| 4 | Doppler `DOPPLER_TOKEN` | HTTP **401** Invalid Auth (token Cursor injecté, **jamais imprimé**) |
| 5 | Env secrets | Noms : `DOPPLER_TOKEN`, `OVH_APPLICATION_KEY/SECRET/CONSUMER_KEY`, `OVH_CLOUD_PROJECT_ID`, `OVH_ENDPOINT`. **Pas** de `ARTCB_SSH_KEY` / `SSH_*` |
| 6 | Agent frère « Clés OVH et secrets Doppler » `bc-6fca082f-dfe1-4d72-957b-624c389a3fcb` | `WAITING_FOR_BACKGROUND_WORK` ; pas de clé SSH dans **cet** environnement |
| 7 | API OVH HMAC | **Invalid signature** (clés alphanumériques, sans whitespace — couple app/CK **invalide** ou périmé). Aucune injection de clé SSH via API |

Script corrigé : **branche obligatoire** (plus de défaut silencieux `main`) ; tampon `ARTCB_GIT_SHA` / `ARTCB_GIT_BRANCH` via `/etc/artcb/release.env` + `start_node.sh`. Exécutable seulement **avec SSH**.

### 2.3 Preuve live (box **ancienne image**, pas 165)

| URL | HTTP | Contenu |
|-----|------|---------|
| `GET /health` | **200** | healthy, v0.3.0, **pas** de `git_sha`, PQC ML-DSA-65 |
| `GET /api/v1/health` | **200** | chain valid, **0 blocs**, hybrid ML-DSA-65, `bob_configured=true` |
| `GET /api/v1/economics/params` | **404** | cette branche absente |
| `GET /api/v1/economics/h-adult` | **404** | |
| `GET /api/v1/mining/protocol` | **404** | |
| `GET /api/v1/mining/protocol/status` | **404** | |

**SHA live vs branche :** le payload health **n’expose pas** de git SHA (code pré-165). Les routes economics/mining 165 n’existent pas sur la box → **404 toujours là**.  
**Bloquant :** pas de clé SSH + Doppler 401 + signature OVH invalide. **Aucun secret inventé.**

Health 165 (quand la box sera déployée) exposera `git_sha` + `git_branch`.

---

## 3. Pytest (A)

Commande : `OQS_INSTALL_PATH=$HOME/_oqs LD_LIBRARY_PATH=$HOME/_oqs/lib PYTHONPATH=src python3 -m pytest tests/ -q --tb=line`  
Log : `logs/20260828_pytest_rapport165_full.txt`

**606 passed, 9 skipped, 0 fail** (202,34 s).

164 : 584 passed / 21 skipped. Écart : tests PQC **exécutés** (liboqs 0.16 natif) + tests Provider / Stripe≠consensus / anti-Sybil flotte.

---

## 4. Simulation E2E 165 (B, C, D, E, F)

Dossier canonique : `simulations/20260828T220852Z_e2e165/`  
Script : `scripts/run_sim165_e2e.py` → même `ProtocolEngine` que 164.  
Log : `run.log` (copie `logs/20260828_sim165_220852Z_run.log`).  
164 non écrasé : `simulations/20260828T200518Z_e2e164/`.  
Run intermédiaire conservé : `20260828T220828Z_e2e165` (oracle stub via fuite env pytest — **non canonique**).

| Preuve | Valeur |
|--------|--------|
| `failures` | `[]` |
| Security modules | **ENABLED** (0 occurrence de `DISABLED` dans le journal) |
| Intervalle sim | `ARTCB_MIN_BLOCK_INTERVAL_SEC=0` (séquentiel, **pas** la prod 60 s) |
| PQC | **ML-DSA-65 natif**, `hybrid=True`, fallback Ed25519 **non** |
| Σ wallets = supply | **59 000 000 000 satoshi = 590 ARTCB** |
| Supply ≤ 21 M | **true** |
| `hmax_frozen` | **false** (pas de lock ONU/WPP) |
| `H_adult` | **5** |
| Hash | v2 natif C ; `chain_valid: true` |
| Provider JP1/JP2 | pool 2 249 999 998 / 2 249 999 999 (50/50 ±1 sat) ; **11,25 ARTCB chacun** |
| Stripe down | `ok=false`, `mints=false`, `consensus_blocked=false` — bloc 8 gravé |

### Jobs

| Job | Conservé | Note |
|-----|----------|------|
| petit … JobPayment no-mint | oui | comme 164 |
| **providers_nonzero** | oui | JP1+JP2 scores > 0, split réellement exercé |
| **stripe_down_no_block** | oui | secret absent → Stripe KO, chaîne OK |

Soldes (satoshi) : A 493,64 ARTCB ; B 45,05 ; C 21,61 ; D 7,20 ; E 0 ; **JP1 11,25 ; JP2 11,25**. Σ = 590.

---

## 5. Sécurité dans le chemin E2E (C)

Avant : `ChainManager(..., enable_security=False)` → journal `Security modules DISABLED`.

Maintenant :

- `ProtocolEngine` **exige** `enable_security=True`. Disable silencieux → `RuntimeError`. Skip nommé seulement via `ARTCB_SECURITY_DISABLE_REASON`.
- Anti-Sybil : unicité `(address, machine_id, role)` — **une flotte du même owner n’est pas un clone Sybil**. Un vrai doublon `(A, A:M1, worker)` est rejeté.
- `datetime.utcnow` remplacé dans slashing (pytest `error::DeprecationWarning`).

**Ce n’est pas** une résistance Sybil complète (rate-limit, réputation, PoL min 0,6 seulement). **Pas de claim production.**

---

## 6. PQC / liboqs (D)

**Cet environnement Cursor :**

- `liboqs-python` 0.16.0 + **liboqs natif 0.16.0** compilé dans `$HOME/_oqs` (0.12.0 cassait `OQS_SIG_supports_ctx_str`).
- Journal 165 : `PQC native ML-DSA-65 ENABLED`, `native_liboqs: true`.

**OVH :** `/health` dit déjà `pqc.available=true` / ML-DSA-65. Impossible d’installer/mettre à jour liboqs **à distance** sans SSH. La box a PQC ; elle n’a **pas** le code 165.

---

## 7. Provider / Worker scores non nuls (E)

`split_pol_pool` + contributeurs `role=provider` poussés dans la chaîne.

Bloc `providers_nonzero` : JP1=JP2=1 124 999 999 sat ; provider_pool ≈ worker_pool ; conservation OK. Point de départ **50/50** inchangé (paramètre, pas un D-xxx gelé).

Les jobs **sans** providers loguent encore `no provider scores — worker takes full PoL pool` — **attendu** (mining worker-only).

---

## 8. Stripe ≠ consensus (F)

`attempt_job_payment_or_continue` : secret manquant / HTTP / réseau → enregistré, **`consensus_blocked=false`**, `mints=false`.  
JobPayment ≠ mint. Stripe **n’est pas** une dépendance de consensus.

Preuve sim : bloc 8 produit malgré `no Stripe secret`. Tests : `test_stripe_down_does_not_block_chain`, `test_stripe_failure_is_not_consensus_dependency`.

Live PaymentIntent **ce** runtime : secret toujours absent (GHA peut le faire).

---

## 9. Multi-nœuds (G) — échafaudage seulement

`scripts/run_sim165_multinode_scaffold.py` → `simulations/20260828T220830Z_multinode165_scaffold/`  
Nœuds A/B/C/D, latence, partition : **placeholders**.  
`certified: false`. **Aucun** claim oracle prod / Sybil total / certif distribuée.

---

## 10. H_adult max (H)

`hmax_frozen = false`. Ancres HBP provisoires. **Pas** de lock ONU WPP inventé.

---

## 11. Trous restants

| Trou | Bloquant ? |
|------|------------|
| OVH ≠ cette branche (economics/mining **404**) | Oui pour « live = Cursor » |
| SSH / Doppler / HMAC OVH | Oui pour déployer |
| Mining sans MachineRegistry → PoL héritage | Oui pour e2e « tout le monde » |
| Oracle ARTCB unlisted | Conversion USD→satoshi live |
| Stripe secret **ce** pod | GHA seulement |
| Sybil / oracle / multi-nœuds | **Non certifiés** |
| `hmax_frozen` | Toujours false |

---

## 12. Fichiers clés 165

- `src/artcb/mining/protocol.py` — security required, providers, Stripe isolé
- `src/artcb/security/anti_sybil.py` — flotte ≠ clone
- `src/artcb/payments/stripe_jobs.py` — `attempt_job_payment_or_continue`
- `src/artcb/release.py` + `src/api/main.py` / `routes.py` — `git_sha`
- `scripts/deploy_ovh.sh` — branche obligatoire
- `scripts/run_sim165_e2e.py`, `scripts/run_sim164_e2e.py`
- `tests/test_provider_worker.py`, `tests/test_e2e_protocol_164.py`, `tests/test_stripe_priority_job.py`

---

## 13. Décisions

Pas de nouveau D-xxx. D-014 / D-024 / D-025 inchangés. **PR #34 reste OPEN.**
