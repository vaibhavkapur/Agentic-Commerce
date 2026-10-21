"""Deterministic exception checks. These run in ordinary application code, never in the model.

Each finding cites the document version and page (or the register record) that supports it.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..extraction import normalize_name
from ..models import (
    Beneficiary,
    Case,
    CaseException,
    CaseStatus,
    DocumentKind,
    DocumentVersion,
    EvidenceLink,
    ExceptionSeverity,
    ExceptionStatus,
    Vendor,
    VerificationStatus,
    utcnow,
)
from ..money import format_minor
from .documents import current_document, effective_fields, field_values
from .vendors import current_beneficiary, match_vendor


@dataclass
class EvidenceRef:
    label: str
    document_version_id: str | None = None
    page: int | None = None
    excerpt: str | None = None
    record_type: str | None = None
    record_id: str | None = None

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class Finding:
    code: str
    severity: str
    title: str
    detail: str
    evidence: list[EvidenceRef] = field(default_factory=list)
    needs_information: bool = False
    facts: dict = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        payload = json.dumps({"code": self.code, "facts": self.facts}, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class CaseContext:
    case: Case
    invoice_doc: DocumentVersion | None
    po_doc: DocumentVersion | None
    delivery_doc: DocumentVersion | None
    invoice: dict
    po: dict
    delivery: dict
    vendor: Vendor | None
    beneficiary: Beneficiary | None
    invoice_fields: dict


INJECTION_PATTERNS = [
    r"ignore (?:all )?(?:previous|prior) instructions",
    r"\bsystem\s*:",
    r"\bassistant\s*:",
    r"approve (?:this|the) (?:invoice|payment) immediately",
    r"update (?:the )?(?:vendor|beneficiary|bank) (?:record|details)",
    r"you are (?:now )?an? ",
    r"do not (?:flag|report|raise)",
]


def load_context(db: Session, case: Case) -> CaseContext:
    invoice_doc = current_document(db, case, DocumentKind.INVOICE.value)
    po_doc = current_document(db, case, DocumentKind.PURCHASE_ORDER.value)
    delivery_doc = current_document(db, case, DocumentKind.DELIVERY_CONFIRMATION.value)
    invoice_fields = effective_fields(db, invoice_doc.id) if invoice_doc else {}
    invoice = field_values(invoice_fields)
    po = field_values(effective_fields(db, po_doc.id)) if po_doc else {}
    delivery = field_values(effective_fields(db, delivery_doc.id)) if delivery_doc else {}
    vendor = match_vendor(db, case.organization_id, invoice.get("supplier_name"), po.get("vendor_code"))
    beneficiary = current_beneficiary(db, vendor.id) if vendor else None
    case.vendor_id = vendor.id if vendor else None
    case.beneficiary_id = beneficiary.id if beneficiary else None
    return CaseContext(case, invoice_doc, po_doc, delivery_doc, invoice, po, delivery, vendor,
                       beneficiary, invoice_fields)


def _doc_ref(ctx_fields: dict, doc: DocumentVersion | None, name: str, label: str) -> EvidenceRef:
    claim = ctx_fields.get(name)
    return EvidenceRef(label=label, document_version_id=doc.id if doc else None,
                       page=claim.page if claim else None, excerpt=claim.excerpt if claim else None)


def _as_int(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return None


def run_checks(db: Session, case: Case) -> tuple[CaseContext, list[Finding]]:
    ctx = load_context(db, case)
    findings: list[Finding] = []
    if ctx.invoice_doc is None:
        findings.append(Finding("INVOICE_MISSING", ExceptionSeverity.BLOCKING.value,
                                "No invoice uploaded", "The case has no invoice document.",
                                needs_information=True))
        return ctx, findings

    findings += _check_injection(ctx)
    findings += _check_required_fields(ctx)
    findings += _check_totals(ctx)
    findings += _check_vendor(db, ctx)
    findings += _check_duplicate(db, ctx)
    findings += _check_purchase_order(ctx)
    findings += _check_delivery(ctx)
    findings += _check_beneficiary(ctx)
    return ctx, findings


def _check_injection(ctx: CaseContext) -> list[Finding]:
    """Document text is evidence, not instruction. Flag text that looks like it is addressing the
    agent so a reviewer sees it; nothing else in the pipeline ever acts on it."""
    hits = []
    for doc in (ctx.invoice_doc, ctx.po_doc, ctx.delivery_doc):
        if doc is None or not doc.text_pages:
            continue
        for page_no, text in enumerate(doc.text_pages, start=1):
            for line in text.splitlines():
                if any(re.search(p, line, re.IGNORECASE) for p in INJECTION_PATTERNS):
                    hits.append(EvidenceRef(label=f"Suspicious text in {doc.kind}", document_version_id=doc.id,
                                            page=page_no, excerpt=line.strip()[:300]))
    if not hits:
        return []
    return [Finding(
        "SUSPICIOUS_DOCUMENT_TEXT", ExceptionSeverity.INFO.value,
        "Document contains instruction-like text",
        "A document contains text that reads like an instruction to the reviewer or the agent. Document "
        "content is treated as evidence only; it has no effect on checks, permissions, or approvals.",
        evidence=hits[:5],
        facts={"hits": [h.excerpt for h in hits], "docs": sorted({h.document_version_id for h in hits})},
    )]


def _check_required_fields(ctx: CaseContext) -> list[Finding]:
    missing = [name for name in ("invoice_number", "supplier_name", "total_minor") if ctx.invoice.get(name) in (None, "")]
    if not missing:
        return []
    return [Finding(
        "INVOICE_FIELDS_MISSING", ExceptionSeverity.BLOCKING.value,
        "Invoice is missing required fields",
        f"Could not determine: {', '.join(missing)}. Correct the extracted fields or upload a clearer copy.",
        evidence=[EvidenceRef(label="Invoice", document_version_id=ctx.invoice_doc.id, page=1)],
        needs_information=True, facts={"missing": missing, "doc": ctx.invoice_doc.id},
    )]


def _check_totals(ctx: CaseContext) -> list[Finding]:
    inv = ctx.invoice
    lines = inv.get("line_items") or []
    subtotal, vat, total = _as_int(inv.get("subtotal_minor")), _as_int(inv.get("vat_minor")), _as_int(inv.get("total_minor"))
    problems = []
    for line in lines:
        expected = int(line["quantity"]) * int(line["unit_price_minor"])
        if expected != int(line["line_total_minor"]):
            problems.append(f"'{line['description']}': {line['quantity']} x {format_minor(line['unit_price_minor'])} "
                            f"= {format_minor(expected)}, invoice shows {format_minor(line['line_total_minor'])}")
    if lines and subtotal is not None:
        line_sum = sum(int(line["line_total_minor"]) for line in lines)
        if line_sum != subtotal:
            problems.append(f"line items sum to {format_minor(line_sum)} but subtotal is {format_minor(subtotal)}")
    if subtotal is not None and total is not None:
        if subtotal + (vat or 0) != total:
            problems.append(f"subtotal {format_minor(subtotal)} + VAT {format_minor(vat or 0)} = "
                            f"{format_minor(subtotal + (vat or 0))}, invoice total is {format_minor(total)}")
    if total is not None and total <= 0:
        problems.append("invoice total is not positive")
    if not problems:
        return []
    return [Finding(
        "TOTAL_MISMATCH", ExceptionSeverity.BLOCKING.value, "Invoice totals are inconsistent",
        "; ".join(problems) + ".",
        evidence=[_doc_ref(ctx.invoice_fields, ctx.invoice_doc, "total_minor", "Invoice total"),
                  _doc_ref(ctx.invoice_fields, ctx.invoice_doc, "line_items", "Invoice line items")],
        facts={"problems": problems, "doc": ctx.invoice_doc.id},
    )]


def _check_vendor(db: Session, ctx: CaseContext) -> list[Finding]:
    if ctx.vendor is not None:
        return []
    return [Finding(
        "VENDOR_NOT_FOUND", ExceptionSeverity.BLOCKING.value, "Supplier is not an approved vendor",
        f"No active vendor record matches supplier '{ctx.invoice.get('supplier_name')}'. An administrator "
        "must onboard the vendor and verify its beneficiary before payment.",
        evidence=[_doc_ref(ctx.invoice_fields, ctx.invoice_doc, "supplier_name", "Invoice supplier")],
        facts={"supplier": normalize_name(ctx.invoice.get("supplier_name"))},
    )]


def _check_duplicate(db: Session, ctx: CaseContext) -> list[Finding]:
    invoice_number = ctx.invoice.get("invoice_number")
    if not invoice_number:
        return []
    supplier_key = normalize_name(ctx.invoice.get("supplier_name"))
    candidates = db.scalars(
        select(Case).where(Case.organization_id == ctx.case.organization_id, Case.id != ctx.case.id,
                           Case.invoice_number == invoice_number,
                           Case.status != CaseStatus.REJECTED.value)
    )
    # The earlier case is treated as the original; later submissions of the same invoice are the
    # duplicates. A case that has already been approved or exported always counts.
    duplicates = [c for c in candidates
                  if ((ctx.vendor and c.vendor_id == ctx.vendor.id)
                      or normalize_name(c.supplier_name) == supplier_key)
                  and (c.created_at <= ctx.case.created_at
                       or c.status in (CaseStatus.APPROVED.value, CaseStatus.EXPORTED.value))]
    if not duplicates:
        return []
    refs = ", ".join(f"{c.reference} ({c.status})" for c in duplicates)
    return [Finding(
        "DUPLICATE_INVOICE", ExceptionSeverity.BLOCKING.value, "Possible duplicate invoice",
        f"Invoice {invoice_number} from this supplier already exists in case(s): {refs}.",
        evidence=[_doc_ref(ctx.invoice_fields, ctx.invoice_doc, "invoice_number", "Invoice number")]
        + [EvidenceRef(label=f"Existing case {c.reference}", record_type="case", record_id=c.id) for c in duplicates],
        facts={"invoice_number": invoice_number, "cases": sorted(c.id for c in duplicates)},
    )]


def _check_purchase_order(ctx: CaseContext) -> list[Finding]:
    out = []
    po_ref = ctx.invoice.get("po_number")
    if ctx.po_doc is None:
        out.append(Finding(
            "PO_MISSING", ExceptionSeverity.BLOCKING.value, "Purchase order not on file",
            (f"The invoice references purchase order {po_ref}, but no purchase order document has been uploaded."
             if po_ref else "The invoice does not reference a purchase order and none has been uploaded."),
            evidence=[_doc_ref(ctx.invoice_fields, ctx.invoice_doc, "po_number", "Invoice PO reference")]
            if po_ref else [],
            needs_information=True, facts={"po_ref": po_ref},
        ))
        return out
    po = ctx.po
    if po_ref and po.get("po_number") and po_ref != po.get("po_number"):
        out.append(Finding(
            "PO_NUMBER_MISMATCH", ExceptionSeverity.BLOCKING.value, "Invoice references a different purchase order",
            f"Invoice cites {po_ref}; the uploaded purchase order is {po.get('po_number')}.",
            evidence=[_doc_ref(ctx.invoice_fields, ctx.invoice_doc, "po_number", "Invoice PO reference"),
                      EvidenceRef(label="Purchase order number", document_version_id=ctx.po_doc.id, page=1)],
            facts={"invoice_po": po_ref, "po": po.get("po_number")},
        ))
    if po.get("supplier_name") and normalize_name(po["supplier_name"]) != normalize_name(ctx.invoice.get("supplier_name")):
        out.append(Finding(
            "PO_SUPPLIER_MISMATCH", ExceptionSeverity.BLOCKING.value, "Purchase order is for a different supplier",
            f"Invoice supplier '{ctx.invoice.get('supplier_name')}' differs from PO supplier '{po['supplier_name']}'.",
            evidence=[_doc_ref(ctx.invoice_fields, ctx.invoice_doc, "supplier_name", "Invoice supplier"),
                      EvidenceRef(label="PO supplier", document_version_id=ctx.po_doc.id, page=1)],
            facts={"invoice_supplier": normalize_name(ctx.invoice.get("supplier_name")),
                   "po_supplier": normalize_name(po["supplier_name"])},
        ))
    # Purchase orders are net of VAT, so compare the invoice net amount (subtotal) when it is known.
    inv_net = _as_int(ctx.invoice.get("subtotal_minor"))
    net_field = "subtotal_minor"
    if inv_net is None:
        inv_net, net_field = _as_int(ctx.invoice.get("total_minor")), "total_minor"
    po_total = _as_int(po.get("total_minor"))
    if inv_net is not None and po_total is not None and inv_net > po_total:
        out.append(Finding(
            "PO_AMOUNT_EXCEEDED", ExceptionSeverity.BLOCKING.value, "Invoice exceeds purchase order",
            f"Invoice net amount {format_minor(inv_net)} exceeds purchase order total {format_minor(po_total)} "
            f"by {format_minor(inv_net - po_total)}.",
            evidence=[_doc_ref(ctx.invoice_fields, ctx.invoice_doc, net_field, "Invoice net amount"),
                      EvidenceRef(label="PO total", document_version_id=ctx.po_doc.id, page=1,
                                  excerpt=f"PO total {format_minor(po_total)}")],
            facts={"invoice_net": inv_net, "po_total": po_total},
        ))
    po_lines = {normalize_name(line["description"]): line for line in (po.get("line_items") or [])}
    mismatches = []
    for line in ctx.invoice.get("line_items") or []:
        key = normalize_name(line["description"])
        match = po_lines.get(key)
        if match is None:
            mismatches.append(f"'{line['description']}' is not on the purchase order")
        else:
            if int(line["quantity"]) > int(match["quantity"]):
                mismatches.append(f"'{line['description']}' invoiced {line['quantity']} vs ordered {match['quantity']}")
            if int(line["unit_price_minor"]) != int(match["unit_price_minor"]):
                mismatches.append(f"'{line['description']}' priced {format_minor(line['unit_price_minor'])} vs "
                                  f"PO {format_minor(match['unit_price_minor'])}")
    if mismatches:
        out.append(Finding(
            "PO_LINE_MISMATCH", ExceptionSeverity.WARNING.value, "Invoice lines differ from purchase order",
            "; ".join(mismatches) + ".",
            evidence=[_doc_ref(ctx.invoice_fields, ctx.invoice_doc, "line_items", "Invoice line items"),
                      EvidenceRef(label="PO line items", document_version_id=ctx.po_doc.id, page=1)],
            facts={"mismatches": mismatches},
        ))
    return out


def _check_delivery(ctx: CaseContext) -> list[Finding]:
    if ctx.delivery_doc is None:
        return [Finding(
            "DELIVERY_MISSING", ExceptionSeverity.BLOCKING.value, "No delivery confirmation",
            "There is no evidence that the goods or services were received. Ask the budget owner for a "
            "signed delivery note or goods-received confirmation.",
            needs_information=True, facts={},
        )]
    delivered = {normalize_name(line["description"]): int(line["quantity"])
                 for line in (ctx.delivery.get("line_items") or [])}
    shortfalls = []
    for line in ctx.invoice.get("line_items") or []:
        got = delivered.get(normalize_name(line["description"]), 0)
        if got < int(line["quantity"]):
            shortfalls.append(f"'{line['description']}': invoiced {line['quantity']}, delivered {got}")
    out = []
    po_ref = ctx.invoice.get("po_number")
    if po_ref and ctx.delivery.get("po_number") and ctx.delivery["po_number"] != po_ref:
        out.append(Finding(
            "DELIVERY_PO_MISMATCH", ExceptionSeverity.WARNING.value, "Delivery note cites a different purchase order",
            f"Delivery note references {ctx.delivery['po_number']}; invoice references {po_ref}.",
            evidence=[EvidenceRef(label="Delivery note PO", document_version_id=ctx.delivery_doc.id, page=1)],
            facts={"delivery_po": ctx.delivery["po_number"], "invoice_po": po_ref},
        ))
    if shortfalls:
        out.append(Finding(
            "DELIVERY_INCOMPLETE", ExceptionSeverity.BLOCKING.value, "Delivery is incomplete",
            "; ".join(shortfalls) + ". Pay only for what was received, or wait for the remaining delivery.",
            evidence=[EvidenceRef(label="Delivered quantities", document_version_id=ctx.delivery_doc.id, page=1),
                      _doc_ref(ctx.invoice_fields, ctx.invoice_doc, "line_items", "Invoice line items")],
            facts={"shortfalls": shortfalls, "delivery_doc": ctx.delivery_doc.id},
        ))
    return out


def _check_beneficiary(ctx: CaseContext) -> list[Finding]:
    if ctx.vendor is None:
        return []
    inv = ctx.invoice
    invoice_bank = {
        "sort_code": (inv.get("bank_sort_code") or "").replace("-", "") or None,
        "account_number": inv.get("bank_account_number") or None,
        "iban": (inv.get("bank_iban") or "").replace(" ", "").upper() or None,
    }
    bene = ctx.beneficiary
    if bene is None or bene.verification_status != VerificationStatus.VERIFIED.value:
        return [Finding(
            "BENEFICIARY_UNVERIFIED", ExceptionSeverity.BLOCKING.value, "Vendor has no verified beneficiary",
            "The approved vendor record has no verified bank account. An administrator must complete "
            "beneficiary verification before this invoice can be paid.",
            evidence=[EvidenceRef(label="Vendor record", record_type="vendor", record_id=ctx.vendor.id)],
            facts={"vendor": ctx.vendor.id},
        )]
    if not any(invoice_bank.values()):
        return []
    differs, compared = [], 0
    if invoice_bank["iban"] and bene.iban:
        compared += 1
        if invoice_bank["iban"] != bene.iban:
            differs.append("IBAN")
    if invoice_bank["sort_code"] and bene.sort_code:
        compared += 1
        if invoice_bank["sort_code"] != bene.sort_code:
            differs.append("sort code")
    if invoice_bank["account_number"] and bene.account_number:
        compared += 1
        if invoice_bank["account_number"] != bene.account_number:
            differs.append("account number")
    if compared == 0:
        # The invoice quotes a different kind of identifier (e.g. domestic details when the register
        # holds only an IBAN). Nothing can be reconciled, so treat it as a change.
        differs.append("bank identifiers (none correspond to the identifiers held in the register)")
    if not differs:
        return []
    evidence = [EvidenceRef(label="Approved beneficiary", record_type="beneficiary", record_id=bene.id,
                            excerpt=f"version {bene.version}, verified {bene.verified_at:%Y-%m-%d}" if bene.verified_at else None)]
    for name in ("bank_sort_code", "bank_account_number", "bank_iban"):
        if name in ctx.invoice_fields:
            evidence.append(_doc_ref(ctx.invoice_fields, ctx.invoice_doc, name, f"Invoice {name.replace('bank_', '').replace('_', ' ')}"))
    return [Finding(
        "BENEFICIARY_CHANGED", ExceptionSeverity.BLOCKING.value, "Invoice bank details differ from approved beneficiary",
        f"The invoice's {', '.join(differs)} do not match approved beneficiary version {bene.version}. "
        "Bank details on an invoice never update the vendor register; an administrator must verify any "
        "change through the independent process, after which the case must be reviewed again.",
        evidence=evidence,
        facts={"beneficiary_version": bene.version, "invoice_bank": invoice_bank, "differs": differs},
    )]


def sync_exceptions(db: Session, case: Case, findings: list[Finding], *,
                    agent_run_id: str | None = None, actor_id: str | None = None) -> list[CaseException]:
    """Reconcile stored exceptions with the latest findings.

    Resolved exceptions stay resolved only while the underlying facts are unchanged; a finding with a
    new fingerprint reopens the exception. Exceptions whose finding disappeared are auto-resolved.
    """
    existing = {e.code: e for e in db.scalars(select(CaseException).where(CaseException.case_id == case.id))}
    changed = False
    seen_codes = set()
    for finding in findings:
        seen_codes.add(finding.code)
        current = existing.get(finding.code)
        if current is None:
            current = CaseException(organization_id=case.organization_id, case_id=case.id, code=finding.code,
                                    severity=finding.severity, title=finding.title, detail=finding.detail,
                                    fingerprint=finding.fingerprint, needs_information=finding.needs_information,
                                    agent_run_id=agent_run_id)
            db.add(current)
            db.flush()
            _replace_evidence(db, case, current, finding)
            audit.record(db, organization_id=case.organization_id, case_id=case.id, actor_type="system",
                         actor_id=actor_id, event_type="exception_raised",
                         payload={"exception_id": current.id, "code": finding.code, "severity": finding.severity})
            changed = True
            continue
        if current.fingerprint != finding.fingerprint:
            reopened = current.status != ExceptionStatus.OPEN.value
            current.fingerprint = finding.fingerprint
            current.detail = finding.detail
            current.title = finding.title
            current.severity = finding.severity
            current.needs_information = finding.needs_information
            if reopened:
                current.status = ExceptionStatus.OPEN.value
                current.resolution_note = None
                current.resolved_by = None
                current.resolved_at = None
            _replace_evidence(db, case, current, finding)
            audit.record(db, organization_id=case.organization_id, case_id=case.id, actor_type="system",
                         event_type="exception_reopened" if reopened else "exception_updated",
                         payload={"exception_id": current.id, "code": finding.code})
            changed = True
    for code, exc in existing.items():
        if code not in seen_codes and exc.status == ExceptionStatus.OPEN.value:
            exc.status = ExceptionStatus.RESOLVED.value
            exc.resolution_note = "No longer detected after re-check."
            exc.resolved_at = utcnow()
            audit.record(db, organization_id=case.organization_id, case_id=case.id, actor_type="system",
                         event_type="exception_auto_resolved", payload={"exception_id": exc.id, "code": code})
            changed = True
    if changed:
        from .approvals import invalidate_approvals

        invalidate_approvals(db, case, reason="exception findings changed")
    return list(db.scalars(select(CaseException).where(CaseException.case_id == case.id)
                           .order_by(CaseException.created_at)))


def _replace_evidence(db: Session, case: Case, exc: CaseException, finding: Finding) -> None:
    for link in db.scalars(select(EvidenceLink).where(EvidenceLink.exception_id == exc.id)):
        db.delete(link)
    for ref in finding.evidence:
        db.add(EvidenceLink(organization_id=case.organization_id, case_id=case.id, exception_id=exc.id,
                            document_version_id=ref.document_version_id, record_type=ref.record_type,
                            record_id=ref.record_id, page=ref.page, excerpt=ref.excerpt, label=ref.label))


def open_blocking(db: Session, case: Case) -> list[CaseException]:
    return list(db.scalars(select(CaseException).where(
        CaseException.case_id == case.id, CaseException.status == ExceptionStatus.OPEN.value,
        CaseException.severity == ExceptionSeverity.BLOCKING.value)))
