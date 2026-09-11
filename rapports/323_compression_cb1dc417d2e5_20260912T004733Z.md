# R323 — compression + publisher-death matrix (R323_20260912T004733Z_cb1dc417d2e5)

`commit_sha` = `cb1dc417d2e50d0471dba5bb3c1810aa68d9b565`

`CERTIFIED_100=false`

## Official compression %

**NON ÉTABLI comme chiffre unique.** Voir tableaux par suite.

## Suites

### L4_8lang_same_meaning

- langs: fr, en, es, pt, it, ru, la, zh
- sum UTF-8 phrases: 294 B ; unique packet: 44 B ; bundle: 2383 B
- C_physique packet vs sum UTF-8: **85.034%**
- C_physique bundle vs sum UTF-8: **-710.5442%**
- C_semantic concepts vs tokens: **97.1429%**
- baselines joined: `{"raw_bytes": 301, "gzip": 252, "zlib": 240, "utf8": 301, "json_utf8": 320}`

### LONG_2lang_redundant

- langs: fr, en
- sum UTF-8 phrases: 344 B ; unique packet: 140 B ; bundle: 1164 B
- C_physique packet vs sum UTF-8: **59.3023%**
- C_physique bundle vs sum UTF-8: **-238.3721%**
- C_semantic concepts vs tokens: **92.0%**
- baselines joined: `{"raw_bytes": 345, "gzip": 209, "zlib": 197, "utf8": 345, "json_utf8": 358}`

### SINGLE_fr_short

- langs: fr
- sum UTF-8 phrases: 40 B ; unique packet: 44 B ; bundle: 309 B
- C_physique packet vs sum UTF-8: **-10.0%**
- C_physique bundle vs sum UTF-8: **-672.5%**
- C_semantic concepts vs tokens: **80.0%**
- baselines joined: `{"raw_bytes": 40, "gzip": 60, "zlib": 48, "utf8": 40, "json_utf8": 52}`

## Publisher-death matrix (simulated)

- A federation: **True**
- B independent replica (n2 no fallback): **False**
- C offline after ingest: **True**
- publisher_death_resilience: **False**

measurement.json sha256 = `9ae249cc5c36f4828b983c228a7e99021d7307454d03af677a0429e1e6a4cc65`

