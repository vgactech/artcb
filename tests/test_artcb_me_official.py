"""Official public domain artcb.me (OVH4 registrar) + CORS transition. No order."""

from __future__ import annotations

import re
from pathlib import Path

from api.main import REPLIT_CORS_ORIGIN_REGEX, cors_allowed_origins, cors_hosts_for_domain
from artcb.config import (
    ARTCB_DNS_A_RECORDS,
    ARTCB_DOMAIN,
    ARTCB_DOMAIN_LABELS,
    ARTCB_DOMAIN_LEGACY,
    BOOTSTRAP_NODES,
)
from artcb.p2p.public_url import is_official_artcb_host, public_register_url_ok

ROOT = Path(__file__).resolve().parents[1]
DNS_SCRIPT = ROOT / "scripts" / "ovh4_artcb_me_dns.py"


def test_official_domain_is_artcb_me() -> None:
    assert ARTCB_DOMAIN == "artcb.me"
    assert ARTCB_DOMAIN_LEGACY == "artcb.space"
    cfg = (ROOT / "src" / "artcb" / "config.py").read_text(encoding="utf-8")
    assert 'ARTCB_DOMAIN = "artcb.me"' in cfg
    assert "artcb.space" in cfg
    env_ex = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "artcb.me" in env_ex
    assert "artcb.space" in env_ex


def test_dns_a_records_map_live_nodes() -> None:
    assert ARTCB_DNS_A_RECORDS[""] == "152.228.144.34"
    assert ARTCB_DNS_A_RECORDS["n1"] == "152.228.144.34"
    assert ARTCB_DNS_A_RECORDS["n2"] == "151.80.107.29"
    assert ARTCB_DNS_A_RECORDS["n3"] == "51.44.222.232"
    assert ARTCB_DNS_A_RECORDS["n4"] == "91.134.45.8"
    assert ARTCB_DNS_A_RECORDS["node"] == "152.228.144.34"
    assert "www" not in ARTCB_DNS_A_RECORDS or ARTCB_DNS_A_RECORDS["www"] == "152.228.144.34"
    assert set(ARTCB_DNS_A_RECORDS.values()) == {
        "152.228.144.34",
        "151.80.107.29",
        "51.44.222.232",
        "91.134.45.8",
    }
    seeds = " ".join(BOOTSTRAP_NODES)
    for ip in ARTCB_DNS_A_RECORDS.values():
        assert ip in seeds


def test_cors_origins_include_official_and_legacy() -> None:
    origins = cors_allowed_origins()
    assert "https://artcb.me" in origins
    assert "http://artcb.me" in origins
    assert "https://n1.artcb.me" in origins
    assert "https://n2.artcb.me" in origins
    assert "https://n3.artcb.me" in origins
    assert "https://n4.artcb.me" in origins
    assert "https://node.artcb.me" in origins
    assert "https://www.artcb.me" in origins
    assert "https://artcb.space" in origins
    assert "https://n1.artcb.space" in origins
    assert "https://n2.artcb.space" in origins
    assert "http://localhost:8000" in origins
    hosts_me = cors_hosts_for_domain("artcb.me")
    assert "artcb.me" in hosts_me
    for label in ARTCB_DOMAIN_LABELS:
        assert f"{label}.artcb.me" in hosts_me


def test_cors_regex_and_no_named_replit_account() -> None:
    assert REPLIT_CORS_ORIGIN_REGEX == r"https://.*\.(replit\.app|repl\.co|replit\.dev)"
    compiled = re.compile(REPLIT_CORS_ORIGIN_REGEX)
    assert compiled.match("https://any-clone.replit.app")
    assert compiled.match("https://foo.repl.co")
    assert not compiled.match("https://evil.example.com")
    assert not compiled.match("https://artcb.me")
    main = (ROOT / "src" / "api" / "main.py").read_text(encoding="utf-8")
    cfg = (ROOT / "src" / "artcb" / "config.py").read_text(encoding="utf-8")
    for blob in (main, cfg):
        assert "vgacofficiel.replit" not in blob
        assert "vgac42371" not in blob
        assert "artcb--vgacofficiel" not in blob
    assert "allow_origin_regex=REPLIT_CORS_ORIGIN_REGEX" in main
    assert "cors_allowed_origins()" in main


