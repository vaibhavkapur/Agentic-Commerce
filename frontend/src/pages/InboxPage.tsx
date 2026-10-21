import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Empty, ErrorNote, Money, Panel, StatusBadge, formatDate } from "../components/ui";
import type { ApprovalRequest, CaseSummary } from "../types";

const ATTENTION_STATUSES = new Set(["needs_information", "investigating", "ready_for_review"]);

export function InboxPage() {
  const { org, user } = useAuth();
  const navigate = useNavigate();
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [queue, setQueue] = useState<ApprovalRequest[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [filter, setFilter] = useState<"all" | "mine">("all");
  const [title, setTitle] = useState("");

  const load = useCallback(async () => {
    if (!org) return;
    try {
      const [list, approvals] = await Promise.all([api.listCases(org.id, { mine: filter === "mine" }), api.approvalQueue(org.id)]);
      setCases(list);
      setQueue(approvals);
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, [org, filter]);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 5000);
    return () => clearInterval(timer);
  }, [load]);

  async function createCase(event: FormEvent) {
    event.preventDefault();
    if (!org) return;
    const created = await api.createCase(org.id, title);
    setTitle("");
    navigate(`/cases/${created.id}`);
  }

  if (!org) return <Empty>You are not a member of any organization.</Empty>;

  const outstanding = cases.filter((c) => c.status === "needs_information");
  const attention = cases.filter((c) => ATTENTION_STATUSES.has(c.status));

  return (
    <div className="grid two">
      <Panel
        title="Cases"
        actions={
          <>
            <select value={filter} onChange={(e) => setFilter(e.target.value as "all" | "mine")}>
              <option value="all">All cases</option>
              <option value="mine">Assigned to me</option>
            </select>
            <form onSubmit={createCase} className="inline-form">
              <input placeholder="New case title (optional)" value={title} onChange={(e) => setTitle(e.target.value)} />
              <button type="submit">New case</button>
            </form>
          </>
        }
      >
        <ErrorNote error={error} />
        {cases.length === 0 ? (
          <Empty>No cases yet. Create one and upload an invoice.</Empty>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Reference</th>
                <th>Supplier / invoice</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Open exceptions</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.id} className={c.assigned_to === user?.id ? "mine" : ""}>
                  <td>
                    <Link to={`/cases/${c.id}`}>{c.reference}</Link>
                    <div className="muted small">{c.title}</div>
                  </td>
                  <td>
                    {c.supplier_name ?? <span className="muted">—</span>}
                    <div className="muted small">{c.invoice_number ?? "no invoice yet"}</div>
                  </td>
                  <td>
                    <Money minor={c.amount_minor} currency={c.currency} />
                  </td>
                  <td>
                    <StatusBadge status={c.status} />
                  </td>
                  <td>{c.open_exceptions ? <strong>{c.open_exceptions}</strong> : <span className="muted">0</span>}</td>
                  <td className="muted small">{formatDate(c.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
      <div className="stack">
        <Panel title={`Approval requests (${queue.length})`} actions={<Link to="/approvals">Open queue</Link>}>
          {queue.length === 0 ? (
            <Empty>Nothing waiting for approval.</Empty>
          ) : (
            <ul className="list">
              {queue.map((q) => (
                <li key={q.id}>
                  <Link to={`/cases/${q.case_id}`}>{q.case?.reference}</Link> — <Money minor={q.snapshot.amount_minor} /> to{" "}
                  {q.snapshot.beneficiary?.account_name}
                  <div className="muted small">
                    requested {formatDate(q.created_at)}; expires {formatDate(q.expires_at)}
                    {q.can_decide ? "" : " · you cannot decide this one"}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title={`Outstanding evidence (${outstanding.length})`}>
          {outstanding.length === 0 ? (
            <Empty>No cases are waiting for documents.</Empty>
          ) : (
            <ul className="list">
              {outstanding.map((c) => (
                <li key={c.id}>
                  <Link to={`/cases/${c.id}`}>{c.reference}</Link> — {c.supplier_name ?? c.title}
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title={`Needs attention (${attention.length})`}>
          {attention.length === 0 ? (
            <Empty>All quiet.</Empty>
          ) : (
            <ul className="list">
              {attention.map((c) => (
                <li key={c.id}>
                  <Link to={`/cases/${c.id}`}>{c.reference}</Link> <StatusBadge status={c.status} />
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
