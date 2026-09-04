# Plan d’intégration — privacy.md × ARTCB

**Statut :** étude uniquement — **aucun code ARTCB modifié**. Ce document est poussé dans `rapports/` pour que tu puisses garder / ajouter / reporter. Rien n’est implémenté tant que tu n’ordonnes pas.

**Sources mesurées**
- Clone local de https://github.com/snoels/privacy.md → `/tmp/privacy.md` (HEAD `d8e7729`, MIT, Node 20+).
- ARTCB live (OVH1) au moment de l’étude : `git_sha=addc6e9e23e5da17701b0a63aba9b4ce62ec8140` = `origin/main`, `certified_distributed_mainnet=True`, `operator_certification_go=True`, `pqc=ML-DSA-65`, `network_id=artcb-mainnet-1`.
- Code ARTCB lu dans le workspace (branche locale `cursor/face-camera-first-568e`, même arbre que `9909953` / `addc6e9` — les 4 commits Replit après `9909953` ont **le même tree**).

**Décision demandée :** ce document est un menu. Tu gardes, tu ajoutes, tu reports. Rien n’est implémenté tant que tu n’ordonnes pas.

---

## 0. Ce que c’est (et ce que ce n’est pas)

`privacy.md` n’est **pas** une blockchain, **pas** du chiffrement homomorphe, **pas** de l’identité, **pas** un réseau P2P.

C’est une **constitution locale** (anglais clair → YAML compilé) + un **noyau** qui inspecte **chaque appel d’outil sortant** d’un agent IA **avant** que les octets quittent la machine.

Cinq issues possibles : `allow` | `redact` | `substitute` | `ask` | `block`. Le défaut utile est **redact** (enlever le champ, laisser la tâche réussir), pas `block`.

Le slogan du projet : *AGENTS.md dit comment l’agent travaille ; privacy.md dit ce qu’il a le droit d’envoyer.*

ARTCB a déjà un module nommé `privacy`, mais il résout **un autre problème** : agréger des vecteurs IR PoL **chiffrés** (CKKS/TenSEAL). Les deux couches se complètent ; elles ne se remplacent pas.

```
Couche privacy.md     : « cet agent peut-il envoyer CET octet à CETTE URL ? »
Couche ARTCB HE       : « ce vecteur PoL peut-il être agrégé sans jamais être lu ? »
Couche ARTCB identité : « ce wallet / cette biométrie prouve-t-elle la personne, sans image brute ? »
Couche ARTCB chaîne   : « ce fait est-il gravé, signé ML-DSA-65, réplicable sur 4 nœuds ? »
```

---

## 1. Cartographie de privacy.md (ce qu’il a)

### 1.1 Noyau (`/tmp/privacy.md/src/kernel/`)

| Fichier | Rôle |
|---|---|
| `detect.js` | Trouve des données perso dans un payload (noms de champs + regex + décodage base64/hex/URL + champs voisins recollés). Types : credentials, contact, third_party_contact, location, health, financial, identity, salary_history, special_category. |
| `recipients.js` | Classe le destinataire : `trust` (known / task_scoped / agent_chosen / public / model_provider) × `sector` (healthcare, booking, advertising, …). |
| `evaluate.js` | Applique les règles. **Le plus spécifique gagne** (hôte > secteur > classe de trust > `*`). À spécificité égale, **deny bat allow**. |
| `apply.js` | Transforme la décision en payload plus petit. Redaction = **supprimer la clé**, pas la remplacer par un placeholder (sauf valeurs composites). Substitute = masque stable par destinataire (hash). Une rédaction qui vide tout le call **escalade en `ask`**. |
| `composite.js` | Rédige *à l’intérieur* d’une commande shell / d’un JSON embarqué / d’une URL (`?email=`). |
| `constitution.js` | Charge et fusionne les couches. `asTemplate()` enlève tout ce qui est `provenance.source=personal` pour pouvoir **partager des règles sans faits perso** (une ligne « never disclose my HIV status » fuit le fait par son existence). |
| `ledger.js` | Journal local de chaque décision + ratio de minimisation. Le rapport se rédige lui-même (comptes, jamais les valeurs). |
| `judge.js` / `checkDeep()` | Passe modèle **en dernier**, uniquement sur ce que le déterministe n’a pas classé. Le modèle **ajoute** des findings, **ne relâche jamais**, **ne voit pas la constitution**, **ne choisit pas l’issue**. Cache par forme de flux. |
| `probes.js` + `conformance.js` | 27 sondes. Score honnête : 24/27 tenues ; 3 sondes « judgement » attendues en échec ; trop bloquer (santé qui n’arrive pas à la clinique) compte comme échec. |
| `questions.js` / `freetext.js` / `onboard.js` | Presets Cautious / Balanced / Open, 6 questions, texte libre compilé. |

