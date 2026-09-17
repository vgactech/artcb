/**
 * RegisterBiometric — R357
 *
 * Architecture cible :
 *   - L'utilisateur choisit un nom de wallet
 *   - Un seul bouton "Créer le wallet" → WebAuthn natif de l'OS
 *   - L'OS décide comment déverrouiller le credential (PIN, Touch ID, Face ID…)
 *   - ARTCB ne présente PAS de choix biométrique (pas de Fingerprint / Face / Both)
 *   - PAS de caméra, PAS de FaceCapture, PAS de face enrollment
 *   - Le même formulaire sert aussi à la connexion (tab Connexion)
 *
 * Séparation garantie :
 *   WebAuthn credential ≠ identité humaine unique ≠ preuve anti-Sybil
 *   (CERTIFIED_100=false — ces preuves sont gérées hors de ce formulaire)
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  webauthnLoginOptions,
  webauthnLoginVerify,
  webauthnRegisterOptions,
  webauthnRegisterVerify,
} from "../api/client";
import { useDashboard } from "../context/DashboardContext";
import { useTranslation } from "../i18n/useTranslation";
import {
  createPlatformCredential,
  getPlatformCredential,
  platformAuthenticatorAvailable,
  serializeCredential,
  webauthnSupported,
} from "../lib/webauthn";

const SESSION_TOKEN_KEY = "artcb_session_token";
const SESSION_WALLET_KEY = "artcb_session_wallet";

type Mode = "register" | "login";

export function RegisterBiometric() {
  const { t } = useTranslation();
  const { setActorAddress } = useDashboard();
  const [mode, setMode] = useState<Mode>("register");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [seed, setSeed] = useState<string | null>(null);
  const [address, setAddress] = useState<string | null>(null);
  const [platformOk, setPlatformOk] = useState<boolean | null>(null);

  useEffect(() => {
    platformAuthenticatorAvailable().then(setPlatformOk).catch(() => setPlatformOk(false));
  }, []);

  const persistSession = (token: string, wallet: string, addr: string) => {
    sessionStorage.setItem(SESSION_TOKEN_KEY, token);
    sessionStorage.setItem(SESSION_WALLET_KEY, wallet);
    setActorAddress(addr);
    setAddress(addr);
  };

  const handleRegister = async () => {
    if (!name.trim()) {
      setError(t("reg_name_required"));
      return;
    }
    if (!webauthnSupported()) {
      setError(t("reg_webauthn_unsupported"));
      return;
    }
    setBusy(true);
    setError(null);
    setInfo(null);
    setSeed(null);
    try {
      // Passe "fingerprint" au backend comme modalité par défaut —
      // l'OS choisit lui-même comment déverrouiller (PIN, biométrie, etc.)
      const begin = await webauthnRegisterOptions(name.trim(), "fingerprint", true);
      const cred = await createPlatformCredential(begin.publicKey);
      const done = await webauthnRegisterVerify(name.trim(), "fingerprint", serializeCredential(cred), true);
      persistSession(done.session_token, done.wallet_name || name.trim(), done.address);
      if (done.seed_hex) setSeed(done.seed_hex);
      setInfo(t("reg_created_ok"));
    } catch (err) {
      const ax = err as { response?: { data?: { detail?: string } } };
      setError(ax?.response?.data?.detail || (err instanceof Error ? err.message : String(err)));
    } finally {
      setBusy(false);
    }
  };

  const handleLogin = async () => {
    if (!name.trim()) {
      setError(t("reg_name_required"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const begin = await webauthnLoginOptions(name.trim(), "fingerprint");
      const cred = await getPlatformCredential(begin.publicKey);
      const done = await webauthnLoginVerify(name.trim(), serializeCredential(cred));
      persistSession(done.session_token, done.wallet_name || name.trim(), done.address);
      setInfo(t("reg_login_ok"));
    } catch (err) {
      const ax = err as { response?: { data?: { detail?: string } } };
      setError(ax?.response?.data?.detail || (err instanceof Error ? err.message : String(err)));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mc-page bio-page">
      <h1 className="dashboard-title">{t("reg_title")}</h1>
      <p className="bio-lead">{t("reg_subtitle")}</p>
      <p className="mc-muted">{t("reg_disclaimer")}</p>

      {/* Onglets Créer / Connexion */}
      <div className="bio-mode-toggle" role="tablist">
        <button
          className={mode === "register" ? "primary" : ""}
          onClick={() => { setMode("register"); setError(null); setInfo(null); }}
          type="button"
        >
          {t("reg_tab_create")}
        </button>
        <button
          className={mode === "login" ? "primary" : ""}
          onClick={() => { setMode("login"); setError(null); setInfo(null); }}
          type="button"
        >
          {t("reg_tab_login")}
        </button>
      </div>

      <div className="panel">
        <label className="bio-label" htmlFor="reg-wallet-name">
          {t("reg_name_label")}
        </label>
        <input
          id="reg-wallet-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t("reg_name_placeholder")}
          autoComplete="username"
          inputMode="text"
          onKeyDown={(e) => e.key === "Enter" && (mode === "register" ? handleRegister() : handleLogin())}
        />

        {platformOk === false && (
          <p className="mc-muted">{t("reg_platform_unavailable")}</p>
        )}
      </div>

      {/* Bouton unique — pas de choix biométrique */}
      {mode === "register" ? (
        <button
          className="bio-choice primary"
          type="button"
          disabled={busy || !name.trim()}
          onClick={handleRegister}
        >
          {busy ? t("reg_busy") : t("reg_create_btn")}
        </button>
      ) : (
        <button
          className="bio-choice primary"
          type="button"
          disabled={busy || !name.trim()}
          onClick={handleLogin}
        >
          {busy ? t("reg_busy") : t("reg_login_btn")}
        </button>
      )}

      {error && <p className="mc-error">{error}</p>}
      {info && <p className="bio-ok">{info}</p>}

      {address && (
        <p className="mc-mono">
          Wallet : {address} — <Link to="/wallets">ouvrir</Link>
        </p>
      )}

      {seed && (
        <div className="panel" style={{ border: "2px solid var(--mc-redstone, #c0392b)" }}>
          <h2>⚠ {t("reg_seed_once")}</h2>
          <p className="mc-mono" style={{ wordBreak: "break-all" }}>{seed}</p>
        </div>
      )}
    </div>
  );
}

