import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  authLogin,
  authLogout,
  createWallet,
  fetchFoundersAllocation,
  fetchWalletBalance,
  fetchWalletRewards,
  fetchWallets,
} from "../api/client";
import { useDashboard } from "../context/DashboardContext";
import { useTranslation } from "../i18n/useTranslation";

// Clé sessionStorage pour persister le token de session entre rechargements
const SESSION_TOKEN_KEY = "artcb_session_token";
const SESSION_WALLET_KEY = "artcb_session_wallet";

type CreatedWallet = {
  name: string;
  address: string;
  address_v2?: string;
  public_key_hex: string;
  /** Clé privée — affichée une seule fois à la création */
  seed_hex: string;
  WARNING: string;
  hybrid: boolean;
};

export function Wallets() {
  const { t } = useTranslation();
  const { actorAddress, setActorAddress } = useDashboard();
  const [wallets, setWallets] = useState<
    Array<{ address: string; name: string; balance?: number; rewards?: number; has_key_file?: boolean }>
  >([]);
  const [founders, setFounders] = useState<
    Array<{ founder_id: number; name: string; balance_artcb: number; is_creator?: boolean }>
  >([]);
  const [newName, setNewName] = useState("");
  // Mot de passe à saisir lors de la création (obligatoire)
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordConfirm, setNewPasswordConfirm] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [rewardHistory, setRewardHistory] = useState<
    Array<{ block_index: number; reward_artcb: number; pol_score: number; timestamp: string }>
  >([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // ── Wallet créé — affiché à l'utilisateur ─────────────────────────
  const [createdWallet, setCreatedWallet] = useState<CreatedWallet | null>(null);
  const [copied, setCopied] = useState(false);
  const [seedCopied, setSeedCopied] = useState(false);
  const [seedVisible, setSeedVisible] = useState(true);
  // UX-1: copier depuis la grille (quel wallet est en cours de copie)
  const [copiedGrid, setCopiedGrid] = useState<string | null>(null);

  // ── Login par nom + mot de passe ─────────────────────────────────
  const [loginName, setLoginName] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);
  // Session persistée dans sessionStorage (survit aux rechargements, pas aux fermetures d'onglet)
  const [sessionToken, setSessionToken] = useState<string | null>(
    () => sessionStorage.getItem(SESSION_TOKEN_KEY)
  );
  const [sessionWallet, setSessionWallet] = useState<string | null>(
    () => sessionStorage.getItem(SESSION_WALLET_KEY)
  );

  // ── Popup "Activer" — demande le mot de passe avant d'activer un wallet ──
  const [activateTarget, setActivateTarget] = useState<{ address: string; name: string } | null>(null);
  const [activatePassword, setActivatePassword] = useState("");
  const [activateError, setActivateError] = useState<string | null>(null);
  const [activateLoading, setActivateLoading] = useState(false);

  // ── Import wallet (entrer une adresse existante) ──────────────────
  const [importAddress, setImportAddress] = useState("");
  const [importError, setImportError]     = useState<string | null>(null);

  const reload = async () => {
    const list = await fetchWallets();
    const withBal = await Promise.all(
      list.map(async (w) => {
        try {
          const b = await fetchWalletBalance(w.address);
          const r = await fetchWalletRewards(w.address);
          return { ...w, balance: b.balance_artcb, rewards: r.total_artcb };
        } catch {
          return { ...w, balance: 0, rewards: 0 };
        }
      }),
    );
    setWallets(withBal);
  };

  useEffect(() => {
    reload().catch(() => setWallets([]));
    fetchFoundersAllocation()
      .then((f) => setFounders(f.balances ?? []))
      .catch(() => {});
  }, []);

  // ── Créer un nouveau wallet ────────────────────────────────────────
  const handleCreate = async () => {
    if (!newName.trim()) return;
    // Validation : mot de passe obligatoire + confirmation
    if (newPassword.length < 8) {
      setError("Le mot de passe doit contenir au moins 8 caractères.");
      return;
    }
    if (newPassword !== newPasswordConfirm) {
      setError("Les mots de passe ne correspondent pas.");
      return;
    }
    setLoading(true);
    setError(null);
    setCreatedWallet(null);
    try {
      // PROTOCOLE : mot de passe obligatoire — chiffre la clé privée côté serveur
      const w = await createWallet(newName.trim(), newPassword);
      // Connexion automatique après création (session valide)
      const loginResult = await authLogin(newName.trim(), newPassword);
      const token = loginResult.session_token;
      setSessionToken(token);
      setSessionWallet(newName.trim());
      sessionStorage.setItem(SESSION_TOKEN_KEY, token);
      sessionStorage.setItem(SESSION_WALLET_KEY, newName.trim());
      setActorAddress(w.address);
      setCreatedWallet(w);         // <── Affichage immédiat à l'utilisateur
      setNewName("");
      setNewPassword("");
      setNewPasswordConfirm("");
      await reload();
    } catch (err: unknown) {
      const axErr = err as { response?: { data?: { detail?: string }; status?: number } };
      if (axErr?.response?.status === 409) {
        setError(`Wallet "${newName.trim()}" existe déjà — choisissez un autre nom.`);
      } else {
        setError(axErr?.response?.data?.detail ?? (err instanceof Error ? err.message : String(err)));
      }
    } finally {
      setLoading(false);
    }
  };

  // ── Login par mot de passe ────────────────────────────────────────
  const handleLogin = async () => {
    if (!loginName.trim() || !loginPassword.trim()) return;
    setLoginLoading(true);
    setLoginError(null);
    try {
      const result = await authLogin(loginName.trim(), loginPassword.trim());
      const token = result.session_token;
      // Persister la session dans sessionStorage (survit aux rechargements de page)
      setSessionToken(token);
      setSessionWallet(result.wallet_name);
      sessionStorage.setItem(SESSION_TOKEN_KEY, token);
      sessionStorage.setItem(SESSION_WALLET_KEY, result.wallet_name);
      setActorAddress(result.address);
      setLoginError(null);
      setLoginName("");
      setLoginPassword("");
      await reload();
    } catch (err: unknown) {
      const axErr = err as { response?: { data?: { detail?: string }; status?: number } };
      setLoginError(axErr?.response?.data?.detail ?? "Identifiants invalides — vérifiez votre nom et mot de passe.");
    } finally {
      setLoginLoading(false);
    }
  };

  // ── Activer un wallet depuis la grille (requiert mot de passe) ─────
  const handleActivate = async () => {
    if (!activateTarget || !activatePassword.trim()) return;
    setActivateLoading(true);
    setActivateError(null);
    try {
      // SÉCURITÉ : le bouton "Activer" appelle /auth/login — sans le bon mot de passe, refusé
      const result = await authLogin(activateTarget.name, activatePassword.trim());
      const token = result.session_token;
      setSessionToken(token);
      setSessionWallet(activateTarget.name);
      sessionStorage.setItem(SESSION_TOKEN_KEY, token);
      sessionStorage.setItem(SESSION_WALLET_KEY, activateTarget.name);
      setActorAddress(result.address);
      setActivateTarget(null);
      setActivatePassword("");
      await reload();
    } catch (err: unknown) {
      const axErr = err as { response?: { data?: { detail?: string }; status?: number } };
      setActivateError(axErr?.response?.data?.detail ?? "Mot de passe incorrect.");
    } finally {
      setActivateLoading(false);
    }
  };

  const copySeed = (seed: string) => {
    navigator.clipboard?.writeText(seed).then(() => {
      setSeedCopied(true);
      setTimeout(() => setSeedCopied(false), 3000);
    }).catch(() => {});
  };

  // ── Copier une adresse ─────────────────────────────────────────────
  const copyAddress = (addr: string) => {
    navigator.clipboard?.writeText(addr).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => {
      // Fallback — sélectionner le texte
      const el = document.createElement("textarea");
      el.value = addr;
      document.body.appendChild(el);
      el.select();
      document.execCommand("copy");
      document.body.removeChild(el);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  // UX-1 FIX: copier une adresse depuis la grille
  const copyFromGrid = (addr: string) => {
    navigator.clipboard?.writeText(addr).then(() => {
      setCopiedGrid(addr);
      setTimeout(() => setCopiedGrid(null), 2000);
    }).catch(() => {
      const el = document.createElement("textarea");
      el.value = addr;
      document.body.appendChild(el);
      el.select();
      document.execCommand("copy");
      document.body.removeChild(el);
      setCopiedGrid(addr);
      setTimeout(() => setCopiedGrid(null), 2000);
    });
  };

  // SÉCURITÉ : déconnexion — appel API + vidage session complète
  const handleDisconnect = async () => {
    if (sessionToken) {
      try {
        await authLogout(sessionToken);
      } catch { /* session déjà expirée côté serveur — OK */ }
    }
    setSessionToken(null);
    setSessionWallet(null);
    sessionStorage.removeItem(SESSION_TOKEN_KEY);
    sessionStorage.removeItem(SESSION_WALLET_KEY);
    setActorAddress("");
  };

  // ── Importer un wallet existant ────────────────────────────────────
  const handleImport = async () => {
    const addr = importAddress.trim();
    if (!addr) return;
    setImportError(null);
    try {
      const b = await fetchWalletBalance(addr);
      setActorAddress(addr);
      setImportError(null);
      setImportAddress("");
      // Ajouter à la liste locale si pas déjà présent
      if (!wallets.find((w) => w.address === addr)) {
        setWallets((prev) => [
          ...prev,
          { address: addr, name: `Import (${addr.slice(0, 8)}…)`, balance: b.balance_artcb, rewards: 0 },
        ]);
      }
    } catch {
      setImportError("Adresse introuvable sur la blockchain — vérifiez l'adresse.");
    }
  };

  const showRewards = async (address: string) => {
    setSelected(address);
    const r = await fetchWalletRewards(address);
    setRewardHistory(r.rewards);
  };

  const slots = Array.from({ length: 27 }, (_, i) => wallets[i] ?? null);

  return (
    <div className="mc-page">
      <h1 className="dashboard-title">{t('wallets_title')}</h1>

      <div className="panel bio-wallets-cta">
        <h2>{t("wallets_bio_title")}</h2>
        <p className="mc-muted">{t("bio_subtitle")}</p>
        <Link to="/register" className="primary bio-choice" style={{ display: "inline-block", textDecoration: "none" }}>
          {t("home_bio_cta_btn")}
        </Link>
      </div>

      {/* ── Wallet actif affiché en haut — avec bouton déconnexion ── */}
      {actorAddress ? (
        <div className="panel" style={{ borderColor: "var(--mc-grass, #56c426)", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem" }}>
          <div>
            <span style={{ color: "var(--mc-grass, #56c426)", fontWeight: 700, marginRight: 8 }}>◇ Wallet actif :</span>
            <span className="mc-mono" style={{ fontSize: 13 }}>{actorAddress}</span>
            {sessionWallet && (
              <span style={{ fontSize: 11, color: "var(--mc-grass)", marginLeft: 10 }}>
                ({sessionWallet}) — session authentifiée
              </span>
            )}
          </div>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button onClick={() => copyAddress(actorAddress)}>
              {copied ? "[OK] Copié !" : "Copier"}
            </button>
            {/* SÉCURITÉ : déconnexion invalide la session côté serveur */}
            <button onClick={handleDisconnect} style={{ color: "var(--mc-redstone, #c0392b)", borderColor: "var(--mc-redstone, #c0392b)" }}>
              ✕ Se déconnecter
            </button>
          </div>
        </div>
      ) : (
        <div className="panel" style={{ borderColor: "var(--mc-gold, #ffd700)", background: "rgba(255,215,0,0.05)" }}>
          <p style={{ margin: 0, color: "var(--mc-gold, #ffd700)", fontWeight: 700 }}>
            ◇ Pas encore de wallet actif — créez-en un ci-dessous ou connectez-vous.
          </p>
        </div>
      )}

      {/* ── Popup : Activer un wallet (mot de passe requis) ──────── */}
      {activateTarget && (
        <div className="panel" style={{ border: "2px solid var(--mc-gold, #ffd700)", background: "rgba(0,0,0,0.85)", position: "fixed", top: "50%", left: "50%", transform: "translate(-50%,-50%)", zIndex: 1000, minWidth: 320, maxWidth: 480 }}>
          <h2 style={{ color: "var(--mc-gold)" }}>🔐 Activer le wallet</h2>
          <p style={{ fontSize: 13, marginBottom: 12 }}>
            <strong>{activateTarget.name}</strong><br />
            <span className="mc-mono" style={{ fontSize: 11 }}>{activateTarget.address}</span>
          </p>
          <p style={{ fontSize: 13, color: "var(--terminal-muted)", marginBottom: 12 }}>
            Entrez votre mot de passe pour accéder à ce wallet. Sans le bon mot de passe, l'accès est impossible.
          </p>
          <div className="toolbar" style={{ flexDirection: "column", gap: "0.5rem" }}>
            <input
              type="password"
              value={activatePassword}
              onChange={(e) => setActivatePassword(e.target.value)}
              placeholder="Votre mot de passe"
              style={{ minWidth: 240 }}
              autoFocus
              onKeyDown={(e) => e.key === "Enter" && handleActivate()}
            />
          </div>
          {activateError && <p className="mc-error" style={{ marginTop: 8 }}>{activateError}</p>}
          <div className="toolbar" style={{ marginTop: 12 }}>
            <button className="primary" onClick={handleActivate} disabled={activateLoading || !activatePassword.trim()}>
              {activateLoading ? "Vérification…" : "Se connecter"}
            </button>
            <button onClick={() => { setActivateTarget(null); setActivatePassword(""); setActivateError(null); }}>
              Annuler
            </button>
          </div>
        </div>
      )}

      {/* ── Panneau : Créer un wallet ─────────────────────────── */}
      <div className="panel">
        <h2>{t('wallets_create_title')}</h2>
        <p style={{ fontSize: 13, color: "var(--terminal-muted, #8b949e)", marginBottom: 8 }}>
          Choisissez un nom et un <strong>mot de passe</strong> (min. 8 caractères).
          Ce mot de passe chiffre votre clé privée — il sera requis pour vous connecter.
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginBottom: 8 }}>
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder={t('wallets_create_placeholder')}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
          />
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="Mot de passe (min. 8 caractères)"
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
          />
          <input
            type="password"
            value={newPasswordConfirm}
            onChange={(e) => setNewPasswordConfirm(e.target.value)}
            placeholder="Confirmer le mot de passe"
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
          />
        </div>
        <button className="primary" onClick={handleCreate} disabled={loading || !newName.trim() || !newPassword.trim() || !newPasswordConfirm.trim()}>
          {loading ? "Création…" : t('wallets_create_button')}
        </button>
        {error && <p className="mc-error" style={{ marginTop: 8 }}>{error}</p>}
      </div>

      {/* ── Résultat création : seed_hex + adresse ────────────── */}
      {createdWallet && (
        <div className="panel" style={{ border: "2px solid var(--mc-redstone, #c0392b)" }}>
          <h2 style={{ color: "var(--mc-redstone, #c0392b)" }}>⚠ SAUVEGARDEZ VOTRE CLÉ PRIVÉE MAINTENANT</h2>
          <p style={{ fontSize: 13, marginBottom: 8, background: "rgba(192,57,43,0.1)", padding: "8px 12px", borderRadius: 4 }}>
            <strong>Cette clé privée (seed_hex) ne sera plus jamais affichée.</strong><br />
            Sans elle, votre compte est définitivement inaccessible.<br />
            Copiez-la dans un gestionnaire de mots de passe ou un fichier sécurisé.
          </p>

          {/* SEED HEX — clé privée */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontWeight: 700, marginBottom: 4, color: "var(--mc-redstone)" }}>🔑 Clé privée (seed_hex) :</div>
            {seedVisible ? (
              <div style={{ background: "#1a1a1a", padding: "10px 12px", borderRadius: 4, fontFamily: "monospace", fontSize: 12, wordBreak: "break-all", border: "1px solid var(--mc-redstone)" }}>
                {createdWallet.seed_hex}
              </div>
            ) : (
              <div style={{ background: "#1a1a1a", padding: "10px 12px", borderRadius: 4, fontFamily: "monospace", fontSize: 12, color: "var(--terminal-muted)", border: "1px solid #444" }}>
                ████████████████████████████████████████████████████████████████
              </div>
            )}
            <div className="toolbar" style={{ marginTop: 6 }}>
              <button className="primary" onClick={() => copySeed(createdWallet.seed_hex)} style={{ borderColor: "var(--mc-redstone)", color: "var(--mc-redstone)" }}>
                {seedCopied ? "✓ Copié !" : "Copier la clé privée"}
              </button>
              <button onClick={() => setSeedVisible((v) => !v)}>
                {seedVisible ? "Masquer" : "Afficher"}
              </button>
            </div>
          </div>

          <table className="mc-table" style={{ marginBottom: 12 }}>
            <tbody>
              <tr>
                <td style={{ fontWeight: 700, width: 140 }}>Nom</td>
                <td className="mc-mono">{createdWallet.name}</td>
              </tr>
              <tr>
                <td style={{ fontWeight: 700 }}>Adresse (publique)</td>
                <td>
                  <span className="mc-mono mc-gold-text" style={{ wordBreak: "break-all", fontSize: 12 }}>
                    {createdWallet.address}
                  </span>
                </td>
              </tr>
              {createdWallet.address_v2 && (
                <tr>
                  <td style={{ fontWeight: 700 }}>Adresse v2 PQC</td>
                  <td>
                    <span className="mc-mono" style={{ wordBreak: "break-all", fontSize: 12, color: "var(--mc-sky, #5bc0de)" }}>
                      {createdWallet.address_v2}
                    </span>
                  </td>
                </tr>
              )}
              <tr>
                <td style={{ fontWeight: 700 }}>Type</td>
                <td className="mc-mono">
                  {createdWallet.hybrid ? "Ed25519 + ML-DSA-65 (post-quantique)" : "Ed25519 standard"}
                </td>
              </tr>
            </tbody>
          </table>

          <div className="toolbar">
            <button onClick={() => copyAddress(createdWallet.address)}>
              {copied ? "[OK] Copié !" : "Copier l'adresse"}
            </button>
            {createdWallet.address_v2 && (
              <button onClick={() => copyAddress(createdWallet.address_v2!)}>
                Copier adresse v2 (PQC)
              </button>
            )}
            <button onClick={() => { setCreatedWallet(null); setSeedVisible(true); }} style={{ marginLeft: "auto" }}>
              J'ai sauvegardé ma clé — Fermer
            </button>
          </div>
        </div>
      )}

      {/* ── Panneau : Login — J'ai déjà un compte ─────────────── */}
      <div className="panel">
        <h2>Connexion — J'ai déjà un compte</h2>
        <p style={{ fontSize: 13, color: "var(--terminal-muted, #8b949e)", marginBottom: 8 }}>
          Connectez-vous avec le <strong>nom de votre wallet</strong> et votre <strong>mot de passe</strong>.
          Une fois connecté, vous pourrez générer des clés API pour ChatGPT, Claude, n8n, etc.
        </p>
        <div className="toolbar" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
          <input
            value={loginName}
            onChange={(e) => setLoginName(e.target.value)}
            placeholder="Nom du wallet"
            style={{ minWidth: 160 }}
            onKeyDown={(e) => e.key === "Enter" && handleLogin()}
          />
          <input
            type="password"
            value={loginPassword}
            onChange={(e) => setLoginPassword(e.target.value)}
            placeholder="Mot de passe"
            style={{ minWidth: 160 }}
            onKeyDown={(e) => e.key === "Enter" && handleLogin()}
          />
          <button className="primary" onClick={handleLogin} disabled={loginLoading || !loginName.trim() || !loginPassword.trim()}>
            {loginLoading ? "Connexion…" : "Se connecter"}
          </button>
        </div>
        {loginError && <p className="mc-error">{loginError}</p>}
        {sessionToken && (
          <p style={{ color: "var(--mc-grass)", fontSize: 12, marginTop: 6 }}>
            ✓ Connecté — session active (utilisez le dashboard pour générer une API key)
          </p>
        )}
      </div>

      {/* ── Panneau : Importer une adresse (lecture seule) ──────── */}
      <div className="panel">
        <h2>Observer un wallet (lecture seule)</h2>
        <p style={{ fontSize: 13, color: "var(--terminal-muted, #8b949e)", marginBottom: 8 }}>
          Entrez une adresse ARTCB pour consulter son solde. <strong>L'adresse seule ne donne pas accès au compte.</strong>
        </p>
        <div className="toolbar">
          <input
            value={importAddress}
            onChange={(e) => setImportAddress(e.target.value)}
            placeholder="artcb1…"
            style={{ fontFamily: "monospace", fontSize: 13 }}
            onKeyDown={(e) => e.key === "Enter" && handleImport()}
          />
          <button onClick={handleImport} disabled={!importAddress.trim()}>
            Consulter le solde
          </button>
        </div>
        {importError && <p className="mc-error">{importError}</p>}
      </div>

      {/* ── Grille wallets (coffre) ────────────────────────────── */}
      <div className="panel mc-chest">
        <h2 style={{ marginBottom: "0.75rem" }}>
          Vos wallets ({wallets.length})
          {wallets.length === 0 && <span className="mc-muted" style={{ fontSize: 13, fontWeight: 400, marginLeft: 8 }}>— Créez votre premier wallet ci-dessus ↑</span>}
        </h2>
        {/* UX-2 FIX: message explicite quand aucun wallet */}
        {wallets.length === 0 && (
          <div style={{ textAlign: "center", padding: "2rem 1rem", color: "var(--muted)" }}>
            <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>◇</div>
            <p>Vous n'avez pas encore de wallet.</p>
            <p style={{ fontSize: 13 }}>Un wallet est votre identité sur la blockchain ARTCB — il vous permet de signer des blocs et de recevoir des récompenses ARTCB.</p>
          </div>
        )}
        <div className="mc-chest-grid">
          {slots.map((w, i) => (
            <div
              key={i}
              className={`mc-chest-slot${w ? " mc-chest-filled" : ""}${w && w.address === actorAddress ? " mc-chest-active" : ""}`}
              onClick={() => w && showRewards(w.address)}
              onKeyDown={(e) => e.key === "Enter" && w && showRewards(w.address)}
              role={w ? "button" : undefined}
              tabIndex={w ? 0 : undefined}
              title={w ? `${w.name} — ${w.address}` : undefined}
            >
              {w ? (
                <>
                  {w.address === actorAddress && <div style={{ fontSize: 8, color: "var(--mc-grass)", textAlign: "center" }}>● ACTIF</div>}
                  <div className="mc-chest-icon">◇</div>
                  <div className="mc-chest-name">{w.name}</div>
                  <div className="mc-gold-text">{(w.balance ?? 0).toFixed(2)} ₳</div>
                  <div className="mc-mono mc-chest-addr">{w.address.slice(0, 8)}…</div>
                  {/* UX-1 FIX: bouton copier + bouton activer sur chaque wallet */}
                  <div style={{ display: "flex", gap: 2, marginTop: 4, justifyContent: "center" }} onClick={(e) => e.stopPropagation()}>
                    <button
                      style={{ fontSize: 9, padding: "1px 4px" }}
                      onClick={() => copyFromGrid(w.address)}
                      title="Copier l'adresse"
                    >
                      {copiedGrid === w.address ? "✓" : "⧉"}
                    </button>
                    {/* SÉCURITÉ : bouton Activer ouvre une popup mot de passe — pas d'accès direct */}
                     {w.address !== actorAddress && w.has_key_file !== false && (
                       <button
                         style={{ fontSize: 9, padding: "1px 4px", color: "var(--mc-grass)" }}
                         onClick={() => { setActivateTarget({ address: w.address, name: w.name }); setActivatePassword(""); setActivateError(null); }}
                         title="Activer ce wallet — mot de passe requis"
                       >
                         ▶
                       </button>
                     )}
                    {/* Wallet importé (lecture seule) — pas de bouton Activer */}
                    {w.has_key_file === false && w.address !== actorAddress && (
                      <span
                        style={{ fontSize: 8, color: "var(--terminal-muted)", padding: "1px 3px" }}
                        title="Wallet en lecture seule — clé privée absente de ce nœud"
                      >
                        👁
                      </span>
                    )}
                  </div>
                </>
              ) : null}
            </div>
          ))}
        </div>
      </div>

      {/* ── Founders (v2 : Créateur + Dev) ───────────────────── */}
      {founders.length > 0 && (
        <div className="panel">
          <h2>{t('wallets_founders_title')}</h2>
          <div className="mc-hotbar">
            {founders.map((f) => (
              <div
                key={f.founder_id}
                className={`mc-slot ${f.is_creator ? "mc-slot-gold" : "mc-slot-active"}`}
                title={f.is_creator ? "Compte Créateur — droits absolus (vote weight 999 999)" : "Compte Développement"}
              >
                <div className="mc-kpi-label">
                  {f.name}
                  {f.is_creator && <span style={{ marginLeft: 4, fontSize: 10 }}>[CREATEUR]</span>}
                </div>
                <div className="mc-kpi-value">{f.balance_artcb.toLocaleString()} ₳</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Historique rewards ─────────────────────────────────── */}
      {selected && (
        <div className="panel">
          <h2>{t('wallets_rewards_title')} — {selected.slice(0, 16)}…</h2>
          <table className="mc-table">
            <thead>
              <tr>
                <th>{t('wallets_rewards_block')}</th>
                <th>{t('wallets_rewards_amount')}</th>
                <th>{t('chain_pol_score')}</th>
                <th>{t('wallets_rewards_timestamp')}</th>
              </tr>
            </thead>
            <tbody>
              {rewardHistory.length === 0 && (
                <tr><td colSpan={4} style={{ textAlign: "center", color: "var(--terminal-muted)" }}>Aucun reward pour ce wallet.</td></tr>
              )}
              {rewardHistory.map((r) => (
                <tr key={r.block_index}>
                  <td>#{r.block_index}</td>
                  <td>{r.reward_artcb}</td>
                  <td>{r.pol_score?.toFixed(2)}</td>
                  <td>{r.timestamp}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