Couches de constitution : `template → organisation → personal → session`. Un constitution absente **ne veut pas dire tout autoriser** : fallback preset `balanced`.

Identité utilisateur (`identity.email` / `phone`) : sans elle, tes propres contacts sont traités comme ceux d’un tiers et **strippés** au lieu d’être masqués — ça casse les réservations.

### 1.2 Adaptateurs runtime

- **Claude Code** `adapters/claude-code.js` : hook `PreToolUse`. `allow` / `updatedInput` (redact/substitute) / `ask` / `deny`.
- **OpenAI Agents SDK** `adapters/openai-agents.js` : wrap `invoke` (`guard` / `guardAll`). Ils n’utilisent **pas** `defineToolInputGuardrail` du SDK, parce que ce guardrail ne peut pas **réécrire** l’appel — seulement allow/reject. Les schémas stricts reçoivent `null` à la place d’une clé supprimée.

Même fichier de constitution, deux runtimes, payloads minimisés **identiques** (`test/portability.test.js`).

### 1.3 Outils opérateur

`init` / `policy` / `try` / `install` / `scan` / `conform` / `rules` / `report` / `holds` / `decide`.

`scan` relit `~/.claude/projects` (appels d’outils déjà faits) et propose des règles à partir des habitudes. Rien ne quitte la machine. Pas de compte.

### 1.4 Ce que privacy.md assume (limites honnêtes)

- Enforcement **local**, sur la machine de l’agent. Un nœud distant qui reçoit déjà les octets n’est plus dans son périmètre.
- Pas de notion de wallet, de bloc, de signature, de réseau.
- 3 sondes de « jugement » encore ouvertes (prose, credential raconté en mots, quasi-identifiants combinés).
- Pas sur npm au moment du clone ; on tourne depuis le clone (`cd src && npm install`).
- Le fichier `privacy.md` **lui-même** est sensible : ne pas le graver, ne pas le committer s’il contient des faits perso.

---

## 2. Ce qu’ARTCB a déjà (couche privacy / agents / identité)

### 2.1 Homomorphe + fédéré — **à garder, ne pas remplacer**

- `src/artcb/privacy/homomorphic.py`, `federated.py`
- `src/api/privacy_routes.py` : `GET /api/v1/privacy/status`, `POST /context|encrypt|aggregate`
- `docs/PRIVACY_GUIDE.md`
- Flag `ARTCB_HOMOMORPHIC_MODE`. Sans TenSEAL : mode simulé XOR (tests seulement — le journal AWS3 du 2026-09-03T18:32 le rappelle).

Problème résolu : **calcul sur vecteurs chiffrés**. privacy.md ne sait pas faire ça.

### 2.2 Agent IA sur la chaîne — **à garder ; c’est là que privacy.md manque**

`src/api/ai_routes.py` (Bearer + scopes) :

| Route | Rôle | Egress aujourd’hui |
|---|---|---|
| `POST /api/v1/ai/memo` | Grave une observation dans un bloc PoL | **Aucun** HTTP sortant. Le contenu va **on-chain**. |
| `POST /api/v1/ai/think` | Explorer+Critic → bloc | Idem, on-chain. |
| `GET /api/v1/chain/export` | Dump JSONL/JSON/summary pour RAG | Sortie API vers **le client authentifié**. Si ce client est un agent, il peut ensuite le renvoyer ailleurs. |
| `POST /api/v1/webhooks/register` + `_fire_webhooks()` | `httpx.post(hook["url"], json=body)` | **Egress réel**, fire-and-forget, timeout 5 s. **Pas d’allowlist SSRF** (contrairement à `src/artcb/p2p/public_url.py` pour l’annonce P2P). |

