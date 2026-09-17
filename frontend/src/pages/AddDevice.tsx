/**
 * AddDevice — Page d'ajout d'un nouvel appareil à une identité ARTCB (R350–R354, 2026-09-17).
 *
 * FLUX ADD_DEVICE (spec §17–18 rapport 367/370) :
 *   1. Étape 1 (NOUVEL appareil) : entrer son human_id → POST /identity/device/add-options
 *      → obtient un challenge à 64 hex
 *   2. Étape 2 (APPAREIL EXISTANT) : capturer la biométrie de l'appareil existant,
 *      entrer le challenge + credential du nouvel appareil →
 *      POST /identity/device/add-verify
 *   3. Résultat : device_id enregistré sous le même HumanID. Aucun nouveau wallet créé.
 *
 * INTERDIT (refus automatique) :
 *   ❌ PIN seul    ❌ nouveau wallet depuis nouvel appareil    ❌ > 5 appareils / HumanID
 *
 * CERTIFIED_100=false — stub fonctionnel.
 */
import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import {
  addDeviceOptions,
  addDeviceVerify,
  listDevices,
  webauthnRegisterOptions,
  type AddDeviceOptionsResponse,
  type AddDeviceVerifyResponse,
  type DeviceListResponse,
} from "../api/client";
import {
  createPlatformCredential,
  platformAuthenticatorAvailable,
  serializeCredential,
  webauthnSupported,
} from "../lib/webauthn";

