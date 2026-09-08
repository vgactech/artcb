"""261 — observe partition vs crash. No live SSH. Not PBFT.

Majority 3/4 still has Q=3 → partitioned=false.
Isolated view 1/4 is below quorum → partitioned=true.
"""

from __future__ import annotations

from artcb.consensus.liveness import assess_liveness


def test_majority_three_of_four_not_below_quorum() -> None:
    majority = assess_liveness(
        include_self=False,
        peer_reachable=[
            ("http://152.228.144.34:8000", True, 1),
            ("http://151.80.107.29:8000", True, 1),
            ("http://51.44.222.232:8000", True, 1),
            ("http://91.134.45.8:8000", False, None),
        ],
    )
    assert majority.n == 4 and majority.q == 3
    assert majority.reachable == 3
    assert majority.below_quorum is False
    assert majority.partitioned is False


def test_isolated_node_sees_below_quorum() -> None:
    isolated = assess_liveness(
        include_self=False,
        peer_reachable=[
            ("http://152.228.144.34:8000", False, None),
            ("http://151.80.107.29:8000", False, None),
            ("http://51.44.222.232:8000", False, None),
            ("http://91.134.45.8:8000", True, 1),
        ],
    )
    assert isolated.reachable == 1
    assert isolated.below_quorum is True
    assert isolated.partitioned is True