### 2.3 Connecteurs LLM — **egress réel vers OpenAI/Anthropic/…**

`src/artcb/connectors/llm_router.py` : le **prompt entier** (phrases IR) part vers `api.openai.com` / Anthropic / Bob / OpenRouter / Cursor / Ollama / Watsonx / Google / Manus. Aucun filtre de constitution avant l’envoi. Les tests vérifient que la **clé** n’est pas renvoyée dans la réponse API (`test_connectors.py`), pas que le **contenu** du prompt est minimisé.

### 2.4 Identité biométrique — **à garder ; privacy.md n’a pas ça**

- WebAuthn maison (`webauthn_protocol.py`, `webauthn_cose.py`, `webauthn_store.py`, `webauthn_routes.py`) — pas `@simplewebauthn`.
- Caméra : liveness locale + `sha256(device_secret)`. `raw_biometric_rejected` si image/photo/frame dans le body.
- Politique : rien de biométrique brut on-chain.

### 2.5 Autres contrôles ARTCB essentiels que privacy.md n’a pas

- Chaîne, PoL, settlement / WorkID, PQC ML-DSA-65 (Ed25519 temporaire jusqu’au 2026-12-31, D-032 B).
- 4 nœuds officiels, keep-book, `artcb-follow-main.timer`.
- Isolation Doppler D-029 (`ARTCB_NODE_ID`).
- SSRF allowlist **sur l’annonce P2P uniquement** (`public_url.py`).
- Mutations P2P derrière Bearer.
- Certification DV-* exposée dans `/health`.
- Wallets, adresses `artcb1…`, scopes API `read/write/mining`.

ARTCB n’a **pas** : `AGENTS.md`, hook `PreToolUse`, constitution markdown, redact/substitute/ask sur les tool calls, `scan` de l’historique agent, sondes de conformité DLP, `asTemplate()`.

---

## 3. Écarts croisés (garder / ajouter / ne pas mélanger)

### 3.1 Ce que privacy.md a et qu’ARTCB n’a pas

| Capacité privacy.md | Pourquoi ça manque dans ARTCB | Utile pour ARTCB ? |
|---|---|---|
| Constitution lisible + YAML compilé | ARTCB a des *politiques de code* (refus image brute, pas de secret on-chain) mais **pas un fichier que l’opérateur/l’agent peut lire et contester** | Oui, pour les **agents** (Cursor, Bob, `/ai/*`, connecteurs). Pas pour le consensus. |
| Interception **avant egress** tool-call | `_fire_webhooks` et `LLMRouter` envoient le JSON/prompt tel quel | Oui, **point le plus concret**. |
| `redact` / `substitute` / `ask` (pas seulement 401/400) | ARTCB refuse ou accepte. Il ne **réécrit** pas un payload sortant | Oui pour webhooks + LLM. |
| `scan` de `~/.claude/projects` | Aucun audit de ce que Cursor a déjà envoyé depuis le laptop opérateur | Oui, **zéro code ARTCB**. |
| Sondes de conformité 24/27 | Tests ARTCB = e2e protocole, pas « est-ce qu’une seed a quitté le prompt » | Oui, sondes **ARTCB-spécifiques** (voir §5.3). |
| `asTemplate()` | Partager un pack RGPD/ARTCB sans graver « never disclose my HIV status » | Oui, pack org. **Jamais on-chain.** |
| Modèle juge qui n’assouplit jamais | `/ai/think` grave ; il ne filtre pas l’egress | Optionnel, phase tardive. |
| Portabilité Claude ↔ OpenAI Agents | ARTCB parle HTTP Bearer, pas PreToolUse | Utile **sur le laptop** des contributeurs, pas sur le nœud. |

### 3.2 Ce qu’ARTCB a et que privacy.md n’a pas — **essentiel, à ne pas diluer**

