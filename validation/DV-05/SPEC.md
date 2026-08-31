# DV-05 — consensus (BLOCKED)

Live API has no BFT engine. Extracted from code:
- sim settlement quorum n//2+1
- sim finality N=2 confirmations
- N>=3F+1 is not implemented live
See `src/artcb/consensus_spec.py`.
