import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Empty, ErrorNote, Money, Panel, ProvenanceBadge, formatDate } from "../components/ui";
import type { ApprovalRequest } from "../types";

export function ApprovalsPage() {
  const { org } = useAuth();
  const [queue, setQueue] = useState<ApprovalRequest[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    if (!org) return;
    try {
      setQueue(await api.approvalQueue(org.id));
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, [org]);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 5000);
    return () => clearInterval(timer);
  }, [load]);

  async function decide(request: ApprovalRequest, decision: "approve" | "reject") {
    if (!org) return;
    try {
      await api.decide(org.id, request.case_id, request.id, decision, notes[request.id] ?? "");
      await load();
    } catch (err) {
      setError(err);
    }
  }

  if (!org) return <Empty>Select an organization.</Empty>;
  return (
    <Panel title={`Approval queue (${queue.length})`}>
      <ErrorNote error={error} />
      {queue.length === 0 ? (
        <Empty>Nothing is waiting for approval.</Empty>
      ) : (
        <div className="stack">
          {queue.map((request) => {
            const s = request.snapshot;
            return (
              <article key={request.id} className="queue-item">
                <header>
                  <Link to={`/cases/${request.case_id}`}>
                    <strong>{request.case?.reference}</strong>
                  </Link>{" "}
                  <span className="muted small">
                    requested {formatDate(request.created_at)} · expires {formatDate(request.expires_at)}
                  </span>
                </header>
                <dl>
                  <dt>Pay</dt>
                  <dd className="big">
                    <Money minor={s.amount_minor} currency={s.currency} />
                  </dd>
                  <dt>For</dt>
                  <dd>
                    Invoice {s.invoice_number} from {s.supplier_name}
                  </dd>
                  <dt>To</dt>
                  <dd>
                    <ProvenanceBadge kind="register" compact /> {s.beneficiary?.account_name} — {s.beneficiary?.sort_code ?? ""} {s.beneficiary?.account_number ?? ""}{" "}
                    {s.beneficiary?.iban ?? ""} <span className="muted small">(v{s.beneficiary?.version})</span>
                  </dd>
                  <dt>Decisions</dt>
                  <dd>
                    {s.exceptions.filter((e) => e.status !== "open").length === 0 ? (
                      <span className="muted">no exceptions were raised</span>
                    ) : (
                      s.exceptions
                        .filter((e) => e.status !== "open")
                        .map((e) => `${e.code} ${e.status}`)
                        .join(", ")
                    )}
                  </dd>
                </dl>
                {request.can_decide ? (
                  <div className="actions">
                    <input placeholder="Note (optional)" value={notes[request.id] ?? ""} onChange={(e) => setNotes({ ...notes, [request.id]: e.target.value })} />
                    <button type="button" onClick={() => void decide(request, "approve")}>
                      Approve
                    </button>
                    <button type="button" className="danger" onClick={() => void decide(request, "reject")}>
                      Reject
                    </button>
                  </div>
                ) : (
                  <p className="muted small">You cannot decide this request (not an approver, or you submitted it).</p>
                )}
              </article>
            );
          })}
        </div>
      )}
    </Panel>
  );
}
