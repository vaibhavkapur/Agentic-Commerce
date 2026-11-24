import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import type { ApprovalRequest, CaseDetail } from "../types";
import { Empty, ErrorNote, Money, Panel, ProvenanceBadge, StatusBadge, formatDate } from "./ui";

interface Props {
  org: string;
  detail: CaseDetail;
  onChanged: () => void;
}

export function ApprovalPanel({ org, detail, onChanged }: Props) {
  const { user, org: membership } = useAuth();
  const [error, setError] = useState<unknown>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const requests = [...detail.approvals].reverse();
  const pending = requests.find((r) => r.status === "pending");
  const approved = requests.find((r) => r.status === "approved");
  const blockers = detail.exceptions.filter((e) => e.status === "open" && e.severity === "blocking");
  const canExport = membership && ["ap_specialist", "approver", "admin"].includes(membership.role);
  const frozen = detail.status === "exported" || detail.status === "rejected";

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      setNote("");
      onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const current = pending ?? approved ?? requests[0];
  const isSubmitter = current && user && (current.requested_by === user.id || detail.created_by === user.id);
  const canDecide = pending && membership?.role === "approver" && !isSubmitter;

  return (
    <Panel
      title="Approval"
      actions={
        !frozen &&
        !pending &&
        !approved && (
          <button type="button" disabled={busy || blockers.length > 0 || !detail.vendor_id} onClick={() => void run(() => api.requestApproval(org, detail.id))} title={blockers.length ? "Resolve blocking exceptions first" : ""}>
            Request approval
          </button>
        )
      }
    >
      <ErrorNote error={error} />
      {blockers.length > 0 && !frozen && (
        <p className="warning">
          {blockers.length} blocking exception{blockers.length === 1 ? "" : "s"} must be resolved before approval: {blockers.map((b) => b.code).join(", ")}.
        </p>
      )}
      {!current ? (
        <Empty>No approval has been requested yet.</Empty>
      ) : (
        <div className="stack">
          <SnapshotView request={current} detail={detail} />
          {canDecide && (
            <div className="decision">
              <h3>Your decision</h3>
              <p className="muted small">
                You are approving exactly the instruction above (snapshot <code>{current.snapshot_hash.slice(0, 16)}…</code>). Any change to documents, amount, beneficiary, or
                exception decisions invalidates it.
              </p>
              <input placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
              <div className="actions">
                <button type="button" disabled={busy} onClick={() => void run(() => api.decide(org, detail.id, current.id, "approve", note))}>
                  Approve
                </button>
                <button type="button" className="danger" disabled={busy} onClick={() => void run(() => api.decide(org, detail.id, current.id, "reject", note))}>
                  Reject
                </button>
              </div>
            </div>
          )}
          {pending && !canDecide && (
            <p className="muted small">
              {isSubmitter ? "You submitted this request or created the case, so a different approver must decide it." : "Waiting for an approver."}
            </p>
          )}
          {approved && !detail.payment_instruction && canExport && (
            <div className="actions">
              <button type="button" disabled={busy} onClick={() => void run(() => api.exportInstruction(org, detail.id))}>
                Export payment instruction
              </button>
              <span className="muted small">The export revalidates the approved snapshot and is idempotent.</span>
            </div>
          )}
          {requests.length > 1 && (
            <details>
              <summary className="muted">{requests.length - 1} earlier request(s)</summary>
              <ul className="list">
                {requests.slice(1).map((r) => (
                  <li key={r.id}>
                    <StatusBadge status={r.status} /> <code>{r.snapshot_hash.slice(0, 12)}…</code> <Money minor={r.snapshot.amount_minor} />{" "}
                    <span className="muted small">{formatDate(r.created_at)}</span>
                    {r.invalidation_reason && <div className="muted small">Invalidated: {r.invalidation_reason}</div>}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
      {detail.payment_instruction && (
        <div className="instruction">
          <h3>
            Exported instruction <code>{detail.payment_instruction.audit_reference}</code>
          </h3>
          <pre>{detail.payment_instruction.summary_text}</pre>
          <details>
            <summary className="muted">Instruction JSON</summary>
            <pre>{JSON.stringify(detail.payment_instruction.instruction, null, 2)}</pre>
          </details>
        </div>
      )}
    </Panel>
  );
}

function SnapshotView({ request, detail }: { request: ApprovalRequest; detail: CaseDetail }) {
  const s = request.snapshot;
  const approver = request.decisions.find((d) => d.decision === "approve");
  return (
    <div className="snapshot">
      <header>
        <StatusBadge status={request.status} />
        <span className="muted small">
          requested by {detail.people[request.requested_by]?.display_name ?? request.requested_by} on {formatDate(request.created_at)} · expires {formatDate(request.expires_at)} · policy{" "}
          {request.policy_version}
        </span>
      </header>
      {request.invalidation_reason && <p className="warning">Invalidated: {request.invalidation_reason}</p>}
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
          {s.beneficiary ? (
            <>
              <ProvenanceBadge kind="register" compact /> {s.beneficiary.account_name} — sort code {s.beneficiary.sort_code ?? "—"}, account {s.beneficiary.account_number ?? "—"}
              {s.beneficiary.iban ? `, IBAN ${s.beneficiary.iban}` : ""} <span className="muted small">(beneficiary version {s.beneficiary.version}, {s.beneficiary.verification_status})</span>
            </>
          ) : (
            <span className="error">No verified beneficiary</span>
          )}
        </dd>
        <dt>Evidence</dt>
        <dd>
          <ul className="list small">
            {s.document_versions.map((d) => (
              <li key={d.document_version_id}>
                {d.kind.replaceAll("_", " ")} v{d.version} <code>{d.sha256.slice(0, 12)}…</code>
              </li>
            ))}
          </ul>
        </dd>
        <dt>Exceptions</dt>
        <dd>
          {s.exceptions.length === 0 ? (
            <span className="muted">none recorded</span>
          ) : (
            <ul className="list small">
              {s.exceptions.map((e) => (
                <li key={e.id}>
                  <code>{e.code}</code> {e.status}
                  {e.resolved_by && <> by {detail.people[e.resolved_by]?.display_name ?? e.resolved_by}</>}
                  {e.resolution_note && <span className="muted"> — {e.resolution_note}</span>}
                </li>
              ))}
            </ul>
          )}
        </dd>
        <dt>Snapshot</dt>
        <dd>
          <code>{request.snapshot_hash}</code>
        </dd>
        {approver && (
          <>
            <dt>Approved by</dt>
            <dd>
              <ProvenanceBadge kind="human" compact /> {detail.people[approver.decided_by]?.display_name ?? approver.decided_by} on {formatDate(approver.created_at)}
              {approver.note && <> — “{approver.note}”</>}
            </dd>
          </>
        )}
      </dl>
    </div>
  );
}
