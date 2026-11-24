from app.fixtures import BankDetails, LineItem
from tests.conftest import (
    SUPPLIER,
    complete_case,
    create_case,
    delivery_pdf,
    exceptions_of,
    invoice_pdf,
    po_pdf,
    upload,
)


def investigate(client, tenant, case_id):
    response = client.post(tenant.url(f"/cases/{case_id}/investigate"), headers=tenant.headers("ap_specialist"))
    assert response.status_code == 202, response.text
    return response.json()


def test_readme_example_finds_all_three_discrepancies(client, tenant):
    """GBP 2,400 invoice against a GBP 2,000 PO, partial delivery, different bank account."""
    case = create_case(client, tenant)
    upload(client, tenant, case["id"], "invoice", invoice_pdf(bank=BankDetails(SUPPLIER, "30-99-99", "99887766")))
    upload(client, tenant, case["id"], "purchase_order",
           po_pdf(lines=[LineItem("Ergonomic chair", 10, 18000), LineItem("Desk lamp", 20, 1000)]))
    upload(client, tenant, case["id"], "delivery_confirmation", delivery_pdf(lines=[("Ergonomic chair", 6), ("Desk lamp", 20)]))

    run = investigate(client, tenant, case["id"])
    assert run["status"] == "interrupted"  # waiting at await_approval
    found = exceptions_of(client, tenant, case["id"])
    assert {"PO_AMOUNT_EXCEEDED", "DELIVERY_INCOMPLETE", "BENEFICIARY_CHANGED"} <= set(found)
    assert "GBP 2,400.00" in found["PO_AMOUNT_EXCEEDED"]["detail"] and "GBP 2,000.00" in found["PO_AMOUNT_EXCEEDED"]["detail"]
    assert "invoiced 10, delivered 6" in found["DELIVERY_INCOMPLETE"]["detail"]
    # Each finding cites its source documents and pages.
    for code in ("PO_AMOUNT_EXCEEDED", "DELIVERY_INCOMPLETE", "BENEFICIARY_CHANGED"):
        assert found[code]["evidence"], code
    bank_refs = [e for e in found["BENEFICIARY_CHANGED"]["evidence"] if e["document_version_id"]]
    assert all(e["page"] == 2 for e in bank_refs)  # payment details are on page 2 of the classic layout
    assert any(e["record_type"] == "beneficiary" for e in found["BENEFICIARY_CHANGED"]["evidence"])
    # The register is untouched by the invoice's bank details.
    vendors = client.get(tenant.url("/vendors"), headers=tenant.headers("admin")).json()
    current = [b for b in vendors[0]["beneficiaries"] if b["is_current"]][0]
    assert current["account_number"] == "12345678"
    assert run["summary"] and "[invoice, page 1]" in run["summary"]


def test_clean_case_has_no_open_exceptions_and_is_ready_for_review(client, tenant):
    case = complete_case(client, tenant)
    investigate(client, tenant, case["id"])
    found = exceptions_of(client, tenant, case["id"])
    assert all(e["status"] != "open" for e in found.values()), found
    detail = client.get(tenant.url(f"/cases/{case['id']}"), headers=tenant.headers("ap_specialist")).json()
    assert detail["status"] == "ready_for_review"
    assert detail["amount"] == "GBP 2,400.00"


def test_missing_delivery_produces_clarification_draft_not_a_message(client, tenant):
    case = create_case(client, tenant)
    upload(client, tenant, case["id"], "invoice", invoice_pdf(layout="compact"))
    upload(client, tenant, case["id"], "purchase_order", po_pdf())
    run = investigate(client, tenant, case["id"])
    assert run["status"] == "completed" and run["outcome"] == "information_requested"
    detail = client.get(tenant.url(f"/cases/{case['id']}"), headers=tenant.headers("ap_specialist")).json()
    assert detail["status"] == "needs_information"
    assert detail["exceptions"][0]["code"] == "DELIVERY_MISSING"
    drafts = detail["clarification_drafts"]
    assert len(drafts) == 1 and drafts[0]["status"] == "draft" and drafts[0]["authored_by"] == "agent"
    assert "delivery note" in drafts[0]["body"].lower()


