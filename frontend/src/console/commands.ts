/** Console.tsx — commandes miroir CLI artcb_cli.py (fetch API réelle). */

export const CONSOLE_HELP = `ARTCB Console — commandes (API réelle, pas de mock):

  help                    — cette aide
  clear                   — effacer l'écran

  CORE
  health                  — GET /api/v1/health
  pol                     — GET /api/v1/pol/score
  metrics                 — GET /api/v1/metrics
  system hardware         — GET /api/v1/system/hardware
  system optimization     — GET /api/v1/system/optimization

  CHAÎNE
  chain                   — GET /api/v1/chain
  chain verify            — GET /api/v1/chain/verify
  chain block <index>     — GET /api/v1/chain/block/{index}

  WALLETS
  wallets                 — GET /api/v1/wallet/list
  wallet create <name>    — POST /api/v1/wallet/create

  AGENTS & MINAGE
  agents <texte>          — POST /api/v1/agents/run
  mining status           — GET /api/v1/dashboard/mining/status
  mining latest           — GET /api/v1/dashboard/logs/mining-latest

  GROUPES & GOUVERNANCE
  groups <address>        — GET /api/v1/groups?address=
  governance proposals    — GET /api/v1/governance/proposals

  CONNECTEURS & NOTIFS
  connectors              — GET /api/v1/connectors
  connectors formats      — GET /api/v1/connectors/formats
  notifications           — GET /api/v1/notifications/channels

  DASHBOARD
  founders                — GET /api/v1/dashboard/founders/allocation
  demo log                — GET /api/v1/dashboard/logs/demo-live

CLI terminal équivalent:
  python3 scripts/artcb_cli.py <commande> [--base URL]
  Voir API_REFERENCE_ARTCB.md
`;
