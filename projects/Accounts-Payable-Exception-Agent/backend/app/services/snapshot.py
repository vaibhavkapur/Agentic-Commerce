"""Canonical approval snapshot.

An approval binds to the hash of exactly what is being approved. Any change to a document version,
amount, beneficiary, exception decision, evidence, or policy produces a different hash and therefore
invalidates the approval.
"""

import hashlib
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Case, CaseException, EvidenceLink, ExtractedField, Vendor
from .checks import load_context
from .documents import current_documents


def canonical_json(data) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(content: dict, policy_version: str, expires_at: datetime) -> str:
    envelope = {"content": content, "policy_version": policy_version,
                "expires_at": expires_at.isoformat()}
    return hashlib.sha256(canonical_json(envelope).encode()).hexdigest()


def build_snapshot_content(db: Session, case: Case) -> dict:
    ctx = load_context(db, case)
    docs = current_documents(db, case)
    corrections = list(db.scalars(
        select(ExtractedField.id).where(ExtractedField.source == "human",
                                        ExtractedField.document_version_id.in_([d.id for d in docs]))
        .order_by(ExtractedField.id)))
    exceptions = db.scalars(select(CaseException).where(CaseException.case_id == case.id)
                            .order_by(CaseException.code))
    evidence = list(db.scalars(select(EvidenceLink.id).where(EvidenceLink.case_id == case.id)
                               .order_by(EvidenceLink.id)))
    vendor = db.get(Vendor, ctx.vendor.id) if ctx.vendor else None
    total = ctx.invoice.get("total_minor")
    return {
        "organization_id": case.organization_id,
        "case_id": case.id,
        "case_reference": case.reference,
        "invoice_number": ctx.invoice.get("invoice_number"),
        "supplier_name": ctx.invoice.get("supplier_name"),
        "amount_minor": int(total) if total is not None else None,
        "currency": case.currency,
        "document_versions": [
            {"document_id": d.document_id, "version": d.version, "kind": d.kind, "sha256": d.sha256,
             "document_version_id": d.id}
            for d in docs
        ],
        "field_corrections": corrections,
        "vendor": {"id": vendor.id, "version": vendor.version, "vendor_code": vendor.vendor_code} if vendor else None,
        "beneficiary": {
            "id": ctx.beneficiary.id, "version": ctx.beneficiary.version,
            "verification_status": ctx.beneficiary.verification_status,
            "account_name": ctx.beneficiary.account_name,
            "sort_code": ctx.beneficiary.sort_code,
            "account_number": ctx.beneficiary.account_number,
            "iban": ctx.beneficiary.iban,
        } if ctx.beneficiary else None,
        "exceptions": [
            {"id": e.id, "code": e.code, "severity": e.severity, "status": e.status,
             "fingerprint": e.fingerprint, "resolved_by": e.resolved_by,
             "resolution_note": e.resolution_note}
            for e in exceptions
        ],
        "evidence_links": evidence,
    }
