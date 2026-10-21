"""Cross-organization access is denied through both the API and the storage path."""

from app.storage import sign_download
from tests.conftest import complete_case, create_case, invoice_pdf, upload


def test_non_member_cannot_read_or_write_cases(client, tenant, other_tenant):
    case = complete_case(client, tenant)
    foreign = other_tenant.headers("admin")

    # Listing or reading another tenant's organization is forbidden even for an administrator.
    assert client.get(tenant.url("/cases"), headers=foreign).status_code == 403
    assert client.get(tenant.url(f"/cases/{case['id']}"), headers=foreign).status_code == 403
    assert client.get(tenant.url("/vendors"), headers=foreign).status_code == 403
    assert client.get(tenant.url("/approvals"), headers=foreign).status_code == 403
    assert client.post(tenant.url(f"/cases/{case['id']}/investigate"), headers=foreign).status_code == 403

    # Addressing a foreign case through your own organization behaves as if it did not exist.
    own = other_tenant.headers("admin")
    assert client.get(other_tenant.url(f"/cases/{case['id']}"), headers=own).status_code == 404
    response = client.post(other_tenant.url(f"/cases/{case['id']}/documents"), data={"kind": "invoice"},
                           files={"file": ("x.pdf", invoice_pdf(), "application/pdf")}, headers=own)
    assert response.status_code == 404
    assert client.post(other_tenant.url(f"/cases/{case['id']}/approvals"), headers=own).status_code == 404
    assert client.post(other_tenant.url(f"/cases/{case['id']}/export"), headers=own).status_code == 404


def test_storage_path_requires_membership_and_valid_signature(client, tenant, other_tenant):
    case = create_case(client, tenant)
    doc = upload(client, tenant, case["id"], "invoice", invoice_pdf())
    url = doc["download_url"]

    ok = client.get(url, headers=tenant.headers("budget_owner"))
    assert ok.status_code == 200 and ok.content.startswith(b"%PDF")

    # A member of another organization cannot use the link, even though it is correctly signed.
    assert client.get(url, headers=other_tenant.headers("admin")).status_code == 403
    # Unauthenticated requests are rejected.
    assert client.get(url).status_code == 401
    # Tampered or expired tokens are rejected.
    assert client.get(url[:-4] + "AAAA", headers=tenant.headers("admin")).status_code == 403
    expired = sign_download(tenant.org_id, doc["id"], ttl_seconds=-10)
    assert client.get(f"/files/{expired}", headers=tenant.headers("admin")).status_code == 403
    # A token forged for another organization does not reveal the document.
    forged = sign_download(other_tenant.org_id, doc["id"])
    assert client.get(f"/files/{forged}", headers=other_tenant.headers("admin")).status_code == 404


def test_role_checks_on_register_and_membership(client, tenant):
    body = {"vendor_code": "V-9", "name": "New Supplier Ltd"}
    for role in ("ap_specialist", "budget_owner", "approver"):
        assert client.post(tenant.url("/vendors"), json=body, headers=tenant.headers(role)).status_code == 403
    assert client.post(tenant.url("/vendors"), json=body, headers=tenant.headers("admin")).status_code == 201
    member = {"email": "new@acme.test", "role": "approver"}
    assert client.post(tenant.url("/members"), json=member, headers=tenant.headers("approver")).status_code == 403
    assert client.post(tenant.url("/members"), json=member, headers=tenant.headers("admin")).status_code == 201


def test_invalid_tokens_are_rejected(client, tenant):
    assert client.get(tenant.url("/cases")).status_code == 401
    assert client.get(tenant.url("/cases"), headers={"Authorization": "Bearer not-a-token"}).status_code == 401
