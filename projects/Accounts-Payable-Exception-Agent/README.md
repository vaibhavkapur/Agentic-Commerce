# Accounts Payable Exception Agent

An assistant for finance teams that investigates supplier invoices, resolves missing information, and prepares evidence-backed payment requests for human approval.

> **[Read the full documentation](docs/index.md)**

Built with Python, FastAPI, LangGraph, React, and TypeScript. The local MVP uses SQLite and private local document storage without external credentials. Optional Supabase and OpenAI integrations are configured separately. The workflow ends at an approved instruction export; it does not submit bank payments.

## Getting Started

```bash
# Requires Python 3.12+, uv, Node.js 20.19+ (or 22.12+), and npm
git clone https://github.com/vaibhavkapur/Agentic-Commerce.git
cd Agentic-Commerce/projects/Accounts-Payable-Exception-Agent
cd backend
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m app.seed
.venv/bin/uvicorn app.main:app --reload --port 8000
```

In a second terminal, from the project directory:

```bash
cd frontend
npm ci
npm run dev
```

- UI: http://127.0.0.1:5173
- API and interactive API reference: http://127.0.0.1:8000/docs
- Development login: `ap@acme.test`; approver: `approver@acme.test`

See [Getting Started](docs/getting-started.md) for setup and seeded users, and [Configuration](docs/configuration.md) for optional services.

## Quick Example

1. Sign in as `ap@acme.test` and open **AP-DEMO-2**, which is missing delivery evidence.
2. Upload `backend/data/demo/SR-0331-service-confirmation.pdf` as a delivery confirmation and run the investigation again.
3. Request approval, then sign in as `approver@acme.test` to review and approve the exact instruction.
4. Return as `ap@acme.test` to export. Uploading the revised invoice invalidates that approval and blocks another export until review.

See the [Demo Script](docs/demo-script.md) for restart and replay checks. The [Recorded Test Report](docs/test-report.md) distinguishes the synthetic deterministic baseline from model-backed behavior; a hosted demo and deployment automation remain open.
