"""Synthetic supplier documents in several layouts.

Each renderer returns PDF bytes plus the ground truth the extractor is expected to recover.
Layouts "classic" and "compact" are development layouts; "formal" is held out for evaluation.
"""

from dataclasses import dataclass, field

from .money import format_minor
from .pdfgen import build_pdf

DEV_LAYOUTS = ("classic", "compact")
HELD_OUT_LAYOUTS = ("formal",)


@dataclass
class LineItem:
    description: str
    quantity: int
    unit_price_minor: int
    line_total_minor: int | None = None  # defaults to qty * unit price; set to inject errors

    @property
    def total(self) -> int:
        return (
            self.line_total_minor
            if self.line_total_minor is not None
            else self.quantity * self.unit_price_minor
        )


@dataclass
class BankDetails:
    account_name: str
    sort_code: str | None = None
    account_number: str | None = None
    iban: str | None = None


@dataclass
class InvoiceSpec:
    supplier_name: str
    supplier_address: str
    invoice_number: str
    invoice_date: str
    due_date: str
    po_number: str | None
    customer_name: str
    lines: list[LineItem]
    bank: BankDetails
    vat_minor: int = 0
    subtotal_override_minor: int | None = None
    total_override_minor: int | None = None
    layout: str = "classic"
    extra_lines: list[str] = field(default_factory=list)  # e.g. injected instructions

    @property
    def subtotal(self) -> int:
        return (
            self.subtotal_override_minor
            if self.subtotal_override_minor is not None
            else sum(line.total for line in self.lines)
        )

    @property
    def total(self) -> int:
        return (
            self.total_override_minor
            if self.total_override_minor is not None
            else self.subtotal + self.vat_minor
        )


@dataclass
class PurchaseOrderSpec:
    po_number: str
    supplier_name: str
    vendor_code: str
    buyer_name: str
    order_date: str
    lines: list[LineItem]
    layout: str = "classic"

    @property
    def total(self) -> int:
        return sum(line.total for line in self.lines)


@dataclass
class DeliverySpec:
    delivery_note_number: str
    po_number: str
    supplier_name: str
    delivered_on: str
    received_by: str
    lines: list[tuple[str, int]]  # description, quantity delivered
    layout: str = "classic"


def _money(minor: int) -> str:
    return format_minor(minor).replace("GBP ", "")


def render_invoice(spec: InvoiceSpec) -> tuple[bytes, dict]:
    page1: list[str] = []
    page2: list[str] = []
    if spec.layout == "classic":
        page1 += ["INVOICE", spec.supplier_name, spec.supplier_address, ""]
        page1 += [
            f"Invoice Number: {spec.invoice_number}",
            f"Invoice Date: {spec.invoice_date}",
            f"Due Date: {spec.due_date}",
        ]
        if spec.po_number:
            page1.append(f"Purchase Order: {spec.po_number}")
        page1 += [f"Bill To: {spec.customer_name}", "", "Description | Qty | Unit Price | Line Total"]
        for line in spec.lines:
            page1.append(
                f"{line.description} | {line.quantity} | {_money(line.unit_price_minor)} | "
                f"{_money(line.total)}"
            )
        page1 += [
            "",
            f"Subtotal: GBP {_money(spec.subtotal)}",
            f"VAT: GBP {_money(spec.vat_minor)}",
            f"Total Due: GBP {_money(spec.total)}",
        ]
        page2 += ["Payment Details", f"Account Name: {spec.bank.account_name}"]
        if spec.bank.sort_code:
            page2.append(f"Sort Code: {spec.bank.sort_code}")
        if spec.bank.account_number:
            page2.append(f"Account Number: {spec.bank.account_number}")
        if spec.bank.iban:
            page2.append(f"IBAN: {spec.bank.iban}")
    elif spec.layout == "compact":
        page1 += [f"{spec.supplier_name} - Invoice", spec.supplier_address, ""]
        page1 += [f"Invoice No. {spec.invoice_number}", f"Date {spec.invoice_date}", f"Payment due {spec.due_date}"]
        if spec.po_number:
            page1.append(f"PO Ref {spec.po_number}")
        page1 += [f"Customer: {spec.customer_name}", ""]
        for line in spec.lines:
            page1.append(
                f"{line.quantity} x {line.description} @ {_money(line.unit_price_minor)} = "
                f"{_money(line.total)}"
            )
        page1 += [
            "",
            f"Net £{_money(spec.subtotal)}",
            f"VAT £{_money(spec.vat_minor)}",
            f"Amount Due £{_money(spec.total)}",
            "",
        ]
        bank_bits = [f"Bank: payable to {spec.bank.account_name}"]
        if spec.bank.sort_code:
            bank_bits.append(f"sort code {spec.bank.sort_code}")
        if spec.bank.account_number:
            bank_bits.append(f"account {spec.bank.account_number}")
        if spec.bank.iban:
            bank_bits.append(f"IBAN {spec.bank.iban}")
        page1.append(", ".join(bank_bits))
    elif spec.layout == "formal":
        page1 += ["TAX INVOICE", "", f"From: {spec.supplier_name}", spec.supplier_address, ""]
        page1 += [f"Reference {spec.invoice_number}", f"Issued {spec.invoice_date}", f"Payable by {spec.due_date}"]
        if spec.po_number:
            page1.append(f"Your order reference {spec.po_number}")
        page1 += [f"Invoiced to {spec.customer_name}", "", "Item                      Quantity   Rate      Amount"]
        for line in spec.lines:
            page1.append(
                f"{line.description:<26}{line.quantity:>8}   {_money(line.unit_price_minor):>8}  "
                f"{_money(line.total):>10}"
            )
        page1 += [
            "",
            f"Goods total GBP {_money(spec.subtotal)}",
            f"Value added tax GBP {_money(spec.vat_minor)}",
            f"Grand Total GBP {_money(spec.total)}",
        ]
        page2 += ["Remittance", f"Beneficiary {spec.bank.account_name}"]
        if spec.bank.iban:
            page2.append(f"IBAN {spec.bank.iban}")
        if spec.bank.sort_code:
            page2.append(f"Sort code {spec.bank.sort_code}")
        if spec.bank.account_number:
            page2.append(f"Account no. {spec.bank.account_number}")
    else:
        raise ValueError(f"Unknown layout {spec.layout}")
    page1 += spec.extra_lines
    pages = [page1] + ([page2] if page2 else [])
    truth = {
        "invoice_number": spec.invoice_number,
        "supplier_name": spec.supplier_name,
        "invoice_date": spec.invoice_date,
        "due_date": spec.due_date,
        "po_number": spec.po_number,
        "subtotal_minor": spec.subtotal,
        "vat_minor": spec.vat_minor,
        "total_minor": spec.total,
        "line_items": [
            {
                "description": line.description,
                "quantity": line.quantity,
                "unit_price_minor": line.unit_price_minor,
                "line_total_minor": line.total,
            }
            for line in spec.lines
        ],
        "bank_account_name": spec.bank.account_name,
        "bank_sort_code": spec.bank.sort_code.replace("-", "") if spec.bank.sort_code else None,
        "bank_account_number": spec.bank.account_number,
        "bank_iban": spec.bank.iban.replace(" ", "") if spec.bank.iban else None,
    }
    return build_pdf(pages, title=f"Invoice {spec.invoice_number}"), truth


