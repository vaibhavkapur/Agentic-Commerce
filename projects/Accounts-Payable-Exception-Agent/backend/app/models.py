"""Application records. Every business record carries an organization_id."""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Timezone-aware timestamps on every backend. SQLite drops tzinfo, so values are normalised to
    UTC on the way in and re-tagged as UTC on the way out."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Role(enum.StrEnum):
    ADMIN = "admin"
    AP_SPECIALIST = "ap_specialist"
    BUDGET_OWNER = "budget_owner"
    APPROVER = "approver"


class CaseStatus(enum.StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    NEEDS_INFORMATION = "needs_information"
    READY_FOR_REVIEW = "ready_for_review"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    EXPORTED = "exported"
    REJECTED = "rejected"


class DocumentKind(enum.StrEnum):
    INVOICE = "invoice"
    PURCHASE_ORDER = "purchase_order"
    DELIVERY_CONFIRMATION = "delivery_confirmation"
    OTHER = "other"


class ExceptionSeverity(enum.StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"
    INFO = "info"


class ExceptionStatus(enum.StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    WAIVED = "waived"


class ApprovalStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"


class VerificationStatus(enum.StrEnum):
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    REJECTED = "rejected"


class RunStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100), unique=True)


class Membership(Base, TimestampMixin):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    user: Mapped[User] = relationship()


class Vendor(Base, TimestampMixin):
    __tablename__ = "vendors"
    __table_args__ = (UniqueConstraint("organization_id", "vendor_code"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    vendor_code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(200), index=True)
    tax_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="active")
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow
    )


class Beneficiary(Base, TimestampMixin):
    """A versioned bank-account record for a vendor. Only administrators create versions."""

    __tablename__ = "beneficiaries"
    __table_args__ = (UniqueConstraint("vendor_id", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    account_name: Mapped[str] = mapped_column(String(200))
    sort_code: Mapped[str | None] = mapped_column(String(16))
    account_number: Mapped[str | None] = mapped_column(String(34))
    iban: Mapped[str | None] = mapped_column(String(40))
    verification_status: Mapped[str] = mapped_column(
        String(32), default=VerificationStatus.PENDING_VERIFICATION.value
    )
    verification_note: Mapped[str | None] = mapped_column(Text)
    verified_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class Case(Base, TimestampMixin):
    __tablename__ = "cases"
    __table_args__ = (UniqueConstraint("organization_id", "reference"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    reference: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(32), default=CaseStatus.OPEN.value, index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    # Derived from the current invoice version; kept here for inbox listing and duplicate checks.
    invoice_number: Mapped[str | None] = mapped_column(String(100), index=True)
    supplier_name: Mapped[str | None] = mapped_column(String(200))
    amount_minor: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="GBP")
    vendor_id: Mapped[str | None] = mapped_column(ForeignKey("vendors.id"))
    beneficiary_id: Mapped[str | None] = mapped_column(ForeignKey("beneficiaries.id"))
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow
    )


class DocumentVersion(Base, TimestampMixin):
    """Immutable stored file. Re-uploading a document creates a new version of the same document."""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version"),
        Index("ix_document_versions_case_kind", "case_id", "kind"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String(32))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100), default="application/pdf")
    storage_key: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    text_pages: Mapped[list | None] = mapped_column(JSON)  # extracted text per page, evidence only
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class ExtractedField(Base, TimestampMixin):
    """A structured claim extracted from a document version, with a page reference.

    source="extractor" rows are machine claims; source="human" rows are corrections and take
    precedence. Corrections never overwrite the original row.
    """

    __tablename__ = "extracted_fields"
    __table_args__ = (Index("ix_extracted_fields_doc_name", "document_version_id", "name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    value_text: Mapped[str | None] = mapped_column(Text)
    value_json: Mapped[dict | list | None] = mapped_column(JSON)
    page: Mapped[int | None] = mapped_column(Integer)
    excerpt: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column()
    source: Mapped[str] = mapped_column(String(32), default="extractor")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class EvidenceLink(Base, TimestampMixin):
    __tablename__ = "evidence_links"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    exception_id: Mapped[str | None] = mapped_column(ForeignKey("exceptions.id"), index=True)
    document_version_id: Mapped[str | None] = mapped_column(ForeignKey("document_versions.id"))
    record_type: Mapped[str | None] = mapped_column(String(64))  # e.g. "beneficiary"
    record_id: Mapped[str | None] = mapped_column(String(36))
    page: Mapped[int | None] = mapped_column(Integer)
    excerpt: Mapped[str | None] = mapped_column(Text)
    label: Mapped[str] = mapped_column(String(200))


class CaseException(Base, TimestampMixin):
    __tablename__ = "exceptions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=ExceptionStatus.OPEN.value)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    needs_information: Mapped[bool] = mapped_column(Boolean, default=False)
    detected_by: Mapped[str] = mapped_column(String(32), default="deterministic_check")
    agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    evidence: Mapped[list["EvidenceLink"]] = relationship(
        primaryjoin="CaseException.id == EvidenceLink.exception_id", viewonly=True
    )


class ClarificationDraft(Base, TimestampMixin):
    __tablename__ = "clarification_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"))
    recipient: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    requested_items: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    authored_by: Mapped[str] = mapped_column(String(32), default="agent")  # agent | user


class CaseComment(Base, TimestampMixin):
    __tablename__ = "case_comments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)


class ApprovalRequest(Base, TimestampMixin):
    __tablename__ = "approval_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    policy_version: Mapped[str] = mapped_column(String(64))
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(16), default=ApprovalStatus.PENDING.value)
    invalidation_reason: Mapped[str | None] = mapped_column(Text)
    decisions: Mapped[list["ApprovalDecision"]] = relationship(back_populates="request")


class ApprovalDecision(Base, TimestampMixin):
    __tablename__ = "approval_decisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    approval_request_id: Mapped[str] = mapped_column(
        ForeignKey("approval_requests.id"), index=True
    )
    decided_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(16))  # approve | reject
    note: Mapped[str | None] = mapped_column(Text)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[ApprovalRequest] = relationship(back_populates="decisions")


class PaymentInstruction(Base, TimestampMixin):
    __tablename__ = "payment_instructions"
    __table_args__ = (UniqueConstraint("approval_request_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    approval_request_id: Mapped[str] = mapped_column(ForeignKey("approval_requests.id"))
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    audit_reference: Mapped[str] = mapped_column(String(64), unique=True)
    instruction: Mapped[dict] = mapped_column(JSON)
    summary_text: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class AgentRun(Base, TimestampMixin):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    thread_id: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(16), default=RunStatus.QUEUED.value)
    started_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    model_name: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    model_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    trace: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(String(64))
    pending_resume: Mapped[dict | None] = mapped_column(JSON)  # set by the API in worker mode
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class AuditEvent(Base, TimestampMixin):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_case_created", "case_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"), index=True)
    actor_type: Mapped[str] = mapped_column(String(16))  # user | agent | system
    actor_id: Mapped[str | None] = mapped_column(String(36))
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
