"""Document text extraction and deterministic field parsing with page references.

The parser is intentionally conservative: every claim carries the page and the line it came from,
and monetary values are validated into integer pence. Where a layout defeats the rules, fields are
simply absent and the agent must ask for them (or, when a model is configured, propose a value that
goes through the same validation).
"""

import io
import re
from dataclasses import dataclass, field

from pypdf import PdfReader

from .models import DocumentKind
from .money import parse_minor


@dataclass
class FieldClaim:
    name: str
    value_text: str | None
    value_json: dict | list | None = None
    page: int | None = None
    excerpt: str | None = None
    confidence: float = 0.9


@dataclass
class ExtractionResult:
    kind: str
    pages: list[str]
    fields: list[FieldClaim] = field(default_factory=list)

    def get(self, name: str) -> FieldClaim | None:
        return next((f for f in self.fields if f.name == name), None)

    def value(self, name: str):
        claim = self.get(name)
        if claim is None:
            return None
        return claim.value_json if claim.value_json is not None else claim.value_text

    def as_dict(self) -> dict:
        return {f.name: (f.value_json if f.value_json is not None else f.value_text) for f in self.fields}


def extract_text_pages(pdf_bytes: bytes) -> list[str]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return [(page.extract_text() or "") for page in reader.pages]


def _lines(pages: list[str]):
    for page_no, text in enumerate(pages, start=1):
        for raw in text.splitlines():
            line = raw.strip()
            if line:
                yield page_no, line


def _first(pages, pattern: str, name: str, flags=re.IGNORECASE, group=1, transform=None,
           confidence=0.9) -> FieldClaim | None:
    regex = re.compile(pattern, flags)
    for page_no, line in _lines(pages):
        match = regex.search(line)
        if match:
            value = match.group(group).strip()
            if transform:
                value = transform(value)
                if value is None:
                    continue
            return FieldClaim(name=name, value_text=str(value), page=page_no, excerpt=line,
                              confidence=confidence)
    return None


def _money_claim(pages, pattern: str, name: str) -> FieldClaim | None:
    regex = re.compile(pattern, re.IGNORECASE)
    for page_no, line in _lines(pages):
        match = regex.search(line)
        if match:
            minor = parse_minor(match.group(1))
            if minor is None:
                continue
            return FieldClaim(name=name, value_text=str(minor), value_json=minor, page=page_no,
                              excerpt=line)
    return None


_PIPE_LINE = re.compile(r"^(?P<desc>[^|]+?)\s*\|\s*(?P<qty>\d+)\s*\|\s*(?P<unit>[\d,]+\.\d{2})\s*\|\s*(?P<total>[\d,]+\.\d{2})$")
_COMPACT_LINE = re.compile(r"^(?P<qty>\d+)\s*x\s*(?P<desc>.+?)\s*@\s*(?P<unit>[\d,]+\.\d{2})\s*=\s*(?P<total>[\d,]+\.\d{2})$", re.IGNORECASE)
_COLUMN_LINE = re.compile(r"^(?P<desc>.+?)\s{2,}(?P<qty>\d+)\s+(?P<unit>[\d,]+\.\d{2})\s+(?P<total>[\d,]+\.\d{2})$")
_DELIVERY_PIPE = re.compile(r"^(?P<desc>[^|]+?)\s*\|\s*(?P<qty>\d+)$")
_DELIVERY_COLUMN = re.compile(r"^(?P<desc>.+?)\s{2,}(?P<qty>\d+)\s+received$", re.IGNORECASE)


def _line_items(pages) -> FieldClaim | None:
    items = []
    first_page = None
    excerpts = []
    for page_no, line in _lines(pages):
        match = _PIPE_LINE.match(line) or _COMPACT_LINE.match(line) or _COLUMN_LINE.match(line)
        if not match:
            continue
        unit = parse_minor(match.group("unit"))
        total = parse_minor(match.group("total"))
        if unit is None or total is None:
            continue
        items.append(
            {
                "description": match.group("desc").strip(),
                "quantity": int(match.group("qty")),
                "unit_price_minor": unit,
                "line_total_minor": total,
                "page": page_no,
            }
        )
        first_page = first_page or page_no
        excerpts.append(line)
    if not items:
        return None
    return FieldClaim(name="line_items", value_text=f"{len(items)} line items", value_json=items,
                      page=first_page, excerpt="\n".join(excerpts))


def _supplier_name(pages) -> FieldClaim | None:
    explicit = _first(pages, r"^(?:From|Supplier)\s*:?\s*(.+?)(?:\s*\(vendor.*)?$", "supplier_name")
    if explicit:
        return explicit
    for page_no, line in _lines(pages):
        upper = line.upper()
        if upper in {"INVOICE", "TAX INVOICE", "PURCHASE ORDER", "DELIVERY CONFIRMATION"}:
            continue
        cleaned = re.sub(r"\s*-\s*Invoice$", "", line, flags=re.IGNORECASE)
        return FieldClaim(name="supplier_name", value_text=cleaned, page=page_no, excerpt=line,
                          confidence=0.7)
    return None


