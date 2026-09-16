/**
 * BiometricIdentityTest — Page de test manuel d'empreinte ARTCB (P0-C 2026-09-16).
 *
 * FLUX COMPLET :
 *   1. L'appareil capture ton empreinte via WebAuthn (capteur natif OS).
 *   2. WebAuthn retourne une signature cryptographique (PAS le template brut — c'est le standard W3C).
 *   3. On dérive un "template simulé" depuis la signature pour nourrir le FuzzyExtractor ARTCB.
 *      NOTE D'HONNÊTETÉ : ce n'est pas un vrai template biométrique extracté — c'est une preuve
 *      de possession du capteur. Pour un vrai template, il faudrait un SDK natif iOS/Android.
 *   4. POST /identity/biometric/uniqueness-check → vérifie si déjà inscrit.
 *   5. POST /identity/biometric/enroll → inscrit, retourne human_id + private_for_client.
 *   6. Affichage : human_id, secret_hex (à sauvegarder), blinding_hex.
 *
 * LIMITES HONNÊTES (CERTIFIED_100=false) :
 *   - unique_human_proven = false partout
 *   - Le template dérivé de WebAuthn ≠ template biométrique brut extracté
 *   - FAR/FRR/PAD non mesurés
 *   - Pour un vrai test en production : SDK natif iOS/Android + enclave sécurisée
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  biometricEnroll,
  biometricUniquenessCheck,
  fetchHumanIdentity,
  listHumanIdentities,
  webauthnRegisterOptions,
  type BiometricEnrollResponse,
  type HumanIdentityRecord,
  type UniquenessCheckResponse,
} from "../api/client";
import { useDashboard } from "../context/DashboardContext";
import {
  createPlatformCredential,
  platformAuthenticatorAvailable,
  serializeCredential,
  webauthnSupported,
} from "../lib/webauthn";

// ─── Clé localStorage pour les données privées du client ────────────────────
const PRIVATE_KEY = "artcb_biometric_private";

function savePrivateData(human_id: string, secret_hex: string, blinding_hex: string) {
  try {
    const existing = JSON.parse(localStorage.getItem(PRIVATE_KEY) || "{}");
    existing[human_id] = { secret_hex, blinding_hex, saved_at: new Date().toISOString() };
    localStorage.setItem(PRIVATE_KEY, JSON.stringify(existing));
  } catch { /* ignore */ }
}

function loadPrivateData(human_id: string): { secret_hex: string; blinding_hex: string } | null {
  try {
    const all = JSON.parse(localStorage.getItem(PRIVATE_KEY) || "{}");
    return all[human_id] || null;
  } catch { return null; }
}

// ─── Dériver un template hex depuis une signature WebAuthn ──────────────────
// NOTE : ceci est une approximation pour le test — PAS un vrai template biométrique.
// En production : SDK natif avec accès TEE/Secure Enclave.
async function deriveTemplateFromWebAuthn(signatureBytes: Uint8Array): Promise<string> {
  // Copie dans un vrai ArrayBuffer pour crypto.subtle (évite l'incompatibilité SharedArrayBuffer)
  const buf = signatureBytes.buffer.slice(
    signatureBytes.byteOffset,
    signatureBytes.byteOffset + signatureBytes.byteLength
  ) as ArrayBuffer;
  const ext = await crypto.subtle.digest("SHA-512", buf);
  return Array.from(new Uint8Array(ext)).map(b => b.toString(16).padStart(2, "0")).join("");
}

// ─── Types état ─────────────────────────────────────────────────────────────
type Step = "idle" | "checking" | "enrolling" | "done" | "already" | "error";

interface EnrollState {
  step: Step;
  human_id: string | null;
  template_hex: string | null;
  enroll_result: BiometricEnrollResponse | null;
  uniqueness_result: UniquenessCheckResponse | null;
  private_saved: boolean;
  error: string | null;
}

