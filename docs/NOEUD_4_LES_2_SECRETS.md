# Nœud 4 — les 2 secrets, expliqués simplement

Tu n’as **rien à inventer**. Je ne peux **pas** te coller ces valeurs dans le chat
(ce serait comme coller tes mots de passe sur GitHub). Voici **d’où** elles
viennent, et **quoi cliquer**.

Le pavé MetaMask / wallet / `blocks.jsonl` est **un autre sujet**. Ignore-le
pour ouvrir le nœud 4.

---

## Image mentale (3 boîtes)

```text
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│ 1. Doppler artcb-4  │     │ 2. Secrets Cursor    │     │ 3. Serveur OVH4 │
│    = le coffre-fort │────▶│    = la clé du coffre│────▶│  91.134.45.8    │
│    Tes clés OVH     │     │    que tu donnes à   │     │  (déjà allumé)  │
│    sont DÉJÀ dedans │     │    CET agent         │     │                 │
└─────────────────────┘     └──────────────────────┘     └─────────────────┘
```

1. **Doppler** `artcb-4` = le coffre à la banque. Tu y as déjà mis les clés OVH.
   Merci. Je te crois. **Je ne peux pas encore l’ouvrir.**
2. **`KEY_API_ARTCB_DOPPLER_4`** = la **clé du coffre**. Elle se fabrique **dans
   Doppler**, puis se colle **dans Cursor**. Pas dans le chat.
3. **`SSH_PRIVATE_KEY`** = la **clé de la porte** du serveur `91.134.45.8`.
   Elle va **dans le coffre Doppler**, pas dans Cursor. Tu n’as pas à la
   chercher : soit elle y est déjà, soit **je la fabrique** dès que j’ai (2).

C’est **exactement** ce que tu as déjà fait pour les nœuds 2 et 3 :

| Nœud | Coffre Doppler | Clé du coffre dans Cursor | Chez cet agent maintenant |
|------|----------------|---------------------------|---------------------------|
| 1 | `artcb-blockchain` | `DOPPLER_TOKEN` | présent, ça marche |
| 2 | `artcb-2` | `KEY_API_ARTCB_DOPPLER_2` | présent, ça marche |
| 3 | `artcb3` | `KEY_API_ARTCB_DOPPLER_3` | présent, ça marche |
| **4** | **`artcb-4`** | **`KEY_API_ARTCB_DOPPLER_4`** | **absent** — c’est le seul trou |

Les jetons 1 / 2 / 3 **refusent** d’ouvrir `artcb-4` (mesuré : HTTP 400
« This token does not have access to requested project artcb-4 »). Donc coller
un jeton nœud 2 dans le champ nœud 4 **ne marchera pas**.

---

## Secret 1 — `KEY_API_ARTCB_DOPPLER_4` (toi, 5 minutes)

Je **ne** génère **pas** cette valeur. Doppler la fabrique **une seule fois**
quand tu cliques. Tu l’as déjà fait pour `_2` et `_3`.

### A. Doppler — fabriquer le badge

