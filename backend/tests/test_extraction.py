import pytest

from app.extraction import extract_document, normalize_name
from app.fixtures import (
    BankDetails,
    DeliverySpec,
    InvoiceSpec,
    LineItem,
    PurchaseOrderSpec,
    render_delivery,
    render_invoice,
    render_purchase_order,
)
from app.money import format_minor, parse_minor

LINES = [LineItem("Ergonomic chair", 10, 18000), LineItem("Desk lamp", 20, 3000)]


@pytest.mark.parametrize("layout", ["classic", "compact", "formal"])
def test_invoice_fields_recovered_with_page_references(layout):
    spec = InvoiceSpec("Northwind Office Supplies Ltd", "12 Market Street, Leeds", "INV-2026-0042", "14 March 2026",
                       "13 April 2026", "PO-7781", "Acme Holdings plc", LINES,
                       BankDetails("Northwind Office Supplies Ltd", "20-00-00", "12345678", "GB29NWBK60161331926819"),
                       vat_minor=48000, layout=layout)
    pdf, truth = render_invoice(spec)
    result = extract_document("invoice", pdf)
    values = result.as_dict()
    for name, expected in truth.items():
        if name == "line_items":
            continue
        assert str(values.get(name)) == str(expected), f"{layout}: {name}"
    assert [(li["description"], li["quantity"], li["unit_price_minor"], li["line_total_minor"]) for li in values["line_items"]] == [
        (li["description"], li["quantity"], li["unit_price_minor"], li["line_total_minor"]) for li in truth["line_items"]]
    # Every claim cites a page and the line it came from.
    for claim in result.fields:
        assert claim.page is not None and claim.excerpt
    # Bank details live on page 2 in the multi-page layouts.
    if layout != "compact":
        assert result.get("bank_account_number").page == 2


@pytest.mark.parametrize("layout", ["classic", "formal"])
def test_purchase_order_and_delivery(layout):
    po_pdf, po_truth = render_purchase_order(PurchaseOrderSpec("PO-7781", "Northwind Office Supplies Ltd", "V-100",
                                                               "Acme Holdings plc", "1 March 2026", LINES, layout=layout))
    po = extract_document("purchase_order", po_pdf).as_dict()
    assert po["po_number"] == "PO-7781" and po["vendor_code"] == "V-100" and po["total_minor"] == po_truth["total_minor"]
    dn_pdf, _ = render_delivery(DeliverySpec("DN-1", "PO-7781", "Northwind Office Supplies Ltd", "10 March 2026",
                                             "B. Okafor", [("Ergonomic chair", 6), ("Desk lamp", 20)], layout=layout))
    dn = extract_document("delivery_confirmation", dn_pdf).as_dict()
    assert dn["delivery_note_number"] == "DN-1" and dn["po_number"] == "PO-7781"
    assert [(li["description"], li["quantity"]) for li in dn["line_items"]] == [("Ergonomic chair", 6), ("Desk lamp", 20)]


def test_money_parsing_is_strict():
    assert parse_minor("GBP 2,400.00") == 240000
    assert parse_minor("£2,400.5") == 240050
    assert parse_minor("2400") == 240000
    assert parse_minor("no amount here") is None
    assert format_minor(240000) == "GBP 2,400.00"
    assert format_minor(-5) == "GBP -0.05"


def test_supplier_name_normalisation():
    assert normalize_name("Northwind Office Supplies Ltd") == normalize_name("NORTHWIND OFFICE SUPPLIES LIMITED")
    assert normalize_name("The Contoso Company plc") == "contoso"
