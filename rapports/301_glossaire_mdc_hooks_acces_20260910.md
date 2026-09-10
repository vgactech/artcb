# 301 — glossaire thinking / .mdc / hooks / accès Mac

**2026-09-10T10:40:00Z.** `CERTIFIED_100=false`. Aucune valeur de mot de passe dans ce fichier.

## Mot de passe sudo Mac

- **Pas** dans Doppler `artcb-1/prd` (noms mesurés : API, wallet passphrase, SSH Cursor — pas SUDO/ROOT).
- Fuite historique dans `rapports/285_…` et `rapports/288_…` **laissée** (règles 11–15). Ne plus recoller. Rotation : `passwd`.
- L’agent ne doit **pas** réafficher la valeur. Accès agent ≠ root.

## Accès de cet agent

Workspace : `/Users/deyi/.bob/playground`. Avec approbation : `~/.ssh`, `~/.artcb`, Doppler CLI, LAN, SSH VMs. **Pas** la totalité du Mac (sandbox, pas Keychain entier, pas sudo par défaut).

## Carte des règles — chemins absolus

Voir `.cursor/rules/artcb-read-all.mdc` section « Chemins absolus ».
