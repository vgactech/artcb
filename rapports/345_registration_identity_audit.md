# R345 — Inscription : ce qui se passe vraiment (+ correctifs)

**UTC:** 2026-09-14T17:25:00Z  
**CERTIFIED_100:** false · **BETA:** true  
**UNIQUE_HUMAN:** false (toujours)

## Ce que tu vois (3 problèmes distincts)

### 1) Création classique `vgactech!` refusée avec `cursor-cloud-agent`

Ce n’est **pas** une collision de nom.

Ordre réel dans `POST /wallet/create` :

1. contrôle **empreinte appareil** → si déjà liée → `409 device_wallet_limit`
2. seulement ensuite → collision de **nom** → `409 wallet_name_exists`

Le message cite `cursor-cloud-agent` parce que c’est le **wallet déjà lié** à l’empreinte, pas parce que tu as tapé ce nom.

**Cause racine (pré-R345) :** la liaison utilisait `DeviceIdentity` du **serveur** (hôte OVH/API), pas ton navigateur. Après qu’un agent/bootstrap a créé `cursor-cloud-agent` sur le nœud, **toute** création classique sur artcb.me était bloquée.

**Correctif R345 :** binding = empreinte **client** `sha256(User-Agent | X-ARTCB-Device-Id)[:32]` + header `X-ARTCB-Device-Id` (localStorage) côté frontend.

### 2) Deux wallets avec le « même visage »

Attendu si on croit à « 1 humain = 1 identité » : **refus**.

Réalité code : **aucune** table `HumanIdentity`, **aucune** comparaison de visage côté serveur.

Le flux visage/caméra ou WebAuthn :

- prouve une **credential / secret appareil**
- crée un wallet si le **nom** est libre
- (pré-R345) **ne** passait **pas** par `wallet_device_binding`
- l’UI dit déjà : raw biometric never stored ; `unique_human_proven: false`

Donc Face ID / caméra ≠ base mondiale d’unicité humaine. C’est **attendu techniquement**, **insuffisant** pour anti-Sybil humain.

R345 ajoute la limite **appareil client** aussi sur le chemin biométrique — ce n’est toujours **pas** UNIQUE_HUMAN.

### 3) Déconnexion biométrique → demande mot de passe

À la création biométrique, le serveur chiffre la seed avec un **vault password aléatoire jamais affiché** (`secrets.token_urlsafe(32)`).

`POST /auth/login` (nom+password) **ne peut pas** réussir pour ces wallets. Le message t’envoie vers `/register` — c’est le canal WebAuthn/visage, pas un bug de « mauvais mot de passe ».

Le formulaire « Connexion — j’ai déjà un compte » (password) est le **mauvais canal**.

## KYB (P0 scaffold)

`creator_may_self_validate` était **inversé** (True si creator==validator).  
Corrigé : A/A → False, A/B → True. Tests négatifs UBO/controller ajoutés.

## Questions de diagnostic (checklist)

1. Quelle empreinte est utilisée à la création : serveur host ou client UA+device-id ?
2. Où est stocké `fingerprint → wallet` (`wallet_device_bindings.json`) ?
3. Le nom est-il testé avant ou après le device check ?
4. Existe-t-il `HumanIdentity` ? Relation Human ↔ Wallet ?
5. WebAuthn credential = HumanIdentity ? (doit rester **non**)
6. Vault password biométrique : jamais montré → login password impossible ?
7. UI login password vs `/register` : routage clair ?
8. Même humain / autre navigateur / autre appareil : recovery ou nouveau wallet ?
9. Deux humains / même machine : politique 1-wallet-device vs 1-humain ?

## Non-revendiqué

CERTIFIED_100=false · UNIQUE_HUMAN=false · QR E2E NOT_PROVEN · KYB live NOT_PROVEN