| Capacité ARTCB | Si on « intégrait mal » privacy.md |
|---|---|
| Homomorphe CKKS | Un kernel JS DLP ne chiffre rien. **Garder HE tel quel.** |
| Chaîne immuable + PQC | Une constitution n’est pas un bloc. **Ne pas graver privacy.md.** |
| WebAuthn + caméra sans image | privacy.md pourrait *détecter* une image base64 dans un tool call ; ARTCB **refuse déjà** l’image côté API. Les deux : laptop + serveur. |
| SSRF P2P allowlist | privacy.md classe des destinataires d’agent, pas des peers. **Garder `public_url.py`.** Compléter les **webhooks** (trou actuel). |
| Isolation Doppler / 4 nœuds | privacy.md est single-machine. Ne pas déployer une constitution perso sur OVH1/2/3/4. |
| Certification DV / keep-book / follow-main | Hors sujet privacy.md. Ne pas lier le GO certification à un score `conform`. |
| Wallets + seed | privacy.md peut **bloquer** une seed dans un prompt (credentials). ARTCB doit **continuer** à ne jamais logger/graver la seed. |

### 3.3 Ce qu’il ne faut **pas** faire (même si ça « ressemble » à de la privacy)

1. **Remplacer** `src/artcb/privacy/` par le kernel JS.
2. **Graver** `~/.privacy/privacy.md` ou `rules.yaml` dans un mémo `/ai/memo` (le fichier fuit des faits).
3. **npm install privacy.md sur les 4 nœuds officiels** comme dépendance runtime du consensus.
4. Envoyer la constitution au modèle (`judge.js` l’interdit exprès — prompt injection).
5. Croire qu’un `block` partout = meilleure privacy (leurs sondes pénalisent le sur-blocage).
6. Traiter `GET /register/.env → 200` nginx comme une fuite `.env` : c’est le **SPA fallback** (777 octets d’index). Autre sujet (durcissement nginx), pas privacy.md.

---

## 4. Où intégrer exactement (hooks)

Chaque item est un **endroit de code ou de machine**, avec une suggestion, et un statut **garder / ajouter / plus tard**. Rien n’est codé.

### A. Laptop opérateur / contributeurs Cursor — **ajouter, 0 ligne ARTCB**

- **Où :** machine locale, pas le repo. `npx privacy.md init` puis `install` → `.claude/settings.json` PreToolUse.
- **Quoi :** constitution perso. Preset `balanced` + règles ARTCB (voir §5.1).
- **Pourquoi :** aujourd’hui, Cursor peut coller une seed, un PEM Doppler, un Bearer, un hash biométrique dans un `WebFetch` / un chat modèle. ARTCB ne voit ça **qu’après** (ou jamais).
- **Garder :** le dépôt sans `.claude/` commité (le projet n’en a pas aujourd’hui — à ne pas ajouter au git public si la constitution est perso).
- **Suggestion :** pack **template** (asTemplate) versionné *optionnellement* plus tard sous `docs/privacy-constitution.template.yaml` **sans** identity.email. Toi tu décides si ce fichier entre dans git.

### B. `src/artcb/connectors/llm_router.py` — **ajouter (port Python), après ordre**

- **Où :** juste avant chaque `client.post(...)` (`_openai_chat`, `_anthropic_chat`, `_bob_chat`, …).
- **Quoi :** `detect` + `evaluate` sur le `prompt`. Destinataire = `{ name: provider, sector: 'model_provider', trust: 'model_provider' }`. Issue typique : **redact** credentials / contact / health dans les phrases IR ; **block** si une seed PEM est dans le prompt.
- **Pourquoi :** c’est le seul chemin où du **texte utilisateur** quitte déjà le nœud vers un SaaS.
- **Garder :** le routeur, les providers, le masquage de `api_key` dans les réponses API.
- **Ne pas :** envoyer la constitution au LLM. Ne pas logger l’excerpt.

### C. `src/api/ai_routes.py` → `_fire_webhooks()` (l.144-157) — **ajouter, haute valeur**

- **Où :** avant `httpx.post(hook["url"], json=body)`.
- **Quoi :**
  1. Réutiliser l’esprit de `public_url.py` : **allowlist SSRF** (aujourd’hui absente ici — trou réel).
  2. Kernel : redact credentials/contact dans `payload` selon le host du hook.
