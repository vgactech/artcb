"""Dashboard frontend route smoke tests — T-F02 navigation."""

from __future__ import annotations

from pathlib import Path

import pytest

FRONTEND = Path("frontend/src")
ROUTES = [
    ("Home", "pages/Home.tsx"),
    ("RegisterBiometric", "pages/RegisterBiometric.tsx"),
    ("Memorize", "pages/Memorize.tsx"),
    ("GraphPage", "pages/GraphPage.tsx"),
    ("ChainPage", "pages/ChainPage.tsx"),
    ("Wallets", "pages/Wallets.tsx"),
    ("Mining", "pages/Mining.tsx"),
    ("SystemPage", "pages/SystemPage.tsx"),
    ("Logs", "pages/Logs.tsx"),
    ("Console", "pages/Console.tsx"),
    ("Groups", "pages/Groups.tsx"),
]

APP_ROUTES = [
    "/",
    "/memorize",
    "/graph",
    "/chain",
    "/wallets",
    "/mining",
    "/system",
    "/logs",
    "/console",
    "/groups",
]


@pytest.mark.parametrize("name,rel_path", ROUTES)
def test_frontend_page_files_exist(name: str, rel_path: str) -> None:
    path = FRONTEND / rel_path
    assert path.is_file(), f"missing {path}"


@pytest.mark.parametrize("route", APP_ROUTES)
def test_app_tsx_declares_route(route: str) -> None:
    app = (FRONTEND / "App.tsx").read_text(encoding="utf-8")
    segment = route.lstrip("/") or 'index'
    if segment == "":
        assert 'index element={<Home />}' in app or 'path="/"' in app
    else:
        assert segment in app, f"route {route} not in App.tsx"


def test_demo_tsx_removed() -> None:
    assert not (FRONTEND / "pages/Demo.tsx").exists()


def test_debug_badge_in_layout() -> None:
    layout = (FRONTEND / "layout/DashboardLayout.tsx").read_text(encoding="utf-8")
    assert "badge-debug" in layout
    assert "DEBUG" in layout


def test_network_selector_in_layout() -> None:
    layout = (FRONTEND / "layout/DashboardLayout.tsx").read_text(encoding="utf-8")
    assert "PRIVÉ" in layout
    assert "GROUPE" in layout
    assert "PUBLIC" in layout
