"""Test fixtures: isolated SQLite database, local storage, and a seeded tenant pair."""

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="ap-tests-"))
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_TMP / 'test.db'}",
    "STORAGE_DIR": str(_TMP / "storage"),
    "LANGGRAPH_CHECKPOINT_PATH": str(_TMP / "checkpoints.sqlite"),
    "AUTH_JWT_SECRET": "test-secret-test-secret-test-secret-test-secret",
    "AGENT_RUN_MODE": "inline",
    "OPENAI_API_KEY": "",
    "APPROVAL_TTL_HOURS": "72",
})

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.auth import create_token  # noqa: E402
from app.db import Base, SessionLocal, engine, init_db  # noqa: E402
from app.fixtures import (  # noqa: E402
    BankDetails,
    DeliverySpec,
    InvoiceSpec,
    LineItem,
    PurchaseOrderSpec,
    render_delivery,
    render_invoice,
    render_purchase_order,
)
from app.main import app  # noqa: E402
from app.models import Membership, Organization, User  # noqa: E402
from app.services import vendors as vendor_service  # noqa: E402

SUPPLIER = "Northwind Office Supplies Ltd"
ADDRESS = "12 Market Street, Leeds LS1 4AB"
BANK = BankDetails(SUPPLIER, "20-00-00", "12345678")
BUYER = "Acme Holdings plc"


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(engine)
    init_db()
    from app.agent import runner

    runner.reset_graph()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class Tenant:
    def __init__(self, org_id: str, users: dict[str, User]):
        self.org_id = org_id
        self.users = users

    def headers(self, role: str) -> dict:
        return {"Authorization": f"Bearer {create_token(self.users[role])}"}

    def url(self, path: str) -> str:
        return f"/orgs/{self.org_id}{path}"


def make_tenant(slug: str, roles=("admin", "ap_specialist", "budget_owner", "approver"), with_vendor=True) -> Tenant:
    with SessionLocal() as db:
        org = Organization(name=slug.title(), slug=slug)
        db.add(org)
        db.flush()
        users = {}
        for role in roles:
            user = User(email=f"{role}@{slug}.test", display_name=f"{role} {slug}")
            db.add(user)
            db.flush()
            db.add(Membership(organization_id=org.id, user_id=user.id, role=role))
            users[role] = user
        # A second approver so separation-of-duties tests can use a non-submitting approver.
        second = User(email=f"approver2@{slug}.test", display_name=f"approver2 {slug}")
        db.add(second)
        db.flush()
        db.add(Membership(organization_id=org.id, user_id=second.id, role="approver"))
        users["approver2"] = second
        if with_vendor:
            vendor = vendor_service.create_vendor(db, organization_id=org.id, vendor_code="V-100", name=SUPPLIER,
                                                 tax_id=None, actor_id=users["admin"].id)
            vendor_service.add_beneficiary_version(db, vendor=vendor, account_name=SUPPLIER, sort_code="20-00-00",
                                                   account_number="12345678", iban=None, actor_id=users["admin"].id,
                                                   verified=True, note="verified")
        db.commit()
        return Tenant(org.id, users)


@pytest.fixture
def tenant() -> Tenant:
    return make_tenant("acme")


@pytest.fixture
def other_tenant() -> Tenant:
    return make_tenant("globex")


LINES = [LineItem("Ergonomic chair", 10, 18000), LineItem("Desk lamp", 20, 3000)]


def invoice_pdf(invoice_number="INV-1", lines=None, bank=BANK, po="PO-1", layout="classic", supplier=SUPPLIER,
                extra_lines=None, **kwargs) -> bytes:
    pdf, _ = render_invoice(InvoiceSpec(supplier, ADDRESS, invoice_number, "1 March 2026", "31 March 2026", po, BUYER,
                                        lines or LINES, bank, layout=layout, extra_lines=extra_lines or [], **kwargs))
    return pdf


def po_pdf(po="PO-1", lines=None, layout="classic") -> bytes:
    pdf, _ = render_purchase_order(PurchaseOrderSpec(po, SUPPLIER, "V-100", BUYER, "1 February 2026",
                                                     lines or LINES, layout=layout))
    return pdf


def delivery_pdf(po="PO-1", lines=None, layout="classic") -> bytes:
    pdf, _ = render_delivery(DeliverySpec("DN-1", po, SUPPLIER, "20 February 2026", "B. Okafor",
                                          lines or [(line.description, line.quantity) for line in LINES],
                                          layout=layout))
    return pdf


def upload(client, tenant: Tenant, case_id: str, kind: str, data: bytes, role="ap_specialist", name="doc.pdf"):
    response = client.post(tenant.url(f"/cases/{case_id}/documents"), data={"kind": kind},
                           files={"file": (name, data, "application/pdf")}, headers=tenant.headers(role))
    assert response.status_code == 201, response.text
    return response.json()


def create_case(client, tenant: Tenant, role="ap_specialist", reference=None) -> dict:
    response = client.post(tenant.url("/cases"), json={"title": "", "reference": reference}, headers=tenant.headers(role))
    assert response.status_code == 201, response.text
    return response.json()


def complete_case(client, tenant: Tenant, invoice_number="INV-1", role="ap_specialist") -> dict:
    """A case whose documents reconcile: invoice, matching PO, full delivery, approved bank details."""
    case = create_case(client, tenant, role=role)
    upload(client, tenant, case["id"], "invoice", invoice_pdf(invoice_number), role=role)
    upload(client, tenant, case["id"], "purchase_order", po_pdf(), role=role)
    upload(client, tenant, case["id"], "delivery_confirmation", delivery_pdf(), role=role)
    return case


def exceptions_of(client, tenant: Tenant, case_id: str) -> dict[str, dict]:
    response = client.get(tenant.url(f"/cases/{case_id}"), headers=tenant.headers("ap_specialist"))
    assert response.status_code == 200, response.text
    return {e["code"]: e for e in response.json()["exceptions"]}


def user_count() -> int:
    with SessionLocal() as db:
        return len(db.scalars(select(User)).all())
