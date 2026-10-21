from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..authz import Principal, require_principal, require_roles
from ..db import get_db
from ..models import AuditEvent, Beneficiary, Membership, Role, User, Vendor
from ..schemas import (
    BeneficiaryRequest,
    CreateVendorRequest,
    MembershipRequest,
    VerifyBeneficiaryRequest,
    audit_out,
    beneficiary_out,
    membership_out,
    vendor_out,
)
from ..services import vendors as vendor_service

router = APIRouter(prefix="/orgs/{organization_id}", tags=["organization"])


@router.get("/members")
def list_members(principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    rows = db.scalars(select(Membership).where(Membership.organization_id == principal.organization_id))
    return [membership_out(m) for m in rows]


@router.post("/members", status_code=201)
def add_member(body: MembershipRequest, principal: Principal = Depends(require_roles(Role.ADMIN)),
               db: Session = Depends(get_db)):
    email = body.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, display_name=body.display_name or email.split("@")[0])
        db.add(user)
        db.flush()
    existing = db.scalar(select(Membership).where(Membership.organization_id == principal.organization_id,
                                                  Membership.user_id == user.id))
    if existing:
        existing.role = body.role
        membership = existing
    else:
        membership = Membership(organization_id=principal.organization_id, user_id=user.id, role=body.role)
        db.add(membership)
    audit.record(db, organization_id=principal.organization_id, actor_id=principal.user.id,
                 event_type="membership_changed", payload={"user_id": user.id, "role": body.role})
    db.commit()
    db.refresh(membership)
    return membership_out(membership)


@router.get("/events")
def recent_events(since: datetime | None = Query(default=None), limit: int = Query(default=100, le=500),
                  principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    """Recent audit events for live inbox and approval-queue updates (poll-based; Supabase Realtime
    can replace this when the frontend reads directly from PostgreSQL under RLS)."""
    query = select(AuditEvent).where(AuditEvent.organization_id == principal.organization_id)
    if since is not None:
        query = query.where(AuditEvent.created_at > since)
    events = db.scalars(query.order_by(AuditEvent.created_at.desc()).limit(limit)).all()
    return [audit_out(e) for e in reversed(events)]


@router.get("/vendors")
def list_vendors(principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    vendors = db.scalars(select(Vendor).where(Vendor.organization_id == principal.organization_id)
                         .order_by(Vendor.name))
    out = []
    for vendor in vendors:
        beneficiaries = list(db.scalars(select(Beneficiary).where(Beneficiary.vendor_id == vendor.id)
                                        .order_by(Beneficiary.version)))
        out.append(vendor_out(vendor, beneficiaries))
    return out


@router.post("/vendors", status_code=201)
def create_vendor(body: CreateVendorRequest, principal: Principal = Depends(require_roles(Role.ADMIN)),
                  db: Session = Depends(get_db)):
    vendor = vendor_service.create_vendor(db, organization_id=principal.organization_id,
                                          vendor_code=body.vendor_code, name=body.name, tax_id=body.tax_id,
                                          actor_id=principal.user.id)
    db.commit()
    return vendor_out(vendor, [])


def _vendor(db: Session, principal: Principal, vendor_id: str) -> Vendor:
    vendor = db.scalar(select(Vendor).where(Vendor.id == vendor_id,
                                            Vendor.organization_id == principal.organization_id))
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return vendor


@router.post("/vendors/{vendor_id}/beneficiaries", status_code=201)
def add_beneficiary(vendor_id: str, body: BeneficiaryRequest,
                    principal: Principal = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    vendor = _vendor(db, principal, vendor_id)
    if not (body.iban or (body.sort_code and body.account_number)):
        raise HTTPException(status_code=422, detail="Provide an IBAN or a sort code and account number")
    beneficiary = vendor_service.add_beneficiary_version(
        db, vendor=vendor, account_name=body.account_name, sort_code=body.sort_code,
        account_number=body.account_number, iban=body.iban, actor_id=principal.user.id,
        verified=body.verified, note=body.note)
    db.commit()
    return beneficiary_out(beneficiary)


@router.post("/vendors/{vendor_id}/beneficiaries/{beneficiary_id}/verify")
def verify_beneficiary(vendor_id: str, beneficiary_id: str, body: VerifyBeneficiaryRequest,
                       principal: Principal = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    vendor = _vendor(db, principal, vendor_id)
    beneficiary = db.scalar(select(Beneficiary).where(Beneficiary.id == beneficiary_id,
                                                      Beneficiary.vendor_id == vendor.id))
    if beneficiary is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    vendor_service.verify_beneficiary(db, beneficiary=beneficiary, actor_id=principal.user.id, note=body.note)
    db.commit()
    return beneficiary_out(beneficiary)
