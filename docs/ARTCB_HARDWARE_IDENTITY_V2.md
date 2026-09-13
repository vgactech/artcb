# ARTCB Hardware Identity v2

**Status:** SPEC + partial implementation (R339) — **CERTIFIED_100=false**  
**Date (UTC):** 2026-09-13T20:55:00Z  
**Extends (does not delete):** `hardware_identity.py` A–E, `replica_identity.py`, `tpm_quote.py`, R338 capability discovery.

## Verdict (this Mac)

| Field | Measured |
| --- | --- |
| Model | MacBookAir7,1 |
| RoT | NONE (no TPM / T2 / SE usable as native RoT) |
| `assurance_h` | **H1** |
| `native_c04` | **UNSUPPORTED_HARDWARE** |
| `fingerprint_v2` | present (hashes only) |
| NodeKey | Ed25519 local (`~/.artcb/node_identity_ed25519.key`) |
| C04 PASS via software | **forbidden** |

## Principles

1. Collect **all available** identifiers; missing field ≠ forbid enrollment.
2. Separate layers: `HardwareProfile` ≠ `NodePrivateKey` ≠ `NodeIdentity` ≠ `Certificate`.
3. Hash before network: serial, UUID, MAC, disk serial.
4. Stability weights: platform UUID/serial/board high; SSD/MAC/RAM low.
5. Fingerprint ≠ attestation. 100 IDs ≠ TPM.
6. `UNSUPPORTED_HARDWARE` = native C04 RoT absent — not `NODE_UNAUTHORIZED`.
7. External authenticator = **H2** (binding required); never auto-H3 for the Mac.
8. APPLE_T2 / APPLE_SE are **distinct** from TPM; never invent presence.

## Assurance ladder

| Level | Meaning | Node roles (policy draft) |
| --- | --- | --- |
| H0 | Declared software IDs only | Observer / limited |
| H1 | Inventory + NodeKey + challenge | Limited replica / non-critical |
| H2 | H1 + external non-exportable key + binding | Reinforced |
| H3 | Native TPM/T2/SE + verified attestation | Strong validator |
| H4 | H3 + measured boot + fresh attestation | Critical governance |

## Enrollment ceremony (target)

1. Hardware inventory → evidence list  
2. Security discovery (honest)  
3. Generate/load NodeKey (Ed25519)  
4. Server challenge → sign locally  
5. Submit public evidence + signature (no private key, no raw serial)  
6. Policy evaluate → certificate / reject / revalidate  
7. On-chain enrollment record (future)

## Revalidation / recovery

| Event | Policy |
| --- | --- |
| SSD replace | revalidation, not automatic NEW DEVICE |
| Motherboard replace | identity changed → revalidation / supersede cert |
| OS reinstall (no RoT) | software key lost → **recovery ceremony** |
| Clone of key+json to Mac B | reject unless fingerprint+challenge bind matches |

## macOS collectable fields (v1 collector)

Implemented in `src/artcb/platform/mac_hardware_inventory.py`:

- Platform: IOPlatformUUID, serial, board-id, model (hashed)
- Firmware: Boot ROM / SMC lines when present (hashed)
- CPU / RAM / storage profile / MAC hashes / USB+TB presence
- Security: TPM device nodes, T2 bridge probe, Apple Silicon flag, `rot_kind`

## Still OPEN (do not drop)

- Full CA-signed `NodeCertificate` on-chain
- External authenticator / FIDO2 H2 path
- Server challenge API wired to registry
- #77 N04 / C04 on capable hosts / TPM quote
- #86 ORG body multi-node ACL (`NOT_PROVEN_acl_session`)
- Anti-Sybil `sample_count≥50` then stats (not auto-certify)
- Rule telemetry depth / Genesis private / langage IA / V-01…V-07

## Code entrypoints

- `scripts/artcb_r339_mac_hardware_enrollment.py`
- `tests/test_r339_mac_hardware_inventory.py`
- R338: `capability_discovery.py` (unchanged meaning of UNSUPPORTED_HARDWARE)