1. Ouvre [https://dashboard.doppler.com](https://dashboard.doppler.com)
   (workplace **lvxsecret**, le même que d’habitude).
2. Clique le projet **`artcb-4`** (l’écran peut afficher **ARTCB_API_4**).
3. Clique la config **`dev`**.
4. Onglet **Access**.
5. Bouton **Generate**.
6. Nom : `artcb4` (ou `cursor-ovh-node-4`).
7. Coche **Write access** (pour que je puisse ranger la clé SSH moi-même).
8. Pas d’expiration (Unlimited).
9. **Generate Service Token**.
10. Doppler affiche **une fois** un texte qui commence par `dp.st.`
11. **Copie-le.** Ne le colle pas dans ce chat.

Si tu fermes la fenêtre sans copier : ce n’est pas grave. Tu en **régénères**
un autre (l’ancien est perdu, c’est normal).

### B. Cursor — coller le badge au même endroit que `_2` et `_3`

1. Ouvre l’environnement Cloud Agent :
   [https://cursor.com/dashboard/cloud-agents/environments/e/fffe9ae0-a3d4-11f1-a7d1-d6b4613131ce](https://cursor.com/dashboard/cloud-agents/environments/e/fffe9ae0-a3d4-11f1-a7d1-d6b4613131ce)
2. Section **Secrets** (le même tableau où tu vois déjà
   `KEY_API_ARTCB_DOPPLER_2` et `KEY_API_ARTCB_DOPPLER_3`).
3. **Add secret** :
   - Nom **exact** : `KEY_API_ARTCB_DOPPLER_4`
   - Valeur : le `dp.st.…` copié
4. Sauvegarde.
5. Réponds ici : **« token Cursor collé »** — **sans** coller le token.

Un agent déjà lancé ne le voit pas tout seul. Un **nouveau message** après
sauvegarde suffit.

Ce n’est **pas** une clé OVH. Ce n’est **pas** une clé SSH. C’est uniquement
le badge Doppler du projet `artcb-4`.

---

## Secret 2 — `SSH_PRIVATE_KEY` dans Doppler `artcb-4`

**Tu n’as pas à me la demander, et je ne te la collerai pas.**

| Ce que c’est | Ce que ce n’est PAS |
|--------------|---------------------|
| Un bloc qui commence par `-----BEGIN OPENSSH PRIVATE KEY-----` (ou `BEGIN RSA`) | La ligne `ssh-ed25519 AAAA…` |
| La clé de la **porte** du serveur | Le secret Cursor `ARTCB_OVH_NODE_4` (c’est la **serrure**, la clé **publique**, déjà dans git) |

La serrure publique est connue (empreinte
`SHA256:LGMsEgc8sgimQVmwvPUCC7je8AT6ft4vC9lmJWcmXcc`, commentaire
`artcb-ovh-node-4`). La clé privée n’est **pas** dans Cursor, **pas** dans git,
**pas** sur le nœud 1. L’agent qui a créé la VM l’avait ; cette machine d’agent
n’existe plus.

### Cas A — tu l’as déjà collée dans Doppler `artcb-4`

Nom du secret : **`SSH_PRIVATE_KEY`**. Dès que le badge Cursor (secret 1) est
là, **je la lis tout seul**. Tu n’as rien d’autre à faire.

### Cas B — tu ne l’as pas (le plus probable)

**Ne la fabrique pas. Ne la cherche pas dans tes mails. Ne colle rien.**

Dès que j’ai `KEY_API_ARTCB_DOPPLER_4` :

1. J’ouvre le coffre `artcb-4` (tes clés OVH déjà mises).
2. Si `SSH_PRIVATE_KEY` y est → SSH vers `ubuntu@91.134.45.8`.
3. Si elle n’y est pas → je génère une nouvelle paire, je range la **privée**
   dans Doppler `artcb-4` (jamais le chat, jamais git), j’ajoute la **publique**
   sur la VM via l’API OVH / la console, **sans rescue**.

---

## Ce que j’ai mesuré (2 sept. 2026) — pas inventé

| Check | Résultat |
|-------|----------|
| Nœud 4 allumé `http://91.134.45.8:8000/health` | HTTP **200** |
| SHA du process nœud 4 | `f28418084d84e00d3d5290ceefb846b30af527de` (branche `cursor/artcb-me-official-16d8`) — **pas encore** `origin/main` |
| `origin/main` / live OVH1 | `ad017bca05c2e3799c7dcd120ca1797968d499b6` — égaux |
| `KEY_API_ARTCB_DOPPLER_4` injecté dans cet agent | **non** |
| Jeton nœud 1 / 2 / 3 → projet `artcb-4` | **400** (pas le droit) |
| Clés `OVH_*` du tableau Cursor | **403** « This credential does not exist » (vieilles clés nœud 1, pas `xy4589-ovh`) |
| SSH nœud 4 avec clé nœud 1 ou nœud 2 | `Permission denied (publickey)` — normal |

Les nouvelles clés OVH (`xy4589-ovh`, projet `926bb1d6755e4f2c98ae9db06ef44e4f`)
doivent vivre **uniquement** dans Doppler `artcb-4`. Une fois le badge Cursor
posé, je les lis là. Pas besoin de les recoller dans Cursor.

---

## Quand c’est bon

Tu m’écris **uniquement** :

```text
token Cursor collé
```

Ensuite je peux SSH / console VNC / keep-book OVH4 sur `origin/main` **sans
rescue**, sans te redemander de coller des PEM dans le chat.