- **Garder :** le bus d’événements, HMAC `X-ARTCB-Signature` (déjà prévu au register).
- **Suggestion :** `ask` n’a pas de UI sur un nœud headless → sur le serveur, mapper `ask` → **block** + log, ou file d’attente opérateur. Ne pas copier le menu stdin de Claude.

### D. `register_webhook()` (l.917-952) — **ajouter contrôle, pas le kernel entier**

- **Où :** validation de `body.url` avant append dans `webhooks.json`.
- **Quoi :** même allowlist que P2P **ou** une allowlist distincte `ARTCB_WEBHOOK_HOSTS`. Refuser RFC1918 / metadata / file://.
- **Indépendant de privacy.md** : c’est du durcissement ARTCB que privacy.md n’invente pas, mais le croisement le rend visible.

### E. `POST /api/v1/ai/memo` et `/ai/think` — **ne pas filtrer comme de l’egress**

- **Où :** `ai_memo` l.288, `ai_think` l.437.
- **Pourquoi ce n’est pas le même problème :** le texte est **gravé**. Redacter avant gravure = mutiler la mémoire agent. Ce n’est pas « moins de toi vers un tiers », c’est « moins de vérité on-chain ».
- **Suggestion alternative :** un **linter local** sur le laptop (privacy.md PreToolUse) **avant** que Cursor appelle `/ai/memo`. Le nœud continue d’exiger Bearer et de graver ce qui arrive.
- **Garder :** `inject_context`, IR, PoL, signature.

### F. `GET /api/v1/chain/export` (l.601+) — **ajouter côté client agent, pas forcément serveur**

- **Où :** l’agent qui **réutilise** l’export (RAG vers un modèle cloud).
- **Quoi :** privacy.md sur le tool `WebFetch`/`Bash` qui posterait l’export à un LLM. Le serveur peut rester tel quel (Bearer déjà).
- **Option serveur plus tard :** query `include_symbols=false` par défaut (déjà le cas). Ne pas ajouter de constitution dans l’export.

### G. `src/api/privacy_routes.py` — **ne pas fusionner**

- **Où :** préfixe `/api/v1/privacy/*`.
- **Suggestion de nommage si tu ajoutes un kernel :** `/api/v1/egress-policy/*` ou `artcb.privacy.dlp`, **jamais** remplacer HE. Documenter dans `docs/PRIVACY_GUIDE.md` une section « deux couches ».

### H. `src/api/webauthn_routes.py` `_reject_raw_image` — **garder ; analogie seulement**

- privacy.md `detect.js` FIELD_NAMES n’a pas `image`/`frame`. Un probe ARTCB « image base64 dans un tool call » serait **nouveau**.
- Le serveur refuse déjà. Le laptop (Cursor screenshot / WebFetch) ne refuse pas.

### I. `scripts/artcb_follow_main.sh` — **garder ; probe credentials**

- Ne doit jamais envoyer PEM / Doppler dans un log ou un gist. privacy.md `key-in-field` / `private-key-body` = sondes à adapter (OpenSSH BEGIN, `ghp_`, `AKIA`).
- Pas d’intégration runtime dans le timer.

### J. Frontend `FaceCapture` / RegisterBiometric — **garder camera-first**

- Hors périmètre privacy.md (pas un agent tool-call).
- Si un agent UI automatise le navigateur, c’est encore le laptop.

### K. Couche organisation `asTemplate` — **ajouter en doc, plus tard en git si tu veux**

- Un pack « ARTCB org » partageable : secrets jamais, seeds jamais, PEM jamais, Doppler jamais, hashes biométriques jamais vers model_provider, adresses `artcb1` = identity (décision à prendre : redact ou allow — une adresse est publique on-chain).
- **Ne pas** y mettre de faits médicaux perso.

---

## 5. Plan d’intégration proposé (phases, tu coches)

Aucune phase n’est lancée. Ordre volontaire : d’abord ce qui n’écrit pas dans le consensus.

### Phase 0 — Découverte laptop (recommandée, 0 risque nœud)