// ────────────────────────────────────────────────────────────────────────────

export function BiometricIdentityTest() {
  const { actorAddress } = useDashboard();
  const [platformOk, setPlatformOk] = useState<boolean | null>(null);
  const [walletName, setWalletName] = useState("");
  const [state, setState] = useState<EnrollState>({
    step: "idle", human_id: null, template_hex: null,
    enroll_result: null, uniqueness_result: null, private_saved: false, error: null,
  });
  const [identities, setIdentities] = useState<string[]>([]);
  const [lookup, setLookup] = useState<string>("");
  const [lookupResult, setLookupResult] = useState<(HumanIdentityRecord & { found: boolean }) | null>(null);
  const [secretVisible, setSecretVisible] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const secretRef = useRef<string | null>(null);

  useEffect(() => {
    platformAuthenticatorAvailable().then(setPlatformOk).catch(() => setPlatformOk(false));
    listHumanIdentities().then(r => setIdentities(r.human_ids)).catch(() => {});
  }, []);

  const copyText = (text: string, key: string) => {
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(key);
      setTimeout(() => setCopied(null), 2500);
    });
  };

  // ── Flux principal : WebAuthn → template → unicité → enrôlement ──────────
  const handleEnroll = useCallback(async () => {
    setState(s => ({ ...s, step: "checking", error: null }));

    try {
      // ── Étape 1 : WebAuthn — capturer l'empreinte via le capteur natif ──
      if (!webauthnSupported()) {
        throw new Error("WebAuthn non supporté sur ce navigateur/appareil.");
      }

      // On crée un credential WebAuthn juste pour obtenir une signature liée au capteur.
      // Le nom de wallet est utilisé comme identifiant utilisateur.
      const nameForWa = walletName.trim() || `biometric_test_${Date.now()}`;
      const begin = await webauthnRegisterOptions(nameForWa, "fingerprint", false);
      const cred = await createPlatformCredential(begin.publicKey);
      const serialized = serializeCredential(cred);

      // ── Étape 2 : Dériver un template depuis la réponse WebAuthn ────────
      // Décoder la signature depuis b64url
      const attObj = serialized.response.attestationObject;
      const sigBytes = Uint8Array.from(
        atob(attObj.replace(/-/g, "+").replace(/_/g, "/")),
        c => c.charCodeAt(0)
      );
      const template_hex = await deriveTemplateFromWebAuthn(sigBytes);
      setState(s => ({ ...s, template_hex }));

      // ── Étape 3 : Vérification d'unicité ────────────────────────────────
      const uniqueness = await biometricUniquenessCheck(template_hex);
      setState(s => ({ ...s, uniqueness_result: uniqueness }));

      if (uniqueness.match_found) {
        // Identité déjà enregistrée — récupérer les données privées locales
        const priv = loadPrivateData(uniqueness.existing_human_id || "");
        setState(s => ({
          ...s,
          step: "already",
          human_id: uniqueness.existing_human_id,
          private_saved: priv !== null,
        }));
        return;
      }

      // ── Étape 4 : Enrôlement ────────────────────────────────────────────
      setState(s => ({ ...s, step: "enrolling" }));
      const result = await biometricEnroll(template_hex, actorAddress || undefined);

      // ── Étape 5 : Sauvegarder les données privées côté client ────────────
      const priv = result.private_for_client;
      savePrivateData(result.human_id, priv.secret_hex, priv.blinding_hex);
      secretRef.current = priv.secret_hex;

      setState(s => ({
        ...s,
        step: "done",
        human_id: result.human_id,
        enroll_result: result,
        private_saved: true,
      }));

      // Rafraîchir la liste
      listHumanIdentities().then(r => setIdentities(r.human_ids)).catch(() => {});

    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: unknown } } };
      const detail = ax?.response?.data?.detail;
      let msg = "";
      if (detail && typeof detail === "object" && "message" in detail) {
        msg = (detail as { message: string }).message;
      } else if (typeof detail === "string") {
        msg = detail;
      } else if (err instanceof Error) {
        msg = err.message;
      } else {
        msg = String(err);
      }
      setState(s => ({ ...s, step: "error", error: msg }));
    }
  }, [walletName, actorAddress]);

  const handleLookup = async () => {
    if (!lookup.trim()) return;
    try {
      const r = await fetchHumanIdentity(lookup.trim());
      setLookupResult(r);
    } catch {
      setLookupResult({ found: false } as HumanIdentityRecord & { found: boolean });
    }
  };

  const handleReset = () => {
    setState({
      step: "idle", human_id: null, template_hex: null,
      enroll_result: null, uniqueness_result: null, private_saved: false, error: null,
    });
    setSecretVisible(false);
    secretRef.current = null;
  };

  // ── Rendu ────────────────────────────────────────────────────────────────
  return (
    <div className="mc-page">
      <h1 className="dashboard-title">◉ Test biométrique manuel — Identité on-chain</h1>

      {/* ── Bannière honnêteté ─────────────────────────────────────────── */}
      <div className="panel" style={{ borderColor: "var(--mc-gold, #ffd700)", background: "rgba(255,215,0,0.04)", marginBottom: 16 }}>
        <p style={{ margin: 0, fontSize: 13 }}>
          <strong style={{ color: "var(--mc-gold)" }}>⚠ Honnêteté ARTCB</strong> —{" "}
          <code>unique_human_proven = false</code> · <code>CERTIFIED_100 = false</code>
        </p>
        <p style={{ margin: "6px 0 0 0", fontSize: 12, color: "var(--terminal-muted)" }}>
          Ce test utilise WebAuthn (capteur natif de ton appareil) pour dériver un template cryptographique.
          Ce n'est <strong>pas</strong> un template biométrique brut (le standard W3C interdit son extraction).
          C'est une preuve de possession du capteur liée à cet appareil.
          FAR/FRR/PAD non mesurés. Pour un test certifié : SDK natif iOS/Android + enclave sécurisée.
        </p>
      </div>

      {/* ── Étape 1 : Config ──────────────────────────────────────────────── */}
      <div className="panel">
        <h2>Étape 1 — Configuration</h2>

        {platformOk === false && (
          <div style={{ padding: "10px 14px", background: "rgba(192,57,43,0.1)", borderRadius: 6, marginBottom: 12, fontSize: 13 }}>
            ❌ Aucun authentificateur biométrique détecté sur cet appareil/navigateur.
            Essayez sur un smartphone ou un laptop avec lecteur d'empreinte.
          </div>
        )}
        {platformOk === true && (
          <div style={{ padding: "10px 14px", background: "rgba(86,196,38,0.08)", borderRadius: 6, marginBottom: 12, fontSize: 13 }}>
            ✅ Authentificateur biométrique détecté — prêt pour le test.
          </div>
        )}

        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
          <input
            value={walletName}
            onChange={e => setWalletName(e.target.value)}
            placeholder="Nom (optionnel — identifiant WebAuthn)"
            style={{ minWidth: 240 }}
          />
          {actorAddress && (
            <span style={{ fontSize: 12, color: "var(--mc-grass)" }}>
              Wallet actif : {actorAddress.slice(0, 14)}… sera lié à l'identité
            </span>
          )}
        </div>
        <p style={{ fontSize: 12, color: "var(--terminal-muted)", margin: "0 0 12px 0" }}>
          Le wallet actif ({actorAddress ? actorAddress.slice(0, 12) + "…" : "aucun"}) sera
          lié à ton identité biométrique. Connecte-toi d'abord dans{" "}
          <Link to="/register">Biométrie</Link> ou <Link to="/wallets">Wallets</Link> si nécessaire.
        </p>
      </div>

      {/* ── Étape 2 : Lancer le test ──────────────────────────────────────── */}
      <div className="panel">
        <h2>Étape 2 — Capturer ton empreinte</h2>

        {state.step === "idle" && (
          <>
            <p style={{ fontSize: 13, marginBottom: 12 }}>
              Clique sur le bouton ci-dessous. Ton appareil va te demander de
              <strong> poser ton doigt sur le lecteur</strong> (ou Face ID / Windows Hello).
              Aucune image biométrique n'est envoyée au serveur.
            </p>
            <button
              className="primary"
              onClick={handleEnroll}
              disabled={platformOk === false}
              style={{ fontSize: 15, padding: "10px 24px" }}
            >
              ◉ Tester mon empreinte biométrique
            </button>
          </>
        )}

        {(state.step === "checking" || state.step === "enrolling") && (
          <div style={{ padding: "16px 0" }}>
            <p style={{ fontSize: 14, fontWeight: 700 }}>
              {state.step === "checking"
                ? "⏳ Capture en cours — pose ton doigt sur le capteur…"
                : "⏳ Enrôlement on-chain en cours…"}
            </p>
            <p style={{ fontSize: 12, color: "var(--terminal-muted)" }}>
              {state.step === "checking"
                ? "Vérification d'unicité → si déjà inscrit, refus automatique."
                : "FuzzyExtractor → BiometricCommitment → HumanIdentityRecord → blockchain."}
            </p>
          </div>
        )}

        {state.step === "already" && (
          <div style={{ padding: "12px 14px", background: "rgba(255,215,0,0.08)", borderRadius: 6, border: "1px solid var(--mc-gold)" }}>
            <p style={{ fontWeight: 700, color: "var(--mc-gold)" }}>
              ◉ Identité déjà enregistrée — création refusée (spec §5)
            </p>
            <p style={{ fontSize: 13, margin: "6px 0" }}>
              human_id : <code className="mc-mono">{state.human_id}</code>
            </p>
            {state.private_saved ? (
              <p style={{ fontSize: 12, color: "var(--mc-grass)" }}>
                ✅ Tes données privées (secret_hex, blinding_hex) sont sauvegardées localement.
              </p>
            ) : (
              <p style={{ fontSize: 12, color: "var(--mc-redstone)" }}>
                ⚠ Données privées non trouvées en local — tu as peut-être changé d'appareil ou vidé le stockage.
              </p>
            )}
            <button onClick={handleReset} style={{ marginTop: 10 }}>Recommencer</button>
          </div>
        )}

        {state.step === "done" && state.enroll_result && (
          <>
            <div style={{ padding: "12px 14px", background: "rgba(86,196,38,0.1)", borderRadius: 6, border: "1px solid var(--mc-grass)", marginBottom: 16 }}>
              <p style={{ fontWeight: 700, color: "var(--mc-grass)", margin: 0 }}>
                ✅ Identité biométrique enregistrée sur la blockchain ARTCB
              </p>
              <p style={{ fontSize: 12, color: "var(--terminal-muted)", margin: "4px 0 0 0" }}>
                unique_human_proven=false · certified=false · stub non certifié
              </p>
            </div>

            {/* human_id */}
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontWeight: 700, marginBottom: 4 }}>◉ human_id (public — on-chain) :</div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <code className="mc-mono" style={{ fontSize: 12, background: "#111", padding: "6px 10px", borderRadius: 4, flex: 1, wordBreak: "break-all" }}>
                  {state.human_id}
                </code>
                <button onClick={() => copyText(state.human_id!, "human_id")}>
                  {copied === "human_id" ? "✓ Copié" : "Copier"}
                </button>
              </div>
            </div>

            {/* Record public */}
            <details style={{ marginBottom: 14 }}>
              <summary style={{ cursor: "pointer", fontSize: 13, userSelect: "none" }}>
                ▸ Record public on-chain (commitment + helper_data)
              </summary>
              <pre style={{ fontSize: 11, background: "#111", padding: 10, borderRadius: 4, overflow: "auto", marginTop: 8 }}>
                {JSON.stringify(state.enroll_result.human_identity_record, null, 2)}
              </pre>
            </details>

            {/* Données privées — CRITIQUE */}
            <div style={{ border: "2px solid var(--mc-redstone, #c0392b)", borderRadius: 6, padding: "14px 16px", marginBottom: 14 }}>
              <h3 style={{ color: "var(--mc-redstone)", marginTop: 0, marginBottom: 8 }}>
                ⚠ DONNÉES PRIVÉES — À sauvegarder maintenant
              </h3>
              <p style={{ fontSize: 12, marginBottom: 10, background: "rgba(192,57,43,0.08)", padding: "6px 10px", borderRadius: 4 }}>
                Ces données permettent de récupérer ton identité sur un nouvel appareil (recovery).
                <strong> Elles ne seront plus jamais affichées.</strong> Elles sont aussi sauvegardées dans
                le localStorage de ce navigateur.
              </p>

              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 4 }}>secret_hex (FuzzyExtractor) :</div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  {secretVisible ? (
                    <code className="mc-mono" style={{ fontSize: 11, background: "#1a0000", padding: "6px 10px", borderRadius: 4, flex: 1, wordBreak: "break-all", border: "1px solid var(--mc-redstone)" }}>
                      {state.enroll_result.private_for_client.secret_hex}
                    </code>
                  ) : (
                    <div style={{ flex: 1, background: "#1a0000", padding: "6px 10px", borderRadius: 4, fontFamily: "monospace", fontSize: 12, letterSpacing: 2, color: "#666", border: "1px solid #333" }}>
                      ████████████████████████████████████████████████████████████████
                    </div>
                  )}
                  <button onClick={() => setSecretVisible(v => !v)}>
                    {secretVisible ? "Masquer" : "Afficher"}
                  </button>
                  {secretVisible && (
                    <button
                      onClick={() => copyText(state.enroll_result!.private_for_client.secret_hex, "secret")}
                      style={{ borderColor: "var(--mc-redstone)", color: "var(--mc-redstone)" }}
                    >
                      {copied === "secret" ? "✓ Copié" : "Copier"}
                    </button>
                  )}
                </div>
              </div>

              <div>
                <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 4 }}>blinding_hex (commitment) :</div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <code className="mc-mono" style={{ fontSize: 11, background: "#1a0000", padding: "6px 10px", borderRadius: 4, flex: 1, wordBreak: "break-all", border: "1px solid var(--mc-redstone)" }}>
                    {secretVisible ? state.enroll_result.private_for_client.blinding_hex : "••••••••••••••••••••••••••••••••"}
                  </code>
                  {secretVisible && (
                    <button
                      onClick={() => copyText(state.enroll_result!.private_for_client.blinding_hex, "blinding")}
                      style={{ borderColor: "var(--mc-redstone)", color: "var(--mc-redstone)" }}
                    >
                      {copied === "blinding" ? "✓ Copié" : "Copier"}
                    </button>
                  )}
                </div>
              </div>
            </div>

            <div style={{ display: "flex", gap: 10 }}>
              <button onClick={handleReset}>Nouveau test</button>
              <Link to="/wallets" className="primary" style={{ textDecoration: "none", display: "inline-block" }}>
                Voir mon wallet →
              </Link>
            </div>
          </>
        )}

        {state.step === "error" && (
          <div style={{ padding: "12px 14px", background: "rgba(192,57,43,0.1)", borderRadius: 6, border: "1px solid var(--mc-redstone)" }}>
            <p style={{ color: "var(--mc-redstone)", fontWeight: 700, margin: "0 0 8px 0" }}>❌ Erreur</p>
            <p style={{ fontSize: 13, margin: 0 }}>{state.error}</p>
            <button onClick={handleReset} style={{ marginTop: 10 }}>Réessayer</button>
          </div>
        )}
      </div>

      {/* ── Lookup : consulter une identité ───────────────────────────────── */}
      <div className="panel">
        <h2>Consulter une identité biométrique</h2>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            value={lookup}
            onChange={e => setLookup(e.target.value)}
            placeholder="human_xxxxx…"
            style={{ fontFamily: "monospace", fontSize: 13, minWidth: 280 }}
            onKeyDown={e => e.key === "Enter" && handleLookup()}
          />
          <button onClick={handleLookup} disabled={!lookup.trim()}>Consulter</button>
        </div>
        {lookupResult && (
          <div style={{ marginTop: 12 }}>
            {lookupResult.found ? (
              <pre style={{ fontSize: 11, background: "#111", padding: 10, borderRadius: 4, overflow: "auto" }}>
                {JSON.stringify(lookupResult, null, 2)}
              </pre>
            ) : (
              <p style={{ color: "var(--mc-redstone)", fontSize: 13 }}>Identité non trouvée.</p>
            )}
          </div>
        )}
      </div>

      {/* ── Liste des identités enregistrées ──────────────────────────────── */}
      <div className="panel">
        <h2>Identités enregistrées ({identities.length})</h2>
        {identities.length === 0 ? (
          <p style={{ color: "var(--terminal-muted)", fontSize: 13 }}>
            Aucune identité biométrique enregistrée sur ce nœud.
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {identities.map(hid => {
              const priv = loadPrivateData(hid);
              return (
                <div key={hid} style={{ display: "flex", gap: 10, alignItems: "center", padding: "6px 10px", background: "#0a0a0a", borderRadius: 4 }}>
                  <code className="mc-mono" style={{ fontSize: 11, flex: 1 }}>{hid}</code>
                  {priv && (
                    <span style={{ fontSize: 11, color: "var(--mc-grass)" }}>✅ clés locales</span>
                  )}
                  <button
                    onClick={() => { setLookup(hid); handleLookup(); }}
                    style={{ fontSize: 11, padding: "2px 8px" }}
                  >
                    Voir
                  </button>
                </div>
              );
            })}
          </div>
        )}
        <button
          onClick={() => listHumanIdentities().then(r => setIdentities(r.human_ids)).catch(() => {})}
          style={{ marginTop: 10, fontSize: 12 }}
        >
          ↺ Rafraîchir
        </button>
      </div>

      {/* ── Données privées locales sauvegardées ──────────────────────────── */}
      <div className="panel">
        <h2>Mes données privées locales (localStorage)</h2>
        <p style={{ fontSize: 12, color: "var(--terminal-muted)", marginBottom: 10 }}>
          secret_hex et blinding_hex stockés dans ce navigateur. Ces données ne sont jamais envoyées au serveur.
          Elles permettent la recovery phrase (spec §10).
        </p>
        {(() => {
          try {
            const all = JSON.parse(localStorage.getItem(PRIVATE_KEY) || "{}");
            const keys = Object.keys(all);
            if (keys.length === 0) return (
              <p style={{ fontSize: 13, color: "var(--terminal-muted)" }}>Aucune donnée privée locale.</p>
            );
            return (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {keys.map(hid => (
                  <div key={hid} style={{ padding: "8px 10px", background: "#0a0a0a", borderRadius: 4 }}>
                    <div style={{ fontSize: 11, fontFamily: "monospace", color: "var(--mc-gold)", marginBottom: 4 }}>{hid}</div>
                    <div style={{ fontSize: 11, color: "var(--terminal-muted)" }}>
                      Sauvegardé le {all[hid].saved_at?.slice(0, 19) || "?"} ·
                      secret: {all[hid].secret_hex?.slice(0, 8)}…
                    </div>
                  </div>
                ))}
              </div>
            );
          } catch { return null; }
        })()}
      </div>
    </div>
  );
}