// ─── Dériver un template hex depuis la signature WebAuthn ──────────────────
async function deriveTemplate(signatureBytes: Uint8Array): Promise<string> {
  const buf = signatureBytes.buffer.slice(
    signatureBytes.byteOffset,
    signatureBytes.byteOffset + signatureBytes.byteLength,
  ) as ArrayBuffer;
  const ext = await crypto.subtle.digest("SHA-512", buf);
  return Array.from(new Uint8Array(ext))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

type Step = "options" | "pending_options" | "verify" | "pending_verify" | "done" | "error";

interface State {
  step: Step;
  human_id: string;
  challenge: string | null;
  options_result: AddDeviceOptionsResponse | null;
  verify_result: AddDeviceVerifyResponse | null;
  new_device_hint: string;
  error: string | null;
  devices: DeviceListResponse | null;
}

export function AddDevice() {
  const [state, setState] = useState<State>({
    step: "options",
    human_id: "",
    challenge: null,
    options_result: null,
    verify_result: null,
    new_device_hint: "",
    error: null,
    devices: null,
  });
  const [lookup_id, setLookupId] = useState("");

  // ── Étape 1 : obtenir le challenge ─────────────────────────────────────────
  const handleOptions = useCallback(async () => {
    if (!state.human_id.trim()) return;
    setState((s) => ({ ...s, step: "pending_options", error: null }));
    try {
      const res = await addDeviceOptions(state.human_id.trim(), state.new_device_hint || "unknown");
      setState((s) => ({
        ...s,
        step: "verify",
        challenge: res.challenge,
        options_result: res,
      }));
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: unknown } } };
      const detail = ax?.response?.data?.detail;
      const msg =
        typeof detail === "string" ? detail :
        detail && typeof detail === "object" && "message" in detail
          ? String((detail as { message: string }).message)
          : err instanceof Error ? err.message : String(err);
      setState((s) => ({ ...s, step: "error", error: msg }));
    }
  }, [state.human_id, state.new_device_hint]);

  // ── Étape 2 : capturer biométrie + vérifier ────────────────────────────────
  const handleVerify = useCallback(async () => {
    if (!state.challenge) return;
    setState((s) => ({ ...s, step: "pending_verify", error: null }));
    try {
      if (!webauthnSupported()) {
        throw new Error("WebAuthn non supporté sur cet appareil/navigateur.");
      }
      const platformOk = await platformAuthenticatorAvailable();
      if (!platformOk) {
        throw new Error("Aucun authentificateur biométrique natif détecté.");
      }

      // Capturer la biométrie de l'APPAREIL EXISTANT
      const begin = await webauthnRegisterOptions(`add_device_${Date.now()}`, "fingerprint", false);
      const cred = await createPlatformCredential(begin.publicKey);
      const serialized = serializeCredential(cred);

      // Template biométrique de l'appareil existant
      const attObj = serialized.response.attestationObject;
      const sigBytes = Uint8Array.from(
        atob(attObj.replace(/-/g, "+").replace(/_/g, "/")),
        (c) => c.charCodeAt(0),
      );
      const existing_template_hex = await deriveTemplate(sigBytes);

      // Credential du NOUVEL appareil (simulé ici : hash du challenge + timestamp)
      const rawNew = new TextEncoder().encode(`new_device:${state.challenge}:${Date.now()}`);
      const newHash = await crypto.subtle.digest("SHA-256", rawNew);
      const new_device_credential_hex = Array.from(new Uint8Array(newHash))
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");

      const res = await addDeviceVerify({
        challenge: state.challenge,
        existing_template_hex,
        new_device_credential_hex,
        new_device_hint: state.new_device_hint || "unknown",
      });

      setState((s) => ({ ...s, step: "done", verify_result: res }));
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: unknown } } };
      const detail = ax?.response?.data?.detail;
      const msg =
        typeof detail === "string" ? detail :
        detail && typeof detail === "object" && "message" in detail
          ? String((detail as { message: string }).message)
          : err instanceof Error ? err.message : String(err);
      setState((s) => ({ ...s, step: "error", error: msg }));
    }
  }, [state.challenge, state.new_device_hint]);

  const handleReset = () =>
    setState({
      step: "options",
      human_id: "",
      challenge: null,
      options_result: null,
      verify_result: null,
      new_device_hint: "",
      error: null,
      devices: null,
    });

  const handleListDevices = async () => {
    if (!lookup_id.trim()) return;
    try {
      const res = await listDevices(lookup_id.trim());
      setState((s) => ({ ...s, devices: res }));
    } catch {
      setState((s) => ({ ...s, devices: null }));
    }
  };

  const isPending = state.step === "pending_options" || state.step === "pending_verify";

  return (
    <div className="mc-page">
      <h1 className="dashboard-title">◉ ADD_DEVICE — Ajouter un appareil à une identité ARTCB</h1>

      {/* Bannière honnêteté */}
      <div className="panel" style={{ borderColor: "var(--mc-gold, #ffd700)", background: "rgba(255,215,0,0.04)", marginBottom: 16 }}>
        <p style={{ margin: 0, fontSize: 13 }}>
          <strong style={{ color: "var(--mc-gold)" }}>⚠ Règles ADD_DEVICE (spec §17–18)</strong> —{" "}
          <code>CERTIFIED_100 = false</code> · <code>unique_human_proven = false</code>
        </p>
        <p style={{ margin: "6px 0 0 0", fontSize: 12, color: "var(--terminal-muted)" }}>
          ❌ PIN seul REFUSÉ · ❌ Nouveau wallet depuis nouvel appareil REFUSÉ ·
          ❌ Plus de 5 appareils / HumanID REFUSÉ.
          La preuve biométrique de l'appareil EXISTANT est obligatoire pour autoriser l'ajout.
        </p>
      </div>

      {/* ── Étape 1 : Options ───────────────────────────────────────────────── */}
      {(state.step === "options" || state.step === "pending_options") && (
        <div className="panel">
          <h2>Étape 1 — Initier l'ajout (depuis le NOUVEL appareil)</h2>
          <p style={{ fontSize: 13, marginBottom: 12 }}>
            Entrez le <strong>human_id</strong> de l'identité à rejoindre.
            Un challenge sera émis — vous devrez ensuite l'approuver depuis l'<strong>appareil existant</strong>.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, maxWidth: 480 }}>
            <input
              value={state.human_id}
              onChange={(e) => setState((s) => ({ ...s, human_id: e.target.value }))}
              placeholder="human_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
              style={{ fontFamily: "monospace", fontSize: 13 }}
              disabled={isPending}
            />
            <input
              value={state.new_device_hint}
              onChange={(e) => setState((s) => ({ ...s, new_device_hint: e.target.value }))}
              placeholder="Description du nouvel appareil (ex: iPhone 15, MacBook M3…)"
              style={{ fontSize: 13 }}
              disabled={isPending}
            />
            <button
              className="primary"
              onClick={handleOptions}
              disabled={isPending || !state.human_id.trim()}
              style={{ fontSize: 14, padding: "10px 20px", alignSelf: "flex-start" }}
            >
              {isPending ? "⏳ En cours…" : "▶ Obtenir le challenge"}
            </button>
          </div>
          <p style={{ fontSize: 12, color: "var(--terminal-muted)", marginTop: 12 }}>
            Pas encore d'identité ? <Link to="/identity-test">Créer une identité biométrique →</Link>
          </p>
        </div>
      )}

      {/* ── Étape 2 : Vérification biométrique ────────────────────────────── */}
      {(state.step === "verify" || state.step === "pending_verify") && state.options_result && (
        <div className="panel">
          <h2>Étape 2 — Approuver depuis l'APPAREIL EXISTANT</h2>
          <div style={{ padding: "12px 14px", background: "rgba(86,196,38,0.06)", borderRadius: 6, border: "1px solid var(--mc-grass)", marginBottom: 16 }}>
            <p style={{ margin: 0, fontSize: 13, fontWeight: 700 }}>✅ Challenge émis</p>
            <p style={{ margin: "6px 0 0 0", fontSize: 11, fontFamily: "monospace", wordBreak: "break-all" }}>
              {state.challenge}
            </p>
            <p style={{ margin: "6px 0 0 0", fontSize: 12, color: "var(--terminal-muted)" }}>
              Expire dans {state.options_result.expires_in}s.
            </p>
          </div>
          <p style={{ fontSize: 13, marginBottom: 12 }}>
            Sur <strong>cet appareil existant</strong> (celui qui possède déjà l'identité),
            capturez votre empreinte biométrique pour autoriser l'ajout.
            ⚠ Le PIN seul est <strong style={{ color: "var(--mc-redstone)" }}>REFUSÉ</strong>.
          </p>
          <div style={{ display: "flex", gap: 10 }}>
            <button
              className="primary"
              onClick={handleVerify}
              disabled={isPending}
              style={{ fontSize: 14, padding: "10px 20px" }}
            >
              {isPending ? "⏳ Capture biométrie…" : "◉ Capturer biométrie + valider"}
            </button>
            <button onClick={handleReset} disabled={isPending}>Annuler</button>
          </div>
        </div>
      )}

      {/* ── Résultat OK ─────────────────────────────────────────────────────── */}
      {state.step === "done" && state.verify_result && (
        <div className="panel">
          <div style={{ padding: "14px 16px", background: "rgba(86,196,38,0.1)", borderRadius: 6, border: "1px solid var(--mc-grass)", marginBottom: 16 }}>
            <p style={{ fontWeight: 700, color: "var(--mc-grass)", margin: 0 }}>
              ✅ Appareil ajouté à l'identité ARTCB
            </p>
            <p style={{ fontSize: 12, color: "var(--terminal-muted)", margin: "4px 0 0 0" }}>
              Aucun nouveau wallet créé · unique_human_proven=false · certified_100=false
            </p>
          </div>
          <pre style={{ fontSize: 11, background: "#111", padding: 10, borderRadius: 4, overflow: "auto" }}>
            {JSON.stringify(state.verify_result, null, 2)}
          </pre>
          <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
            <button onClick={handleReset}>Ajouter un autre appareil</button>
            <Link to="/identity-test" style={{ textDecoration: "none" }}>
              <button>← Retour identité</button>
            </Link>
          </div>
        </div>
      )}

      {/* ── Erreur ──────────────────────────────────────────────────────────── */}
      {state.step === "error" && (
        <div className="panel" style={{ borderColor: "var(--mc-redstone)" }}>
          <p style={{ color: "var(--mc-redstone)", fontWeight: 700 }}>❌ Erreur</p>
          <p style={{ fontSize: 13 }}>{state.error}</p>
          <button onClick={handleReset} style={{ marginTop: 8 }}>Réessayer</button>
        </div>
      )}

      {/* ── Consulter les appareils d'une identité ──────────────────────────── */}
      <div className="panel" style={{ marginTop: 16 }}>
        <h2>Appareils enregistrés pour une identité</h2>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          <input
            value={lookup_id}
            onChange={(e) => setLookupId(e.target.value)}
            placeholder="human_xxxxxxxx…"
            style={{ fontFamily: "monospace", fontSize: 13, minWidth: 280 }}
            onKeyDown={(e) => e.key === "Enter" && handleListDevices()}
          />
          <button onClick={handleListDevices} disabled={!lookup_id.trim()}>Consulter</button>
        </div>
        {state.devices && (
          <div>
            <p style={{ fontSize: 13, marginBottom: 8 }}>
              <strong>{state.devices.active_count}</strong> appareil(s) actif(s) /{" "}
              {state.devices.count} total pour <code className="mc-mono">{state.devices.human_id.slice(0, 20)}…</code>
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {state.devices.devices.map((d) => (
                <div key={d.device_id} style={{ padding: "8px 10px", background: "#0a0a0a", borderRadius: 4, display: "flex", gap: 10, alignItems: "center" }}>
                  <code className="mc-mono" style={{ fontSize: 11, flex: 1 }}>{d.device_id.slice(0, 16)}…</code>
                  <span style={{ fontSize: 12 }}>{d.device_hint || "unknown"}</span>
                  <span style={{ fontSize: 11, color: d.revoked ? "var(--mc-redstone)" : "var(--mc-grass)" }}>
                    {d.revoked ? "❌ révoqué" : "✅ actif"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
