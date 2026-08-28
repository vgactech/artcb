import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { chainQueryParams, fetchChain, fetchMiningLatest, fetchMiningStatus } from "../api/client";
import { McBlockRow } from "../components/McBlockRow";
import { McKpiSlot } from "../components/McKpiSlot";
import { useDashboard } from "../context/DashboardContext";
import { useTranslation } from "../i18n/useTranslation";
import type { ChainBlock } from "../types";

export function Mining() {
  const { t } = useTranslation();
  const { visibility, groupId } = useDashboard();
  const [blocks, setBlocks] = useState<ChainBlock[]>([]);
  const [status, setStatus] = useState<{
    current_reward_artcb: number;
    blocks_until_halving: number | null;
    remaining_supply_artcb?: number | null;
    total_rewards_artcb: number;
    pol_score: number;
  } | null>(null);
  const [miningLog, setMiningLog] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    const q = chainQueryParams(visibility, groupId);
    fetchChain(q).then(setBlocks).catch(() => {});
    fetchMiningStatus().then(setStatus).catch(() => {});
    fetchMiningLatest()
      .then((m) => setMiningLog(m.data))
      .catch(() => setMiningLog(null));
  }, [visibility, groupId]);

  const summary = miningLog?.summary as Record<string, unknown> | undefined;
  const lastResult = (miningLog?.results as Array<Record<string, unknown>> | undefined)?.[0];

  return (
    <div className="mc-page">
      <h1 className="dashboard-title">{t('mining_title')}</h1>

      <div className="panel mc-mining-panel">
        <div className="mc-mining-hero">
          <div>
            <h2>{t('mining_hero_title')}</h2>
            <p className="mc-muted">{t('mining_epoch')} : {status?.current_reward_artcb ?? 1} ARTCB/bloc</p>
          </div>
        </div>

        <div className="mc-hotbar">
          <McKpiSlot
            icon="PoL"
            label={t('mining_kpi_pol_session')}
            value={status?.pol_score?.toFixed(2) ?? "—"}
            gold
          />
          <McKpiSlot icon="▣" label={t('mining_kpi_blocks_mined')} value={String(blocks.length)} />
          <McKpiSlot
            icon="₳"
            label={t('mining_kpi_rewards_total')}
            value={`${status?.total_rewards_artcb?.toFixed(1) ?? "0"} ₳`}
          />
          <McKpiSlot
            icon="◷"
            label={t('mining_kpi_halving')}
            value={String(status?.blocks_until_halving ?? "—")}
            sub={t('mining_kpi_halving_blocks')}
          />
        </div>

        {lastResult && (
          <div className="panel">
            <h3>{t('mining_last_result_title')}</h3>
            <p className="mc-muted">
              {t('mining_last_result_pol')}: {String(lastResult.pol_score)} · {t('mining_last_result_reversible')}: {String(lastResult.reversible)} · {t('mining_last_result_nodes')}:{" "}
              {String(lastResult.nodes_count)}
            </p>
            {summary && (
              <p className="mc-gold-text">{t('mining_last_result_reward')}: {String(summary.total_reward_artcb)}</p>
            )}
          </div>
        )}

        <h3>{t('mining_kpi_blocks_mined')}</h3>
        <McBlockRow blocks={blocks} limit={10} />
        <p className="mc-muted">
          {t('mining_launch_hint')} <Link to="/console">Console</Link> — {t('mining_real_scripts')}
        </p>
      </div>
    </div>
  );
}
