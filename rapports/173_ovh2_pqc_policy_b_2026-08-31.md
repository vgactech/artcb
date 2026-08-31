# Rapport 173 — OVH2 live + politique crypto B (ML-DSA-65 prioritaire)

**Horodatage UTC :** 2026-08-31T18:50:00Z  
**Branche :** `cursor/ovh2-pqc-policy-b-16d8`  
**OVH1 :** `5b4b24ae` — **non redéployé**  
**AWS3 probe avant PQC :** `66244d7` Ed25519 fallback  
**OVH2 :** instance créée GRA11 d2-8  
**Certification :** `READY FOR NEXT TEST` — **NOT MAINNET CERTIFIED**.

Aucun secret n’est reproduit ici. Les V-01…V-07 **tokenomics** restent provisoires (série économique). Les validations distribuées sont **DV-01…DV-07**.

---

## A. Décisions gelées

| ID | Choix utilisateur | Contenu |
|----|-------------------|---------|
| D-032 | **B** (+ C si PQC présent) | ML-DSA-65 prioritaire ; Ed25519 temporaire jusqu’au 2026-12-31T00:00:00Z ; hybrid:ed25519+ML-DSA-65 dès que liboqs est là ; anti-downgrade par peer_id |
| D-033 | DV profil B | DV-01 C, DV-02 C, DV-03 B, DV-04 C, DV-05 C, DV-06 B, DV-07 C |
| V éco | inchangé | Snapshot / transfer / grace / retire / finality / H_adult / HBP toujours ⏳ |

IAM : droits larges **conservés** en phase test (ordre utilisateur). Rotation des secrets exposés : après validation d’accès, clés AWS renouvelées dans Doppler `artcb3` (détail dans la section rotation du run).

---

## B. OVH2 — instance réelle

| Champ | Valeur publique |
|-------|-----------------|
| projet | `1fc10a3fb27d4511a8c7873cd16243f2` status `ok` |
| nic | `vc491276-ovh` |
| instance | `node-artcb-ovh-2` `6470522e-1561-4741-9254-5f58b909eeb9` |
| région / flavor | GRA11 / d2-8 |
| IPv4 | `151.80.107.29` |
| SSH | `ubuntu@151.80.107.29` clé `artcb-ovh-node-2` |

OVH1 `152.228.144.34` n’a pas été modifié.

---

## C. Politique crypto exposée

`/health` et `/api/v1/p2p/status` publient `protocol_version=173-devnet-1` + `pqc.policy` (B).  
`PeerManager.add_peer` refuse un downgrade ML-DSA → Ed25519-only pour le même `peer_id`.

---

## D. Déploiement / PQC

Renseigné après `deploy_ovh2.sh` + compile native liboqs (AWS3 + OVH2).

Tests unitaires 170–173 : **19 passed** (pré-deploy).
