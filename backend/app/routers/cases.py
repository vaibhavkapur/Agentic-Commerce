import secrets

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..agent import runner
from ..authz import Principal, ensure_roles, load_case, require_principal
from ..db import get_db
from ..models import (
    AgentRun,
    ApprovalRequest,
    AuditEvent,
    Case,
    CaseComment,
    CaseException,
    CaseStatus,
    ClarificationDraft,
    DocumentVersion,
    ExceptionStatus,
    ExtractedField,
    PaymentInstruction,
    Role,
    User,
    utcnow,
)
from ..schemas import (
    AssignRequest,
    CommentRequest,
    CreateCaseRequest,
    DraftUpdateRequest,
    FieldCorrectionRequest,
    ResolveExceptionRequest,
    approval_out,
    audit_out,
    case_out,
    comment_out,
    document_out,
    draft_out,
    exception_out,
    instruction_out,
    run_out,
)
from ..services import documents as document_service
from ..services.approvals import invalidate_approvals
from ..services.checks import run_checks, sync_exceptions
from ..storage import build_storage, sign_download

router = APIRouter(prefix="/orgs/{organization_id}/cases", tags=["cases"])

RESOLVER_ROLES = (Role.AP_SPECIALIST, Role.BUDGET_OWNER, Role.APPROVER, Role.ADMIN)


