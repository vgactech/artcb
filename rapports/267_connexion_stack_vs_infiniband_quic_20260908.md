# 267 — Stack de connexion ARTCB mesurée vs InfiniBand / 800G / QUIC / WireGuard

Date mesure : **2026-09-08T16:24:05Z** (plus GET HTTP versions 16:24:45Z).  
JSON brut : `logs/267_stack_20260908T162405Z.json`  
SHA live ×4 : `230b8eb5a5c9569e7baed5b866c3f200f57de52f`

## Réponse courte

ARTCB **n’utilise pas** InfiniBand NDR/XDR, Terabit Ethernet 800G, RoCE, QUIC/HTTP/3, gRPC-Protobuf comme mesh, ni WireGuard/NordLynx comme tunnel inter-nœuds.

Ce qui tourne **en 2026 sur les 4 VM officielles** : IPv4 public, NIC virtuelle (`ens3` / `ens5`), **nginx 1.24.0** TLS, **uvicorn HTTP/1.1** `:8000`, API JSON REST, PBFT en HTTP JSON, Bearer HTTPS `:8443`. Latence mesurée depuis le VM agent Cursor : **~350–510 ms** aller-retour GET `/health`, pas les **< 1 µs** d’un fabric HPC.

Le tableau marketing collé dans le prompt décrit des produits **data-center / VPN grand public**. Ce n’est pas l’infra ARTCB actuelle.

## 1. Couche matérielle (mesurée SSH ×4)

| Nœud | Hostname | NIC | `/sys/class/infiniband` | Speed ethtool | WireGuard |
|---|---|---|---|---|---|
| ovh-node-1 `152.228.144.34` | artcb-node-1 | `ens3` | **absent** | Unknown / `-1` (virtio) | **NO_WIREGUARD**, `wg` absent |
| ovh-node-2 `151.80.107.29` | node-artcb-ovh-2 | `ens3` | **absent** | Unknown / `-1` | **NO_WIREGUARD** |
| aws-node-3 `51.44.222.232` | ip-172-31-8-93 | `ens5` | **absent** | vide (ENA virtuel) | **NO_WIREGUARD** |
| ovh-node-4 `91.134.45.8` | node-artcb-ovh-4 | `ens3` | **absent** | Unknown / `-1` | **NO_WIREGUARD** |

SSH rc = 0 ×4. Kernel : Ubuntu 6.8 OVH / 7.0 AWS. Pas de device RDMA.

Comparé au tableau opérateur :

| Technologie du tableau | Sur ARTCB live |
|---|---|
| InfiniBand NDR/XDR 400–800 Gbps, < 1 µs | **Non** |
| Terabit Ethernet 800G | **Non** — IPv4 Internet / virtio cloud |
| RoCE | **Non** |

Ce sont des VMs GRA11 / AWS eu-west-3 (`t3` côté AWS3 dans les rapports antérieurs), pas un cluster HPC à fabric dédié.

## 2. Couche logicielle & protocoles (mesurée)

### Ce qui écoute

OVH1 `ss` : `:80`, `:443`, `:8443` nginx ; `:8000` uvicorn (`python` pid). Même schéma sur les 4 (probe `ss` ×4 dans le JSON).

nginx **1.24.0 (Ubuntu)**, OpenSSL 3.0.13. Compilé avec `--with-http_v2_module`. **Pas** `--with-http_v3_module` / quic dans `nginx -V`.

Fichiers listen (OVH1) :

```
listen 80;
listen 443 ssl;          # Certbot — pas de flag http2
listen 8443 ssl;         # artcb-tls.conf — pas de flag http2
```

`proxy_http_version 1.1` dans `deploy/nginx/artcb-me-http.conf`. Header `Upgrade` présent (capacité WebSocket **possible** au reverse-proxy) ; le mesh nœud-nœud **n’est pas** un canal WebSocket persistant : c’est du **HTTP JSON** vers `:8000`.

### Versions HTTP depuis ce VM (curl 8.5.0, nghttp2, **pas** HTTP/3)

`curl --http3-only` : `the installed libcurl version doesn't support this`.

GET (pas HEAD : HEAD `/health` = **405** allow GET) :

