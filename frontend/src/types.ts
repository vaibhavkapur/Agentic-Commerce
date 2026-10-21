export type Role = "admin" | "ap_specialist" | "budget_owner" | "approver";

export interface User {
  id: string;
  email: string;
  display_name: string;
}

export interface OrganizationMembership {
  id: string;
  name: string;
  slug: string;
  role: Role;
}

export interface CaseSummary {
  id: string;
  organization_id: string;
  reference: string;
  title: string;
  status: string;
  created_by: string;
  assigned_to: string | null;
  invoice_number: string | null;
  supplier_name: string | null;
  amount_minor: number | null;
  amount: string | null;
  currency: string;
  vendor_id: string | null;
  beneficiary_id: string | null;
  created_at: string;
  updated_at: string;
  open_exceptions?: number;
}

export interface ExtractedField {
  id: string;
  name: string;
  value_text: string | null;
  value_json: unknown;
  page: number | null;
  excerpt: string | null;
  confidence: number | null;
  source: "extractor" | "agent_proposal" | "human";
  revision: number;
  created_by: string | null;
  created_at: string;
}

export interface DocumentVersion {
  id: string;
  document_id: string;
  version: number;
  kind: string;
  filename: string;
  sha256: string;
  size_bytes: number;
  page_count: number;
  is_current: boolean;
  uploaded_by: string;
  created_at: string;
  download_url: string | null;
  text_pages: string[];
  fields: ExtractedField[];
  effective_fields: Record<string, ExtractedField>;
}

export interface EvidenceLink {
  id: string;
  label: string;
  document_version_id: string | null;
  page: number | null;
  excerpt: string | null;
  record_type: string | null;
  record_id: string | null;
}

export interface CaseException {
  id: string;
  code: string;
  severity: "blocking" | "warning" | "info";
  title: string;
  detail: string;
  status: "open" | "resolved" | "waived";
  needs_information: boolean;
  detected_by: string;
  agent_run_id: string | null;
  resolution_note: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  created_at: string;
  evidence: EvidenceLink[];
}

export interface ClarificationDraft {
  id: string;
  agent_run_id: string | null;
  recipient: string;
  subject: string;
  body: string;
  requested_items: string[];
  status: string;
  authored_by: string;
  created_at: string;
}

export interface Comment {
  id: string;
  author: User | null;
  body: string;
  created_at: string;
}

export interface ApprovalDecision {
  id: string;
  approval_request_id: string;
  decided_by: string;
  decision: "approve" | "reject";
  note: string | null;
  snapshot_hash: string;
  created_at: string;
}

export interface ApprovalRequest {
  id: string;
  case_id: string;
  case: CaseSummary | null;
  snapshot_hash: string;
  snapshot: Snapshot;
  policy_version: string;
  requested_by: string;
  expires_at: string;
  status: string;
  invalidation_reason: string | null;
  created_at: string;
  decisions: ApprovalDecision[];
  can_decide?: boolean;
}

export interface Snapshot {
  organization_id: string;
  case_id: string;
  case_reference: string;
  invoice_number: string | null;
  supplier_name: string | null;
  amount_minor: number | null;
  currency: string;
  document_versions: { document_id: string; version: number; kind: string; sha256: string; document_version_id: string }[];
  beneficiary: {
    id: string;
    version: number;
    verification_status: string;
    account_name: string;
    sort_code: string | null;
    account_number: string | null;
    iban: string | null;
  } | null;
  vendor: { id: string; version: number; vendor_code: string } | null;
  exceptions: { id: string; code: string; severity: string; status: string; resolved_by: string | null; resolution_note: string | null }[];
}

export interface PaymentInstruction {
  id: string;
  case_id: string;
  approval_request_id: string;
  snapshot_hash: string;
  audit_reference: string;
  instruction: Record<string, unknown>;
  summary_text: string;
  created_by: string;
  created_at: string;
  created?: boolean;
}

export interface TraceEntry {
  type: "node" | "tool_call" | "model_error";
  node?: string;
  tool?: string;
  at?: string;
  [key: string]: unknown;
}

export interface AgentRun {
  id: string;
  case_id: string;
  thread_id: string;
  status: string;
  started_by: string;
  model_name: string | null;
  prompt_version: string | null;
  model_calls: number;
  tool_calls: number;
  summary: string | null;
  outcome: string | null;
  error: string | null;
  trace: TraceEntry[];
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface AuditEvent {
  id: string;
  case_id: string | null;
  actor_type: "user" | "agent" | "system";
  actor_id: string | null;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface CaseDetail extends CaseSummary {
  documents: DocumentVersion[];
  exceptions: CaseException[];
  clarification_drafts: ClarificationDraft[];
  comments: Comment[];
  approvals: ApprovalRequest[];
  agent_runs: AgentRun[];
  payment_instruction: PaymentInstruction | null;
  people: Record<string, { id: string; display_name: string; email: string }>;
}

export interface Beneficiary {
  id: string;
  vendor_id: string;
  version: number;
  account_name: string;
  sort_code: string | null;
  account_number: string | null;
  iban: string | null;
  verification_status: string;
  verification_note: string | null;
  verified_by: string | null;
  verified_at: string | null;
  is_current: boolean;
  created_at: string;
}

export interface Vendor {
  id: string;
  vendor_code: string;
  name: string;
  tax_id: string | null;
  status: string;
  version: number;
  created_at: string;
  beneficiaries: Beneficiary[];
}

export interface Member {
  id: string;
  user: User;
  role: Role;
}
