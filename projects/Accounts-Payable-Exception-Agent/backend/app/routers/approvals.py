from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent import runner
from ..authz import Principal, load_case, require_principal
from ..db import get_db
from ..models import ApprovalRequest, Case
from ..schemas import DecisionRequest, approval_out, decision_out, instruction_out
from ..services import approvals as approval_service
from ..services import export as export_service

router = APIRouter(prefix="/orgs/{organization_id}", tags=["approvals"])


@router.get("/approvals")
def approval_queue(principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    out = []
    for request in approval_service.pending_queue(db, principal.organization_id):
        case = db.get(Case, request.case_id)
        out.append({**approval_out(request, case),
                    "can_decide": principal.role.value == "approver"
                    and principal.user.id not in (request.requested_by, case.created_by)})
    return out


@router.post("/cases/{case_id}/approvals", status_code=201)
def request_approval(case_id: str, principal: Principal = Depends(require_principal),
                     db: Session = Depends(get_db)):
    case = load_case(db, principal, case_id)
    request = approval_service.request_approval(db, case, principal)
    db.commit()
    db.refresh(request)
    return approval_out(request, case)


def _request(db: Session, case: Case, approval_id: str) -> ApprovalRequest:
    request = db.scalar(select(ApprovalRequest).where(ApprovalRequest.id == approval_id,
                                                      ApprovalRequest.case_id == case.id))
    if request is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return request


@router.post("/cases/{case_id}/approvals/{approval_id}/decision")
def decide(case_id: str, approval_id: str, body: DecisionRequest,
           principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    case = load_case(db, principal, case_id)
    request = _request(db, case, approval_id)
    decision = approval_service.decide(db, case, request, principal, decision=body.decision, note=body.note)
    db.commit()
    # Wake the investigation graph; it re-checks authority from the database before recording anything.
    run = runner.resume_run(db, case, {"approval_request_id": request.id, "decision": body.decision})
    db.commit()
    return {**decision_out(decision), "request_status": request.status, "case_status": case.status,
            "agent_run": {"id": run.id, "status": run.status, "outcome": run.outcome} if run else None}


@router.post("/cases/{case_id}/export")
def export(case_id: str, response: Response, principal: Principal = Depends(require_principal),
           db: Session = Depends(get_db)):
    case = load_case(db, principal, case_id)
    instruction, created = export_service.export_instruction(db, case, principal)
    db.commit()
    response.status_code = 201 if created else 200
    return {**instruction_out(instruction), "created": created}


@router.get("/cases/{case_id}/export")
def get_export(case_id: str, principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    case = load_case(db, principal, case_id)
    instruction = export_service.existing_instruction(db, case)
    if instruction is None:
        raise HTTPException(status_code=404, detail="No instruction exported for this case")
    return instruction_out(instruction)


@router.get("/cases/{case_id}/export/summary.txt")
def get_export_summary(case_id: str, principal: Principal = Depends(require_principal),
                       db: Session = Depends(get_db)):
    case = load_case(db, principal, case_id)
    instruction = export_service.existing_instruction(db, case)
    if instruction is None:
        raise HTTPException(status_code=404, detail="No instruction exported for this case")
    return Response(content=instruction.summary_text, media_type="text/plain")
