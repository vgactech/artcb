# R326 — tip diverge P0 (R326_20260912T015951Z_a79685493370)

`commit_sha` = `a7968549337064c5bea28baa79e0542d3c226901`

`CERTIFIED_100=false`

## Verdict

**P0_STATUS_SEMANTICS_AND_PUBLIC_STALL**

ovh1 height inflation is almost entirely visibility=private blocks without pbft_cert after public tip 1140; n2/n3/n4 public tip still 1140 hash 013f327cb76bef8b…

- classic_pbft_split_brain_675_public: **False**
- public tip aligned @1140: **True**
- ovh1 after 1140 private: 710 ; public_after: 0 ; with_cert: 0
- heights raw: `{'https://artcb.me': 1855, 'https://n2.artcb.me': 1141, 'https://n3.artcb.me': 1141, 'https://n4.artcb.me': 1141}`

## Action

Do not rewind/wipe. Report public_tip separately from total height. Investigate why public PBFT append stopped at 1140. Hole 716 remains secondary to public stall + private-only ovh1 growth.

Never invent 717. Never wipe.