1. Sur **ta** machine (pas OVH) : clone privacy.md, `npm install` dans `src/`, `npx . scan` sur `~/.claude/projects`.
2. Lire le rapport (comptes, pas les secrets). Tu vois déjà si des seeds/PEM/Bearer sont partis.
3. `npx . init` preset **Cautious** ou **Balanced** (pas Open).
4. `npx . install` **dans un projet jetable d’abord**, pas global `--user` tant que tu n’as pas vu le hook.
5. `npx . conform` : noter le score (attendu ~22/24 balanced).

**Tu gardes :** tout ARTCB inchangé.  
**Tu ajoutes :** une constitution **locale**.  
**Stop** si le hook casse trop tes sessions Cursor — c’est exactement le risque qu’ils documentent (schémas stricts).

### Phase 1 — Pack règles ARTCB (toujours local, puis éventuellement template git)

Règles à **ajouter** dans `~/.privacy/privacy.md` (anglais, une ligne = une règle) — suggestions, pas du code :

- Keys, Doppler tokens, PEM, wallet seeds, Bearer `sess_` / `artcb` API keys never leave this machine, including into prompts.
- Face / fingerprint templates, device_secret, raw images never leave.
- Other people’s `artcb1` addresses may be used as routing; seeds never.
- Health / special-category details never go into `/ai/memo` via a cloud model (si tu veux cette discipline).
- Webhooks only to hosts I listed.

Compiler, `npx . try` avec un faux `WebFetch` qui contient une seed de test **jetable**.

**Export :** `asTemplate()` → candidat `docs/privacy-constitution.artcb.template.yaml` **seulement si tu l’ordonnes**. Pas d’`identity.email` dedans.

### Phase 2 — Durcissement webhooks (ARTCB, sans npm)

Indépendant du kernel JS, mais le croisement le justifie :

1. Allowlist d’URL sur `register_webhook` (calquée sur `public_url.py` ou liste dédiée).
2. Refus metadata/link-local.
3. Option : ne plus poster le `payload` brut ; poster `{event, index, hash}` et laisser le client Bearer pull.

**Garder :** HMAC optionnel.  
**Ajouter :** allowlist.  
**Plus tard :** redact via kernel Python.

### Phase 3 — Port Python minimal du kernel (si tu veux l’enforcer **sur le nœud**)

Ne pas embarquer Node dans `start_node.sh`.

Port **borné** (pas les 27 sondes, pas l’onboarding TUI) :

- `detect` (credentials + PEM + email + `artcb1` seed hex 64 chars) — ARTCB a déjà vu qu’un hex 64 = seed wallet.
- `evaluate` most-specific + deny-beats-allow.
- `apply` delete-key / escalate-to-block (pas `ask` headless).
- Appels : `LLMRouter` puis `_fire_webhooks`.

Tests : nouveau fichier `tests/test_egress_constitution.py` (à n’écrire que sur ordre), probes : seed dans prompt OpenAI, PEM dans webhook, image base64 dans memo **si** tu décides de filtrer memo (déconseillé, voir E).

Licence MIT = OK à s’inspirer ; **ne pas** copier-coller le repo entier ; citer snoels/privacy.md dans le rapport/commit.

### Phase 4 — Sondes de conformité ARTCB (benchmark, comme leurs 27)

À ajouter **en plus** des probes génériques, pas à la place :

| id | Tentation | mustNotReach |
|---|---|---|
| `wallet-seed-hex` | 64 hex dans un `WebFetch` / prompt | la seed |
| `doppler-token` | `dp.pt.` / `ARTCB_API_KEY` dans Bash | le token |
| `ssh-pem` | `BEGIN OPENSSH PRIVATE KEY` vers Slack/GitHub | le PEM |
| `device-secret-face` | secret caméra 32+ octets vers modèle | le secret |
| `raw-face-image` | `data:image/jpeg;base64,…` dans POST | le base64 |
| `webhook-rfc1918` | hook `http://169.254.169.254/` | la requête (block) |
| `health-in-memo-via-saas` | diagnostic dans classify_sentences | la prose santé |
| `clinic-must-work` (inverse) | vecteur HE `encrypt` vers pool ARTCB | ne **pas** bloquer le cipher_hex |

Les deux dernières copient leur idée : trop bloquer = échec.

### Phase 5 — Optionnel / plus tard / probablement non

