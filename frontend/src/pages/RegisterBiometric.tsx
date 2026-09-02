import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  faceEnrollOptions,
  faceEnrollVerify,
  faceLogin,
  faceLoginOptions,
  webauthnLoginOptions,
  webauthnLoginVerify,
  webauthnRegisterOptions,
  webauthnRegisterVerify,
  webauthnStatus,
} from "../api/client";
import { FaceCapture, loadFaceSecret, saveFaceSecret } from "../components/FaceCapture";
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

type Modality = "fingerprint" | "face" | "both";
type Mode = "register" | "login";

export function RegisterBiometric() {
  const { t } = useTranslation();
  const { setActorAddress } = useDashboard();
  const [mode, setMode] = useState<Mode>("register");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [cameraOn, setCameraOn] = useState(false);
  const [cameraIntent, setCameraIntent] = useState<"enroll" | "login" | null>(null);
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

  const runWebauthnRegister = async (modality: "fingerprint" | "face", alsoCreate: boolean) => {
    if (!webauthnSupported()) {
      throw new Error("Ce navigateur ne prend pas en charge WebAuthn (empreinte / Face ID).");
    }
    const begin = await webauthnRegisterOptions(name.trim(), modality, alsoCreate);
    const cred = await createPlatformCredential(begin.publicKey);
    const done = await webauthnRegisterVerify(name.trim(), modality, serializeCredential(cred), alsoCreate);
    persistSession(done.session_token, done.wallet_name || name.trim(), done.address);
    if (done.seed_hex) setSeed(done.seed_hex);
    return done;
  };

  const enrollFaceCamera = useCallback(
    async (secret: string) => {
      setCameraOn(false);
      setBusy(true);
      setError(null);
      try {
        const begin = await faceEnrollOptions(name.trim(), true);
        const done = await faceEnrollVerify({
          name: name.trim(),
          nonce: begin.nonce,
          device_secret: secret,
          liveness_ok: true,
          create_wallet: true,
        });
        saveFaceSecret(name.trim(), secret);
        persistSession(done.session_token, done.wallet_name || name.trim(), done.address);
        if (done.seed_hex) setSeed(done.seed_hex);
        setInfo("Reconnaissance faciale (caméra) enregistrée. Aucune photo n'a été stockée.");
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
        setCameraIntent(null);
      }
    },
    [name, setActorAddress],
  );

  const loginFaceCamera = useCallback(
    async (secret: string) => {
      setCameraOn(false);
      setBusy(true);
      setError(null);
      try {
        const begin = await faceLoginOptions(name.trim());
        const stored = loadFaceSecret(name.trim()) || secret;
        const done = await faceLogin({
          name: name.trim(),
          nonce: begin.nonce,
          device_secret: stored,
          liveness_ok: true,
        });
        persistSession(done.session_token, done.wallet_name || name.trim(), done.address);
        setInfo("Connecté par reconnaissance faciale.");
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
        setCameraIntent(null);
      }
    },
    [name, setActorAddress],
  );

  const handleRegister = async (choice: Modality) => {
    if (!name.trim()) {
      setError("Choisissez un nom de wallet.");
      return;
    }
    setBusy(true);
    setError(null);
    setInfo(null);
    setSeed(null);
    try {
      if (choice === "fingerprint") {
        await runWebauthnRegister("fingerprint", true);
        setInfo("Empreinte enregistrée via le capteur de l'appareil (WebAuthn).");
      } else if (choice === "face") {
        // Camera first. WebAuthn "face" is the same OS sensor as fingerprint
        // (Android/iOS cannot open the selfie camera via navigator.credentials).
        setCameraIntent("enroll");
        setCameraOn(true);
        setInfo("Caméra avant : placez votre visage dans le cadre. Aucune photo n'est envoyée.");
      } else {
        await runWebauthnRegister("fingerprint", true);
        setCameraIntent("enroll");
        setCameraOn(true);
        setInfo("Empreinte enregistrée. Caméra avant pour le visage — aucune photo n'est envoyée.");
      }
    } catch (err) {
      const ax = err as { response?: { data?: { detail?: string } } };
      setError(ax?.response?.data?.detail || (err instanceof Error ? err.message : String(err)));
    } finally {
      setBusy(false);
    }
  };

  const handleLogin = async (choice: Exclude<Modality, "both">) => {
    if (!name.trim()) {
      setError("Indiquez le nom du wallet.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (choice === "fingerprint") {
        const begin = await webauthnLoginOptions(name.trim(), "fingerprint");
        const cred = await getPlatformCredential(begin.publicKey);
        const done = await webauthnLoginVerify(name.trim(), serializeCredential(cred));
        persistSession(done.session_token, done.wallet_name || name.trim(), done.address);
        setInfo("Connecté par empreinte.");
      } else {
        const st = await webauthnStatus(name.trim()).catch(() => null);
        const hasCamera = Boolean(st?.face_camera_enrolled || loadFaceSecret(name.trim()));
        if (hasCamera) {
          setCameraIntent("login");
          setCameraOn(true);
          setInfo("Caméra avant : placez votre visage dans le cadre.");
        } else {
          // Existing enrollments created via OS sensor (same as fingerprint).
          const begin = await webauthnLoginOptions(name.trim(), "face");
          const cred = await getPlatformCredential(begin.publicKey);
          const done = await webauthnLoginVerify(name.trim(), serializeCredential(cred));
          persistSession(done.session_token, done.wallet_name || name.trim(), done.address);
          setInfo("Connecté par le capteur de l'appareil (Face ID / empreinte OS). La caméra s'ouvre pour les nouveaux comptes visage.");
        }
      }
    } catch (err) {
      const ax = err as { response?: { data?: { detail?: string } } };
      setError(ax?.response?.data?.detail || (err instanceof Error ? err.message : String(err)));
    } finally {
      setBusy(false);
    }
  };

  const onLive = useCallback(
    (secret: string) => {
      if (cameraIntent === "login") loginFaceCamera(secret);
      else enrollFaceCamera(secret);
    },
    [cameraIntent, enrollFaceCamera, loginFaceCamera],
  );

  return (
    <div className="mc-page bio-page">
      <h1 className="dashboard-title">{t("bio_title")}</h1>
      <p className="bio-lead">{t("bio_subtitle")}</p>
      <p className="mc-muted">{t("bio_raw_never_stored")}</p>

      <div className="bio-mode-toggle" role="tablist">
        <button className={mode === "register" ? "primary" : ""} onClick={() => setMode("register")} type="button">
          {t("bio_register_tab")}
        </button>
        <button className={mode === "login" ? "primary" : ""} onClick={() => setMode("login")} type="button">
          {t("bio_login")}
        </button>
      </div>

      <div className="panel">
        <label className="bio-label" htmlFor="bio-wallet-name">
          {t("bio_name_label")}
        </label>
        <input
          id="bio-wallet-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t("bio_name_placeholder")}
          autoComplete="username"
          inputMode="text"
        />
        {platformOk === false && (
          <p className="mc-muted">{t("bio_unsupported")}</p>
        )}
      </div>

      {mode === "register" ? (
        <div className="bio-choices">
          <button className="bio-choice primary" type="button" disabled={busy || !name.trim()} onClick={() => handleRegister("fingerprint")}>
            {t("bio_fingerprint")}
          </button>
          <button className="bio-choice" type="button" disabled={busy || !name.trim()} onClick={() => handleRegister("face")}>
            {t("bio_face")}
          </button>
          <button className="bio-choice" type="button" disabled={busy || !name.trim()} onClick={() => handleRegister("both")}>
            {t("bio_both")}
          </button>
        </div>
      ) : (
        <div className="bio-choices">
          <button className="bio-choice primary" type="button" disabled={busy || !name.trim()} onClick={() => handleLogin("fingerprint")}>
            {t("bio_login_fingerprint")}
          </button>
          <button className="bio-choice" type="button" disabled={busy || !name.trim()} onClick={() => handleLogin("face")}>
            {t("bio_login_face")}
          </button>
        </div>
      )}

      <FaceCapture
        active={cameraOn}
        onLive={onLive}
        onError={(msg) => {
          setError(msg);
          setCameraOn(false);
        }}
        label={t("bio_camera_help")}
      />

      {busy && <p className="mc-muted">{t("bio_webauthn_prompt")}</p>}
      {error && <p className="mc-error">{error}</p>}
      {info && <p className="bio-ok">{info}</p>}
      {address && (
        <p className="mc-mono">
          Wallet : {address} — <Link to="/wallets">ouvrir</Link>
        </p>
      )}
      {seed && (
        <div className="panel" style={{ border: "2px solid var(--mc-redstone, #c0392b)" }}>
          <h2>⚠ {t("bio_seed_once")}</h2>
          <p className="mc-mono" style={{ wordBreak: "break-all" }}>{seed}</p>
        </div>
      )}
    </div>
  );
}

export function useWebauthnStatus(name: string) {
  const [status, setStatus] = useState<Awaited<ReturnType<typeof webauthnStatus>> | null>(null);
  useEffect(() => {
    if (!name) return;
    webauthnStatus(name).then(setStatus).catch(() => setStatus(null));
  }, [name]);
  return status;
}
