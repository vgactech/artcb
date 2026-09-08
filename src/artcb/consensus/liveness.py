"""Partition / failover *observation* — does not steal produce, does not stop nodes.

188 live BFT is settlement prepare/commit (N=4, F=1, Q=3).
Block append is still longest valid public chain. GO-E produce stays off.

This module answers: can we still form a quorum right now?
It is a detector, not a demonstrated adversarial partition test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.artcb.consensus.live_bft import n_f_q
from src.artcb.trace.ns import now_mono_ns, now_wall_ns


@dataclass
class PeerPulse:
    host: str
    reachable: bool
    rtt_ns: int | None = None
    error: str | None = None


@dataclass
class LivenessReport:
    n: int
    f: int | None
    q: int
    reachable: int
    below_quorum: bool
    partitioned: bool
    would_failover: bool
    pulses: list[PeerPulse] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "f": self.f,
            "q": self.q,
            "reachable": self.reachable,
            "below_quorum": self.below_quorum,
            "partitioned": self.partitioned,
            "would_failover": self.would_failover,
            "pulses": [
                {
                    "host": p.host,
                    "reachable": p.reachable,
                    "rtt_ns": p.rtt_ns,
                    "error": p.error,
                }
                for p in self.pulses
            ],
            "ts_ns": now_wall_ns(),
            "scope": "liveness_observe_only",
            "not_block_append_bft": True,
            "nodes_not_stopped": True,
            "note": self.note,
        }


def assess_liveness(
    *,
    self_reachable: bool = True,
    peer_reachable: list[tuple[str, bool, int | None]] | None = None,
    producer_silent: bool = False,
    include_self: bool = True,
) -> LivenessReport:
    """Pure function — tests inject the reachability matrix. No live SSH.

    peer_reachable: (host, ok, rtt_ns)
    """
    pulses: list[PeerPulse] = []
    if include_self:
        pulses.append(
            PeerPulse(host="self", reachable=self_reachable, rtt_ns=0 if self_reachable else None)
        )
    for host, ok, rtt in peer_reachable or []:
        pulses.append(PeerPulse(host=host, reachable=ok, rtt_ns=rtt, error=None if ok else "unreachable"))
    n_declared = len(pulses)
    reachable = sum(1 for p in pulses if p.reachable)
    _n, f, q = n_f_q(n_declared)
    below = reachable < q
    return LivenessReport(
        n=n_declared,
        f=f,
        q=q,
        reachable=reachable,
        below_quorum=below,
        partitioned=below,
        would_failover=producer_silent and not below,
        pulses=pulses,
        note=(
            "observe only — GO-E produce off; do not stop official nodes to 'test' this. "
            "BFT for settlement remains /consensus/propose. Block append is longest chain."
        ),
    )


def probe_hosts(hosts: list[str], *, timeout: float = 1.5) -> list[tuple[str, bool, int | None]]:
    """HTTP /health on each host. Used by the route; tests mock this."""
    import urllib.request

    out: list[tuple[str, bool, int | None]] = []
    for host in hosts:
        url = host if host.startswith("http") else f"http://{host}:8000/health"
        if not url.endswith("/health"):
            url = url.rstrip("/") + "/health"
        t0 = now_mono_ns()
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                ok = 200 <= resp.status < 400
            out.append((host, ok, now_mono_ns() - t0))
        except Exception:
            out.append((host, False, now_mono_ns() - t0))
    return out
