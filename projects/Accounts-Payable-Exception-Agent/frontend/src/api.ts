import type {
  AgentRun,
  ApprovalRequest,
  AuditEvent,
  Beneficiary,
  CaseDetail,
  CaseException,
  CaseSummary,
  ClarificationDraft,
  Comment,
  DocumentVersion,
  ExtractedField,
  Member,
  OrganizationMembership,
  PaymentInstruction,
  User,
  Vendor,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "/api";
const TOKEN_KEY = "ap.token";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : (detail as { message?: string })?.message ?? `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${BASE}${path}`, { ...init, headers });
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) throw new ApiError(response.status, data?.detail ?? data);
  return data as T;
}

export const api = {
  devLogin: (email: string) =>
    request<{ access_token: string; user: User }>("/auth/dev-login", { method: "POST", body: JSON.stringify({ email }) }),
  me: () => request<{ user: User; organizations: OrganizationMembership[] }>("/auth/me"),

  listCases: (org: string, params: { status?: string; mine?: boolean } = {}) => {
    const query = new URLSearchParams();
    if (params.status) query.set("status", params.status);
    if (params.mine) query.set("mine", "true");
    const suffix = query.toString() ? `?${query}` : "";
    return request<CaseSummary[]>(`/orgs/${org}/cases${suffix}`);
  },
  createCase: (org: string, title: string, reference?: string) =>
    request<CaseSummary>(`/orgs/${org}/cases`, { method: "POST", body: JSON.stringify({ title, reference: reference || null }) }),
  getCase: (org: string, id: string) => request<CaseDetail>(`/orgs/${org}/cases/${id}`),
  uploadDocument: (org: string, caseId: string, kind: string, file: File) => {
    const body = new FormData();
    body.set("kind", kind);
    body.set("file", file);
    return request<DocumentVersion>(`/orgs/${org}/cases/${caseId}/documents`, { method: "POST", body });
  },
  correctField: (org: string, caseId: string, docId: string, payload: { name: string; value_text?: string | null; value_json?: unknown; page?: number | null; note?: string }) =>
    request<ExtractedField>(`/orgs/${org}/cases/${caseId}/documents/${docId}/fields`, { method: "POST", body: JSON.stringify(payload) }),
  rerunChecks: (org: string, caseId: string) => request<CaseException[]>(`/orgs/${org}/cases/${caseId}/checks`, { method: "POST" }),
  resolveException: (org: string, caseId: string, exceptionId: string, action: "resolve" | "waive" | "reopen", note: string) =>
    request<CaseException>(`/orgs/${org}/cases/${caseId}/exceptions/${exceptionId}`, { method: "POST", body: JSON.stringify({ action, note }) }),
  updateDraft: (org: string, caseId: string, draftId: string, status: string) =>
    request<ClarificationDraft>(`/orgs/${org}/cases/${caseId}/drafts/${draftId}`, { method: "POST", body: JSON.stringify({ status }) }),
  addComment: (org: string, caseId: string, body: string) =>
    request<Comment>(`/orgs/${org}/cases/${caseId}/comments`, { method: "POST", body: JSON.stringify({ body }) }),
  investigate: (org: string, caseId: string) => request<AgentRun>(`/orgs/${org}/cases/${caseId}/investigate`, { method: "POST" }),
  closeCase: (org: string, caseId: string) => request<CaseSummary>(`/orgs/${org}/cases/${caseId}/close`, { method: "POST" }),
  timeline: (org: string, caseId: string) => request<AuditEvent[]>(`/orgs/${org}/cases/${caseId}/timeline`),

  approvalQueue: (org: string) => request<ApprovalRequest[]>(`/orgs/${org}/approvals`),
  requestApproval: (org: string, caseId: string) => request<ApprovalRequest>(`/orgs/${org}/cases/${caseId}/approvals`, { method: "POST" }),
  decide: (org: string, caseId: string, approvalId: string, decision: "approve" | "reject", note: string) =>
    request<{ request_status: string; case_status: string }>(`/orgs/${org}/cases/${caseId}/approvals/${approvalId}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, note }),
    }),
  exportInstruction: (org: string, caseId: string) => request<PaymentInstruction>(`/orgs/${org}/cases/${caseId}/export`, { method: "POST" }),

  vendors: (org: string) => request<Vendor[]>(`/orgs/${org}/vendors`),
  createVendor: (org: string, payload: { vendor_code: string; name: string; tax_id?: string | null }) =>
    request<Vendor>(`/orgs/${org}/vendors`, { method: "POST", body: JSON.stringify(payload) }),
  addBeneficiary: (org: string, vendorId: string, payload: { account_name: string; sort_code?: string; account_number?: string; iban?: string; verified?: boolean; note?: string }) =>
    request<Beneficiary>(`/orgs/${org}/vendors/${vendorId}/beneficiaries`, { method: "POST", body: JSON.stringify(payload) }),
  verifyBeneficiary: (org: string, vendorId: string, beneficiaryId: string, note: string) =>
    request<Beneficiary>(`/orgs/${org}/vendors/${vendorId}/beneficiaries/${beneficiaryId}/verify`, { method: "POST", body: JSON.stringify({ note }) }),
  members: (org: string) => request<Member[]>(`/orgs/${org}/members`),
  addMember: (org: string, payload: { email: string; display_name?: string; role: string }) =>
    request<Member>(`/orgs/${org}/members`, { method: "POST", body: JSON.stringify(payload) }),
  events: (org: string, since?: string) => request<AuditEvent[]>(`/orgs/${org}/events${since ? `?since=${encodeURIComponent(since)}` : ""}`),

  fileUrl: (path: string) => `${BASE}${path}`,
};

export async function fetchFileBlob(path: string): Promise<string> {
  const response = await fetch(api.fileUrl(path), { headers: { Authorization: `Bearer ${getToken() ?? ""}` } });
  if (!response.ok) throw new ApiError(response.status, await response.text());
  return URL.createObjectURL(await response.blob());
}
