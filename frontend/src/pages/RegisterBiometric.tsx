/**
 * RegisterBiometric — R358
 *
 * Onglet CRÉER :
 *   - Aucun champ de nom
 *   - Un seul bouton "Créer un wallet"
 *   - Appelle /api/v1/auth/anon/register/options + verify
 *   - Le wallet_name est dérivé automatiquement du credential_id WebAuthn
 *   - L'OS décide du mécanisme de déverrouillage (PIN, Touch ID, Face ID…)
 *   - ARTCB n'affiche aucun choix biométrique
 *
 * Onglet SE CONNECTER :
 *   - Champ "Adresse ou nom de wallet" (technique) pour retrouver le credential
 *   - Appelle /api/v1/auth/webauthn/login/options + verify
 *   - L'OS déverrouille le credential enregistré
 *
 * Séparation garantie :
 *   WebAuthn credential ≠ clé wallet ARTCB (Ed25519) ≠ identité humaine unique
 *   CERTIFIED_100=false — inchangé
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  anonRegisterOptions,
  anonRegisterVerify,
  webauthnLoginOptions,
  webauthnLoginVerify,
} from "../api/client";
import { useDashboard } from "../context/DashboardContext";
import { useTranslation } from "../i18n/useTranslation";
import {
  createPlatformCredential,
  getPlatformCredential,
  serializeCredential,
  webauthnSupported,
} from "../lib/webauthn";

const SESSION_TOKEN_KEY = "artcb_session_token";
const SESSION_WALLET_KEY = "artcb_session_wallet";

type Mode = "create" | "login";

export function RegisterBiometric() {
  const { t } = useTranslation();
  const { setActorAddress } = useDashboard();
  const [mode, setMode] = useState<Mode>("create");

  // Onglet connexion uniquement
  const [loginName, setLoginName] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [seed, setSeed] = useState<string | null>(null);
  // R361 — clé privée PQC ML-DSA-65 (4032 octets = 8064 hex chars)
  const [pqcSecret, setPqcSecret] = useState<string | null>(null);
  const [address, setAddress] = useState<string | null>(null);
  const [walletName, setWalletName] = useState<string | null>(null);

  const persistSession = (token: string, wallet: string, addr: string) => {
    sessionStorage.setItem(SESSION_TOKEN_KEY, token);
    sessionStorage.setItem(SESSION_WALLET_KEY, wallet);
    setActorAddress(addr);
    setAddress(addr);
    setWalletName(wallet);
  };

  // ── Création anonyme ────────────────────────────────────────────────────────
  const handleCreate = async () => {
    if (!webauthnSupported()) {
      setError(t("reg_webauthn_unsupported"));
      return;
    }
    setBusy(true);
    setError(null);
    setInfo(null);
    setSeed(null);
    setPqcSecret(null);
    try {
      const begin = await anonRegisterOptions(true);
      const cred = await createPlatformCredential(begin.publicKey);
      const done = await anonRegisterVerify(serializeCredential(cred), true);
      persistSession(done.session_token, done.wallet_name, done.address);
      if (done.seed_hex) setSeed(done.seed_hex);
      // R361 — clé privée PQC reçue si wallet hybride
      if ((done as Record<string, unknown>).pqc_secret_key_hex) {
        setPqcSecret((done as Record<string, unknown>).pqc_secret_key_hex as string);
      }
      setInfo(t("reg_created_ok"));
    } catch (err) {
      const ax = err as { response?: { data?: { detail?: unknown } } };
      const detail = ax?.response?.data?.detail;
      setError(
        typeof detail === "string"
          ? detail
          : detail
            ? JSON.stringify(detail)
            : err instanceof Error
              ? err.message
              : String(err),
      );
    } finally {
      setBusy(false);
    }
  };

  // ── Connexion (nom/adresse requis pour retrouver le credential) ─────────────
  const handleLogin = async () => {
    if (!loginName.trim()) {
      setError(t("reg_login_name_required"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const begin = await webauthnLoginOptions(loginName.trim());
      const cred = await getPlatformCredential(begin.publicKey);
      const done = await webauthnLoginVerify(loginName.trim(), serializeCredential(cred));
      persistSession(done.session_token, done.wallet_name || loginName.trim(), done.address);
      setInfo(t("reg_login_ok"));
    } catch (err) {
      // R385: err.message already contains a clear diagnostic if thrown by webauthnLoginOptions
      const ax = err as { response?: { data?: { detail?: unknown } }; message?: string };
      const detail = ax?.response?.data?.detail;
      const msg =
        typeof detail === "string"
          ? detail
          : detail
            ? JSON.stringify(detail)
            : ax?.message || (err instanceof Error ? err.message : String(err));
      setError(msg);
    } finally {
      setBusy(false);
    }
  };

  const switchMode = (m: Mode) => {
    setMode(m);
    setError(null);
    setInfo(null);
  };

  return (
    <div className="mc-page bio-page">
      <h1 className="dashboard-title">{t("reg_title")}</h1>
      <p className="bio-lead">{t("reg_subtitle")}</p>

      {/* Onglets */}
      <div className="bio-mode-toggle" role="tablist">
        <button
          className={mode === "create" ? "primary" : ""}
          onClick={() => switchMode("create")}
          type="button"
        >
          {t("reg_tab_create")}
        </button>
        <button
          className={mode === "login" ? "primary" : ""}
          onClick={() => switchMode("login")}
          type="button"
        >
          {t("reg_tab_login")}
        </button>
      </div>

      {/* ── Onglet CRÉER — zéro champ ─────────────────────────────────────── */}
      {mode === "create" && (
        <div className="panel">
          <p className="mc-muted">{t("reg_create_help")}</p>
          <button
            className="bio-choice primary"
            type="button"
            disabled={busy}
            onClick={handleCreate}
            style={{ marginTop: "1rem" }}
          >
            {busy ? t("reg_busy") : t("reg_create_btn")}
          </button>
        </div>
      )}

      {/* ── Onglet CONNEXION — champ nom technique ────────────────────────── */}
      {mode === "login" && (
        <div className="panel">
          <label className="bio-label" htmlFor="reg-login-name">
            {t("reg_login_name_label")}
          </label>
          <input
            id="reg-login-name"
            value={loginName}
            onChange={(e) => setLoginName(e.target.value)}
            placeholder={t("reg_login_name_placeholder")}
            autoComplete="username"
            inputMode="text"
            onKeyDown={(e) => e.key === "Enter" && handleLogin()}
          />
          <p className="mc-muted" style={{ fontSize: "0.8em" }}>
            {t("reg_login_name_hint")}
          </p>
          <button
            className="bio-choice primary"
            type="button"
            disabled={busy || !loginName.trim()}
            onClick={handleLogin}
            style={{ marginTop: "0.5rem" }}
          >
            {busy ? t("reg_busy") : t("reg_login_btn")}
          </button>
        </div>
      )}

      {error && <p className="mc-error">{error}</p>}
      {info && <p className="bio-ok">{info}</p>}

      {/* Wallet créé — afficher l'adresse et le nom technique */}
      {address && walletName && (
        <div className="panel" style={{ marginTop: "1rem" }}>
          <p className="mc-muted">{t("reg_wallet_id_label")}</p>
          <p className="mc-mono" style={{ wordBreak: "break-all" }}>{walletName}</p>
          <p className="mc-muted">{t("reg_address_label")}</p>
          <p className="mc-mono" style={{ wordBreak: "break-all" }}>{address}</p>
          <Link to="/wallets">{t("reg_open_wallet")}</Link>
        </div>
      )}

      {/* R361 — Clés privées — afficher UNE SEULE FOIS */}
      {(seed || pqcSecret) && (
        <div className="panel" style={{ border: "2px solid var(--mc-redstone, #c0392b)", marginTop: "1rem" }}>
          <h2>⚠ {t("reg_seed_once")}</h2>

          {seed && (
            <>
              <p className="mc-muted" style={{ marginTop: "0.75rem" }}>
                {t("reg_key_ed25519_label")}
              </p>
              <p className="mc-mono" style={{ wordBreak: "break-all", fontSize: "0.8em" }}>{seed}</p>
            </>
          )}

          {pqcSecret && (
            <>
              <p className="mc-muted" style={{ marginTop: "0.75rem" }}>
                {t("reg_key_pqc_label")}
              </p>
              <p className="mc-mono" style={{
                wordBreak: "break-all",
                fontSize: "0.7em",
                maxHeight: "8em",
                overflowY: "auto",
                border: "1px solid var(--mc-border, #e5e7eb)",
                padding: "0.4em",
              }}>
                {pqcSecret}
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
