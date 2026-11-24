"""Immutable document versions, extraction persistence, and human corrections."""

import hashlib
import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..extraction import ExtractionResult, extract_document, normalize_name
from ..models import (
    Case,
    CaseStatus,
    DocumentKind,
    DocumentVersion,
    ExtractedField,
)
from ..storage import Storage, document_key

SINGLE_DOCUMENT_KINDS = {
    DocumentKind.INVOICE.value,
    DocumentKind.PURCHASE_ORDER.value,
    DocumentKind.DELIVERY_CONFIRMATION.value,
}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
LOCKED_STATUSES = {CaseStatus.EXPORTED.value, CaseStatus.REJECTED.value}


def current_documents(db: Session, case: Case) -> list[DocumentVersion]:
    return list(
        db.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.case_id == case.id, DocumentVersion.is_current.is_(True))
            .order_by(DocumentVersion.created_at)
        )
    )


def current_document(db: Session, case: Case, kind: str) -> DocumentVersion | None:
    return db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.case_id == case.id,
            DocumentVersion.kind == kind,
            DocumentVersion.is_current.is_(True),
        )
    )


def effective_fields(db: Session, document_version_id: str) -> dict[str, ExtractedField]:
    """Latest claim per field name, preferring human corrections over extractor output."""
    rows = db.scalars(
        select(ExtractedField)
        .where(ExtractedField.document_version_id == document_version_id)
        .order_by(ExtractedField.revision, ExtractedField.created_at)
    )
    result: dict[str, ExtractedField] = {}
    for row in rows:
        current = result.get(row.name)
        if current is None or SOURCE_RANK[row.source] >= SOURCE_RANK[current.source]:
            result[row.name] = row
    return result


# Human corrections override agent proposals, which override the deterministic extractor.
SOURCE_RANK = {"extractor": 0, "agent_proposal": 1, "human": 2}


def field_values(fields: dict[str, ExtractedField]) -> dict:
    return {
        name: (f.value_json if f.value_json is not None else f.value_text) for name, f in fields.items()
    }


def store_document_version(
    db: Session,
    *,
    case: Case,
    kind: str,
    filename: str,
    data: bytes,
    uploaded_by: str,
    storage: Storage,
    content_type: str = "application/pdf",
) -> tuple[DocumentVersion, ExtractionResult]:
    if case.status in LOCKED_STATUSES:
        raise HTTPException(status_code=409, detail=f"Case is {case.status}; documents are frozen")
    if kind not in {k.value for k in DocumentKind}:
        raise HTTPException(status_code=422, detail=f"Unknown document kind {kind}")
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=422, detail="Only PDF uploads are supported")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Document exceeds the upload limit")

    previous = current_document(db, case, kind) if kind in SINGLE_DOCUMENT_KINDS else None
    document_id = previous.document_id if previous else str(uuid.uuid4())
    version = (previous.version + 1) if previous else 1
    if previous:
        previous.is_current = False

    doc = DocumentVersion(
        organization_id=case.organization_id,
        case_id=case.id,
        document_id=document_id,
        version=version,
        kind=kind,
        filename=filename,
        content_type=content_type,
        storage_key="",
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        uploaded_by=uploaded_by,
    )
    db.add(doc)
    db.flush()
    doc.storage_key = document_key(case.organization_id, case.id, doc.id, filename)
    storage.put(doc.storage_key, data, content_type)

    extraction = extract_document(kind, data)
    doc.page_count = len(extraction.pages)
    doc.text_pages = extraction.pages
    for claim in extraction.fields:
        db.add(
            ExtractedField(
                organization_id=case.organization_id,
                document_version_id=doc.id,
                name=claim.name,
                value_text=claim.value_text,
                value_json=claim.value_json,
                page=claim.page,
                excerpt=claim.excerpt,
                confidence=claim.confidence,
                source="extractor",
                revision=1,
            )
        )
    db.flush()

    if kind == DocumentKind.INVOICE.value:
        refresh_case_summary(db, case, doc)

    audit.record(
        db,
        organization_id=case.organization_id,
        case_id=case.id,
        actor_id=uploaded_by,
        event_type="document_uploaded",
        payload={
            "document_version_id": doc.id,
            "document_id": document_id,
            "version": version,
            "kind": kind,
            "filename": filename,
            "sha256": doc.sha256,
            "fields_extracted": len(extraction.fields),
        },
    )

    from .approvals import invalidate_approvals  # local import to avoid a cycle

    invalidate_approvals(db, case, reason=f"{kind} document version {version} uploaded")
    return doc, extraction


def refresh_case_summary(db: Session, case: Case, invoice_doc: DocumentVersion | None = None) -> None:
    invoice_doc = invoice_doc or current_document(db, case, DocumentKind.INVOICE.value)
    if invoice_doc is None:
        return
    values = field_values(effective_fields(db, invoice_doc.id))
    case.invoice_number = values.get("invoice_number")
    case.supplier_name = values.get("supplier_name")
    total = values.get("total_minor")
    case.amount_minor = int(total) if isinstance(total, int | str) and str(total).lstrip("-").isdigit() else None
    if case.title in {"", None} or case.title.startswith("Invoice "):
        case.title = f"Invoice {case.invoice_number or '?'} from {case.supplier_name or 'unknown supplier'}"


def correct_field(
    db: Session,
    *,
    case: Case,
    document: DocumentVersion,
    name: str,
    value_text: str | None,
    value_json,
    page: int | None,
    note: str | None,
    user_id: str,
) -> ExtractedField:
    if case.status in LOCKED_STATUSES:
        raise HTTPException(status_code=409, detail=f"Case is {case.status}; fields are frozen")
    if name.endswith("_minor"):
        if not (isinstance(value_json, int) or (isinstance(value_text, str) and value_text.lstrip("-").isdigit())):
            raise HTTPException(status_code=422, detail="Monetary corrections must be integer minor units")
        value_json = int(value_json if value_json is not None else value_text)
        value_text = str(value_json)
    last_revision = db.scalar(
        select(func.max(ExtractedField.revision)).where(
            ExtractedField.document_version_id == document.id, ExtractedField.name == name
        )
    ) or 0
    correction = ExtractedField(
        organization_id=case.organization_id,
        document_version_id=document.id,
        name=name,
        value_text=value_text,
        value_json=value_json,
        page=page,
        excerpt=note,
        confidence=1.0,
        source="human",
        revision=last_revision + 1,
        created_by=user_id,
    )
    db.add(correction)
    db.flush()
    if document.kind == DocumentKind.INVOICE.value:
        refresh_case_summary(db, case, document)
    audit.record(
        db,
        organization_id=case.organization_id,
        case_id=case.id,
        actor_id=user_id,
        event_type="field_corrected",
        payload={"document_version_id": document.id, "field": name, "revision": correction.revision,
                 "value": value_json if value_json is not None else value_text},
    )
    from .approvals import invalidate_approvals

    invalidate_approvals(db, case, reason=f"field '{name}' corrected")
    return correction


def supplier_key(name: str | None) -> str:
    return normalize_name(name)