| URL | `--http1.1` | `--http2` | HTTP/3 |
|---|---|---|---|
| `https://152.228.144.34:8443/health` | **HTTP/1.1** 200 ~0,49 s | **HTTP/1.1** 200 ~0,50 s (pas de h2 negocié) | non supporté client |
| `https://artcb.me/health` | **HTTP/1.1** 200 ~0,49 s | **HTTP/1.1** 200 ~0,49 s | idem |
| `http://152.228.144.34:8000/health` | HTTP/1.1 200 ~0,35 s, `Server: uvicorn` | reste 1.1 | n/a |

GET urllib `/health` HTTPS OVH1 : HTTP **200**, `Server: nginx/1.24.0 (Ubuntu)`, **`Alt-Svc` absent** (pas d’annonce h3), `X-ARTCB-Trace-Ns` = 38 303 772 (serveur). Client `dur_ns` = 509 626 848.

Le script avait marqué `http2_in_nginx: true` parce que **le binaire** a le module v2. La **socket** n’a pas `listen … http2`. Le trafic réel mesuré est **HTTP/1.1**.

### Mesh applicatif

| Chemin | Protocole réel |
|---|---|
| Santé / API opérateur | HTTPS nginx → uvicorn, JSON, Bearer |
| Replica / P2P / PBFT | HTTP `:8000` JSON (PRE-PREPARE, PREPARE, COMMIT, certificate, client-request) |
| gRPC + Protobuf | **pas** le transport des 4 nœuds |
| QUIC 0-RTT | **non** |
| WebSocket persistante | **non** pour le consensus (HTTP requête/réponse) |

Ingest mémo 267 : POST `/ai/memo` ~16,7 s (`dur_ns` 16 719 898 784) dont PBFT view 6, cert ×4. Ce n’est pas un handshake 0-RTT QUIC.

Comparé au tableau opérateur :

| Tableau | ARTCB live |
|---|---|
| QUIC / HTTP/3 +20–40 % vs H2 | **Non déployé** ; on est en HTTP/1.1 TLS |
| gRPC 10× vs REST/JSON | Mesh = **REST/JSON** |
| WebSockets −95 % vs polling | Consensus = **POST HTTP**, pas un socket bidirectionnel dédié |

## 3. Couche sécurité / VPN (mesurée)

| Tableau | ARTCB live |
|---|---|
| WireGuard 80–92 % de la ligne | **`wg` absent**, `wg show` = `NO_WIREGUARD` ×4 |
| NordLynx / Lightway | **Non** (produits VPN grand public, hors stack) |

Chiffrement réel : TLS sur `:443` / `:8443` (Let’s Encrypt côté `artcb.me` ; cert IP `:8443` pinné côté agent). Pas de tunnel WireGuard entre OVH1/2/AWS3/OVH4. Isolation Doppler **n’est pas** un VPN.

Crypto nœud (hors sujet réseau mais mesuré health) : `pqc=ML-DSA-65` annoncé ; politique D-032 B (Ed25519 temporaire jusqu’au 2026-12-31). Ce n’est **pas** InfiniBand.

## 4. Latence honnête (pas du marketing HPC)

Depuis le cloud agent Cursor vers OVH1 :

- GET HTTP `:8000` `/health` : ~349 ms client, ~29 ms `X-ARTCB-Trace-Ns` serveur
- GET HTTPS `:8443` `/health` : ~510 ms client, ~38 ms serveur
- SSH probe stack : ~2,4–3,2 s par nœud (commande python distante, pas le RTT TCP seul)

InfiniBand « < 1 microseconde » : **trois à six ordres de grandeur en dessous** de ce chemin Internet VM→VM. On ne revendique pas ces chiffres.

## 5. Si l’on voulait se rapprocher du tableau (constat, pas un déploiement)

Sans l’avoir fait dans ce tour :

- Activer `listen 443 ssl http2;` (le module v2 est **déjà compilé**)
- HTTP/3 exigerait nginx+quic / un client nghttp3 — **absent** aujourd’hui
- gRPC changerait le protocole PBFT (aujourd’hui JSON)
- InfiniBand / 800G / RoCE = autre classe de machines, pas ces 4 IPv4 publics
- WireGuard = overlay optionnel ; **pas** en place

Rien de tout cela n’est « la techno actuelle ». La techno actuelle est **HTTP/1.1 + TLS + JSON + PBFT HTTP**.

## Fichiers

- `logs/267_stack_20260908T162405Z.json`
- `scripts/artcb267_measure_stack.py`
- `deploy/nginx/artcb-me-http.conf` (`proxy_http_version 1.1`)
