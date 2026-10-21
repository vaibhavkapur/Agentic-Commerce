"""Separation of duties, freshness, blockers, and idempotent export."""

from datetime import timedelta

from app.db import SessionLocal
from app.fixtures import BankDetails, LineItem
from app.models import ApprovalRequest, utcnow
from tests.conftest import SUPPLIER, complete_case, create_case, delivery_pdf, invoice_pdf, po_pdf, upload


def request_approval(client, tenant, case_id, role="ap_specialist", expect=201):
    response = client.post(tenant.url(f"/cases/{case_id}/approvals"), headers=tenant.headers(role))
    assert response.status_code == expect, response.text
    return response.json()


def decide(client, tenant, case_id, approval_id, role, decision="approve", expect=200):
    response = client.post(tenant.url(f"/cases/{case_id}/approvals/{approval_id}/decision"),
                           json={"decision": decision, "note": "reviewed"}, headers=tenant.headers(role))
    assert response.status_code == expect, response.text
    return response.json()


def export(client, tenant, case_id, role="ap_specialist", expect=201):
    response = client.post(tenant.url(f"/cases/{case_id}/export"), headers=tenant.headers(role))
    assert response.status_code == expect, response.text
    return response.json()


def test_submitter_cannot_approve_own_request(client, tenant):
    # The approver creates and submits the case, so they are the submitter.
    case = complete_case(client, tenant, role="approver")
    approval = request_approval(client, tenant, case["id"], role="approver")
    decide(client, tenant, case["id"], approval["id"], role="approver", expect=403)
    # Non-approver roles cannot decide at all.
    decide(client, tenant, case["id"], approval["id"], role="budget_owner", expect=403)
    decide(client, tenant, case["id"], approval["id"], role="admin", expect=403)
    # A different approver can.
    result = decide(client, tenant, case["id"], approval["id"], role="approver2")
    assert result["request_status"] == "approved" and result["case_status"] == "approved"


def test_case_creator_cannot_approve_even_if_someone_else_requested(client, tenant):
    case = complete_case(client, tenant, role="approver")
    approval = request_approval(client, tenant, case["id"], role="ap_specialist")
    decide(client, tenant, case["id"], approval["id"], role="approver", expect=403)


def test_blocking_exceptions_prevent_approval_and_export(client, tenant):
    case = create_case(client, tenant)
    upload(client, tenant, case["id"], "invoice", invoice_pdf())
    upload(client, tenant, case["id"], "purchase_order", po_pdf())
    # Delivery evidence is missing: approval cannot even be requested.
    body = request_approval(client, tenant, case["id"], expect=409)
    assert "DELIVERY_MISSING" in [b["code"] for b in body["detail"]["blockers"]]
    export(client, tenant, case["id"], expect=409)
    # Supplying the evidence clears the blocker.
    upload(client, tenant, case["id"], "delivery_confirmation", delivery_pdf())
    request_approval(client, tenant, case["id"])


def test_changed_beneficiary_blocks_export_until_register_is_verified_and_case_re_reviewed(client, tenant):
    case = create_case(client, tenant)
    upload(client, tenant, case["id"], "invoice", invoice_pdf(bank=BankDetails(SUPPLIER, "30-99-99", "99887766")))
    upload(client, tenant, case["id"], "purchase_order", po_pdf())
    upload(client, tenant, case["id"], "delivery_confirmation", delivery_pdf())
    body = request_approval(client, tenant, case["id"], expect=409)
    assert "BENEFICIARY_CHANGED" in [b["code"] for b in body["detail"]["blockers"]]

    # Administrator records the new account but has not verified it yet: still blocked.
    vendor = client.get(tenant.url("/vendors"), headers=tenant.headers("admin")).json()[0]
    new_version = client.post(tenant.url(f"/vendors/{vendor['id']}/beneficiaries"),
                              json={"account_name": SUPPLIER, "sort_code": "30-99-99", "account_number": "99887766"},
                              headers=tenant.headers("admin")).json()
    assert new_version["verification_status"] == "pending_verification"
    request_approval(client, tenant, case["id"], expect=409)

    # Verification completes through the administrator's process; the case is reviewed again and passes.
    response = client.post(tenant.url(f"/vendors/{vendor['id']}/beneficiaries/{new_version['id']}/verify"),
                           json={"note": "Call-back to registered finance contact completed"}, headers=tenant.headers("admin"))
    assert response.status_code == 200 and response.json()["is_current"]
    approval = request_approval(client, tenant, case["id"])
    assert approval["snapshot"]["beneficiary"]["version"] == 2
    decide(client, tenant, case["id"], approval["id"], role="approver")
    instruction = export(client, tenant, case["id"])
    assert instruction["instruction"]["beneficiary"]["account_number"] == "99887766"


def test_beneficiary_change_after_approval_invalidates_it(client, tenant):
    case = complete_case(client, tenant)
    approval = request_approval(client, tenant, case["id"])
    decide(client, tenant, case["id"], approval["id"], role="approver")
    vendor = client.get(tenant.url("/vendors"), headers=tenant.headers("admin")).json()[0]
    client.post(tenant.url(f"/vendors/{vendor['id']}/beneficiaries"),
                json={"account_name": SUPPLIER, "sort_code": "11-11-11", "account_number": "11111111", "verified": True,
                      "note": "verified"}, headers=tenant.headers("admin"))
    export(client, tenant, case["id"], expect=409)
    detail = client.get(tenant.url(f"/cases/{case['id']}"), headers=tenant.headers("ap_specialist")).json()
    assert detail["approvals"][0]["status"] == "invalidated"


