import { useEffect, useState, type FormEvent } from "react";
import { api, fetchFileBlob } from "../api";
import type { CaseDetail, DocumentVersion, ExtractedField } from "../types";
import { Empty, ErrorNote, Money, Panel, ProvenanceBadge, sourceToProvenance } from "./ui";

const KINDS = [
  ["invoice", "Invoice"],
  ["purchase_order", "Purchase order"],
  ["delivery_confirmation", "Delivery confirmation"],
  ["other", "Other"],
];

interface Props {
  org: string;
  detail: CaseDetail;
  focus: { documentId: string; page: number } | null;
  canEdit: boolean;
  onChanged: () => void;
}

export function DocumentsPanel({ org, detail, focus, canEdit, onChanged }: Props) {
  const current = detail.documents.filter((d) => d.is_current);
  const [selectedId, setSelectedId] = useState<string | null>(current[0]?.id ?? null);
  const [page, setPage] = useState(1);
  const [kind, setKind] = useState("invoice");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (focus) {
      setSelectedId(focus.documentId);
      setPage(focus.page || 1);
    }
  }, [focus]);

  useEffect(() => {
    if (!selectedId || !detail.documents.some((d) => d.id === selectedId)) setSelectedId(current[0]?.id ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail.documents]);

  const selected = detail.documents.find((d) => d.id === selectedId) ?? null;
  const frozen = detail.status === "exported" || detail.status === "rejected";

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const doc = await api.uploadDocument(org, detail.id, kind, file);
      setFile(null);
      setSelectedId(doc.id);
      setPage(1);
      onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel
      title="Documents"
      actions={
        !frozen && (
          <form onSubmit={upload} className="inline-form">
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              {KINDS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <input type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <button type="submit" disabled={!file || busy}>
              {busy ? "Uploading…" : "Upload PDF"}
            </button>
          </form>
        )
      }
    >
      <ErrorNote error={error} />
      {detail.documents.length === 0 ? (
        <Empty>No documents yet. Upload the invoice to start.</Empty>
      ) : (
        <div className="documents">
          <ul className="doc-list">
            {detail.documents.map((d) => (
              <li key={d.id} className={`${d.id === selectedId ? "selected" : ""} ${d.is_current ? "" : "superseded"}`}>
                <button type="button" className="link" onClick={() => setSelectedId(d.id)}>
                  <strong>{labelFor(d.kind)}</strong> v{d.version}
                  {!d.is_current && <span className="muted"> (superseded)</span>}
                  <div className="muted small">
                    {d.filename} · {d.page_count} page{d.page_count === 1 ? "" : "s"} · sha256 {d.sha256.slice(0, 12)}…
                  </div>
                </button>
              </li>
            ))}
          </ul>
          {selected && (
            <div className="doc-detail">
              <DocumentViewer doc={selected} page={page} onPage={setPage} />
              <FieldsTable org={org} caseId={detail.id} doc={selected} canEdit={canEdit && !frozen && selected.is_current} onChanged={onChanged} onJump={setPage} />
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

export function labelFor(kind: string): string {
  return KINDS.find(([value]) => value === kind)?.[1] ?? kind;
}

function DocumentViewer({ doc, page, onPage }: { doc: DocumentVersion; page: number; onPage: (p: number) => void }) {
  const [mode, setMode] = useState<"text" | "pdf">("text");
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    let revoked = false;
    if (mode === "pdf" && doc.download_url) {
      fetchFileBlob(doc.download_url)
        .then((url) => {
          if (!revoked) setBlobUrl(url);
        })
        .catch(() => setBlobUrl(null));
    }
    return () => {
      revoked = true;
      if (blobUrl) URL.revokeObjectURL(blobUrl);
      setBlobUrl(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, doc.id]);

  const pageCount = Math.max(doc.page_count, doc.text_pages.length, 1);
  const safePage = Math.min(Math.max(page, 1), pageCount);
  return (
    <div className="viewer">
      <div className="viewer-toolbar">
        <span>
          Page {safePage} of {pageCount}
        </span>
        <button type="button" disabled={safePage <= 1} onClick={() => onPage(safePage - 1)}>
          ‹
        </button>
        <button type="button" disabled={safePage >= pageCount} onClick={() => onPage(safePage + 1)}>
          ›
        </button>
        <span className="spacer" />
        <button type="button" className={mode === "text" ? "active" : ""} onClick={() => setMode("text")}>
          Text
        </button>
        <button type="button" className={mode === "pdf" ? "active" : ""} onClick={() => setMode("pdf")}>
          PDF
        </button>
      </div>
      {mode === "text" ? (
        <pre className="page-text">{doc.text_pages[safePage - 1] ?? "(no text extracted)"}</pre>
      ) : blobUrl ? (
        <iframe title={doc.filename} src={`${blobUrl}#page=${safePage}`} className="pdf-frame" />
      ) : (
        <p className="muted">Loading PDF…</p>
      )}
    </div>
  );
}

function FieldsTable({ org, caseId, doc, canEdit, onChanged, onJump }: { org: string; caseId: string; doc: DocumentVersion; canEdit: boolean; onChanged: () => void; onJump: (page: number) => void }) {
  const [editing, setEditing] = useState<string | null>(null);
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<unknown>(null);
  const names = Object.keys(doc.effective_fields).sort();

  async function save(name: string) {
    setError(null);
    try {
      const payload: { name: string; value_text?: string; value_json?: unknown; note: string } = { name, note };
      if (name.endsWith("_minor")) payload.value_json = Math.round(Number(value.replace(/[^0-9.-]/g, "")) * 100);
      else if (name === "line_items") payload.value_json = JSON.parse(value);
      else payload.value_text = value;
      await api.correctField(org, caseId, doc.id, payload);
      setEditing(null);
      setNote("");
      onChanged();
    } catch (err) {
      setError(err);
    }
  }

  if (names.length === 0) return <Empty>No fields were extracted from this document.</Empty>;
  return (
    <div className="fields">
      <ErrorNote error={error} />
      <table className="table compact">
        <thead>
          <tr>
            <th>Field</th>
            <th>Value</th>
            <th>Source</th>
            <th>Page</th>
            {canEdit && <th />}
          </tr>
        </thead>
        <tbody>
          {names.map((name) => {
            const field = doc.effective_fields[name];
            const history = doc.fields.filter((f) => f.name === name);
            return (
              <tr key={name}>
                <td>
                  <code>{name}</code>
                  {history.length > 1 && <div className="muted small">{history.length} revisions</div>}
                </td>
                <td>
                  {editing === name ? (
                    <div className="stack small-gap">
                      <input value={value} onChange={(e) => setValue(e.target.value)} placeholder={name.endsWith("_minor") ? "e.g. 2400.00" : ""} />
                      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why is this correction needed?" />
                      <div>
                        <button type="button" onClick={() => void save(name)}>
                          Save as new revision
                        </button>{" "}
                        <button type="button" className="secondary" onClick={() => setEditing(null)}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <FieldValue field={field} />
                  )}
                </td>
                <td>
                  <ProvenanceBadge kind={sourceToProvenance(field.source)} compact />
                  {field.confidence !== null && field.source === "extractor" && <span className="muted small"> {Math.round(field.confidence * 100)}%</span>}
                </td>
                <td>
                  {field.page ? (
                    <button type="button" className="link" onClick={() => onJump(field.page!)} title={field.excerpt ?? ""}>
                      p.{field.page}
                    </button>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                {canEdit && (
                  <td>
                    {editing !== name && (
                      <button
                        type="button"
                        className="secondary small"
                        onClick={() => {
                          setEditing(name);
                          setValue(name.endsWith("_minor") ? (Number(field.value_json ?? field.value_text ?? 0) / 100).toFixed(2) : name === "line_items" ? JSON.stringify(field.value_json) : (field.value_text ?? ""));
                        }}
                      >
                        Correct
                      </button>
                    )}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function FieldValue({ field }: { field: ExtractedField }) {
  if (field.name.endsWith("_minor")) return <Money minor={Number(field.value_json ?? field.value_text)} />;
  if (field.name === "line_items" && Array.isArray(field.value_json)) {
    const items = field.value_json as { description: string; quantity: number; unit_price_minor?: number; line_total_minor?: number }[];
    return (
      <ul className="line-items">
        {items.map((item, i) => (
          <li key={i}>
            {item.quantity} × {item.description}
            {item.unit_price_minor !== undefined && (
              <>
                {" "}
                @ <Money minor={item.unit_price_minor} /> = <Money minor={item.line_total_minor} />
              </>
            )}
          </li>
        ))}
      </ul>
    );
  }
  return <span>{field.value_text ?? JSON.stringify(field.value_json)}</span>;
}
