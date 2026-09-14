import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  authMe,
  generateApiKey,
  listApiKeys,
  revokeApiKey,
  type ApiKeyRecord,
} from "../api/client";
import { useTranslation } from "../i18n/useTranslation";

const SCOPE_OPTIONS = ["read", "write", "mining", "admin"];

function ts(epoch: number) {
  return new Date(epoch * 1000).toLocaleString();
}

function httpStatus(err: unknown): number | null {
  const ax = err as { response?: { status?: number } };
  return ax?.response?.status ?? null;
}

export function ApiKeys() {
  const { t } = useTranslation();
  const [keys, setKeys] = useState<ApiKeyRecord[] | null>(null); // null = not loaded
  const [sessionOk, setSessionOk] = useState<boolean | null>(null);
  const [sessionWallet, setSessionWallet] = useState<string | null>(null);
  const [sessionAddress, setSessionAddress] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [scopes, setScopes] = useState<string[]>(["read", "write", "mining"]);
  const [expiresDays, setExpiresDays] = useState<string>("7");
  const [newToken, setNewToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [authHint, setAuthHint] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const checkSession = async (): Promise<boolean> => {
    try {
      const me = await authMe();
      // backend: authenticated false for anonymous; true for sess_
      const wallet = (me as { wallet_name?: string | null }).wallet_name ?? null;
      const addr = (me as { address?: string | null }).address ?? null;
      const authed =
        (me as { authenticated?: boolean }).authenticated === true ||
        Boolean(wallet && addr);
      setSessionOk(authed);
      setSessionWallet(wallet);
      setSessionAddress(addr);
      if (!authed) {
        setAuthHint(
          "Aucune session utilisateur (sess_…) — connectez d’abord le wallet sur la page Portefeuilles."
        );
        setKeys(null);
      } else {
        setAuthHint(null);
      }
      return authed;
    } catch (e) {
      const st = httpStatus(e);
      setSessionOk(false);
      setSessionWallet(null);
      setSessionAddress(null);
      setKeys(null);
      setAuthHint(
        st === 401
          ? "Session absente ou expirée (HTTP 401). Connectez le wallet avant de gérer les clés API."
          : `Impossible de vérifier la session : ${String(e)}`
      );
      return false;
    }
  };

  const reload = async () => {
    setError(null);
    const ok = await checkSession();
    if (!ok) return;
    try {
      const res = await listApiKeys();
      setKeys(res.keys);
    } catch (e) {
      const st = httpStatus(e);
      setKeys(null);
      if (st === 401) {
        setSessionOk(false);
        setAuthHint(
          "Impossible de charger les clés : HTTP 401 (session requise). Ce n’est pas « 0 clé »."
        );
      } else {
        setError(String(e));
      }
    }
  };

  useEffect(() => {
    void reload();
  }, []);

  const handleGenerate = async () => {
    if (!label.trim() || sessionOk !== true) return;
    setLoading(true);
    setError(null);
    setNewToken(null);
    setCopied(false);
    try {
      const res = await generateApiKey({
        label: label.trim(),
        scopes,
        expires_days: expiresDays ? parseInt(expiresDays, 10) : 7,
      });
      setNewToken(res.token);
      setLabel("");
      await reload();
    } catch (e) {
      const st = httpStatus(e);
      if (st === 401) {
        setSessionOk(false);
        setAuthHint("Génération refusée : session invalide (401). Reconnectez le wallet.");
      } else {
        setError(String(e));
      }
    } finally {
      setLoading(false);
    }
  };

  const handleRevoke = async (keyId: string) => {
    if (sessionOk !== true) return;
    try {
      await revokeApiKey(keyId);
      await reload();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleCopy = () => {
    if (!newToken) return;
    navigator.clipboard.writeText(newToken).then(() => setCopied(true));
  };

  const toggleScope = (s: string) => {
    setScopes((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]
    );
  };

  const canManage = sessionOk === true;

  return (
    <div className="mc-page">
      <h1 className="dashboard-title">{t("api_keys_title")}</h1>
      <p className="mc-hint">
        Une clé <code>artcb_…</code> donne un <strong>accès API</strong> lié au wallet
        connecté (session). Ce n’est pas une preuve d’humain unique, ni d’identité
        Cursor = wallet. Ne transmettez jamais le <code>seed_hex</code> à Cursor —
        uniquement le token <code>artcb_…</code>.
      </p>

      {authHint && (
        <div className="panel" style={{ border: "1px solid var(--mc-gold)" }}>
          <p className="mc-error">{authHint}</p>
          <Link to="/wallets" className="mc-btn primary" style={{ display: "inline-block" }}>
            Se connecter / Portefeuilles
          </Link>
        </div>
      )}

      {canManage && sessionWallet && (
        <p className="mc-muted">
          Session : <strong>{sessionWallet}</strong>
          {sessionAddress ? ` · ${sessionAddress.slice(0, 18)}…` : ""}
        </p>
      )}

      {error && <p className="mc-error">{error}</p>}

      {newToken && (
        <div className="panel" style={{ border: "2px solid var(--mc-gold)" }}>
          <h2 className="mc-gold-text">[!] {t("api_keys_token_warning")}</h2>
          <p className="mc-mono" style={{ wordBreak: "break-all", fontSize: "0.85rem" }}>
            {newToken}
          </p>
          <button className="mc-btn" onClick={handleCopy}>
            {copied ? "[OK] Copié" : "Copier"}
          </button>
          <button
            className="mc-btn-sm"
            style={{ marginLeft: "0.5rem" }}
            onClick={() => setNewToken(null)}
          >
            Fermer
          </button>
          <p className="mc-muted" style={{ marginTop: "0.5rem" }}>
            Cursor / agent : <code>ARTCB_API_KEY={newToken}</code> — accès API seulement.
          </p>
        </div>
      )}

      <section className="mc-card">
        <h2>{t("api_keys_new_key")}</h2>
        {!canManage ? (
          <p className="mc-muted">
            Génération désactivée tant qu’aucune session <code>sess_…</code> n’est valide.
          </p>
        ) : (
          <>
            <label>
              Nom de la clé
              <input
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="Cursor / agent de développement"
              />
            </label>

            <label>
              Droits (scopes)
              <div className="toolbar" style={{ flexWrap: "wrap", gap: "0.5rem", marginTop: "0.25rem" }}>
                {SCOPE_OPTIONS.map((s) => (
                  <label key={s} style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
                    <input
                      type="checkbox"
                      checked={scopes.includes(s)}
                      onChange={() => toggleScope(s)}
                    />
                    {s}
                  </label>
                ))}
              </div>
            </label>

            <label>
              Expiration (jours — défaut 7 pour tests)
              <input
                type="number"
                value={expiresDays}
                onChange={(e) => setExpiresDays(e.target.value)}
                placeholder="7"
                min={1}
                max={3650}
                style={{ width: "8rem" }}
              />
            </label>

            <button
              type="button"
              className="mc-btn primary"
              onClick={handleGenerate}
              disabled={loading || label.trim().length === 0 || scopes.length === 0}
            >
              {loading ? "Génération…" : "Générer la clé"}
            </button>
          </>
        )}
      </section>

      <section className="mc-card">
        <h2>
          {t("api_keys_active")}
          {keys === null
            ? " — non chargées"
            : ` (${keys.filter((k) => k.active).length})`}
        </h2>
        {!canManage && (
          <p className="mc-muted">
            Liste non disponible sans session. Un affichage « 0 clé » après 401 serait trompeur —
            il est volontairement évité ici.
          </p>
        )}
        {canManage && keys !== null && keys.length === 0 && (
          <p className="mc-muted">Aucune clé active pour ce wallet — créez-en une ci-dessus.</p>
        )}
        {canManage && keys && (
          <ul className="mc-connector-list">
            {keys.map((k) => (
              <li
                key={k.key_id}
                className={`mc-connector-item${k.active ? "" : " mc-muted"}`}
              >
                <strong>{k.label}</strong>
                {!k.active && <span className="mc-error"> [RÉVOQUÉE]</span>}
                <p className="mc-mono" style={{ fontSize: "0.8rem" }}>
                  {k.key_preview} · scopes: {k.scopes.join(", ")}
                </p>
                <p className="mc-muted" style={{ fontSize: "0.8rem" }}>
                  Créée: {ts(k.created_at)}
                  {k.expires_at && ` · Expire: ${ts(k.expires_at)}`}
                  {k.last_used_at && ` · Dernier usage: ${ts(k.last_used_at)}`}
                </p>
                {k.active && (
                  <div className="mc-connector-actions">
                    <button
                      type="button"
                      className="mc-btn-sm mc-btn-danger"
                      onClick={() => handleRevoke(k.key_id)}
                    >
                      Révoquer
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mc-card">
        <h2>{t("api_keys_cursor_usage")}</h2>
        <ol style={{ lineHeight: "2" }}>
          <li>Connecter le wallet déjà existant (session <code>sess_…</code>)</li>
          <li>Générer une clé scopes <code>read,write,mining</code> (TTL court recommandé)</li>
          <li>
            Dans Cursor : <code>ARTCB_API_KEY=artcb_…</code> (jamais le seed)
          </li>
          <li>
            Vérifier read / write / mining, puis révocation → ancienne clé = 401
          </li>
        </ol>
      </section>
    </div>
  );
}
