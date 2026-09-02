"""Phase 201 — merge artcb.me onto main, nginx :80 proxy, Replit PIN = origin/main.

certified stays false (D-052). No domain order. No genesis wipe.
"""

from __future__ import annotations

from pathlib import Path

from artcb.devnet_validation import (
    DECISIONS_201,
    OPERATOR_MAINNET_CERTIFICATION_GO,
    certification_gate,
    public_lock,
)
from api.main import public_certification_block

ROOT = Path(__file__).resolve().parents[1]
NGINX = ROOT / "deploy" / "nginx" / "artcb-me-http.conf"
ENABLE = ROOT / "scripts" / "enable_artcb_me_nginx.sh"
SIM = ROOT / "scripts" / "run_sim201_main_nginx.py"
AWS = ROOT / "scripts" / "provision_aws_ec2.py"


def test_d052_lock_and_certified_stays_false() -> None:
    text = DECISIONS_201["D-052"]
    assert "git_branch=main" in text
    assert "Welcome to nginx" in text
    assert "ARTCB_REPLIT_PIN_SHA" in text
    assert "certified_distributed_mainnet stays false" in text
    assert OPERATOR_MAINNET_CERTIFICATION_GO is False
    lock = public_lock()
    assert lock["distributed_certified"] is False
    assert "decisions_201" in lock
    gate = certification_gate(
        {k: "PASS" for k in ("DV-01", "DV-02", "DV-03", "DV-04", "DV-05", "DV-06", "DV-07")}
    )
    assert gate["certified_distributed_mainnet"] is False
    assert gate["operator_certification_go"] is False
    assert "operator_certification_go=false" in gate["reason"]
    health = public_certification_block()
    assert health["certified_distributed_mainnet"] is False
    assert "operator_certification_go=false" in health["certification_reason"]
    assert "dv_not_pass:" in health["certification_reason"]


def test_nginx_http_proxy_kills_default_welcome() -> None:
    conf = NGINX.read_text(encoding="utf-8")
    sh = ENABLE.read_text(encoding="utf-8")
    assert "listen 80 default_server" in conf
    assert "proxy_pass http://127.0.0.1:8000" in conf
    assert "server_name artcb.me" in conf
    assert "n4.artcb.me" in conf
    assert "Welcome to nginx" not in conf
    assert "sites-enabled/default" in sh
    assert "default.disabled" in sh
    assert "artcb-me-http.conf" in sh
    assert "register-unsafely-without-email" in sh
    assert "install.sh" not in sh
    assert "init_genesis" not in sh


def test_sim201_keep_book_main_never_orders_or_wipes_or_certifies() -> None:
    sim = SIM.read_text(encoding="utf-8")
    assert 'BRANCH = "main"' in sim
    assert "install.sh not executed" in sim
    assert "init_genesis.py not executed" in sim
    assert "init-node not executed" in sim
    assert "blocks.jsonl not emptied" in sim
    assert "git_bundle" in sim
    assert "certified stays false" in sim
    assert "/order/cart" not in sim
    assert "autoPayWithPreferredPaymentMethod" not in sim
    assert "bash install.sh" not in sim
    assert "OPERATOR_MAINNET_CERTIFICATION_GO is False" in sim
    aws = AWS.read_text(encoding="utf-8")
    assert "80, 443, 8000, 8443" in aws or "22, 80, 443, 8000, 8443" in aws
    assert "--open-http" in aws
    assert "InvalidPermission.Duplicate" in aws
    assert 'env.pop("AWS_PROFILE"' in aws


def test_replit_default_branch_is_main() -> None:
    sync = (ROOT / "scripts" / "replit_git_sync.sh").read_text(encoding="utf-8")
    auto = (ROOT / "scripts" / "replit_autoscale.sh").read_text(encoding="utf-8")
    start = (ROOT / "scripts" / "replit_start.sh").read_text(encoding="utf-8")
    replit = (ROOT / ".replit").read_text(encoding="utf-8")
    assert 'ARTCB_REPLIT_BRANCH="${ARTCB_REPLIT_BRANCH:-main}"' in sync
    assert 'ARTCB_REPLIT_BRANCH="${ARTCB_REPLIT_BRANCH:-main}"' in auto
    assert "GITHUB_BRANCH:-main" in start
    assert 'ARTCB_REPLIT_BRANCH = "main"' in replit
    assert 'ARTCB_REPLIT_BRANCH = "cursor/replit-sync-ready-16d8"' not in replit
    # PIN is still a secret, never baked into .replit
    assert "ARTCB_REPLIT_PIN_SHA =" not in replit