def test_p2p_allowlist_accepts_official_domain(monkeypatch) -> None:
    monkeypatch.delenv("ARTCB_PUBLIC_PEER_HOSTS", raising=False)
    ok, reason = public_register_url_ok("https://n1.artcb.me")
    assert ok is True
    assert reason == "official_domain"
    ok2, reason2 = public_register_url_ok("http://artcb.me:8000")
    assert ok2 is True
    assert reason2 == "official_domain"
    ok3, reason3 = public_register_url_ok("https://n2.artcb.space")
    assert ok3 is True
    assert reason3 == "official_domain"
    assert is_official_artcb_host("n4.artcb.me") is True
    assert is_official_artcb_host("evil.example.com") is False
    ok4, reason4 = public_register_url_ok("https://evil.example.com")
    assert ok4 is False
    assert reason4 == "host_not_allowlisted"


def test_dns_script_refuses_order_cart_checkout() -> None:
    script = DNS_SCRIPT.read_text(encoding="utf-8")
    assert DNS_SCRIPT.is_file()
    assert "xy4589-ovh" in script
    assert "artcb.me" in script
    assert "forbidden_order_cart_checkout" in script
    assert "pas sur OVH4, cherche dans le manager" in script
    assert "Never copies process OVH_*" in script
    assert "POST /order" not in script
    assert "/order/cart" not in script
    assert "autoPayWithPreferredPaymentMethod" not in script
    assert "waiveRetractationPeriod" not in script
    assert "def order_domain" not in script
    assert "--order" not in script
    assert "print(ak" not in script
    assert "print(as_" not in script
    assert "print(ck" not in script
    assert "init_genesis" not in script
    assert "install.sh" not in script
    sys_path_ok = str(ROOT / "scripts")
    import sys

    if sys_path_ok not in sys.path:
        sys.path.insert(0, sys_path_ok)
    import ovh4_artcb_me_dns as dns

    code, body = dns.ovh("POST", "/order/cart", {"ovhSubsidiary": "FR"})
    assert code == 0
    assert isinstance(body, dict)
    assert body.get("error") == "forbidden_order_cart_checkout"
    code2, body2 = dns.ovh("POST", "/order/cart/x/checkout", {})
    assert code2 == 0
    assert body2.get("error") == "forbidden_order_cart_checkout"
    code3, body3 = dns.ovh("GET", "/order/cart")
    assert code3 == 0
    assert body3.get("error") == "forbidden_order_cart_checkout"


def test_public_url_imports_src_artcb_for_live_uvicorn() -> None:
    """Live start_node.sh runs uvicorn src.api.main:app from repo root (no PYTHONPATH=src)."""
    text = (ROOT / "src" / "artcb" / "p2p" / "public_url.py").read_text(encoding="utf-8")
    assert "from src.artcb.config import ARTCB_DOMAIN, ARTCB_DOMAIN_LEGACY" in text
    assert "from artcb.config import ARTCB_DOMAIN" not in text


def test_sim200_keep_book_never_orders_or_wipes() -> None:
    sim = (ROOT / "scripts" / "run_sim200_artcb_me.py").read_text(encoding="utf-8")
    assert 'BRANCH = "cursor/artcb-me-official-16d8"' in sim
    assert "install.sh not executed" in sim
    assert "init_genesis.py not executed" in sim
    assert "init-node not executed" in sim
    assert "blocks.jsonl not emptied" in sim
    assert "git_bundle" in sim
    assert "/order/cart" not in sim
    assert "autoPayWithPreferredPaymentMethod" not in sim
    assert "def order_domain" not in sim
    assert "bash install.sh" not in sim
    assert "certified stays false" in sim
