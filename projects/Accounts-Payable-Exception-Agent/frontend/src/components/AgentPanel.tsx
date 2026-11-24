import { useState } from "react";
import { api } from "../api";
import type { CaseDetail } from "../types";
import { Empty, ErrorNote, Panel, ProvenanceBadge, StatusBadge, formatDate } from "./ui";

interface Props {
  org: string;
  detail: CaseDetail;
  onChanged: () => void;
}

export function AgentPanel({ org, detail, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const runs = [...detail.agent_runs].reverse();
  const latest = runs[0];
  const frozen = detail.status === "exported" || detail.status === "rejected";

  async function investigate() {
    setBusy(true);
    setError(null);
    try {
      await api.investigate(org, detail.id);
      onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel
      title="Agent investigation"
      actions={
        !frozen && (
          <button type="button" onClick={() => void investigate()} disabled={busy || detail.documents.length === 0}>
            {busy ? "Running…" : runs.length ? "Run investigation again" : "Run investigation"}
          </button>
        )
      }
    >
      <ErrorNote error={error} />
      {!latest ? (
        <Empty>The agent has not investigated this case yet.</Empty>
      ) : (
        <div className="stack">
          <div className="run-meta">
            <StatusBadge status={latest.status} />
            {latest.outcome && <span className="badge">{latest.outcome.replaceAll("_", " ")}</span>}
            <span className="muted small">
              {latest.model_name ?? "deterministic"} · {latest.model_calls} model call{latest.model_calls === 1 ? "" : "s"} · {latest.tool_calls} tool call
              {latest.tool_calls === 1 ? "" : "s"} · started {formatDate(latest.started_at)}
            </span>
          </div>
          {latest.error && <pre className="error">{latest.error}</pre>}
          {latest.summary && (
            <div className="agent-summary">
              <ProvenanceBadge kind="agent" /> <span className="muted small">Cited case summary for the reviewer</span>
              <pre>{latest.summary}</pre>
            </div>
          )}
          {detail.clarification_drafts.length > 0 && (
            <div className="stack">
              <h3>Clarification drafts</h3>
              <p className="muted small">Drafts are never sent automatically. Copy the text into your own channel and mark it accordingly.</p>
              {[...detail.clarification_drafts].reverse().map((draft) => (
                <article key={draft.id} className="draft">
                  <header>
                    <ProvenanceBadge kind={draft.authored_by === "agent" ? "agent" : "human"} compact />
                    <strong>{draft.subject}</strong> <span className="muted">to {draft.recipient}</span> <StatusBadge status={draft.status} />
                  </header>
                  <pre>{draft.body}</pre>
                  {draft.status === "draft" && !frozen && (
                    <div className="actions">
                      <button type="button" className="secondary small" onClick={() => navigator.clipboard?.writeText(draft.body)}>
                        Copy text
                      </button>
                      <button type="button" className="secondary small" onClick={() => api.updateDraft(org, detail.id, draft.id, "sent_manually").then(onChanged)}>
                        Mark as sent
                      </button>
                      <button type="button" className="secondary small" onClick={() => api.updateDraft(org, detail.id, draft.id, "dismissed").then(onChanged)}>
                        Dismiss
                      </button>
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
          <details>
            <summary className="muted">Run trace ({latest.trace.length} entries)</summary>
            <ol className="trace">
              {latest.trace.map((entry, i) => (
                <li key={i}>
                  {entry.type === "node" ? (
                    <>
                      <strong>{entry.node}</strong> <span className="muted small">{String(entry.at ?? "")}</span>{" "}
                      <span className="muted small">{describe(entry)}</span>
                    </>
                  ) : entry.type === "tool_call" ? (
                    <span className="muted">
                      tool <code>{entry.tool}</code> {describe(entry)}
                    </span>
                  ) : (
                    <span className="error">{String(entry.error)}</span>
                  )}
                </li>
              ))}
            </ol>
          </details>
          {runs.length > 1 && (
            <details>
              <summary className="muted">{runs.length - 1} earlier run(s)</summary>
              <ul className="list">
                {runs.slice(1).map((run) => (
                  <li key={run.id}>
                    <StatusBadge status={run.status} /> {run.outcome ?? ""} <span className="muted small">{formatDate(run.created_at)}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </Panel>
  );
}

function describe(entry: Record<string, unknown>): string {
  const skip = new Set(["type", "node", "tool", "at"]);
  return Object.entries(entry)
    .filter(([key]) => !skip.has(key))
    .map(([key, value]) => `${key}=${typeof value === "object" ? JSON.stringify(value) : String(value)}`)
    .join(" ");
}
