import { useEffect, useState } from "react";
import {
  fetchGraph,
  fetchWaillyExcerpt,
  runAgents,
  runMiningPipeline,
  storeGraph,
  wsUrl,
} from "../api/client";
import { AgentPanel } from "../components/AgentPanel";
import { GraphViewer } from "../components/GraphViewer";
import { PolGauge } from "../components/PolGauge";
import { useDashboard } from "../context/DashboardContext";
import { useTranslation } from "../i18n/useTranslation";

export function Memorize() {
  const { t } = useTranslation();
  const {
    sessionId,
    setSessionId,
    useLlm,
    setUseLlm,
    actorAddress,
    text,
    setText,
    graph,
    setGraph,
    graphId,
    setGraphId,
    pol,
    setPol,
    messages,
    pushMessage,
    clearMessages,
    setChainBlock,
    visibility,
    setVisibility,
    groupId,
    useDistributedPool,
    encryptTransport,
    setUseDistributedPool,
    markChecklist,
  } = useDashboard();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (text) return;
    fetchWaillyExcerpt(2)
      .then(setText)
      .catch(() => setText("Collez votre texte ici — extrait Wailly indisponible."));
  }, [text, setText]);

  const animateViaWebSocket = (inputText: string): Promise<void> =>
    new Promise((resolve, reject) => {
      const ws = new WebSocket(wsUrl(sessionId));
      ws.onopen = () => ws.send(JSON.stringify({ type: "encode", payload: { text: inputText } }));
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "node_added") {
          pushMessage("explorer", `Node ${data.node.id} (${data.node.t}): ${data.node.txt.slice(0, 60)}…`);
        }
        if (data.type === "encode_complete") {
          ws.close();
          resolve();
        }
        if (data.type === "error") {
          ws.close();
          reject(new Error(data.message));
        }
      };
      ws.onerror = () => reject(new Error("WebSocket connection failed"));
    });

  const handleMemorize = async () => {
    if (!text.trim()) return;
    setLoading(true);
    clearMessages();
    setChainBlock(null);

    try {
      if (useDistributedPool) {
        pushMessage("explorer", "Pool distribué ML-KEM E2E — dispatch chunks chiffrés…");
        const mined = await runMiningPipeline({
          text,
          session_id: sessionId,
          use_llm: useLlm,
          actor_address: actorAddress || undefined,
          visibility,
          group_id: visibility === "group" ? groupId : null,
          use_distributed_pool: true,
          encrypt_transport: encryptTransport,
          auto_finalize: false,
          chunk_chars: 200,
        });
        pushMessage("critic", `Pool ${String(mined.mode)} — job ${String(mined.job_id ?? "—")} status ${String(mined.job_status ?? mined.message)}`);
        if (mined.graph_id) setGraphId(String(mined.graph_id));
        if (mined.pol_score != null) {
          setPol({
            pol_score: Number(mined.pol_score),
            delta_compression: 0,
            validation_rate: 1,
            retrieval_accuracy: 1,
            block_accepted: true,
          });
        }
        if (mined.block_index != null) {
          setChainBlock({
            index: Number(mined.block_index),
            hash: String(mined.block_hash ?? ""),
            signature: "",
            pol_score: Number(mined.pol_score ?? 0),
            graph_id: String(mined.graph_id ?? ""),
            block_reward: 0,
          });
        }
        markChecklist("memorized");
        return;
      }

      pushMessage("explorer", "Décomposition IR en cours…");
      await animateViaWebSocket(text);
      pushMessage("critic", "Validation PoL…");
      const result = await runAgents(text, sessionId, useLlm);
      setGraphId(result.graph_id);
      setPol(result.pol);
      const fullGraph = await fetchGraph(result.graph_id);
      setGraph(fullGraph);
      markChecklist("memorized");
      pushMessage("critic", `PoL ${result.pol.pol_score.toFixed(2)} — ${result.node_count} nœuds validés`);
    } catch (err) {
      pushMessage("critic", `Erreur: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setLoading(false);
    }
  };

  const handleStore = async () => {
    if (!graphId) return;
    setLoading(true);
    try {
      if (visibility === "group") {
        if (!groupId) {
          pushMessage("critic", "Sélectionnez un groupe (V10)");
          return;
        }
        if (!actorAddress) {
          pushMessage("critic", "Wallet requis");
          return;
        }
      }
      const block = await storeGraph(
        graphId,
        sessionId,
        visibility,
        visibility === "group" ? groupId : null,
        visibility === "group" ? actorAddress : undefined,
      );
      setChainBlock({
        index: block.block_index,
        hash: block.hash,
        signature: block.signature,
        pol_score: block.pol_score,
        graph_id: graphId,
        block_reward: block.block_reward,
      });
      markChecklist("signed");
      pushMessage("critic", `Bloc #${block.block_index} signé (${visibility})`);
    } catch (err) {
      pushMessage("critic", `Store failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mc-page">
      <h1 className="dashboard-title">{t('memorize_title')}</h1>

      <div className="panel">
        <h2>{t('memorize_session')}</h2>
        <div className="toolbar">
          <label>
            session_id:
            {/* BUG-R3: placeholder visible — sessionId vide par défaut */}
            <input
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              placeholder="demo_session"
            />
          </label>
          <label>
            <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} /> use_llm
          </label>
          <label>
            <input
              type="checkbox"
              checked={useDistributedPool}
              onChange={(e) => setUseDistributedPool(e.target.checked)}
            />{" "}
            calcul distribué (pool E2E)
          </label>
          {useDistributedPool && (
            <label>
              <input
                type="checkbox"
                checked={encryptTransport}
                disabled
                readOnly
              />{" "}
              ML-KEM chiffré (obligatoire)
            </label>
          )}
        </div>
        <label className="mc-network-select" aria-label="Visibilité réseau mémorisation">
          Réseau :
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
        <p className="mc-muted" aria-live="polite">
          Visibilité actuelle : <strong>{visibility}</strong>
          {visibility === "group" && !groupId && " — sélectionnez un groupe dans /groups"}
        </p>
      </div>

      <div className="panel mc-crafting">
        <h2>{t('memorize_source_title')}</h2>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t('memorize_placeholder')}
          aria-label="Texte source"
          className="mc-crafting-area"
        />
        <div className="toolbar">
          <button className="primary" onClick={handleMemorize} disabled={loading}>
            {loading ? t('memorize_button_loading') : t('memorize_button')}
          </button>
          <button onClick={() => fetchWaillyExcerpt(3).then(setText)}>Charger Wailly</button>
          {graphId && (
            <button onClick={handleStore} disabled={loading}>
              {t('memorize_sign_block')}
            </button>
          )}
        </div>
      </div>

      <div className="demo-grid">
        <div className="panel mc-graph-panel">
          <h2>{t('memorize_graph_title')}</h2>
          <div className="mc-graph-viewport">
            <GraphViewer graph={graph} selectedNodeId={null} onSelectNode={() => {}} />
          </div>
          {graphId && (
            <p className="mc-muted">
              graph_id={graphId} · {graph?.nodes.length ?? 0} nœuds
            </p>
          )}
        </div>
        <div className="mc-side-stack">
          <AgentPanel messages={messages} />
          <PolGauge pol={pol} />
        </div>
      </div>
    </div>
  );
}