def render_purchase_order(spec: PurchaseOrderSpec) -> tuple[bytes, dict]:
    page: list[str] = []
    if spec.layout == "formal":
        page += ["PURCHASE ORDER CONFIRMATION", f"Order reference {spec.po_number}", f"Placed {spec.order_date}"]
        page += [f"Supplier {spec.supplier_name} (vendor {spec.vendor_code})", f"Ordered by {spec.buyer_name}", ""]
        page.append("Item                      Quantity   Rate      Amount")
        for line in spec.lines:
            page.append(
                f"{line.description:<26}{line.quantity:>8}   {_money(line.unit_price_minor):>8}  "
                f"{_money(line.total):>10}"
            )
        page += ["", f"Order total GBP {_money(spec.total)}"]
    else:
        page += ["PURCHASE ORDER", f"PO Number: {spec.po_number}", f"Order Date: {spec.order_date}"]
        page += [f"Supplier: {spec.supplier_name}", f"Vendor Code: {spec.vendor_code}", f"Buyer: {spec.buyer_name}", ""]
        page.append("Description | Qty | Unit Price | Line Total")
        for line in spec.lines:
            page.append(
                f"{line.description} | {line.quantity} | {_money(line.unit_price_minor)} | "
                f"{_money(line.total)}"
            )
        page += ["", f"PO Total: GBP {_money(spec.total)}"]
    truth = {
        "po_number": spec.po_number,
        "supplier_name": spec.supplier_name,
        "vendor_code": spec.vendor_code,
        "total_minor": spec.total,
        "line_items": [
            {
                "description": line.description,
                "quantity": line.quantity,
                "unit_price_minor": line.unit_price_minor,
                "line_total_minor": line.total,
            }
            for line in spec.lines
        ],
    }
    return build_pdf([page], title=f"Purchase order {spec.po_number}"), truth


def render_delivery(spec: DeliverySpec) -> tuple[bytes, dict]:
    page: list[str] = []
    if spec.layout == "formal":
        page += ["GOODS RECEIVED", f"Note {spec.delivery_note_number}", f"Against order {spec.po_number}"]
        page += [f"Supplier {spec.supplier_name}", f"Received {spec.delivered_on} by {spec.received_by}", ""]
        for description, quantity in spec.lines:
            page.append(f"{description:<26}{quantity:>8} received")
    else:
        page += ["DELIVERY CONFIRMATION", f"Delivery Note: {spec.delivery_note_number}", f"Purchase Order: {spec.po_number}"]
        page += [f"Supplier: {spec.supplier_name}", f"Delivered On: {spec.delivered_on}", f"Received By: {spec.received_by}", ""]
        page.append("Description | Qty Delivered")
        for description, quantity in spec.lines:
            page.append(f"{description} | {quantity}")
    truth = {
        "delivery_note_number": spec.delivery_note_number,
        "po_number": spec.po_number,
        "supplier_name": spec.supplier_name,
        "delivered_on": spec.delivered_on,
        "line_items": [{"description": d, "quantity": q} for d, q in spec.lines],
    }
    return build_pdf([page], title=f"Delivery {spec.delivery_note_number}"), truth
