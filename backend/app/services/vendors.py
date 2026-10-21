"""Approved vendor register and versioned beneficiaries (administrator-managed)."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..extraction import normalize_name
from ..models import Beneficiary, Case, CaseStatus, Vendor, VerificationStatus, utcnow


def match_vendor(db: Session, organization_id: str, supplier_name: str | None,
                 vendor_code: str | None = None) -> Vendor | None:
    if vendor_code:
        vendor = db.scalar(
            select(Vendor).where(Vendor.organization_id == organization_id,
                                 Vendor.vendor_code == vendor_code, Vendor.status == "active")
        )
        if vendor:
            return vendor
    key = normalize_name(supplier_name)
    if not key:
        return None
    return db.scalar(
        select(Vendor).where(Vendor.organization_id == organization_id,
                             Vendor.normalized_name == key, Vendor.status == "active")
    )


def current_beneficiary(db: Session, vendor_id: str) -> Beneficiary | None:
    return db.scalar(
        select(Beneficiary).where(Beneficiary.vendor_id == vendor_id, Beneficiary.is_current.is_(True))
    )


def create_vendor(db: Session, *, organization_id: str, vendor_code: str, name: str,
                  tax_id: str | None, actor_id: str) -> Vendor:
    existing = db.scalar(select(Vendor).where(Vendor.organization_id == organization_id,
                                              Vendor.vendor_code == vendor_code))
    if existing:
        raise HTTPException(status_code=409, detail="Vendor code already exists")
    vendor = Vendor(organization_id=organization_id, vendor_code=vendor_code, name=name,
                    normalized_name=normalize_name(name), tax_id=tax_id)
    db.add(vendor)
    db.flush()
    audit.record(db, organization_id=organization_id, actor_id=actor_id, event_type="vendor_created",
                 payload={"vendor_id": vendor.id, "vendor_code": vendor_code, "name": name})
    return vendor


def add_beneficiary_version(db: Session, *, vendor: Vendor, account_name: str, sort_code: str | None,
                            account_number: str | None, iban: str | None, actor_id: str,
                            verified: bool = False, note: str | None = None) -> Beneficiary:
    """Create a new beneficiary version. It starts unverified unless the administrator attests
    that the out-of-band verification process has been completed."""
    latest = db.scalar(
        select(Beneficiary).where(Beneficiary.vendor_id == vendor.id).order_by(Beneficiary.version.desc())
    )
    beneficiary = Beneficiary(
        organization_id=vendor.organization_id,
        vendor_id=vendor.id,
        version=(latest.version + 1) if latest else 1,
        account_name=account_name,
        sort_code=sort_code.replace("-", "").replace(" ", "") if sort_code else None,
        account_number=account_number,
        iban=iban.replace(" ", "").upper() if iban else None,
        created_by=actor_id,
        verification_note=note,
    )
    db.add(beneficiary)
    db.flush()
    audit.record(db, organization_id=vendor.organization_id, actor_id=actor_id,
                 event_type="beneficiary_version_created",
                 payload={"vendor_id": vendor.id, "beneficiary_id": beneficiary.id,
                          "version": beneficiary.version})
    if verified:
        verify_beneficiary(db, beneficiary=beneficiary, actor_id=actor_id, note=note)
    _invalidate_open_cases_for_vendor(db, vendor, reason=f"beneficiary version {beneficiary.version} added")
    return beneficiary


def verify_beneficiary(db: Session, *, beneficiary: Beneficiary, actor_id: str,
                       note: str | None) -> Beneficiary:
    for other in db.scalars(select(Beneficiary).where(Beneficiary.vendor_id == beneficiary.vendor_id,
                                                      Beneficiary.is_current.is_(True))):
        other.is_current = False
    beneficiary.verification_status = VerificationStatus.VERIFIED.value
    beneficiary.verified_by = actor_id
    beneficiary.verified_at = utcnow()
    beneficiary.verification_note = note
    beneficiary.is_current = True
    vendor = db.get(Vendor, beneficiary.vendor_id)
    vendor.version += 1
    audit.record(db, organization_id=beneficiary.organization_id, actor_id=actor_id,
                 event_type="beneficiary_verified",
                 payload={"vendor_id": vendor.id, "beneficiary_id": beneficiary.id,
                          "version": beneficiary.version})
    _invalidate_open_cases_for_vendor(db, vendor, reason=f"beneficiary version {beneficiary.version} verified")
    return beneficiary


def _invalidate_open_cases_for_vendor(db: Session, vendor: Vendor, reason: str) -> None:
    from .approvals import invalidate_approvals

    for case in db.scalars(select(Case).where(Case.vendor_id == vendor.id,
                                              Case.status.notin_([CaseStatus.EXPORTED.value,
                                                                  CaseStatus.REJECTED.value]))):
        invalidate_approvals(db, case, reason=reason)
