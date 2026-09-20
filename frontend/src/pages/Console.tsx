import { useEffect, useRef, useState } from "react";
import { CONSOLE_HELP } from "../console/commands";
import { useTranslation } from "../i18n/useTranslation";

async function apiGet(path: string): Promise<unknown> {
  const r = await fetch(`/api/v1${path}`);
  const text = await r.text();
  try {
    return JSON.parse(text);
  } catch {
    return { status: r.status, raw: text };
  }
}

async function apiPost(path: string, body?: unknown): Promise<unknown> {
  const r = await fetch(`/api/v1${path}`, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  try {
    return JSON.parse(text);
  } catch {
    return { status: r.status, raw: text };
  }
}

export function Console() {
  const { t } = useTranslation();
  const [lines, setLines] = useState<string[]>([t('console_welcome'), "> "]);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  /* BUG-R2: auto-scroll après chaque mise à jour des lignes */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  const runCommand = async (cmd: string) => {
    const trimmed = cmd.trim();
    if (!trimmed) return;
    const out: string[] = [`> ${trimmed}`];

    try {
      if (trimmed === "help") {
        out.push(CONSOLE_HELP);
      } else if (trimmed === "clear") {
        setLines(["> "]);
        setInput("");
        return;
      } else if (trimmed === "health") {
        out.push(JSON.stringify(await apiGet("/health"), null, 2));
      } else if (trimmed === "pol") {
        out.push(JSON.stringify(await apiGet("/pol/score"), null, 2));
      } else if (trimmed === "metrics") {
        out.push(JSON.stringify(await apiGet("/metrics"), null, 2));
      } else if (trimmed === "system hardware") {
        out.push(JSON.stringify(await apiGet("/system/hardware"), null, 2));
      } else if (trimmed === "system optimization") {
        out.push(JSON.stringify(await apiGet("/system/optimization"), null, 2));
      } else if (trimmed === "chain") {
        out.push(JSON.stringify(await apiGet("/chain"), null, 2));
      } else if (trimmed === "chain verify") {
        out.push(JSON.stringify(await apiGet("/chain/verify"), null, 2));
      } else if (trimmed.startsWith("chain block ")) {
        const idx = trimmed.slice("chain block ".length).trim();
        out.push(JSON.stringify(await apiGet(`/chain/block/${idx}`), null, 2));
      } else if (trimmed === "wallets") {
        out.push(JSON.stringify(await apiGet("/wallet/list"), null, 2));
      } else if (trimmed.startsWith("wallet create ")) {
        const name = trimmed.slice("wallet create ".length).trim();
        out.push(JSON.stringify(await apiPost("/wallet/create", { name }), null, 2));
      } else if (trimmed.startsWith("agents ")) {
        const text = trimmed.slice("agents ".length).trim();
        out.push(
          JSON.stringify(
            await apiPost("/agents/run", { text, session_id: "console", use_llm: false }),
            null,
            2,
          ),
        );
      } else if (trimmed === "mining status") {
        out.push(JSON.stringify(await apiGet("/dashboard/mining/status"), null, 2));
      } else if (trimmed === "mining latest") {
        out.push(JSON.stringify(await apiGet("/dashboard/logs/mining-latest"), null, 2));
      } else if (trimmed === "pool status") {
        out.push(JSON.stringify(await apiGet("/pool/status"), null, 2));
      } else if (trimmed === "pool prefs") {
        out.push(JSON.stringify(await apiGet("/pool/preferences"), null, 2));
      } else if (trimmed === "pool jobs") {
        out.push(JSON.stringify(await apiGet("/pool/jobs"), null, 2));
      } else if (trimmed === "pool incoming") {
        out.push(JSON.stringify(await apiGet("/pool/incoming"), null, 2));
      } else if (trimmed.startsWith("groups ")) {
        const addr = trimmed.slice("groups ".length).trim();
        out.push(JSON.stringify(await apiGet(`/groups?address=${encodeURIComponent(addr)}`), null, 2));
      } else if (trimmed === "governance proposals") {
        out.push(JSON.stringify(await apiGet("/governance/proposals"), null, 2));
      } else if (trimmed === "connectors") {
        out.push(JSON.stringify(await apiGet("/connectors"), null, 2));
      } else if (trimmed === "connectors formats") {
        out.push(JSON.stringify(await apiGet("/connectors/formats"), null, 2));
      } else if (trimmed === "notifications") {
        out.push(JSON.stringify(await apiGet("/notifications/channels"), null, 2));
      } else if (trimmed === "founders") {
        out.push(JSON.stringify(await apiGet("/dashboard/founders/allocation"), null, 2));
      } else if (trimmed === "demo log") {
        out.push(JSON.stringify(await apiGet("/dashboard/logs/demo-live"), null, 2));
      } else {
        out.push(`${t('console_unknown_command')}: ${trimmed}`);
          out.push(`${t('console_type_help')} — ou utilisez: python3 scripts/artcb_cli.py`);
      }
    } catch (e) {
      out.push(`Erreur: ${e instanceof Error ? e.message : String(e)}`);
    }

    setLines((prev) => [...prev.slice(0, -1), ...out, "> "]);
    setInput("");
  };

  return (
    <div className="mc-page mc-console-page">
      <h1 className="dashboard-title">{t('console_title')}</h1>
      <p className="mc-muted">
        {t('console_hint')} : <code>python3 scripts/artcb_cli.py help</code> ·{" "}
        <code>API_REFERENCE_ARTCB.md</code>
      </p>
      <div className="mc-console" role="log" aria-live="polite">
        {lines.map((line, i) => (
          <div key={i} className="mc-console-line">
            {line}
          </div>
        ))}
        {/* BUG-R2: sentinel pour auto-scroll */}
        <div ref={bottomRef} />
      </div>
      <form
        className="mc-console-input-row"
        onSubmit={(e) => {
          e.preventDefault();
          runCommand(input);
        }}
      >
        <input
          className="mc-console-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t('console_placeholder')}
          aria-label="Commande console"
          autoFocus
        />
        <button type="submit">{t('console_execute')}</button>
      </form>
    </div>
  );
}
