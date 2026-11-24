import type { ReactNode } from "react";

/** Provenance badges. The UI must always say whether a value is an extracted claim, a verified
 * register record, an agent recommendation, or a human decision. */
export type Provenance = "extracted" | "register" | "agent" | "human" | "system";

const PROVENANCE_LABEL: Record<Provenance, string> = {
  extracted: "Extracted claim",
  register: "Verified record",
  agent: "Agent recommendation",
  human: "Human decision",
  system: "System check",
};

export function ProvenanceBadge({ kind, compact = false }: { kind: Provenance; compact?: boolean }) {
  return (
    <span className={`badge provenance provenance-${kind}`} title={PROVENANCE_LABEL[kind]}>
      {compact ? PROVENANCE_LABEL[kind].split(" ")[0] : PROVENANCE_LABEL[kind]}
    </span>
  );
}

export function sourceToProvenance(source: string): Provenance {
  if (source === "human") return "human";
  if (source === "agent_proposal") return "agent";
  return "extracted";
}

export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge status status-${status}`}>{status.replaceAll("_", " ")}</span>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  return <span className={`badge severity severity-${severity}`}>{severity}</span>;
}

export function Money({ minor, currency = "GBP" }: { minor: number | null | undefined; currency?: string }) {
  if (minor === null || minor === undefined) return <span className="muted">—</span>;
  const sign = minor < 0 ? "-" : "";
  const abs = Math.abs(minor);
  const pounds = Math.floor(abs / 100).toLocaleString("en-GB");
  const pence = String(abs % 100).padStart(2, "0");
  return (
    <span className="money">
      {currency} {sign}
      {pounds}.{pence}
    </span>
  );
}

export function Panel({ title, actions, children, className = "" }: { title: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`panel ${className}`}>
      <header className="panel-header">
        <h2>{title}</h2>
        {actions && <div className="panel-actions">{actions}</div>}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="muted empty">{children}</p>;
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const detail = (error as { detail?: unknown }).detail;
  let text = (error as Error).message ?? String(error);
  if (detail && typeof detail === "object" && "blockers" in (detail as object)) {
    const blockers = (detail as { blockers: { code?: string }[] | string[] }).blockers;
    text += ": " + blockers.map((b) => (typeof b === "string" ? b : b.code)).join(", ");
  }
  return <p className="error">{text}</p>;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}
