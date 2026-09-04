# Rapport 215 — Intégration et corrections issues des rapports 210 → 214

**Date :** 2026-09-04  
**Branche :** `cursor/privacy-md-activity-reports-568e` (rebasée sur `origin/main` `16d29fb`)  
**Live au début :** OVH1 `/health` 200, `git_sha=187716b8…`, `main`, ML-DSA-65 — un commit derrière `16d29fb` (le timer follow-main le rattrape ; `16d29fb` ne touche qu’un `.md`).  
**Entrées :** `212` (= `2012`, doublon octet pour octet), `213`, `214` (rapports « chat et simulation »), `210` (activités users), `211` (plan privacy.md).  
**Règle appliquée :** `docs/PROTOCOL_SOURCE_OF_TRUTH.md` — les rapports 212-214 sont du rang 6 ; rien n’y est implémenté par le fait d’y être écrit. Ce rapport dit **ce qui a été codé, testé, et ce qui reste**.

---

## 1. Ce que les rapports 212-214 demandaient (extraction, pas interprétation)

| Source | Demande | Statut avant 215 |
|---|---|---|
| 212/213 §5-7 | Réparer OVH4, SSH, même SHA sur 4 nœuds | **Fait** avant (PR #54 follow-main, rapport 207) |
| 212/213 §17 | `iperf3` mesh 4×4 | **Non fait** (203 : « pas d’iperf3 encore ») |
| 212/213 §18 | `measured_bandwidth_mbps` ≈ 0 vs `estimated=100` fallback | **Déjà distingué** dans `hardware.py` (`bandwidth_source`, D-053) — reste à ne jamais lire `estimated` comme WAN |
| 212/213 §21 | Étapes 1-5 puis tests de panne 1-6 | Partiel via DV (voir §5) |
| 212/213 §28 | Matrice Décidée / Simulée / Codée / Testée / Live | **Institué** ici (§6) + `docs/PROTOCOL_SOURCE_OF_TRUTH.md` |
| 212/213 §29 | D-055 validation distribuée 4 nœuds | D-055 **existe** (WebAuthn + gate) ; D-056 GO après DV-02/06 PASS |
| 213 L2611-2645 | Mandat agent (CAN / CANNOT), domaines | **Conceptuel**, pas codé — proposition §7 |
| 214 L153-193, L677 | **Anomalie n°1** : README ≠ D-024/D-025 | **Corrigé** (§2.4) |
| 214 L607-627 | Hiérarchie source de vérité | **Corrigé** (`docs/PROTOCOL_SOURCE_OF_TRUTH.md`) |
| 214 L364-400 | `GROUPES_RESEAUX_ARTCB.md` obsolète, audit groupes/privacy | Doc **marquée obsolète** ; audit code groupes **ouvert** (§7) |
| 214 L1540-1548 | Ne pas appeler la caméra « reconnaissance faciale » | **Corrigé** (§2.3) |
| 214 L1515 | Journal d’audit biométrique | **Corrigé** (§2.3) |
| 214 L1671 | Audit « Enrollment → Human Proof → Wallet Creation » par wallet | **Fait** dans 210 §9 ; complété §4 |
| 210 §9.8 A | `/wallet/list` public énumère noms/clés | **Corrigé** (§2.2) |
| 210 §9.8 B | Wallets biométriques inactivables par mot de passe | **Corrigé côté message + journal** ; le design (vault aléatoire) est conservé — voir §7 |
| 210 §9.8 E | 401 login sans nom de wallet dans le journal | **Corrigé** |
| 211 Phase 2 | Allowlist SSRF webhooks | **Codé** |
| 211 Phase 3 | Redaction secrets avant LLM / webhooks | **Codé** (port Python minimal) |

---

## 2. Ce qui a été codé (4 commits)

### 2.1 `feat(privacy): egress policy` — `8f48683`

- Nouveau `src/artcb/privacy/egress.py` : `detect()`, `check_payload()`, `redact_text()`, `webhook_url_ok()`, `record()`.
  - Champs nommés (`api_key`, `token`, `seed`, `device_secret`, `password`, `pem`, `doppler_token`…) → **retirés**.
  - Motifs : PEM, `sk-`, `sk-ant-`, `ghp_`, `github_pat_`, `xox…`, `AKIA`, `AIza`, `dp.st./dp.pt.` (Doppler), `artcb_…` (clé API ARTCB), `sess_…` (session ARTCB), Stripe, `Bearer …`.
  - PEM n’importe où → **block**. Rédaction qui vide le payload → **block**.
  - **Limite documentée** : un 64-hex n’est pas classé seed (même forme qu’un hash de bloc) ; seul le nom de champ tranche.
  - Ledger `artcb.privacy.egress` : comptes et types, **jamais la valeur**.
- `src/api/ai_routes.py` : `register_webhook` refuse une URL hors politique (`400 webhook_url_rejected:<raison>`) ; `_fire_webhooks` re-vérifie la destination à chaque envoi, passe le payload par `check_payload`.
- `src/artcb/connectors/llm_router.py` : le prompt `classify_sentences` est rédigé **avant** OpenAI / Anthropic / Bob / etc.
- HE (`homomorphic.py`, `/api/v1/privacy/*`) **inchangé**. `/ai/memo` et `/ai/think` **non filtrés** (gravure ≠ egress, 211 §4.E).

### 2.2 `fix(api): /wallet/list + 401 login` — `077e5ff`

- `GET /api/v1/wallet/list` sans Bearer → projection `{name, address, address_v2, hybrid, created_at, has_key_file}` + `projection:"public"`. Avec `Bearer sess_…` ou `Bearer artcb_…` valide → métadonnées complètes. `ARTCB_WALLET_LIST_PUBLIC=0` → 401 sans Bearer.
- `POST /api/v1/auth/login` : un seul texte 401 (pas d’énumération), avec l’indice « wallet créé par empreinte/visage → /register ». `WARNING Login failed wallet=<nom> reason=<wallet_unknown|password_mismatch|key_unreadable> client=<ip>` — jamais le mot de passe.

### 2.3 `feat(biometric): assurance + audit + présence faciale` — `6c77688`

- `ASSURANCE_LEVELS` (0-3, rapport 214) : `password=0`, `face_camera=1`, `webauthn_fingerprint=2`, `webauthn_face=2`. **Aucune méthode n’atteint 3** (humain unique vérifié).
- `/auth/webauthn/status` expose `assurance`, `max_assurance_level`, `unique_human_proven:false`.
- `face/enroll/options|verify`, `face/login` retournent `label="Vérification de présence faciale locale"` + `assurance`.
- Journal `artcb.api.webauthn.audit` : `webauthn_register_ok|failed`, `webauthn_login_ok|failed`, `face_enroll_ok|failed`, `face_login_ok|failed` avec wallet, client, raison, niveau — **sans secret, sans hash de secret**.
- Frontend : « reconnaissance faciale » → « présence faciale locale » (FR/EN), mention « ne prouve pas qu’une personne est un humain unique ». Dist rebuild `index-DXwjByNk.js`.

### 2.4 `docs` — `1cea0a2`

- README §Tokenomics : plus de « Halving fixe », « 1 ARTCB / bloc », « 5 × 210 000 ». Tableau aligné D-014 / D-024 / D-025 avec renvoi aux sources.
- `GROUPES_RESEAUX_ARTCB.md` : bandeau **OBSOLÈTE** (ses « Non — pas de backend » datent de juillet ; `groups_routes.py` / `privacy_routes.py` existent).
- `docs/PROTOCOL_SOURCE_OF_TRUTH.md` : hiérarchie 1 décisions → 2 specs → 3 code → 4 tests/RESULT → 5 live → 6 rapports → 7 README.

---

## 3. Tests

`tests/test_e2e215_egress_wallet_list_audit.py` — **14 tests, 14 PASS** (`T-E42`).

| Test | Vérifie |
|---|---|
| `test_egress_named_field_is_removed_not_masked` | `api_key` retiré, hash 64-hex conservé |
| `test_egress_inline_token_is_replaced_and_pem_blocks` | `sk-…` remplacé, email non forcé, PEM → block |
| `test_egress_redaction_that_empties_payload_escalates_to_block` | `{"token":…}` → block |
| `test_egress_detects_artcb_specific_shapes` | `artcb_`, `sess_`, `dp.st.` |
| `test_webhook_url_policy` | 169.254 / 127.0.0.1 / 10.x / ftp / userinfo refusés ; `ARTCB_WEBHOOK_HOSTS` ; local en test |
| `test_webhook_register_rejects_metadata_target` | API 400 sur IMDS, 200 sur cible autorisée |
| `test_llm_router_redacts_prompt_before_provider` | le fournisseur ne voit pas la clé |
| `test_wallet_list_anonymous_is_public_projection` | pas de `pqc_public_key_hex` / `auth_methods` sans Bearer ; complet avec |
| `test_wallet_list_can_be_made_private` | `ARTCB_WALLET_LIST_PUBLIC=0` → 401 |
| `test_login_failure_same_detail_and_audited` | même 401 ghost/known ; journal `reason=` ; mot de passe absent |
| `test_biometric_wallet_cannot_use_password_login` | reproduit le cas **testA** (210 §9.4) |
| `test_webauthn_status_reports_assurance_and_audit_lines` | niveau 1, `unique_human_proven=false`, lignes d’audit, secrets absents |
| `test_frontend_wording_is_presence_not_recognition` | plus de « reconnaissance faciale » |
| `test_readme_follows_d024_d025_not_halving` | README / docs / GROUPES |

Régression lancée sur `webauthn_biometric`, `e2e205`, `e2e208`, `auth_wallet_protocol`, `connectors`, `e2e177`, `sdk`, `mcp_server`, `wallet_rewards`, `e2e169`, `privacy_homomorphic` : **147 passed, 12 failed** — les 12 sont **préexistants sur `main`** (vérifié par `git stash`) :
- `test_wallet_rewards.py` ×6 (balance / rewards, antérieur),
- `test_sdk.py` ×4 (`Refuse Bearer over cleartext HTTP` — durcissement 169 non répercuté dans ces tests),
- `test_e2e169_secure_live.py` ×2 = 503 « suite-order » déjà consigné en T-E31 ; **7/7 PASS** isolé.

Aucune des 12 n’est introduite par 215. Elles sont listées §7 comme dette.

---

## 4. Audit « Enrollment → Human Proof → Wallet Creation » (214 L1671) — par wallet réel OVH1

Sources : journal `artcb` + nginx OVH1 (relus le 2026-09-04), `data/wallets/*.json` (clés seulement), `credentials.json`, `face_unlock.json`. Aucun secret lu.

| Wallet | Créé | Méthode(s) réelle(s) | Niveau max (§2.3) | Preuve d’humain unique | Écart |
|---|---|---|---|---|---|
| Gabriel | 2026-09-02 21:29:33Z (`85.69.218.227`) | WebAuthn ×4 : 1 fingerprint + **3 face OS** | 2 | **Non** | 3 creds `face` créés **avant** camera-first (bug #56) ; pas de `face_camera` ; migration possible depuis l’onglet inscription (Visage → caméra sur wallet existant) |
| Chaves | 22:03:50Z (même IP) | WebAuthn fingerprint + `face_camera` | 2 | Non | parcours « les deux » post-#56, conforme |
| Victor | 22:05:37Z (même IP) | WebAuthn fingerprint | 2 | Non | conforme |
| testA | 2026-09-03 19:47:23Z (`195.220.106.83`) | `face_camera` seul, après **4× `/auth/login` 401** | 1 | Non | lockout mot de passe (vault aléatoire) → corrigé côté message + journal (§2.2) |
| cursor-cloud-agent | 2026-08-29 | mot de passe (agent) | 0 | Non | — |

Zéro `webauthn/login` ni `face/login` dans nginx (`access.log`, `.1`) : quatre inscriptions, **aucune reconnexion biométrique** enregistrée. `signCount=0` seul n’aurait pas suffi à le dire.

---

## 5. Étapes 1-5 et tests de panne 1-6 (212/213 §21-23) ↔ ce qui existe

| Demande 212/213 | Couvert par | Verdict fichier | Honnêteté |
|---|---|---|---|
| Étape 1 réparer OVH4 | PR #54, rapport 206/207 | — | Fait, 4 nœuds `HEAD` identique |
| Étape 2 même SHA 4/4 | follow-main timer 5 min | — | Fait, mesuré 2026-09-04 |
| Étape 3 livre (`height`, `last_hash`, `chain_valid`) | sim 189/203 | DV-04 PASS | `height` non relu dans 215 |
| Étape 4 ping / perte / **iperf3** | 203 (ping 4×4) | — | **iperf3 absent** |
| Étape 5 bench distribué P50/P95/P99 | — | — | **Non mesuré** (203 : interdit tant que iperf3 et SHA ≠) |
| Test 1 arrêt N4 → consensus | sim 188 (stop/start OVH4) | DV-05 PASS | scope = settlement WorkID, **pas** `append_block` |
| Test 2 latence artificielle | sim 208 netem 80 ms / 25 % OVH4 | DV-06 PASS | « not chaos C » |
| Test 3 réintégration | sim 208 restore netem | DV-06 PASS | même limite |
| Test 4 bloc invalide → rejet | sim 190 (`register-public` SSRF 400, gossip 401) | DV-02 PASS | rejet **réseau**, pas bloc forgé |
| Test 5 double dépense | — | — | **Non testé live** |
| Test 6 partition → convergence | — | — | **Non testé live** |

Conclusion 212/213 maintenue : le réseau 4 nœuds est **homogène et certifié par la porte** (`certified_distributed_mainnet=True` sur DV-01…07), mais Tests 5-6, iperf3 et P50/P95/P99 distribués **restent à mesurer**. Ce rapport ne les invente pas.

---

## 6. Matrice obligatoire — Règle | Décidée | Simulée | Codée | Testée | Live

| Règle | Décidée | Simulée | Codée | Testée | Live |
|---|---|---|---|---|---|
| Secrets jamais dans un webhook sortant | proposition 211 | 211 | `egress.py`, `ai_routes.py` | T-E42 | **non** (attend merge + follow-main) |
| Secrets jamais dans un prompt LLM connecteur | proposition 211 | 211 | `llm_router.py` | T-E42 | non |
| Webhooks : pas de cible privée / metadata | 211 §4.C-D (trou 210) | — | `egress.webhook_url_ok` | T-E42 | non |
| `/wallet/list` public minimal | 210 §9.6 | — | `routes.py` | T-E42 | non |
| 401 login uniforme + journal | 210 §9.4/E | — | `auth_routes.py` | T-E42 | non |
| Caméra = présence locale, pas identité | 214 | 214 | `webauthn_routes.py`, i18n | T-E42 | non |
| Journal d’audit biométrique | 214 L1515 | — | `webauthn_routes.py` | T-E42 | non |
| README = reflet de D-024/D-025 | D-024, D-025 | 161-163 | `tokenomics.py` (déjà) | T-E01/E02 + T-E42 | code live déjà conforme ; texte non |
| Hiérarchie source de vérité | 214 L607 | — | `docs/PROTOCOL_SOURCE_OF_TRUTH.md` | T-E42 | doc |
| 21 M / R(H) / pas de halving | D-014 D-024 D-025 | 159-163 | `tokenomics.py` `emission.py` | T-E01 T-E02 | `addc6e9`/`187716b` |
| DV-01…07 PASS → certified | D-055 D-056 | 188-208 | `devnet_validation.py` | T-E40 | `certified=True` |
| iperf3 mesh | 212/213 §17 | — | — | — | — |
| TPS distribué P50/P95/P99 | 212/213 §15 | — | — | — | — |
| Double dépense live (Test 5) | 212/213 §23 | — | — | — | — |
| Partition réseau (Test 6) | 212/213 §23 | — | — | — | — |
| Mandat agent CAN/CANNOT | 213 L2617 | 213 | — | — | — |
| Domaines / Cross-domain grant | 213 L3139 | 213 | — | — | — |
| Machine à états identité (PENDING…ACTIVE) | 214 L1429 | 214 | — | — | — |
| Challenge dynamique liveness (tête, cligner) | 214 L1049 | 214 | — | — | — |

Case vide = **non**.

---

## 7. Ce qui reste et **ce qui attend un GO** (rien de ceci n’a été codé)

**Corrections restantes sans décision protocolaire (pures dettes) :**
1. `test_wallet_rewards.py` ×6, `test_sdk.py` ×4 (ajouter `ARTCB_ALLOW_INSECURE_HTTP=1` dans ces tests), `test_e2e169` suite-order 503.
2. Audit code réel `groups_routes.py` / `privacy_routes.py` : `visibility:"private"` filtré ou seulement stocké ? (214 « illusion de confidentialité »). À faire fichier par fichier, rapport 216.
3. iperf3 mesh 4×4 puis campagne TPS distribué (203 §campagnes 3-4). Nécessite `iperf3` sur les 4 VMs — installation = commande sur les nœuds officiels → **ordre opérateur**.

**Décisions à prendre (propositions, pas D-0xx tant que non validées) :**
- **P-215-1 Wallet biométrique et mot de passe.** Aujourd’hui un wallet caméra/empreinte a un vault aléatoire jamais montré : `/auth/login` échoue toujours (cas testA). Options : (a) garder — la biométrie est la seule porte, le seed_hex affiché une fois est la récupération ; (b) proposer « définir un mot de passe » après enrôlement biométrique ; (c) bouton Activer masqué pour ces wallets.
- **P-215-2 Dédoublonnage `save_credential` par (wallet, modality).** Gabriel a 3 creds `face`. Dédoublonner casse le multi-appareils légitime. Alternative : garder, exposer le compte dans `status` (fait), laisser l’utilisateur révoquer.
- **P-215-3 `/wallet/list` fermé par défaut** (`ARTCB_WALLET_LIST_PUBLIC=0`) sur les nœuds officiels : les noms Gabriel/Chaves/Victor restent lisibles tant que c’est ouvert. Le frontend « Activer » a besoin des noms.
- **P-215-4 Tests 5-6 live** (double dépense, partition) : nécessitent d’injecter du trafic adversarial sur le mainnet certifié → ordre explicite.
- **P-215-5 Mandat agent / domaines / machine à états identité** (213-214) : conception à écrire en spec (rang 2) avant tout code.
- **P-215-6 Constitution privacy.md sur le laptop opérateur** (211 Phase 0) : hors dépôt, action opérateur.

---

## 8. Ce qui n’a **pas** été fait, volontairement

- Aucun `D-0xx` ajouté à `DECISIONS_UTILISATEUR_ARTCB` (rang 1 = opérateur).
- Aucune modification de `certified_distributed_mainnet`, des `RESULT.json`, de `blocks.jsonl`, du timer.
- Aucun déploiement manuel : `main` sera suivi par `artcb-follow-main.timer` après merge.
- Pas de `npm install privacy.md` dans le dépôt ; port Python minimal, cité MIT.
- `/ai/memo` / `/ai/think` non filtrés (gravure).

## 9. Fichiers

- Code : `src/artcb/privacy/egress.py`, `src/api/ai_routes.py`, `src/artcb/connectors/llm_router.py`, `src/api/routes.py`, `src/api/auth_routes.py`, `src/api/webauthn_routes.py`, `frontend/src/i18n/translations.ts`, `frontend/src/pages/RegisterBiometric.tsx`, `frontend/dist/*`.
- Docs : `README.md`, `GROUPES_RESEAUX_ARTCB.md`, `docs/PROTOCOL_SOURCE_OF_TRUTH.md`.
- Tests : `tests/test_e2e215_egress_wallet_list_audit.py` ; `LISTE_TESTS_ARTCB.md` T-E42.
