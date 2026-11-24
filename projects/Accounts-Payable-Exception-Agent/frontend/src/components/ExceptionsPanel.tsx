import { useState } from "react";
import { api } from "../api";
import type { CaseDetail, CaseException, EvidenceLink } from "../types";
import { labelFor } from "./DocumentsPanel";
import { Empty, ErrorNote, Panel, ProvenanceBadge, SeverityBadge, StatusBadge, formatDate } from "./ui";

interface Props {
  org: string;
  detail: CaseDetail;
  canResolve: boolean;
  onChanged: () => void;
  onShowEvidence: (link: EvidenceLink) => void;
}

const REGISTER_ONLY = new Set(["BENEFICIARY_CHANGED", "BENEFICIARY_UNVERIFIED", "VENDOR_NOT_FOUND"]);

export function ExceptionsPanel({ org, detail, canResolve, onChanged, onShowEvidence }: Props) {
  const open = detail.exceptions.filter((e) => e.status === "open");
  const closed = detail.exceptions.filter((e) => e.status !== "open");
  const frozen = detail.status === "exported" || detail.status === "rejected";
  return (
    <Panel
      title={`Exceptions (${open.length} open)`}
      actions={
        !frozen && (
          <button type="button" className="secondary" onClick={() => api.rerunChecks(org, detail.id).then(onChanged)}>
            Re-run checks
          </button>
        )
      }
    >
      {detail.exceptions.length === 0 ? (
        <Empty>No checks have run yet. Upload documents and run the investigation.</Empty>
      ) : (
        <div className="stack">
          {open.map((e) => (
            <ExceptionCard key={e.id} org={org} detail={detail} exception={e} canResolve={canResolve && !frozen} onChanged={onChanged} onShowEvidence={onShowEvidence} />
          ))}
          {closed.length > 0 && (
            <details>
              <summary className="muted">
                {closed.length} resolved or waived exception{closed.length === 1 ? "" : "s"}
              </summary>
              <div className="stack">
                {closed.map((e) => (
                  <ExceptionCard key={e.id} org={org} detail={detail} exception={e} canResolve={canResolve && !frozen} onChanged={onChanged} onShowEvidence={onShowEvidence} />
                ))}
              </div>
            </details>
          )}
        </div>
      )}
    </Panel>
  );
}

function ExceptionCard({ org, detail, exception, canResolve, onChanged, onShowEvidence }: Props & { exception: CaseException }) {
  const [action, setAction] = useState<"resolve" | "waive" | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<unknown>(null);
  const registerOnly = REGISTER_ONLY.has(exception.code);

  async function submit(kind: "resolve" | "waive" | "reopen") {
    setError(null);
    try {
      await api.resolveException(org, detail.id, exception.id, kind, kind === "reopen" ? "Reopened by reviewer" : note);
      setAction(null);
      setNote("");
      onChanged();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <article className={`exception severity-${exception.severity} status-${exception.status}`}>
      <header>
        <SeverityBadge severity={exception.severity} />
        <code>{exception.code}</code>
        <strong>{exception.title}</strong>
        <StatusBadge status={exception.status} />
        <ProvenanceBadge kind="system" compact />
        {exception.needs_information && <span className="badge">needs information</span>}
      </header>
      <p>{exception.detail}</p>
      {exception.evidence.length > 0 && (
        <ul className="evidence">
          {exception.evidence.map((link) => (
            <li key={link.id}>
              <EvidenceChip link={link} detail={detail} onShow={onShowEvidence} />
            </li>
          ))}
        </ul>
      )}
      {exception.status !== "open" && (
        <p className="resolution">
          <ProvenanceBadge kind={exception.resolved_by ? "human" : "system"} compact /> {exception.status} by{" "}
          {exception.resolved_by ? (detail.people[exception.resolved_by]?.display_name ?? exception.resolved_by) : "re-check"} on {formatDate(exception.resolved_at)}
          {exception.resolution_note && <> — “{exception.resolution_note}”</>}
        </p>
      )}
      {canResolve && exception.status === "open" && !registerOnly && (
        <div className="actions">
          {action ? (
            <div className="stack small-gap">
              <input placeholder={`Reason for ${action === "resolve" ? "resolving" : "waiving"} (recorded in the audit trail)`} value={note} onChange={(e) => setNote(e.target.value)} />
              <div>
                <button type="button" disabled={note.trim().length < 3} onClick={() => void submit(action)}>
                  Confirm {action}
                </button>{" "}
                <button type="button" className="secondary" onClick={() => setAction(null)}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <>
              <button type="button" className="secondary small" onClick={() => setAction("resolve")}>
                Resolve
              </button>
              <button type="button" className="secondary small" onClick={() => setAction("waive")}>
                Waive
              </button>
            </>
          )}
        </div>
      )}
      {canResolve && exception.status === "open" && registerOnly && (
        <p className="muted small">Only an administrator can clear this by updating and verifying the vendor register.</p>
      )}
      {canResolve && exception.status !== "open" && exception.resolved_by && (
        <button type="button" className="link small" onClick={() => void submit("reopen")}>
          Reopen
        </button>
      )}
      <ErrorNote error={error} />
    </article>
  );
}

export function EvidenceChip({ link, detail, onShow }: { link: EvidenceLink; detail: CaseDetail; onShow: (link: EvidenceLink) => void }) {
  if (link.document_version_id) {
    const doc = detail.documents.find((d) => d.id === link.document_version_id);
    return (
      <button type="button" className="chip" onClick={() => onShow(link)} title={link.excerpt ?? ""}>
        <ProvenanceBadge kind="extracted" compact /> {link.label} — {doc ? `${labelFor(doc.kind)} v${doc.version}` : "document"}
        {link.page ? `, page ${link.page}` : ""}
      </button>
    );
  }
  return (
    <span className="chip static" title={link.excerpt ?? ""}>
      <ProvenanceBadge kind="register" compact /> {link.label}
      {link.excerpt ? ` (${link.excerpt})` : ""}
    </span>
  );
}
