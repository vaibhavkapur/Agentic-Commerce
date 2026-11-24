"""Request bodies and response serializers."""

from pydantic import BaseModel, Field

from .models import (
    AgentRun,
    ApprovalDecision,
    ApprovalRequest,
    AuditEvent,
    Beneficiary,
    Case,
    CaseComment,
    CaseException,
    ClarificationDraft,
    DocumentVersion,
    EvidenceLink,
    ExtractedField,
    Membership,
    Organization,
    PaymentInstruction,
    User,
    Vendor,
)
from .money import format_minor

# ------------------------------------------------------------------ request bodies

class DevLoginRequest(BaseModel):
    email: str


class CreateCaseRequest(BaseModel):
    title: str = Field(default="", max_length=300)
    reference: str | None = Field(default=None, max_length=64)


class CommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class AssignRequest(BaseModel):
    user_id: str | None


class FieldCorrectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    value_text: str | None = None
    value_json: dict | list | int | None = None
    page: int | None = None
    note: str | None = None


class ResolveExceptionRequest(BaseModel):
    action: str = Field(pattern="^(resolve|waive|reopen)$")
    note: str = Field(min_length=3, max_length=2000)


class DecisionRequest(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    note: str | None = Field(default=None, max_length=2000)


class CreateVendorRequest(BaseModel):
    vendor_code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    tax_id: str | None = None


class BeneficiaryRequest(BaseModel):
    account_name: str = Field(min_length=1, max_length=200)
    sort_code: str | None = None
    account_number: str | None = None
    iban: str | None = None
    verified: bool = False
    note: str | None = None


class VerifyBeneficiaryRequest(BaseModel):
    note: str = Field(min_length=3, max_length=2000)


class MembershipRequest(BaseModel):
    email: str
    display_name: str | None = None
    role: str = Field(pattern="^(admin|ap_specialist|budget_owner|approver)$")


class DraftUpdateRequest(BaseModel):
    status: str = Field(pattern="^(draft|sent_manually|dismissed)$")


# ------------------------------------------------------------------ serializers

def user_out(user: User | None) -> dict | None:
    if user is None:
        return None
    return {"id": user.id, "email": user.email, "display_name": user.display_name}


def organization_out(org: Organization, membership: Membership) -> dict:
    return {"id": org.id, "name": org.name, "slug": org.slug, "role": membership.role}


def membership_out(m: Membership) -> dict:
    return {"id": m.id, "user": user_out(m.user), "role": m.role}


def vendor_out(vendor: Vendor, beneficiaries: list[Beneficiary]) -> dict:
    return {
        "id": vendor.id, "vendor_code": vendor.vendor_code, "name": vendor.name, "tax_id": vendor.tax_id,
        "status": vendor.status, "version": vendor.version, "created_at": vendor.created_at,
        "beneficiaries": [beneficiary_out(b) for b in beneficiaries],
    }


def beneficiary_out(b: Beneficiary) -> dict:
    return {
        "id": b.id, "vendor_id": b.vendor_id, "version": b.version, "account_name": b.account_name,
        "sort_code": b.sort_code, "account_number": b.account_number, "iban": b.iban,
        "verification_status": b.verification_status, "verification_note": b.verification_note,
        "verified_by": b.verified_by, "verified_at": b.verified_at, "is_current": b.is_current,
        "created_at": b.created_at,
    }


def case_out(case: Case) -> dict:
    return {
        "id": case.id, "organization_id": case.organization_id, "reference": case.reference,
        "title": case.title, "status": case.status, "created_by": case.created_by,
        "assigned_to": case.assigned_to, "invoice_number": case.invoice_number,
        "supplier_name": case.supplier_name, "amount_minor": case.amount_minor,
        "amount": format_minor(case.amount_minor, case.currency) if case.amount_minor is not None else None,
        "currency": case.currency, "vendor_id": case.vendor_id, "beneficiary_id": case.beneficiary_id,
        "created_at": case.created_at, "updated_at": case.updated_at,
    }


def field_out(f: ExtractedField) -> dict:
    return {
        "id": f.id, "name": f.name, "value_text": f.value_text, "value_json": f.value_json, "page": f.page,
        "excerpt": f.excerpt, "confidence": f.confidence, "source": f.source, "revision": f.revision,
        "created_by": f.created_by, "created_at": f.created_at,
    }


def document_out(doc: DocumentVersion, fields: list[ExtractedField], effective: dict[str, ExtractedField],
                 download_url: str | None) -> dict:
    return {
        "id": doc.id, "document_id": doc.document_id, "version": doc.version, "kind": doc.kind,
        "filename": doc.filename, "sha256": doc.sha256, "size_bytes": doc.size_bytes,
        "page_count": doc.page_count, "is_current": doc.is_current, "uploaded_by": doc.uploaded_by,
        "created_at": doc.created_at, "download_url": download_url,
        "text_pages": doc.text_pages or [],
        "fields": [field_out(f) for f in fields],
        "effective_fields": {name: field_out(f) for name, f in effective.items()},
    }


def evidence_out(link: EvidenceLink) -> dict:
    return {
        "id": link.id, "label": link.label, "document_version_id": link.document_version_id, "page": link.page,
        "excerpt": link.excerpt, "record_type": link.record_type, "record_id": link.record_id,
    }


def exception_out(exc: CaseException) -> dict:
    return {
        "id": exc.id, "code": exc.code, "severity": exc.severity, "title": exc.title, "detail": exc.detail,
        "status": exc.status, "needs_information": exc.needs_information, "detected_by": exc.detected_by,
        "agent_run_id": exc.agent_run_id, "resolution_note": exc.resolution_note,
        "resolved_by": exc.resolved_by, "resolved_at": exc.resolved_at, "created_at": exc.created_at,
        "evidence": [evidence_out(link) for link in exc.evidence],
    }


def draft_out(d: ClarificationDraft) -> dict:
    return {
        "id": d.id, "agent_run_id": d.agent_run_id, "recipient": d.recipient, "subject": d.subject, "body": d.body,
        "requested_items": d.requested_items or [], "status": d.status, "authored_by": d.authored_by,
        "created_at": d.created_at,
    }


def comment_out(c: CaseComment, author: User | None) -> dict:
    return {"id": c.id, "author": user_out(author), "body": c.body, "created_at": c.created_at}


def decision_out(d: ApprovalDecision) -> dict:
    return {"id": d.id, "approval_request_id": d.approval_request_id, "decided_by": d.decided_by,
            "decision": d.decision, "note": d.note, "snapshot_hash": d.snapshot_hash, "created_at": d.created_at}


def approval_out(r: ApprovalRequest, case: Case | None = None) -> dict:
    return {
        "id": r.id, "case_id": r.case_id, "case": case_out(case) if case else None,
        "snapshot_hash": r.snapshot_hash, "snapshot": r.snapshot, "policy_version": r.policy_version,
        "requested_by": r.requested_by, "expires_at": r.expires_at, "status": r.status,
        "invalidation_reason": r.invalidation_reason, "created_at": r.created_at,
        "decisions": [decision_out(d) for d in r.decisions],
    }


def instruction_out(p: PaymentInstruction) -> dict:
    return {
        "id": p.id, "case_id": p.case_id, "approval_request_id": p.approval_request_id,
        "snapshot_hash": p.snapshot_hash, "audit_reference": p.audit_reference, "instruction": p.instruction,
        "summary_text": p.summary_text, "created_by": p.created_by, "created_at": p.created_at,
    }


def run_out(run: AgentRun) -> dict:
    return {
        "id": run.id, "case_id": run.case_id, "thread_id": run.thread_id, "status": run.status,
        "started_by": run.started_by, "model_name": run.model_name, "prompt_version": run.prompt_version,
        "model_calls": run.model_calls, "tool_calls": run.tool_calls, "summary": run.summary,
        "outcome": run.outcome, "error": run.error, "trace": run.trace or [], "started_at": run.started_at,
        "finished_at": run.finished_at, "created_at": run.created_at,
    }


def audit_out(e: AuditEvent) -> dict:
    return {"id": e.id, "case_id": e.case_id, "actor_type": e.actor_type, "actor_id": e.actor_id,
            "event_type": e.event_type, "payload": e.payload, "created_at": e.created_at}
