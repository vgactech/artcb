"""Phase 194 — operator GO may charge the OVH4 preferred card for one Eco."""

from __future__ import annotations

from pathlib import Path

from artcb.devnet_validation import DECISIONS_194, certification_gate, public_lock
from artcb.node_registry import NODES

ROOT = Path(__file__).resolve().parents[1]


def test_d048_operator_go_allows_card_on_ovh4_only() -> None:
    text = DECISIONS_194["D-048"]
    assert "xy4589-ovh" in text
    assert "CREDIT_CARD" in text
    assert "Public Cloud" in text
    assert "91.134.45.8" in text
    assert "GRA/RBX/SBG" in text
    assert "400/402" in text
    lock = public_lock()
    assert lock["decisions_194"]["D-048"] == text


def test_d049_hourly_measured_month_only_and_existing_order_stops() -> None:
    text = DECISIONS_194["D-049"]
    assert "intervalUnit is month" in text
    assert "0 hour" in text
    assert "258100013" in text
    assert "1 mois" in text
    assert "does not POST --order" in text
    assert "91.134.45.8" in text
    assert public_lock()["decisions_194"]["D-049"] == text


def test_eco_catalog_intervals_reads_unit_not_1h_stock() -> None:
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from ovh_baremetal_quote import eco_catalog_intervals

    fixture = {
        "plans": [
            {
                "planCode": "25skb012",
                "invoiceName": "KS-B",
                "pricings": [
                    {
                        "interval": 1,
                        "intervalUnit": "month",
                        "capacities": ["renew"],
                        "price": 999000000,
                        "description": "rental for 1 month",
                        "mode": "default",
                    },
                    {
                        "interval": 0,
                        "intervalUnit": "none",
                        "capacities": ["installation"],
                        "price": 999000000,
                    },
                ],
            },
            {
                "planCode": "24sk50-v1",
                "invoiceName": "KS-5",
                "pricings": [
                    {
                        "interval": 1,
                        "intervalUnit": "month",
                        "capacities": ["renew"],
                        "price": 1799000000,
                        "description": "rental for 1 month",
                        "mode": "default",
                    }
                ],
            },
        ]
    }
    measured = eco_catalog_intervals(fixture)
    assert measured["invented"] is False
    assert measured["hourly_exists"] is False
    assert measured["hourly_plan_count"] == 0
    assert measured["monthly_plan_count"] == 2
    assert measured["billing"] == "month_only"
    assert measured["renew_interval_units"] == {"month": 2}
    hour_fixture = {
        "plans": [
            {
                "planCode": "fake-hour",
                "invoiceName": "fake",
                "pricings": [
                    {
                        "interval": 1,
                        "intervalUnit": "hour",
                        "capacities": ["renew"],
                        "price": 10000000,
                    }
                ],
            }
        ]
    }
    hourly = eco_catalog_intervals(hour_fixture)
    assert hourly["hourly_exists"] is True
    assert hourly["billing"] == "hour_only"


def test_pick_cheapest_combo_prefers_fr_then_price() -> None:
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from ovh4_baremetal_order import pick_cheapest_combo

    syd = {
        "planCode": "24sk302-syd",
        "total_eur": 18.99,
        "dcs_fr": [],
        "dcs_all": [{"dc": "syd"}],
    }
    rbx = {
        "planCode": "24sk50-v1",
        "total_eur": 26.99,
        "dcs_fr": [{"dc": "rbx"}],
        "datacenter": "rbx",
    }
    gra_dearer = {
        "planCode": "24sk50-v1",
        "total_eur": 34.99,
        "dcs_fr": [{"dc": "gra"}],
        "datacenter": "gra",
    }
    picked = pick_cheapest_combo([syd, rbx, gra_dearer])
    assert picked is not None
    assert picked["total_eur"] == 26.99
    assert picked["datacenter"] == "rbx"
    tie = pick_cheapest_combo(
        [
            {"total_eur": 26.99, "dcs_fr": [{"dc": "rbx"}], "datacenter": "rbx"},
            {"total_eur": 26.99, "dcs_fr": [{"dc": "gra"}], "datacenter": "gra"},
        ]
    )
    assert tie is not None
    assert tie["datacenter"] == "gra"


def test_decide_order_go_opens_card_tender_without_executing() -> None:
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from ovh4_baremetal_order import decide_order

    dedicated_empty = {"http": 200, "count": 0, "servers": [], "eco_in_delivery": False}
    sku = {
        "planCode": "24sk50-v1",
        "total_eur": 26.99,
        "in_stock": True,
        "fqn": "24sk50-v1.ram-32g-ecc-2400.softraid-3x4000sa",
        "datacenter": "rbx",
    }
    dry = decide_order(
        nic="xy4589-ovh",
        me_http=200,
        prepaid_eur=0.0,
        dedicated=dedicated_empty,
        sku=sku,
        want_order=True,
        operator_go=False,
    )
    assert dry["executed"] is False
    assert dry["blocked_reason"] == "prepaid_below_sku"

    go = decide_order(
        nic="xy4589-ovh",
        me_http=200,
        prepaid_eur=0.0,
        dedicated=dedicated_empty,
        sku=sku,
        want_order=True,
        operator_go=True,
    )
    assert go["executed"] is False
    assert go["blocked_reason"] is None
    assert go["would_order"]["tender"] == "preferred_payment_method_CREDIT_CARD"
    assert go["would_order"]["planCode"] == "24sk50-v1"

    ovh2 = decide_order(
        nic="vc491276-ovh",
        me_http=200,
        prepaid_eur=0.0,
        dedicated=dedicated_empty,
        sku=sku,
        want_order=True,
        operator_go=True,
    )
    assert ovh2["executed"] is False
    assert ovh2["blocked_reason"] == "forbidden_nic_ovh2_vc491276"

    already = decide_order(
        nic="xy4589-ovh",
        me_http=200,
        prepaid_eur=0.0,
        dedicated={"http": 200, "count": 1, "servers": [{"name": "ns1"}], "eco_in_delivery": True},
        sku=sku,
        want_order=True,
        operator_go=True,
    )
    assert already["executed"] is False
    assert already["blocked_reason"] == "dedicated_already_listed_or_delivering"


def test_ovh4_vm_kept_and_cert_false() -> None:
    assert NODES["ovh-node-4"].ssh_host == "91.134.45.8"
    assert NODES["ovh-baremetal-1"].ssh_host != "91.134.45.8"
    assert NODES["ovh-baremetal-1"].ssh_host is None
    assert "258100013" in NODES["ovh-baremetal-1"].public_notes
    assert "Do not POST a second --order" in NODES["ovh-baremetal-1"].public_notes
    gate = certification_gate(
        {letter: "PASS" for letter in ("DV-01", "DV-02", "DV-03", "DV-04", "DV-05", "DV-06", "DV-07")}
    )
    assert gate["certified_distributed_mainnet"] is False
    body = (ROOT / "scripts" / "ovh4_baremetal_order.py").read_text(encoding="utf-8")
    assert "list_dedicated_servers" in body
    assert body.index("list_dedicated_servers") < body.index("place_eco_order")
    assert "autoPayWithPreferredPaymentMethod" in body
    assert "Never prints API keys" in body
    assert "CREDIT_CARD" in body
    assert "91.134.45.8" in body