def test_revised_evidence_invalidates_existing_approval(client, tenant):
    case = complete_case(client, tenant)
    approval = request_approval(client, tenant, case["id"])
    decide(client, tenant, case["id"], approval["id"], role="approver")
    # A revised invoice (one lamp fewer) arrives after approval.
    upload(client, tenant, case["id"], "invoice", invoice_pdf(lines=[LineItem("Ergonomic chair", 10, 18000), LineItem("Desk lamp", 19, 3000)]))
    detail = client.get(tenant.url(f"/cases/{case['id']}"), headers=tenant.headers("ap_specialist")).json()
    assert detail["status"] == "investigating"
    assert detail["approvals"][0]["status"] == "invalidated"
    assert "uploaded" in detail["approvals"][0]["invalidation_reason"]
    export(client, tenant, case["id"], expect=409)
    # The new snapshot has a different hash and must be approved again.
    second = request_approval(client, tenant, case["id"])
    assert second["snapshot_hash"] != approval["snapshot_hash"]
    assert second["snapshot"]["amount_minor"] == 237000
    decide(client, tenant, case["id"], second["id"], role="approver")
    instruction = export(client, tenant, case["id"])
    assert instruction["instruction"]["amount_minor"] == 237000
    assert instruction["instruction"]["approval"]["snapshot_hash"] == second["snapshot_hash"]


def test_field_correction_and_exception_decisions_invalidate_approval(client, tenant):
    case = complete_case(client, tenant)
    approval = request_approval(client, tenant, case["id"])
    detail = client.get(tenant.url(f"/cases/{case['id']}"), headers=tenant.headers("ap_specialist")).json()
    invoice = next(d for d in detail["documents"] if d["kind"] == "invoice")
    response = client.post(tenant.url(f"/cases/{case['id']}/documents/{invoice['id']}/fields"),
                           json={"name": "total_minor", "value_json": 240001, "page": 1, "note": "typo on invoice"},
                           headers=tenant.headers("ap_specialist"))
    assert response.status_code == 201 and response.json()["source"] == "human"
    detail = client.get(tenant.url(f"/cases/{case['id']}"), headers=tenant.headers("ap_specialist")).json()
    assert detail["approvals"][0]["status"] == "invalidated"
    assert detail["amount_minor"] == 240001
    decide(client, tenant, case["id"], approval["id"], role="approver", expect=409)


def test_replayed_approval_and_export_requests_have_no_duplicate_effects(client, tenant):
    case = complete_case(client, tenant)
    first = request_approval(client, tenant, case["id"])
    again = request_approval(client, tenant, case["id"])
    assert again["id"] == first["id"]
    queue = client.get(tenant.url("/approvals"), headers=tenant.headers("approver")).json()
    assert [q["id"] for q in queue] == [first["id"]] and queue[0]["can_decide"] is True

    decision = decide(client, tenant, case["id"], first["id"], role="approver")
    replay = decide(client, tenant, case["id"], first["id"], role="approver")
    assert replay["id"] == decision["id"]
    # A conflicting decision after the fact is refused rather than recorded.
    decide(client, tenant, case["id"], first["id"], role="approver2", decision="reject", expect=409)

    instruction = export(client, tenant, case["id"])
    repeat = export(client, tenant, case["id"], expect=200)
    assert repeat["id"] == instruction["id"] and repeat["audit_reference"] == instruction["audit_reference"]
    assert repeat["created"] is False
    detail = client.get(tenant.url(f"/cases/{case['id']}"), headers=tenant.headers("ap_specialist")).json()
    assert detail["status"] == "exported"
    timeline = client.get(tenant.url(f"/cases/{case['id']}/timeline"), headers=tenant.headers("ap_specialist")).json()
    exported_events = [e for e in timeline if e["event_type"] == "instruction_exported"]
    assert len(exported_events) == 1
    summary = client.get(tenant.url(f"/cases/{case['id']}/export/summary.txt"), headers=tenant.headers("approver"))
    assert summary.status_code == 200 and instruction["audit_reference"] in summary.text
    # Exported cases are frozen.
    response = client.post(tenant.url(f"/cases/{case['id']}/documents"), data={"kind": "invoice"},
                           files={"file": ("x.pdf", invoice_pdf(), "application/pdf")}, headers=tenant.headers("ap_specialist"))
    assert response.status_code == 409


def test_expired_approval_cannot_be_decided_or_exported(client, tenant):
    case = complete_case(client, tenant)
    approval = request_approval(client, tenant, case["id"])
    with SessionLocal() as db:
        request = db.get(ApprovalRequest, approval["id"])
        request.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    decide(client, tenant, case["id"], approval["id"], role="approver", expect=409)


def test_snapshot_contents_bind_the_approval(client, tenant):
    case = complete_case(client, tenant)
    approval = request_approval(client, tenant, case["id"])
    snapshot = approval["snapshot"]
    assert snapshot["organization_id"] == tenant.org_id and snapshot["case_id"] == case["id"]
    assert snapshot["amount_minor"] == 240000 and snapshot["currency"] == "GBP"
    assert {d["kind"] for d in snapshot["document_versions"]} == {"invoice", "purchase_order", "delivery_confirmation"}
    assert all(len(d["sha256"]) == 64 for d in snapshot["document_versions"])
    assert snapshot["beneficiary"]["version"] == 1 and snapshot["beneficiary"]["verification_status"] == "verified"
    assert approval["policy_version"] == "ap-policy-v1" and approval["expires_at"]
