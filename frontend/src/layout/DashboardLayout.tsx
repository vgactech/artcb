import { useEffect, useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import axios from "axios";
import { chainQueryParams, fetchChain, fetchPolScore } from "../api/client";
import { useDashboard } from "../context/DashboardContext";
import { LanguageSelector } from "../i18n/LanguageSelector";
import { useTranslation } from "../i18n/useTranslation";
import type { ChainBlock } from "../types";

export function DashboardLayout() {
  const { t } = useTranslation();
  const { visibility, setVisibility, groupId, chainBlock, actorAddress, setActorAddress } = useDashboard();
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const [polScore, setPolScore] = useState<number | null>(null);
  const [blocks, setBlocks] = useState<ChainBlock[]>([]);
  const [chainValid, setChainValid] = useState<boolean | null>(null);

  const NAV = [
    { section: "CORE", items: [
      { to: "/", label: t('nav_dashboard'), icon: "▶" },
      { to: "/register", label: t('nav_register'), icon: "◉" },
      { to: "/memorize", label: t('nav_memorize'), icon: "W" },
      { to: "/graph", label: t('nav_graph'), icon: "◎" },
    ]},
    { section: "CHAIN", items: [
      { to: "/chain", label: t('nav_chain'), icon: "▣" },
      { to: "/wallets", label: t('nav_wallets'), icon: "◇" },
      { to: "/mining", label: t('nav_mining'), icon: "#" },
    ]},
    { section: "SYSTEM", items: [
      { to: "/system", label: t('nav_system'), icon: "F3" },
      { to: "/logs", label: t('nav_logs'), icon: "=" },
      { to: "/console", label: t('nav_console'), icon: ">" },
      { to: "/integrations", label: t('nav_integrations'), icon: "+" },
      { to: "/network", label: t('nav_network'), icon: "~" },
      { to: "/governance", label: t('nav_governance'), icon: "G" },
      { to: "/groups", label: t('nav_groups'), icon: "[G]" },
      { to: "/api-keys", label: t('nav_api_keys'), icon: "K" },
      { to: "/agent-memory", label: t('nav_agent_memory'), icon: "AI" },
    ]},
  ];

  useEffect(() => {
    const tick = async () => {
      // B5 FIX: fetches parallèles au lieu de séquentiels (+279ms/cycle économisé)
      const q = chainQueryParams(visibility, groupId);
      const [healthResult, polResult, chainResult, verifyResult] = await Promise.allSettled([
        axios.get("/api/v1/health", { timeout: 3000 }),
        fetchPolScore(),
        fetchChain(q),
        axios.get("/api/v1/chain/verify"),
      ]);

      if (healthResult.status === "fulfilled") setApiOk(true);
      else setApiOk(false);

      if (polResult.status === "fulfilled") {
        const newPol = polResult.value.pol_score;
        // B6 FIX: ne mettre à jour que si la valeur a changé
        setPolScore(prev => prev !== newPol ? newPol : prev);
      }

      if (chainResult.status === "fulfilled") {
        const newChain = chainResult.value;
        // B6 FIX: ne mettre à jour que si le nombre de blocs a changé
        setBlocks(prev =>
          prev.length !== newChain.length ? newChain : prev
        );
      }

      if (verifyResult.status === "fulfilled") {
        const valid = (verifyResult.value as { data: { valid?: boolean } }).data.valid ?? false;
        setChainValid(valid);
      } else {
        setChainValid(null);
      }
    };
    tick();
    const id = setInterval(tick, 5000);
    return () => clearInterval(id);
  }, [visibility, groupId]);

  const lastBlock = chainBlock ?? blocks[blocks.length - 1] ?? null;

  return (
    <div className="mc-dashboard">
      {/* B12 FIX: Skip-to-content WCAG 2.4.1 Level A */}
      <a href="#main-content" className="skip-link">Aller au contenu principal</a>
      <header className="mc-header">
        {/* B10 FIX: min-height réservé pour éviter layout shift quand PoL charge async */}
        <div className="mc-header-left" style={{ minHeight: "56px" }}>
          <span className="mc-logo">ARTCB</span>
          <span className={`mc-api-badge${apiOk === false ? " mc-api-down" : ""}`}>
            {apiOk === null ? "…" : apiOk ? "+ API OK" : "X API DOWN"}
          </span>
          {/* placeholder invisible pour réserver la place avant que PoL arrive */}
          <span className="mc-header-kpi" style={{ minWidth: "80px", display: "inline-block" }}>
            {polScore !== null ? `◆ PoL ${polScore.toFixed(2)}` : <span style={{ visibility: "hidden" }}>◆ PoL 0.00</span>}
          </span>
          <span className="mc-header-kpi">▣ Blocs {blocks.length}</span>
          {chainValid !== null && (
            <span className="mc-header-kpi">{chainValid ? "Chain OK" : "Chain X"}</span>
          )}
          {/* UX-4 FIX: wallet actif visible dans le header global */}
          {actorAddress ? (
            <span className="mc-header-kpi" style={{ color: "var(--mc-grass, #56c426)", cursor: "pointer" }} title={actorAddress}>
              <Link to="/wallets" style={{ color: "inherit", textDecoration: "none" }}>
                ◇ {actorAddress.slice(0, 12)}…
              </Link>
              <button
                onClick={() => setActorAddress("")}
                title="Se déconnecter"
                style={{ marginLeft: 4, fontSize: 9, padding: "1px 4px", background: "transparent", border: "1px solid var(--mc-redstone, #c0392b)", color: "var(--mc-redstone, #c0392b)", cursor: "pointer", borderRadius: 2 }}
              >
                ✕
              </button>
            </span>
          ) : (
            <>
            <Link to="/register" className="mc-header-kpi" style={{ color: "var(--mc-gold, #ffd700)", textDecoration: "none" }} title="Inscription biométrie">
              ◉ {t("nav_register")}
            </Link>
            <Link to="/wallets" className="mc-header-kpi" style={{ color: "var(--mc-gold, #ffd700)", textDecoration: "none" }} title="Aucun wallet actif — cliquez pour en créer un">
              ◇ Wallet ?
            </Link>
            </>
          )}
        </div>
        <div className="mc-header-right">
          <label className="mc-network-select" aria-label="Sélecteur réseau">
            Réseau:
            <select
              value={visibility}
              aria-label="Visibilité réseau"
              onChange={(e) => setVisibility(e.target.value as "private" | "group" | "public")}
            >
              <option value="private">PRIVÉ</option>
              <option value="group">GROUPE{groupId ? ` (${groupId.slice(0, 8)}…)` : ""}</option>
              <option value="public">PUBLIC</option>
            </select>
          </label>
          <LanguageSelector />
          <span className="badge-debug">DEBUG</span>
          <Link to="/console" className="mc-console-link">CONSOLE</Link>
        </div>
      </header>

      <div className="mc-body">
        <nav className="mc-sidebar" aria-label="Navigation dashboard">
          {NAV.map((group) => (
            <div key={group.section} className="mc-nav-group">
              <div className="mc-nav-section">{group.section}</div>
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) => `mc-nav-item${isActive ? " mc-nav-active" : ""}`}
                >
                  <span className="mc-nav-icon">{item.icon}</span>
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <main className="mc-main" id="main-content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>

      <footer className="chain-footer mc-footer">
        <span>
          {lastBlock
            ? `Bloc #${lastBlock.index} · hash ${lastBlock.hash.slice(0, 8)}…`
            : "Aucun bloc"}
          {lastBlock?.pol_score != null && ` · PoL ${lastBlock.pol_score.toFixed(2)}`}
        </span>
      </footer>
    </div>
  );
}
