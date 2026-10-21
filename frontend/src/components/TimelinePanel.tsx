import { useState, type FormEvent } from "react";
import { api } from "../api";
import type { AuditEvent, CaseDetail } from "../types";
import { Empty, Panel, ProvenanceBadge, formatDate, type Provenance } from "./ui";

export function TimelinePanel({ events, detail }: { events: AuditEvent[]; detail: CaseDetail }) {
  return (
    <Panel title={`Timeline (${events.length})`}>
      {events.length === 0 ? (
        <Empty>No events yet.</Empty>
      ) : (
        <ol className="timeline">
          {[...events].reverse().map((event) => (
            <li key={event.id} className={`actor-${event.actor_type}`}>
              <ProvenanceBadge kind={actorProvenance(event)} compact />
              <strong>{event.event_type.replaceAll("_", " ")}</strong>
              <span className="muted small">
                {" "}
                {formatDate(event.created_at)} · {actorName(event, detail)}
              </span>
              <div className="muted small payload">{summarisePayload(event)}</div>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}

function actorProvenance(event: AuditEvent): Provenance {
  if (event.actor_type === "agent") return "agent";
  if (event.actor_type === "system") return "system";
  return "human";
}

function actorName(event: AuditEvent, detail: CaseDetail): string {
  if (event.actor_type === "user" && event.actor_id) return detail.people[event.actor_id]?.display_name ?? "user";
  if (event.actor_type === "agent") return "agent";
  return "system";
}

function summarisePayload(event: AuditEvent): string {
  const skip = new Set(["document_version_id", "exception_id", "approval_request_id", "payment_instruction_id", "draft_id", "run_id"]);
  return Object.entries(event.payload)
    .filter(([key, value]) => !skip.has(key) && value !== null && value !== undefined && value !== "")
    .map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : String(value)}`)
    .join(" · ");
}

export function CommentsPanel({ org, detail, onChanged }: { org: string; detail: CaseDetail; onChanged: () => void }) {
  const [body, setBody] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!body.trim()) return;
    await api.addComment(org, detail.id, body.trim());
    setBody("");
    onChanged();
  }
  return (
    <Panel title={`Comments (${detail.comments.length})`}>
      <ul className="comments">
        {detail.comments.map((c) => (
          <li key={c.id}>
            <strong>{c.author?.display_name ?? "unknown"}</strong> <span className="muted small">{formatDate(c.created_at)}</span>
            <p>{c.body}</p>
          </li>
        ))}
      </ul>
      <form onSubmit={submit} className="inline-form">
        <input placeholder="Add a comment for the case team" value={body} onChange={(e) => setBody(e.target.value)} />
        <button type="submit" disabled={!body.trim()}>
          Post
        </button>
      </form>
    </Panel>
  );
}
