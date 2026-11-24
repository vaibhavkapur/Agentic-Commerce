# API Reference

[Documentation](index.md) · [Getting Started](getting-started.md) · [Repository README](../README.md)

The API runs at `http://127.0.0.1:8000`. Interactive request and response schemas are available at `/docs`; the machine-readable schema is at `/openapi.json`.

Use `POST /auth/dev-login` with `{"email":"ap@acme.test"}` only in local development, then send the returned token as `Authorization: Bearer <token>`. Organization-scoped routes also enforce membership and role checks. File downloads use short-lived signed tokens. See [schemas.py](../backend/app/schemas.py) for request models.

`GET /health` reports API health. The route inventory below is taken from the implementation.

## Approvals

[Route implementation](../backend/app/routers/approvals.py)

- `GET /orgs/{organization_id}/approvals`
- `POST /orgs/{organization_id}/cases/{case_id}/approvals`
- `POST /orgs/{organization_id}/cases/{case_id}/approvals/{approval_id}/decision`
- `POST /orgs/{organization_id}/cases/{case_id}/export`
- `GET /orgs/{organization_id}/cases/{case_id}/export`
- `GET /orgs/{organization_id}/cases/{case_id}/export/summary.txt`

## Auth

[Route implementation](../backend/app/routers/auth.py)

- `POST /auth/dev-login`
- `GET /auth/me`

## Cases

[Route implementation](../backend/app/routers/cases.py)

- `GET /orgs/{organization_id}/cases`
- `POST /orgs/{organization_id}/cases`
- `GET /orgs/{organization_id}/cases/{case_id}`
- `POST /orgs/{organization_id}/cases/{case_id}/assign`
- `POST /orgs/{organization_id}/cases/{case_id}/comments`
- `POST /orgs/{organization_id}/cases/{case_id}/documents`
- `POST /orgs/{organization_id}/cases/{case_id}/documents/{document_version_id}/fields`
- `POST /orgs/{organization_id}/cases/{case_id}/checks`
- `POST /orgs/{organization_id}/cases/{case_id}/exceptions/{exception_id}`
- `POST /orgs/{organization_id}/cases/{case_id}/drafts/{draft_id}`
- `POST /orgs/{organization_id}/cases/{case_id}/investigate`
- `GET /orgs/{organization_id}/cases/{case_id}/runs`
- `POST /orgs/{organization_id}/cases/{case_id}/close`
- `GET /orgs/{organization_id}/cases/{case_id}/timeline`

## Files

[Route implementation](../backend/app/routers/files.py)

- `GET /files/{token}`

## Organizations

[Route implementation](../backend/app/routers/organizations.py)

- `GET /orgs/{organization_id}/members`
- `POST /orgs/{organization_id}/members`
- `GET /orgs/{organization_id}/events`
- `GET /orgs/{organization_id}/vendors`
- `POST /orgs/{organization_id}/vendors`
- `POST /orgs/{organization_id}/vendors/{vendor_id}/beneficiaries`
- `POST /orgs/{organization_id}/vendors/{vendor_id}/beneficiaries/{beneficiary_id}/verify`