def _bank_fields(pages) -> list[FieldClaim]:
    claims = []
    name = _first(
        pages,
        r"(?:Account Name|payable to|Beneficiary)\s*:?\s*([^,]+?)(?:,|$)",
        "bank_account_name",
    )
    if name:
        claims.append(name)
    sort_code = _first(pages, r"Sort\s*code\s*:?\s*(\d{2}-?\d{2}-?\d{2})", "bank_sort_code",
                       transform=lambda v: v.replace("-", ""))
    if sort_code:
        claims.append(sort_code)
    account = _first(pages, r"(?:Account Number|Account no\.?|\baccount)\s*:?\s*(\d{8})\b",
                     "bank_account_number")
    if account:
        claims.append(account)
    iban = _first(pages, r"IBAN\s*:?\s*([A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,4})?)",
                  "bank_iban", flags=0, transform=lambda v: v.replace(" ", ""))
    if iban:
        claims.append(iban)
    return claims


def extract_invoice(pages: list[str]) -> ExtractionResult:
    result = ExtractionResult(kind=DocumentKind.INVOICE.value, pages=pages)
    candidates = [
        _first(pages, r"(?:Invoice\s*(?:Number|No\.?|#)|^Reference)\s*:?\s*([A-Z0-9][A-Z0-9/-]*)",
               "invoice_number"),
        _supplier_name(pages),
        _first(pages, r"(?:Invoice Date|^Date|^Issued)\s*:?\s*(.+)$", "invoice_date"),
        _first(pages, r"(?:Due Date|Payment due|Payable by)\s*:?\s*(.+)$", "due_date"),
        _first(pages, r"(?:Purchase Order|PO\s*(?:Ref|Number)|order reference)\s*:?\s*([A-Z0-9-]+)",
               "po_number"),
        _money_claim(pages, r"(?:Subtotal|^Net|Goods total)\s*:?\s*((?:GBP|£)?\s*[\d,]+\.\d{2})",
                     "subtotal_minor"),
        _money_claim(pages, r"(?:VAT|Value added tax)\s*(?:\([^)]*\))?\s*:?\s*((?:GBP|£)?\s*[\d,]+\.\d{2})",
                     "vat_minor"),
        _money_claim(pages, r"(?:Total Due|Amount Due|Grand Total)\s*:?\s*((?:GBP|£)?\s*[\d,]+\.\d{2})",
                     "total_minor"),
        _line_items(pages),
        *_bank_fields(pages),
    ]
    result.fields = [c for c in candidates if c is not None]
    return result


def extract_purchase_order(pages: list[str]) -> ExtractionResult:
    result = ExtractionResult(kind=DocumentKind.PURCHASE_ORDER.value, pages=pages)
    candidates = [
        _first(pages, r"(?:PO Number|Order reference)\s*:?\s*([A-Z0-9-]+)", "po_number"),
        _first(pages, r"^Supplier\s*:?\s*(.+?)(?:\s*\(vendor.*)?$", "supplier_name"),
        _first(pages, r"(?:Vendor Code\s*:?\s*|\(vendor\s+)([A-Z0-9-]+)", "vendor_code"),
        _first(pages, r"(?:Order Date|Placed)\s*:?\s*(.+)$", "order_date"),
        _money_claim(pages, r"(?:PO Total|Order total)\s*:?\s*((?:GBP|£)?\s*[\d,]+\.\d{2})",
                     "total_minor"),
        _line_items(pages),
    ]
    result.fields = [c for c in candidates if c is not None]
    return result


def extract_delivery(pages: list[str]) -> ExtractionResult:
    result = ExtractionResult(kind=DocumentKind.DELIVERY_CONFIRMATION.value, pages=pages)
    items, excerpts, first_page = [], [], None
    for page_no, line in _lines(pages):
        match = _DELIVERY_PIPE.match(line) or _DELIVERY_COLUMN.match(line)
        if match and not line.lower().startswith("description"):
            items.append({"description": match.group("desc").strip(), "quantity": int(match.group("qty")),
                          "page": page_no})
            excerpts.append(line)
            first_page = first_page or page_no
    candidates = [
        _first(pages, r"(?:Delivery Note|^Note)\s*:?\s*([A-Z0-9-]+)", "delivery_note_number"),
        _first(pages, r"(?:Purchase Order|Against order)\s*:?\s*([A-Z0-9-]+)", "po_number"),
        _first(pages, r"^Supplier\s*:?\s*(.+)$", "supplier_name"),
        _first(pages, r"(?:Delivered On|^Received)\s*:?\s*(.+?)(?:\s+by\s+.*)?$", "delivered_on"),
        FieldClaim(name="line_items", value_text=f"{len(items)} delivered lines", value_json=items,
                   page=first_page, excerpt="\n".join(excerpts)) if items else None,
    ]
    result.fields = [c for c in candidates if c is not None]
    return result


EXTRACTORS = {
    DocumentKind.INVOICE.value: extract_invoice,
    DocumentKind.PURCHASE_ORDER.value: extract_purchase_order,
    DocumentKind.DELIVERY_CONFIRMATION.value: extract_delivery,
}


def extract_document(kind: str, pdf_bytes: bytes) -> ExtractionResult:
    pages = extract_text_pages(pdf_bytes)
    extractor = EXTRACTORS.get(kind)
    if extractor is None:
        return ExtractionResult(kind=kind, pages=pages)
    return extractor(pages)


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    cleaned = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    cleaned = re.sub(r"\b(ltd|limited|plc|llp|inc|co|company|the)\b", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()
