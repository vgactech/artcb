/**
 * ReflexStatus — Page d'état du moteur réflexe ARTCB (R350–R354, 2026-09-17).
 *
 * Affiche en temps réel :
 *   - Priorité courante (REFLEX_MEMORY / SECURITY / PQC / OTHER)
 *   - Nombre de triggers détectés
 *   - Table des niveaux de priorité
 *   - État CERTIFIED_100 / unique_human_proven
 *   - Outil de test : entrer un texte → vérifier le réflexe
 *
 * CERTIFIED_100=false — stub fonctionnel.
 */
import { useCallback, useEffect, useState } from "react";
import axios from "axios";

// R424 — fetchReflexStatus/ReflexStatusResponse supprimés de client.ts (backend-only).
// Définis localement ici pour éviter la dépendance client.ts.
interface ReflexStatusResponse {
  certified: boolean;
  unique_human_proven: boolean;
  current_priority: string;
  current_priority_name: string;
  triggers_detected: number;
  priorities: Record<string, number>;
  active_since: number | null;
  note: string;
  // Champs optionnels exposés par le backend (peuvent être absents selon la version)
  engine?: string;
  rules?: number;
  total_triggers?: number;
  activated_at?: number | null;
}

async function fetchReflexStatus(): Promise<ReflexStatusResponse> {
  const { data } = await axios.get<ReflexStatusResponse>("/api/v1/reflex/status");
  return data;
}

interface ReflexCheckResult {
  reflex_activated: boolean;
  priority: number;
  priority_name: string;
  triggers: Array<{
    name: string;
    priority: number;
    priority_name: string;
    reason: string;
    keywords: string[];
    files_affected: string[];
  }>;
  activated_at: number | null;
  certified: boolean;
  unique_human_proven: boolean;
  action: string;
  note: string;
}

const PRIORITY_COLORS: Record<string, string> = {
  REFLEX_MEMORY: "var(--mc-redstone, #c0392b)",
  SECURITY:      "var(--mc-gold, #ffd700)",
  PQC:           "var(--mc-grass, #56c426)",
  OTHER:         "var(--terminal-muted, #888)",
};

const PRIORITY_LABELS: Record<string, string> = {
  REFLEX_MEMORY: "⚡ MÉMOIRE / THINKING — PRIORITÉ ABSOLUE",
  SECURITY:      "🔒 SÉCURITÉ / IDENTITÉ — Priorité 1",
  PQC:           "🔐 POST-QUANTIQUE — Priorité 2",
  OTHER:         "◦ Standard — aucun réflexe critique",
};

