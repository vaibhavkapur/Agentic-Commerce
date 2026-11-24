"""Version-bound approvals with separation of duties and freshness checks."""

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..authz import Principal
from ..config import get_settings
from ..models import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    Case,
    CaseStatus,
    Role,
    VerificationStatus,
    utcnow,
)
from .checks import open_blocking, run_checks, sync_exceptions
from .snapshot import build_snapshot_content, compute_hash

ACTIVE_STATUSES = (ApprovalStatus.PENDING.value, ApprovalStatus.APPROVED.value)


def invalidate_approvals(db: Session, case: Case, *, reason: str) -> int:
    """Invalidate pending and approved-but-not-exported requests after a relevant change."""
    if case.status == CaseStatus.EXPORTED.value:
        return 0
    requests = list(db.scalars(select(ApprovalRequest).where(
        ApprovalRequest.case_id == case.id, ApprovalRequest.status.in_(ACTIVE_STATUSES))))
    for request in requests:
        request.status = ApprovalStatus.INVALIDATED.value
        request.invalidation_reason = reason
        audit.record(db, organization_id=case.organization_id, case_id=case.id, actor_type="system",
                     event_type="approval_invalidated",
                     payload={"approval_request_id": request.id, "reason": reason,
                              "snapshot_hash": request.snapshot_hash})
    if requests and case.status in (CaseStatus.PENDING_APPROVAL.value, CaseStatus.APPROVED.value,
                                    CaseStatus.READY_FOR_REVIEW.value):
        case.status = CaseStatus.INVESTIGATING.value
    return len(requests)


def current_hash(db: Session, case: Case, request: ApprovalRequest) -> str:
    content = build_snapshot_content(db, case)
    return compute_hash(content, request.policy_version, request.expires_at)


def request_approval(db: Session, case: Case, principal: Principal) -> ApprovalRequest:
    settings = get_settings()
    if case.status in (CaseStatus.EXPORTED.value, CaseStatus.REJECTED.value):
        raise HTTPException(status_code=409, detail=f"Case is {case.status}")

    # Always re-run the deterministic checks so the approval reflects current evidence.
    ctx, findings = run_checks(db, case)
    sync_exceptions(db, case, findings, actor_id=principal.user.id)
    blockers = open_blocking(db, case)
    if blockers:
        raise HTTPException(status_code=409, detail={
            "message": "Unresolved blocking exceptions prevent approval",
            "blockers": [{"id": b.id, "code": b.code, "title": b.title} for b in blockers],
        })
    if ctx.beneficiary is None or ctx.beneficiary.verification_status != VerificationStatus.VERIFIED.value:
        raise HTTPException(status_code=409, detail="Vendor has no verified beneficiary")
    if ctx.invoice.get("total_minor") in (None, "") or int(ctx.invoice["total_minor"]) <= 0:
        raise HTTPException(status_code=409, detail="Invoice amount is not established")

    content = build_snapshot_content(db, case)
    existing = db.scalar(select(ApprovalRequest).where(
        ApprovalRequest.case_id == case.id, ApprovalRequest.status == ApprovalStatus.PENDING.value))
    if existing and existing.expires_at > utcnow():
        if compute_hash(content, existing.policy_version, existing.expires_at) == existing.snapshot_hash:
            return existing  # idempotent replay
        existing.status = ApprovalStatus.INVALIDATED.value
        existing.invalidation_reason = "superseded by a new approval request"

    expires_at = utcnow() + timedelta(hours=settings.approval_ttl_hours)
    request = ApprovalRequest(
        organization_id=case.organization_id, case_id=case.id,
        snapshot_hash=compute_hash(content, settings.approval_policy_version, expires_at),
        snapshot=content, policy_version=settings.approval_policy_version,
        requested_by=principal.user.id, expires_at=expires_at,
    )
    db.add(request)
    db.flush()
    case.status = CaseStatus.PENDING_APPROVAL.value
    audit.record(db, organization_id=case.organization_id, case_id=case.id, actor_id=principal.user.id,
                 event_type="approval_requested",
                 payload={"approval_request_id": request.id, "snapshot_hash": request.snapshot_hash,
                          "amount_minor": content["amount_minor"], "expires_at": expires_at.isoformat()})
    return request


def decide(db: Session, case: Case, request: ApprovalRequest, principal: Principal, *, decision: str,
           note: str | None) -> ApprovalDecision:
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=422, detail="decision must be 'approve' or 'reject'")
    if not principal.has_role(Role.APPROVER):
        raise HTTPException(status_code=403, detail="Only approvers can decide approval requests")
    if principal.user.id in (request.requested_by, case.created_by):
        raise HTTPException(status_code=403, detail="Separation of duties: the submitter cannot approve "
                                                    "their own request")
    if request.case_id != case.id:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if request.status != ApprovalStatus.PENDING.value:
        replay = next((d for d in request.decisions
                       if d.decided_by == principal.user.id and d.decision == decision), None)
        if replay:
            return replay  # idempotent replay of the same decision
        raise HTTPException(status_code=409, detail=f"Approval request is {request.status}")
    if request.expires_at <= utcnow():
        request.status = ApprovalStatus.EXPIRED.value
        case.status = CaseStatus.INVESTIGATING.value
        raise HTTPException(status_code=409, detail="Approval request has expired")
    if current_hash(db, case, request) != request.snapshot_hash:
        invalidate_approvals(db, case, reason="case changed since approval was requested")
        raise HTTPException(status_code=409, detail="Case changed since approval was requested; request a "
                                                    "new approval")

    record = ApprovalDecision(organization_id=case.organization_id, approval_request_id=request.id,
                              decided_by=principal.user.id, decision=decision, note=note,
                              snapshot_hash=request.snapshot_hash)
    db.add(record)
    if decision == "approve":
        request.status = ApprovalStatus.APPROVED.value
        case.status = CaseStatus.APPROVED.value
    else:
        request.status = ApprovalStatus.REJECTED.value
        case.status = CaseStatus.INVESTIGATING.value
    audit.record(db, organization_id=case.organization_id, case_id=case.id, actor_id=principal.user.id,
                 event_type=f"approval_{decision}d" if decision == "approve" else "approval_rejected",
                 payload={"approval_request_id": request.id, "snapshot_hash": request.snapshot_hash,
                          "note": note})
    return record


def pending_queue(db: Session, organization_id: str) -> list[ApprovalRequest]:
    return list(db.scalars(select(ApprovalRequest).where(
        ApprovalRequest.organization_id == organization_id,
        ApprovalRequest.status == ApprovalStatus.PENDING.value).order_by(ApprovalRequest.created_at)))
