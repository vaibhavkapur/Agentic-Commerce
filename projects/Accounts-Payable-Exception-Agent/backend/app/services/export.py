"""Idempotent export of an approved payment instruction.

The export revalidates the approved snapshot against the current state of the case before emitting
anything. Repeating the request for the same approval returns the original instruction.
"""

import secrets

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit
from ..authz import Principal
from ..models import (
    ApprovalRequest,
    ApprovalStatus,
    Beneficiary,
    Case,
    CaseStatus,
    PaymentInstruction,
    Role,
    User,
    VerificationStatus,
    utcnow,
)
from ..money import format_minor
from .approvals import current_hash, invalidate_approvals
from .checks import open_blocking

EXPORT_ROLES = (Role.AP_SPECIALIST, Role.APPROVER, Role.ADMIN)


def approved_request(db: Session, case: Case) -> ApprovalRequest | None:
    return db.scalar(select(ApprovalRequest).where(
        ApprovalRequest.case_id == case.id, ApprovalRequest.status == ApprovalStatus.APPROVED.value)
        .order_by(ApprovalRequest.created_at.desc()))


def existing_instruction(db: Session, case: Case) -> PaymentInstruction | None:
    return db.scalar(select(PaymentInstruction).where(PaymentInstruction.case_id == case.id))


def export_instruction(db: Session, case: Case, principal: Principal) -> tuple[PaymentInstruction, bool]:
    """Returns (instruction, created). created=False means an identical earlier export was returned."""
    if not principal.has_role(*EXPORT_ROLES):
        raise HTTPException(status_code=403, detail="Not permitted to export instructions")

    already = existing_instruction(db, case)
    if already:
        return already, False

    request = approved_request(db, case)
    if request is None:
        raise HTTPException(status_code=409, detail="Case has no approved snapshot")

    # Revalidate the approved snapshot against current authority.
    if request.expires_at <= utcnow():
        request.status = ApprovalStatus.EXPIRED.value
        case.status = CaseStatus.INVESTIGATING.value
        raise HTTPException(status_code=409, detail="Approval has expired; request a new approval")
    if current_hash(db, case, request) != request.snapshot_hash:
        invalidate_approvals(db, case, reason="case changed after approval")
        raise HTTPException(status_code=409, detail="Case changed after approval; the new snapshot must be "
                                                    "approved before export")
    blockers = open_blocking(db, case)
    if blockers:
        invalidate_approvals(db, case, reason="blocking exceptions present at export")
        raise HTTPException(status_code=409, detail={"message": "Unresolved blocking exceptions prevent export",
                                                     "blockers": [b.code for b in blockers]})
    snapshot = request.snapshot
    beneficiary = db.get(Beneficiary, snapshot["beneficiary"]["id"]) if snapshot.get("beneficiary") else None
    if (beneficiary is None or not beneficiary.is_current
            or beneficiary.verification_status != VerificationStatus.VERIFIED.value
            or beneficiary.version != snapshot["beneficiary"]["version"]):
        invalidate_approvals(db, case, reason="approved beneficiary is no longer current")
        raise HTTPException(status_code=409, detail="Approved beneficiary is no longer the current verified "
                                                    "record; the case must be reviewed again")

    approval = next(d for d in request.decisions if d.decision == "approve")
    approver = db.get(User, approval.decided_by)
    audit_reference = f"API-{utcnow():%Y%m%d}-{secrets.token_hex(4).upper()}"
    instruction = {
        "schema": "ap-payment-instruction/v1",
        "audit_reference": audit_reference,
        "organization_id": case.organization_id,
        "case_id": case.id,
        "case_reference": case.reference,
        "invoice_number": snapshot["invoice_number"],
        "supplier_name": snapshot["supplier_name"],
        "amount_minor": snapshot["amount_minor"],
        "amount": format_minor(snapshot["amount_minor"], snapshot["currency"]),
        "currency": snapshot["currency"],
        "beneficiary": {
            "id": beneficiary.id, "version": beneficiary.version, "account_name": beneficiary.account_name,
            "sort_code": beneficiary.sort_code, "account_number": beneficiary.account_number,
            "iban": beneficiary.iban,
        },
        "approval": {
            "request_id": request.id, "snapshot_hash": request.snapshot_hash,
            "policy_version": request.policy_version, "requested_by": request.requested_by,
            "approved_by": approval.decided_by, "approved_at": approval.created_at.isoformat(),
            "expires_at": request.expires_at.isoformat(),
        },
        "evidence": snapshot["document_versions"],
        "exception_decisions": [e for e in snapshot["exceptions"] if e["status"] != "open"],
        "exported_by": principal.user.id,
        "exported_at": utcnow().isoformat(),
    }
    summary = "\n".join([
        f"Payment instruction {audit_reference}",
        f"Case {case.reference}: invoice {snapshot['invoice_number']} from {snapshot['supplier_name']}",
        f"Amount: {instruction['amount']}",
        f"Pay to: {beneficiary.account_name} (beneficiary version {beneficiary.version}, "
        f"sort code {beneficiary.sort_code or '-'}, account {beneficiary.account_number or '-'}, "
        f"IBAN {beneficiary.iban or '-'})",
        f"Approved by {approver.display_name if approver else approval.decided_by} on "
        f"{approval.created_at:%Y-%m-%d %H:%M} under policy {request.policy_version}",
        f"Snapshot {request.snapshot_hash[:16]}… covering {len(snapshot['document_versions'])} document version(s) "
        f"and {len(instruction['exception_decisions'])} resolved exception(s)",
    ])
    record = PaymentInstruction(organization_id=case.organization_id, case_id=case.id,
                                approval_request_id=request.id, snapshot_hash=request.snapshot_hash,
                                audit_reference=audit_reference, instruction=instruction,
                                summary_text=summary, created_by=principal.user.id)
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return existing_instruction(db, case), False
    case.status = CaseStatus.EXPORTED.value
    audit.record(db, organization_id=case.organization_id, case_id=case.id, actor_id=principal.user.id,
                 event_type="instruction_exported",
                 payload={"payment_instruction_id": record.id, "audit_reference": audit_reference,
                          "approval_request_id": request.id, "amount_minor": snapshot["amount_minor"]})
    return record, True
