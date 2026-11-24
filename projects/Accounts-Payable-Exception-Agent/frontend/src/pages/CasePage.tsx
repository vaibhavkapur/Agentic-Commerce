import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { AgentPanel } from "../components/AgentPanel";
import { ApprovalPanel } from "../components/ApprovalPanel";
import { DocumentsPanel } from "../components/DocumentsPanel";
import { ExceptionsPanel } from "../components/ExceptionsPanel";
import { CommentsPanel, TimelinePanel } from "../components/TimelinePanel";
import { Empty, ErrorNote, Money, StatusBadge } from "../components/ui";
import type { AuditEvent, CaseDetail, EvidenceLink } from "../types";

const RESOLVER_ROLES = new Set(["ap_specialist", "budget_owner", "approver", "admin"]);

export function CasePage() {
  const { caseId = "" } = useParams();
  const { org } = useAuth();
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [focus, setFocus] = useState<{ documentId: string; page: number } | null>(null);
  const [tab, setTab] = useState<"workspace" | "approval" | "timeline">("workspace");

  const load = useCallback(async () => {
    if (!org) return;
    try {
      const [d, t] = await Promise.all([api.getCase(org.id, caseId), api.timeline(org.id, caseId)]);
      setDetail(d);
      setEvents(t);
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, [org, caseId]);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 8000);
    return () => clearInterval(timer);
  }, [load]);

  if (!org) return <Empty>Select an organization.</Empty>;
  if (error) return <ErrorNote error={error} />;
  if (!detail) return <Empty>Loading case…</Empty>;

  const canResolve = RESOLVER_ROLES.has(org.role);
  const showEvidence = (link: EvidenceLink) => {
    if (link.document_version_id) {
      setTab("workspace");
      setFocus({ documentId: link.document_version_id, page: link.page ?? 1 });
    }
  };

  return (
    <div className="case">
      <header className="case-header">
        <div>
          <Link to="/" className="muted small">
            ← Inbox
          </Link>
          <h1>
            {detail.reference} <StatusBadge status={detail.status} />
          </h1>
          <p className="muted">{detail.title}</p>
        </div>
        <dl className="case-facts">
          <dt>Supplier</dt>
          <dd>{detail.supplier_name ?? "—"}</dd>
          <dt>Invoice</dt>
          <dd>{detail.invoice_number ?? "—"}</dd>
          <dt>Amount</dt>
          <dd>
            <Money minor={detail.amount_minor} currency={detail.currency} />
          </dd>
          <dt>Vendor match</dt>
          <dd>{detail.vendor_id ? "approved vendor" : <span className="warning-text">none</span>}</dd>
          <dt>Assigned</dt>
          <dd>{detail.assigned_to ? (detail.people[detail.assigned_to]?.display_name ?? "—") : "—"}</dd>
        </dl>
      </header>
      <nav className="tabs">
        {(["workspace", "approval", "timeline"] as const).map((t) => (
          <button key={t} type="button" className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
            {t === "workspace" ? "Case workspace" : t === "approval" ? "Approval & export" : "Timeline"}
          </button>
        ))}
      </nav>
      {tab === "workspace" && (
        <div className="grid two wide-left">
          <DocumentsPanel org={org.id} detail={detail} focus={focus} canEdit={canResolve} onChanged={() => void load()} />
          <div className="stack">
            <ExceptionsPanel org={org.id} detail={detail} canResolve={canResolve} onChanged={() => void load()} onShowEvidence={showEvidence} />
            <AgentPanel org={org.id} detail={detail} onChanged={() => void load()} />
            <CommentsPanel org={org.id} detail={detail} onChanged={() => void load()} />
          </div>
        </div>
      )}
      {tab === "approval" && <ApprovalPanel org={org.id} detail={detail} onChanged={() => void load()} />}
      {tab === "timeline" && <TimelinePanel events={events} detail={detail} />}
    </div>
  );
}