def test_duplicate_and_arithmetic_errors(client, tenant):
    original = complete_case(client, tenant, invoice_number="INV-77")
    investigate(client, tenant, original["id"])
    duplicate = create_case(client, tenant)
    upload(client, tenant, duplicate["id"], "invoice",
           invoice_pdf("INV-77", lines=[LineItem("Ergonomic chair", 10, 18000, 190000), LineItem("Desk lamp", 20, 3000)],
                       layout="formal"))
    investigate(client, tenant, duplicate["id"])
    found = exceptions_of(client, tenant, duplicate["id"])
    assert found["DUPLICATE_INVOICE"]["severity"] == "blocking"
    assert any(e["record_type"] == "case" and e["record_id"] == original["id"] for e in found["DUPLICATE_INVOICE"]["evidence"])
    assert "10 x GBP 180.00 = GBP 1,800.00, invoice shows GBP 1,900.00" in found["TOTAL_MISMATCH"]["detail"]
    # The original case is not penalised for a later resubmission.
    assert "DUPLICATE_INVOICE" not in exceptions_of(client, tenant, original["id"])


def test_resolving_and_reopening_tracks_fingerprints(client, tenant):
    case = create_case(client, tenant)
    upload(client, tenant, case["id"], "invoice", invoice_pdf())
    upload(client, tenant, case["id"], "purchase_order", po_pdf(lines=[LineItem("Ergonomic chair", 10, 18000), LineItem("Desk lamp", 20, 1000)]))
    upload(client, tenant, case["id"], "delivery_confirmation", delivery_pdf())
    investigate(client, tenant, case["id"])
    exc = exceptions_of(client, tenant, case["id"])["PO_AMOUNT_EXCEEDED"]
    response = client.post(tenant.url(f"/cases/{case['id']}/exceptions/{exc['id']}"),
                           json={"action": "waive", "note": "Price increase agreed with budget owner"},
                           headers=tenant.headers("budget_owner"))
    assert response.status_code == 200 and response.json()["status"] == "waived"
    # Re-running checks with unchanged facts keeps the waiver.
    client.post(tenant.url(f"/cases/{case['id']}/checks"), headers=tenant.headers("ap_specialist"))
    assert exceptions_of(client, tenant, case["id"])["PO_AMOUNT_EXCEEDED"]["status"] == "waived"
    # A new invoice version with a different overage reopens it.
    upload(client, tenant, case["id"], "invoice", invoice_pdf(lines=[LineItem("Ergonomic chair", 10, 19000), LineItem("Desk lamp", 20, 3000)]))
    client.post(tenant.url(f"/cases/{case['id']}/checks"), headers=tenant.headers("ap_specialist"))
    assert exceptions_of(client, tenant, case["id"])["PO_AMOUNT_EXCEEDED"]["status"] == "open"


def test_beneficiary_exception_cannot_be_waived_by_reviewers(client, tenant):
    case = create_case(client, tenant)
    upload(client, tenant, case["id"], "invoice", invoice_pdf(bank=BankDetails(SUPPLIER, "30-99-99", "99887766")))
    client.post(tenant.url(f"/cases/{case['id']}/checks"), headers=tenant.headers("ap_specialist"))
    exc = exceptions_of(client, tenant, case["id"])["BENEFICIARY_CHANGED"]
    for role in ("ap_specialist", "budget_owner", "approver", "admin"):
        response = client.post(tenant.url(f"/cases/{case['id']}/exceptions/{exc['id']}"),
                               json={"action": "waive", "note": "looks fine"}, headers=tenant.headers(role))
        assert response.status_code == 409, role