@router.get("")
def list_cases(status: str | None = Query(default=None), mine: bool = Query(default=False),
               principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    query = select(Case).where(Case.organization_id == principal.organization_id)
    if status:
        query = query.where(Case.status.in_(status.split(",")))
    if mine:
        query = query.where((Case.assigned_to == principal.user.id) | (Case.created_by == principal.user.id))
    cases = db.scalars(query.order_by(Case.updated_at.desc())).all()
    counts: dict[str, int] = {}
    if cases:
        rows = db.execute(
            select(CaseException.case_id, func.count(CaseException.id))
            .where(CaseException.status == ExceptionStatus.OPEN.value,
                   CaseException.case_id.in_([c.id for c in cases]))
            .group_by(CaseException.case_id)
        ).all()
        counts = {case_id: count for case_id, count in rows}
    return [{**case_out(c), "open_exceptions": counts.get(c.id, 0)} for c in cases]


@router.post("", status_code=201)
def create_case(body: CreateCaseRequest, principal: Principal = Depends(require_principal),
                db: Session = Depends(get_db)):
    reference = body.reference or f"AP-{utcnow():%Y%m%d}-{secrets.token_hex(2).upper()}"
    if db.scalar(select(Case).where(Case.organization_id == principal.organization_id, Case.reference == reference)):
        raise HTTPException(status_code=409, detail="Case reference already exists")
    case = Case(organization_id=principal.organization_id, reference=reference,
                title=body.title or f"Case {reference}", created_by=principal.user.id,
                assigned_to=principal.user.id)
    db.add(case)
    db.flush()
    audit.record(db, organization_id=case.organization_id, case_id=case.id, actor_id=principal.user.id,
                 event_type="case_created", payload={"reference": reference})
    db.commit()
    return case_out(case)


@router.get("/{case_id}")
def get_case(case_id: str, principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    case = load_case(db, principal, case_id)
    documents = db.scalars(select(DocumentVersion).where(DocumentVersion.case_id == case.id)
                           .order_by(DocumentVersion.kind, DocumentVersion.version)).all()
    docs_out = []
    for doc in documents:
        fields = db.scalars(select(ExtractedField).where(ExtractedField.document_version_id == doc.id)
                            .order_by(ExtractedField.name, ExtractedField.revision)).all()
        effective = document_service.effective_fields(db, doc.id)
        url = f"/files/{sign_download(case.organization_id, doc.id)}"
        docs_out.append(document_out(doc, fields, effective, url))
    exceptions = db.scalars(select(CaseException).where(CaseException.case_id == case.id)
                            .order_by(CaseException.created_at)).all()
    drafts = db.scalars(select(ClarificationDraft).where(ClarificationDraft.case_id == case.id)
                        .order_by(ClarificationDraft.created_at)).all()
    comments = db.scalars(select(CaseComment).where(CaseComment.case_id == case.id)
                          .order_by(CaseComment.created_at)).all()
    approvals = db.scalars(select(ApprovalRequest).where(ApprovalRequest.case_id == case.id)
                           .order_by(ApprovalRequest.created_at)).all()
    runs = db.scalars(select(AgentRun).where(AgentRun.case_id == case.id).order_by(AgentRun.created_at)).all()
    instruction = db.scalar(select(PaymentInstruction).where(PaymentInstruction.case_id == case.id))
    users = {u.id: u for u in db.scalars(select(User))}
    return {
        **case_out(case),
        "documents": docs_out,
        "exceptions": [exception_out(e) for e in exceptions],
        "clarification_drafts": [draft_out(d) for d in drafts],
        "comments": [comment_out(c, users.get(c.author_id)) for c in comments],
        "approvals": [approval_out(a) for a in approvals],
        "agent_runs": [run_out(r) for r in runs],
        "payment_instruction": instruction_out(instruction) if instruction else None,
        "people": {uid: {"id": u.id, "display_name": u.display_name, "email": u.email} for uid, u in users.items()
                   if uid in {case.created_by, case.assigned_to, *(a.requested_by for a in approvals),
                              *(d.decided_by for a in approvals for d in a.decisions),
                              *(e.resolved_by for e in exceptions if e.resolved_by),
                              *(c.author_id for c in comments)}},
    }


@router.post("/{case_id}/assign")
def assign_case(case_id: str, body: AssignRequest, principal: Principal = Depends(require_principal),
                db: Session = Depends(get_db)):
    case = load_case(db, principal, case_id)
    case.assigned_to = body.user_id
    audit.record(db, organization_id=case.organization_id, case_id=case.id, actor_id=principal.user.id,
                 event_type="case_assigned", payload={"assigned_to": body.user_id})
    db.commit()
    return case_out(case)


@router.post("/{case_id}/comments", status_code=201)
def add_comment(case_id: str, body: CommentRequest, principal: Principal = Depends(require_principal),
                db: Session = Depends(get_db)):
    case = load_case(db, principal, case_id)
    comment = CaseComment(organization_id=case.organization_id, case_id=case.id, author_id=principal.user.id,
                          body=body.body)
    db.add(comment)
    audit.record(db, organization_id=case.organization_id, case_id=case.id, actor_id=principal.user.id,
                 event_type="comment_added", payload={"length": len(body.body)})
    db.commit()
    return comment_out(comment, principal.user)


@router.post("/{case_id}/documents", status_code=201)
def upload_document(case_id: str, kind: str = Form(...), file: UploadFile = File(...),
                    principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    case = load_case(db, principal, case_id)
    data = file.file.read()
    doc, extraction = document_service.store_document_version(
        db, case=case, kind=kind, filename=file.filename or "document.pdf", data=data,
        uploaded_by=principal.user.id, storage=build_storage())
    db.commit()
    fields = db.scalars(select(ExtractedField).where(ExtractedField.document_version_id == doc.id)).all()
    return document_out(doc, fields, document_service.effective_fields(db, doc.id),
                        f"/files/{sign_download(case.organization_id, doc.id)}")


@router.post("/{case_id}/documents/{document_version_id}/fields", status_code=201)
def correct_field(case_id: str, document_version_id: str, body: FieldCorrectionRequest,
                  principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    ensure_roles(principal, RESOLVER_ROLES)
    case = load_case(db, principal, case_id)
    doc = db.scalar(select(DocumentVersion).where(DocumentVersion.id == document_version_id,
                                                  DocumentVersion.case_id == case.id))
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    correction = document_service.correct_field(
        db, case=case, document=doc, name=body.name, value_text=body.value_text, value_json=body.value_json,
        page=body.page, note=body.note, user_id=principal.user.id)
    db.commit()
    from ..schemas import field_out

    return field_out(correction)


@router.post("/{case_id}/checks")
def rerun_checks(case_id: str, principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    """Re-run the deterministic checks without the agent."""
    case = load_case(db, principal, case_id)
    _, findings = run_checks(db, case)
    exceptions = sync_exceptions(db, case, findings, actor_id=principal.user.id)
    db.commit()
    return [exception_out(e) for e in exceptions]


@router.post("/{case_id}/exceptions/{exception_id}")
def resolve_exception(case_id: str, exception_id: str, body: ResolveExceptionRequest,
                      principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    ensure_roles(principal, RESOLVER_ROLES)
    case = load_case(db, principal, case_id)
    if case.status in (CaseStatus.EXPORTED.value, CaseStatus.REJECTED.value):
        raise HTTPException(status_code=409, detail=f"Case is {case.status}")
    exc = db.scalar(select(CaseException).where(CaseException.id == exception_id, CaseException.case_id == case.id))
    if exc is None:
        raise HTTPException(status_code=404, detail="Exception not found")
    if body.action == "reopen":
        exc.status = ExceptionStatus.OPEN.value
        exc.resolution_note, exc.resolved_by, exc.resolved_at = None, None, None
    else:
        if exc.code in ("BENEFICIARY_CHANGED", "BENEFICIARY_UNVERIFIED", "VENDOR_NOT_FOUND"):
            raise HTTPException(status_code=409, detail="Beneficiary and vendor exceptions can only be cleared by an "
                                                        "administrator updating and verifying the vendor register")
        exc.status = ExceptionStatus.RESOLVED.value if body.action == "resolve" else ExceptionStatus.WAIVED.value
        exc.resolution_note = body.note
        exc.resolved_by = principal.user.id
        exc.resolved_at = utcnow()
    audit.record(db, organization_id=case.organization_id, case_id=case.id, actor_id=principal.user.id,
                 event_type=f"exception_{body.action}d" if body.action != "reopen" else "exception_reopened",
                 payload={"exception_id": exc.id, "code": exc.code, "note": body.note})
    invalidate_approvals(db, case, reason=f"exception {exc.code} {body.action}d")
    db.commit()
    return exception_out(exc)


@router.post("/{case_id}/drafts/{draft_id}")
def update_draft(case_id: str, draft_id: str, body: DraftUpdateRequest,
                 principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    case = load_case(db, principal, case_id)
    draft = db.scalar(select(ClarificationDraft).where(ClarificationDraft.id == draft_id,
                                                       ClarificationDraft.case_id == case.id))
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    draft.status = body.status
    audit.record(db, organization_id=case.organization_id, case_id=case.id, actor_id=principal.user.id,
                 event_type="clarification_draft_updated", payload={"draft_id": draft.id, "status": body.status})
    db.commit()
    return draft_out(draft)


@router.post("/{case_id}/investigate", status_code=202)
def investigate(case_id: str, principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    case = load_case(db, principal, case_id)
    if case.status in (CaseStatus.EXPORTED.value, CaseStatus.REJECTED.value):
        raise HTTPException(status_code=409, detail=f"Case is {case.status}")
    run = runner.start_run(db, case, principal.user.id)
    return run_out(run)


@router.get("/{case_id}/runs")
def list_runs(case_id: str, principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    case = load_case(db, principal, case_id)
    runs = db.scalars(select(AgentRun).where(AgentRun.case_id == case.id).order_by(AgentRun.created_at))
    return [run_out(r) for r in runs]


@router.post("/{case_id}/close")
def close_case(case_id: str, principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    ensure_roles(principal, RESOLVER_ROLES)
    case = load_case(db, principal, case_id)
    if case.status == CaseStatus.EXPORTED.value:
        raise HTTPException(status_code=409, detail="Exported cases cannot be rejected")
    invalidate_approvals(db, case, reason="case rejected")
    case.status = CaseStatus.REJECTED.value
    audit.record(db, organization_id=case.organization_id, case_id=case.id, actor_id=principal.user.id,
                 event_type="case_rejected", payload={})
    db.commit()
    return case_out(case)


@router.get("/{case_id}/timeline")
def timeline(case_id: str, principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    case = load_case(db, principal, case_id)
    events = db.scalars(select(AuditEvent).where(AuditEvent.case_id == case.id).order_by(AuditEvent.created_at))
    return [audit_out(e) for e in events]
