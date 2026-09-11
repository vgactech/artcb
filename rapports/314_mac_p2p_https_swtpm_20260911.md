# R314 — swtpm/TPM + pourquoi P2P Mac n’était pas « direct »

**UTC :** 2026-09-11T16:30:00Z  
**CERTIFIED_100 :** `false`

## Pourquoi pas P2P Mac « directement » avant ?

| Chemin | Résultat mesuré |
|--------|-----------------|
| Peers IPv4 `:8000` (OVH/AWS) | **timeout** — filtre egress Mac → IPv4 publics (même famille que SSH) |
| RFC1918 `10.x:8001` comme URL publique | **interdit** (`private_or_loopback_forbidden`, R287) |
| Tunnel public inbound | **absent** (ngrok 0) → les seeds ne peuvent pas joindre le Mac |
| HTTPS `artcb.me` / `n2|n3|n4.artcb.me:443` | **OK** (avec `artcb_dns_fix`) |

Donc on ne « saute » pas le tunnel pour le **fan-in** PBFT. En revanche on **peut** faire du **P2P outbound** Mac → seeds en HTTPS.

## Fait ce tour

1. Ajout peers HTTPS ×4 sur Mac (`peer_*_artcb_me_443`).
2. `POST /p2p/sync/peer_artcb_me_443` → HTTP 200, pull **received 783** (chiffré), **imported 0** blocs chaîne (livre Mac ≠ tip seeds ; anonymous public ≠ full book).
3. Hauteur Mac contexte reste **8** vs seeds **~1160** — tip×5 **FAIL** tant que replica officielle / catch-up livre non fait.
4. Script : `scripts/artcb_mac_p2p_https_peers.py [--sync]`.

## TPM / swtpm

- `libtpms` **installé**.
- Brew **encore** sur deps (`mpfr` make check / suite X11) — `swtpm` pas encore dans Cellar.
- Rappel R281/R284 : **guest swtpm ≠ L3/L4** ; max honnête Mac = SOFTWARE_TPM / NOT_APPLICABLE L4.

## Suite

1. Laisser finir `brew install swtpm` (ou reprendre si FAIL).
2. Démarrer swtpm socket local + classer SOFTWARE_TPM.
3. Catch-up livre Mac (replica officielle / import contrôlé — **jamais wipe**).
4. Tunnel public si fan-in PBFT Mac requis.
