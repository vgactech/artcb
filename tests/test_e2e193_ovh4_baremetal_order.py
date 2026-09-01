"""Phase 193 — OVH4 Eco commander gates. No invented prepaid, no OVH2 order."""

from __future__ import annotations

from pathlib import Path

from artcb.devnet_validation import DECISIONS_193, certification_gate, public_lock
from artcb.node_registry import NODES

ROOT = Path(__file__).resolve().parents[1]


def test_d047_ovh4_credit_is_public_cloud_not_prepaid() -> None:
    text = DECISIONS_193["D-047"]
    assert "xy4589-ovh" in text
    assert "0.00" in text
    assert "Public Cloud" in text
    assert "vc491276-ovh" in text
    assert "91.134.45.8" in text
    assert "25skb012" in text
    lock = public_lock()
    assert "decisions_193" in lock
    assert lock["decisions_193"]["D-047"] == text


def test_ovh_baremetal_1_still_has_no_ip() -> None:
    spec = NODES["ovh-baremetal-1"]
    assert spec.ssh_host is None
    assert spec.health_http is None
    assert spec.api_https is None
    assert "91.134.45.8" in spec.public_notes
    assert "Never destroy" in spec.public_notes
    assert NODES["ovh-node-4"].ssh_host == "91.134.45.8"
    assert NODES["ovh-node-4"].ssh_host != spec.ssh_host


def test_decide_order_blocks_zero_prepaid_and_ovh2() -> None:
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from ovh4_baremetal_order import decide_order

    dedicated_empty = {"http": 200, "count": 0, "servers": [], "eco_in_delivery": False}
    sku = {"planCode": "25skb012", "price_eur": 9.99, "in_stock": True}
    ovh2 = decide_order(
        nic="vc491276-ovh",
        me_http=200,
        prepaid_eur=100.0,
        dedicated=dedicated_empty,
        sku=sku,
        want_order=True,
    )
    assert ovh2["executed"] is False
    assert ovh2["blocked_reason"] == "forbidden_nic_ovh2_vc491276"

    zero = decide_order(
        nic="xy4589-ovh",
        me_http=200,
        prepaid_eur=0.0,
        dedicated=dedicated_empty,
        sku=sku,
        want_order=True,
    )
    assert zero["executed"] is False
    assert zero["blocked_reason"] == "prepaid_below_sku"

    rupture = decide_order(
        nic="xy4589-ovh",
        me_http=200,
        prepaid_eur=10.0,
        dedicated=dedicated_empty,
        sku={"planCode": "25skb012", "price_eur": 9.99, "in_stock": False},
        want_order=True,
    )
    assert rupture["executed"] is False
    assert rupture["blocked_reason"] == "sku_unavailable"

    already = decide_order(
        nic="xy4589-ovh",
        me_http=200,
        prepaid_eur=20.0,
        dedicated={"http": 200, "count": 1, "servers": [{"name": "ns123"}], "eco_in_delivery": True},
        sku=sku,
        want_order=True,
    )
    assert already["executed"] is False
    assert already["blocked_reason"] == "dedicated_already_listed_or_delivering"


def test_certification_stays_false() -> None:
    gate = certification_gate(
        {
            "DV-01": "PASS",
            "DV-02": "PASS",
            "DV-03": "PASS",
            "DV-04": "PASS",
            "DV-05": "PASS",
            "DV-06": "PASS",
            "DV-07": "PASS",
        }
    )
    assert gate["certified_distributed_mainnet"] is False


def test_commander_script_lists_servers_before_order() -> None:
    body = (ROOT / "scripts" / "ovh4_baremetal_order.py").read_text(encoding="utf-8")
    assert "list_dedicated_servers" in body
    assert body.index("list_dedicated_servers") < body.index("want_order")
    assert "vc491276-ovh" in body
    assert "91.134.45.8" in body
    assert "Never prints API keys" in body
    assert "CREDIT_CARD" in body
