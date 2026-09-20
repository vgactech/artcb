import { useEffect, useState } from "react";
import {
  decodeGraph,
  fetchGraph,
  fetchWallets,
  searchNodes,
  storeGraph,
} from "../api/client";
import { GraphViewer } from "../components/GraphViewer";
import { PolGauge } from "../components/PolGauge";
import { Reconstruct } from "../components/Reconstruct";
import { useDashboard } from "../context/DashboardContext";
import { useTranslation } from "../i18n/useTranslation";

export function GraphPage() {
  const { t } = useTranslation();
  const {
    sessionId,
    actorAddress,
    graph,
    setGraph,
    graphId,
    text,
    pol,
    selectedNodeId,
    setSelectedNodeId,
    pushMessage,
    setChainBlock,
    visibility,
    groupId,
    markChecklist,
  } = useDashboard();
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Array<{ node_id: string; score: number; text: string }>>([]);
  const [highlightIds, setHighlightIds] = useState<string[]>([]);
  const [showReconstruct, setShowReconstruct] = useState(false);
  const [reconstructed, setReconstructed] = useState("");
  const [similarity, setSimilarity] = useState(1);
  const [reversible, setReversible] = useState(false);
  const [nodeDetail, setNodeDetail] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (graphId && !graph) {
      fetchGraph(graphId).then(setGraph).catch(() => {});
    }
  }, [graphId, graph, setGraph]);

  useEffect(() => {
    if (graphId && graph) markChecklist("explored");
  }, [graphId, graph, markChecklist]);

  useEffect(() => {
    if (!selectedNodeId || !graph) {
      setNodeDetail("");
      return;
    }
    const node = graph.nodes.find((n) => n.id === selectedNodeId);
    setNodeDetail(node?.txt ?? "");
  }, [selectedNodeId, graph]);

  const handleSearch = async () => {
    if (!graphId || !searchQuery.trim()) return;
    const results = await searchNodes(searchQuery, graphId);
    setSearchResults(results);
    if (results.length) {
      setHighlightIds(results.map((r) => r.node_id));
      setSelectedNodeId(results[0].node_id);
      markChecklist("searched");
      pushMessage("explorer", `Trouvé: "${results[0].text.slice(0, 80)}…"`);
    }
  };

  const handleReconstruct = async () => {
    if (!graphId) return;
    const data = await decodeGraph(graphId);
    setReconstructed(data.original_text);
    setSimilarity(data.similarity);
    setReversible(data.reversible);
    setShowReconstruct(true);
  };

  const handleStore = async () => {
    if (!graphId) return;
    setLoading(true);
    try {
      let actor = actorAddress;
      if (visibility === "group") {
        if (!groupId) {
          pushMessage("critic", "Sélectionnez un groupe (V10)");
          return;
        }
        if (!actor) {
          const wallets = await fetchWallets();
          actor = wallets[0]?.address;
        }
        if (!actor) {
          pushMessage("critic", "Wallet requis");
          return;
        }
      }
      const block = await storeGraph(graphId, sessionId, visibility, groupId, actor);
      setChainBlock({
        index: block.block_index,
        hash: block.hash,
        signature: block.signature,
        pol_score: block.pol_score,
        graph_id: graphId,
        block_reward: block.block_reward,
      });
      markChecklist("signed");
      pushMessage("critic", `Bloc #${block.block_index} signé`);
    } catch (err) {
      pushMessage("critic", `Erreur: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setLoading(false);
    }
  };

  if (!graphId) {
    return (
      <div className="mc-page mc-empty">
        <h1 className="dashboard-title">{t('graph_title')}</h1>
        <div className="panel mc-empty-panel">
          <p className="mc-empty-icon"></p>
          <p>{t('graph_no_graph')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mc-page">
      <h1 className="dashboard-title">{t('graph_title_with_id')} {graphId.slice(0, 12)}…</h1>
      <div className="demo-grid">
        <div className="panel mc-graph-panel">
          <div className="mc-graph-viewport mc-graph-viewport-tall">
            <GraphViewer
              graph={graph}
              selectedNodeId={selectedNodeId}
              highlightIds={highlightIds}
              onSelectNode={setSelectedNodeId}
            />
          </div>
          {nodeDetail && (
            <div className="mc-node-detail">
              <strong>Sélectionné:</strong> {nodeDetail}
            </div>
          )}
          <div className="toolbar">
            <input
              className="mc-search-input"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('graph_search_placeholder')}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            />
            <button onClick={handleSearch}>{t('graph_search_button')}</button>
            <button onClick={handleReconstruct}>{t('reconstruct_title')}</button>
            <button
              onClick={async () => {
                if (!nodeDetail) return;
                try {
                  const r = await fetch("/api/v1/integrations/gradium/tts", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ text: nodeDetail, language: "fr" }),
                  });
                  const data = await r.json();
                  if (data.mode === "gradium" && data.audio_base64) {
                    const audio = new Audio(`data:audio/mp3;base64,${data.audio_base64}`);
                    await audio.play();
                  } else if ("speechSynthesis" in window) {
                    const u = new SpeechSynthesisUtterance(nodeDetail);
                    u.lang = "fr-FR";
                    window.speechSynthesis.speak(u);
                  }
                } catch {
                  if ("speechSynthesis" in window && nodeDetail) {
                    const u = new SpeechSynthesisUtterance(nodeDetail);
                    u.lang = "fr-FR";
                    window.speechSynthesis.speak(u);
                  }
                }
              }}
              disabled={!selectedNodeId}
            >
              {t('graph_tts_button')}
            </button>
            <button className="primary" onClick={handleStore} disabled={loading}>
              {t('graph_sign_button')}
            </button>
          </div>
          {searchResults.length > 0 && (
            <ul className="mc-search-results">
              {searchResults.map((r) => (
                <li key={r.node_id}>
                  {r.node_id} score {r.score.toFixed(2)} — {r.text.slice(0, 60)}…
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="mc-side-stack">
          <PolGauge pol={pol} />
        </div>
      </div>
      <Reconstruct
        original={text}
        reconstructed={reconstructed}
        similarity={similarity}
        reversible={reversible}
        visible={showReconstruct}
      />
    </div>
  );
}
