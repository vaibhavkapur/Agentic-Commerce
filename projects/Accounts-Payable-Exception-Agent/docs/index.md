# Accounts Payable Exception Agent

An assistant for finance teams that investigates supplier invoices, resolves missing information, and prepares evidence-backed payment requests for human approval.

[Get Started](getting-started.md) · [API Reference](api-reference.md) · [Repository README](../README.md)

## Key Features

- Immutable document versions, field extraction, and evidence-linked invoice exceptions.
- Deterministic checks for totals, duplicates, purchase-order mismatches, incomplete delivery, and beneficiary changes.
- Clarification drafts, case history, version-bound human approval, and idempotent instruction export.

## Tech Stack and Scope

Python 3.12+, FastAPI, SQLAlchemy, LangGraph, React, TypeScript, and Vite. SQLite and local files are the defaults; Supabase PostgreSQL/Auth/Storage and model-assisted drafting are optional. The UI polls for updates. No bank payment submission, hosted demo, or production readiness is claimed.

## Documentation

- [Getting Started](getting-started.md)
- [Architecture](architecture.md)
- [API Reference](api-reference.md)
- [Configuration](configuration.md)
- [Database](database.md)
- [Testing](testing.md)
- [Deployment](deployment.md)
- [Demo Script](demo-script.md)
- [Recorded Test Report](test-report.md)
- [Product and Design Notes](design-notes.md)

## Project Structure

- `backend/app/`: API, domain services, document extraction, LangGraph, and worker.
- `backend/supabase/migrations/`: PostgreSQL schema and access policies.
- `backend/tests/` and `backend/eval/`: application checks and synthetic evaluation harness.
- `frontend/src/`: case workspace, vendor administration, approvals, and timeline.
- `docs/`: setup, architecture, API, configuration, testing, deployment, and demonstration.

## Related Projects

These are independent companion repositories, not runtime dependencies or claims of implemented integrations.

- [Merchant Integration Copilot](https://github.com/vaibhavkapur/Merchant-Integration-Copilot)
- [Payment Incident Investigator](https://github.com/vaibhavkapur/Payment-Incident-Investigator)
