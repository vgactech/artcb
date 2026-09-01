"""Phase 193 — hunt OVH credit, refuse Eco order without prepaid+stock."""

from __future__ import annotations

from pathlib import Path

from artcb.devnet_validation import DECISIONS_193, certification_gate, public_lock
from artcb.node_registry import NODES

ROOT = Path(__file__).resolve().parents[1]


def test_d047_does_not_invent_ten_euros_prepaid() -> None:
    text = DECISIONS_193["D-047"]
    assert "xy4589-ovh" in text
    assert "0.00 EUR" in text
    assert "10.00 EUR" in text
    assert "Public Cloud" in text
    assert "25skb012" in text
    assert "unavailable" in text
    assert "certified_distributed_mainnet stays false" in text


def test_baremetal_slot_still_has_no_ip() -> None:
    spec = NODES["ovh-baremetal-1"]
    assert spec.ssh_host is None
    assert spec.health_http is None
    assert "xy4589-ovh" in spec.public_notes
    assert "0.00 EUR" in spec.public_notes
    assert "152.228.144.34" in spec.public_notes
    assert "Never reuse" in spec.public_notes


def test_quote_still_refuses_order_without_ovh3() -> None:
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from ovh_baremetal_quote import measure_ovh3_credit, quote

    credit = measure_ovh3_credit()
    assert credit["invented"] is False
    assert credit.get("balance_eur") is None
    quoted = quote(want_order=True)
    assert quoted["invented_balance"] is False
    assert quoted["order"]["executed"] is False
    assert quoted["selected"]["planCode"] == "25skb012"
    assert quoted["selected"]["price_eur"] == 9.99


def test_lock_exposes_d047_and_stays_uncertified() -> None:
    lock = public_lock()
    assert "decisions_193" in lock
    assert "D-047" in lock["decisions_193"]
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


def test_sim193_forbids_wipe_checkout_and_replit_hosts() -> None:
    sim = (ROOT / "scripts" / "run_sim193_ovh_order.py").read_text(encoding="utf-8")
    assert "install.sh" in sim
    assert "init_genesis.py" in sim
    assert "init-node" in sim
    assert "checkout" in sim
    assert "vgac42371" not in sim
    assert "vgacofficiel" not in sim
    assert "Never invent" in sim
    assert "Never POST /order/cart" in sim