export function ReflexStatus() {
  const [status, setStatus] = useState<ReflexStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [testText, setTestText] = useState("");
  const [testFiles, setTestFiles] = useState("");
  const [checkResult, setCheckResult] = useState<ReflexCheckResult | null>(null);
  const [checking, setChecking] = useState(false);

  const loadStatus = useCallback(async () => {
    try {
      const res = await fetchReflexStatus();
      setStatus(res);
      setError(null);
    } catch {
      setError("Impossible de joindre /api/v1/reflex/status");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
    const id = setInterval(loadStatus, 5000);
    return () => clearInterval(id);
  }, [loadStatus]);

  const handleCheck = useCallback(async () => {
    if (!testText.trim() && !testFiles.trim()) return;
    setChecking(true);
    setCheckResult(null);
    try {
      const files = testFiles.split("\n").map(f => f.trim()).filter(Boolean);
      const { data } = await axios.post<ReflexCheckResult>("/api/v1/reflex/check", {
        text: testText,
        files,
      });
      setCheckResult(data);
    } catch {
      setCheckResult(null);
    } finally {
      setChecking(false);
    }
  }, [testText, testFiles]);

  return (
    <div className="mc-page">
      <h1 className="dashboard-title">⚡ Réflexe ARTCB — Moteur R350–R354</h1>

      {/* Bannière honnêteté */}
      <div className="panel" style={{ borderColor: "var(--mc-gold, #ffd700)", background: "rgba(255,215,0,0.04)", marginBottom: 16 }}>
        <p style={{ margin: 0, fontSize: 13 }}>
          <strong style={{ color: "var(--mc-gold)" }}>⚠ Honnêteté R354</strong> —{" "}
          Ce moteur est un <strong>stub fonctionnel</strong>. L'activation réelle dépend des hooks Bob IDE / Cursor.
          Il détecte et classe, mais n'impose pas une contrainte système irréfutable.
        </p>
        <p style={{ margin: "4px 0 0 0", fontSize: 12, color: "var(--terminal-muted)" }}>
          <code>CERTIFIED_100=false</code> · <code>unique_human_proven=false</code> ·
          Règles R350–R354 actives dans les hooks Bob IDE
        </p>
      </div>

      {/* ── État global ─────────────────────────────────────────────────────── */}
      <div className="panel">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <h2 style={{ margin: 0 }}>État du moteur réflexe</h2>
          <button onClick={loadStatus} style={{ fontSize: 12, padding: "4px 10px" }}>↺ Rafraîchir</button>
        </div>

        {loading && <p style={{ fontSize: 13, color: "var(--terminal-muted)" }}>⏳ Chargement…</p>}
        {error && <p style={{ color: "var(--mc-redstone)", fontSize: 13 }}>❌ {error}</p>}

        {status && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <div style={{ padding: "10px 16px", background: "#0a0a0a", borderRadius: 6, flex: 1 }}>
                <div style={{ fontSize: 11, color: "var(--terminal-muted)", marginBottom: 4 }}>Moteur</div>
                <div style={{ fontSize: 13, fontWeight: 700 }}>{status.engine}</div>
              </div>
              <div style={{ padding: "10px 16px", background: "#0a0a0a", borderRadius: 6, flex: 1 }}>
                <div style={{ fontSize: 11, color: "var(--terminal-muted)", marginBottom: 4 }}>Règles</div>
                <div style={{ fontSize: 13, fontWeight: 700 }}>{status.rules}</div>
              </div>
              <div style={{ padding: "10px 16px", background: "#0a0a0a", borderRadius: 6, flex: 1 }}>
                <div style={{ fontSize: 11, color: "var(--terminal-muted)", marginBottom: 4 }}>Triggers détectés</div>
                <div style={{ fontSize: 18, fontWeight: 700 }}>{status.total_triggers}</div>
              </div>
              <div style={{ padding: "10px 16px", background: status.certified ? "rgba(86,196,38,0.08)" : "rgba(192,57,43,0.08)", borderRadius: 6, flex: 1, border: `1px solid ${status.certified ? "var(--mc-grass)" : "var(--mc-redstone)"}` }}>
                <div style={{ fontSize: 11, color: "var(--terminal-muted)", marginBottom: 4 }}>CERTIFIED_100</div>
                <div style={{ fontSize: 13, fontWeight: 700, color: status.certified ? "var(--mc-grass)" : "var(--mc-redstone)" }}>
                  {status.certified ? "✅ TRUE" : "❌ FALSE"}
                </div>
              </div>
            </div>

            {status.activated_at && (
              <p style={{ fontSize: 12, color: "var(--terminal-muted)", margin: 0 }}>
                Dernière activation : {new Date(status.activated_at * 1000).toISOString()}
              </p>
            )}

            <p style={{ fontSize: 12, color: "var(--terminal-muted)", margin: 0, fontStyle: "italic" }}>
              {status.note}
            </p>
          </div>
        )}
      </div>

      {/* ── Table des priorités ─────────────────────────────────────────────── */}
      {status && (
        <div className="panel">
          <h2>Table des priorités</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {Object.entries(status.priorities).map(([name, value]) => (
              <div key={name} style={{
                display: "flex", gap: 12, alignItems: "center",
                padding: "10px 14px", background: "#0a0a0a", borderRadius: 6,
                borderLeft: `3px solid ${PRIORITY_COLORS[name] || "#555"}`,
              }}>
                <span style={{ fontSize: 20, fontWeight: 900, minWidth: 28, color: PRIORITY_COLORS[name] }}>
                  {String(value)}
                </span>
                <span style={{ fontSize: 13, fontWeight: 700, color: PRIORITY_COLORS[name] }}>
                  {PRIORITY_LABELS[name] || name}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Outil de test réflexe ───────────────────────────────────────────── */}
      <div className="panel">
        <h2>Tester le réflexe</h2>
        <p style={{ fontSize: 13, marginBottom: 12 }}>
          Entrez un texte de prompt et/ou des chemins de fichiers pour voir la priorité réflexe détectée.
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 600 }}>
          <textarea
            value={testText}
            onChange={e => setTestText(e.target.value)}
            placeholder="Texte du prompt à analyser (ex: 'mémoire ARTCB thinking réflexe')"
            rows={3}
            style={{ fontFamily: "monospace", fontSize: 13, resize: "vertical" }}
          />
          <textarea
            value={testFiles}
            onChange={e => setTestFiles(e.target.value)}
            placeholder={"Fichiers modifiés (un par ligne)\nex: src/artcb/reflex/core.py\nsrc/artcb/identity/biometric_onchain.py"}
            rows={3}
            style={{ fontFamily: "monospace", fontSize: 12, resize: "vertical" }}
          />
          <button
            className="primary"
            onClick={handleCheck}
            disabled={checking || (!testText.trim() && !testFiles.trim())}
            style={{ alignSelf: "flex-start", padding: "8px 20px" }}
          >
            {checking ? "⏳ Analyse…" : "▶ Analyser le réflexe"}
          </button>
        </div>

        {checkResult && (
          <div style={{ marginTop: 16 }}>
            <div style={{
              padding: "12px 16px", borderRadius: 6, marginBottom: 12,
              background: `${PRIORITY_COLORS[checkResult.priority_name]}18`,
              border: `1px solid ${PRIORITY_COLORS[checkResult.priority_name]}`,
            }}>
              <p style={{ margin: 0, fontWeight: 700, fontSize: 15, color: PRIORITY_COLORS[checkResult.priority_name] }}>
                {PRIORITY_LABELS[checkResult.priority_name] || checkResult.priority_name}
              </p>
              <p style={{ margin: "6px 0 0 0", fontSize: 13 }}>{checkResult.action}</p>
            </div>

            {checkResult.triggers.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>
                  {checkResult.triggers.length} déclencheur(s) détecté(s) :
                </div>
                {checkResult.triggers.map((t, i) => (
                  <div key={i} style={{ padding: "8px 10px", background: "#0a0a0a", borderRadius: 4, marginBottom: 6, borderLeft: `2px solid ${PRIORITY_COLORS[t.priority_name] || "#555"}` }}>
                    <div style={{ fontWeight: 700, fontSize: 12, color: PRIORITY_COLORS[t.priority_name] }}>
                      {t.name} (priorité {t.priority})
                    </div>
                    <div style={{ fontSize: 12, color: "var(--terminal-muted)" }}>{t.reason}</div>
                    {t.keywords.length > 0 && (
                      <div style={{ fontSize: 11, marginTop: 4 }}>
                        Mots-clés : {t.keywords.map(k => <code key={k} style={{ marginRight: 4, background: "#111", padding: "1px 4px", borderRadius: 2 }}>{k}</code>)}
                      </div>
                    )}
                    {t.files_affected.length > 0 && (
                      <div style={{ fontSize: 11, marginTop: 4 }}>
                        Fichiers : {t.files_affected.map(f => <code key={f} style={{ marginRight: 4, background: "#111", padding: "1px 4px", borderRadius: 2 }}>{f}</code>)}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {checkResult.triggers.length === 0 && (
              <p style={{ fontSize: 13, color: "var(--terminal-muted)" }}>
                Aucun déclencheur réflexe détecté — priorité standard (OTHER).
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