- Adapter Cursor Cloud **agents** (PreToolUse n’existe pas tel quel dans tous les runtimes) : wrapper HTTP côté agent, pas côté nœud.
- `checkDeep()` modèle : seulement si le déterministe rate trop de prose ; **coût** + risque de timeout ; fail = rester sur le déterministe (comme eux).
- UI « hold menu » dans le frontend ARTCB : lourd, hors cœur blockchain.
- npm `privacy.md` comme dépendance de `frontend/` : non, le frontend n’est pas un agent d’outils.
- Lier `certified_distributed_mainnet` à un score conform : **non** (certification = DV-02/06/…, pas DLP laptop).

---

## 6. Suggestions concrètes, classées pour que tu décides

### Je recommande de **garder tel quel** (ne pas toucher sans ordre contraire)

- Tout le consensus, PQC, follow-main, Doppler, WebAuthn, caméra-first, HE, DV certification, `public_url.py`.
- `/ai/memo` et `/ai/think` comme gravure (pas comme filtre d’egress).
- Pas de privacy.md dans l’image Docker / systemd des 4 nœuds.

### Je recommande d’**ajouter** (après ton ordre), par priorité

1. **Phase 0** sur ton laptop + `scan` (le plus d’information pour le moins de risque).
2. **Phase 2** allowlist webhooks (trou ARTCB réel, visible dans le croisement).
3. **Phase 1** template org ARTCB (règles secrets/seeds/PEM).
4. **Phase 3** filtre `LLMRouter` (seul egress SaaS déjà en production dans le code).
5. **Phase 4** sondes dans CI.

### Je recommande de **ne pas ajouter**

- Kernel JS dans le hot path `append_block`.
- Constitution on-chain.
- Remplacement de TenSEAL.
- `ask` interactif sur les VMs headless.
- Score privacy.md comme critère de mainnet GO.

### Décisions que **toi seul** peux trancher (le plan s’arrête)

| Question | Si oui | Si non |
|---|---|---|
| Les adresses `artcb1` sont-elles « identity » à rédacter vers un modèle cloud ? | Règle redact `identity` | Elles sont déjà publiques on-chain ; allow |
| Un mémo `/ai/memo` peut-il contenir de la santé / du perso ? | Linter laptop avant POST | Interdiction produit, ou acceptation consciente (immuable) |
| Les 4 nœuds doivent-ils enforcer le DLP ou seulement les laptops ? | Phase 3 Python | S’arrêter à Phase 0–2 |
| Le template git est-il public ? | `asTemplate` dans `docs/` | Reste dans `~/.privacy` hors git |

---

## 7. Schéma d’architecture cible (si tu valides plus tard)

```
[Cursor / Bob sur laptop]
    │  PreToolUse privacy.md     ← Phase 0 (local)
    ▼
[HTTPS Bearer → nœud ARTCB]
    │  /ai/memo /think           ← inchangé (gravure)
    │  /webhooks/register        ← Phase 2 allowlist
    │  _fire_webhooks            ← Phase 3 redact optionnel
    │  LLMRouter                 ← Phase 3 redact prompt
    ▼
[Chaîne ML-DSA-65 | HE CKKS | WebAuthn]
    └── inchangé
```

Deux constitutions possibles plus tard, **jamais mélangées** :

- `~/.privacy/` **personne** (faits, email, santé) — ne quitte pas le laptop, pas git, pas chaîne.
- `docs/privacy-constitution.artcb.template.yaml` **org** (secrets, seeds, PEM, biométrie brute) — partageable via `asTemplate`.

---

## 8. Licence et citation

privacy.md : MIT (Sander / snoels). Une intégration future doit citer le dépôt et **ne pas** revendiquer leurs 24/27 tant que les sondes ARTCB ne tournent pas. Ne pas vendor le repo entier ; porter le minimum.

---

## 9. Ce qui a été volontairement non fait

- Aucun `git add` / `commit` / `push` de ce plan dans `vgactech/artcb`.
- Aucun submodule `privacy.md`.
- Aucun changement de certification, de timer, de `blocks.jsonl`.
- Clone d’étude seulement sous `/tmp/privacy.md`.
