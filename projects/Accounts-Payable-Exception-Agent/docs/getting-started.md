# Getting Started

[Documentation](index.md) · [Getting Started](getting-started.md) · [Repository README](../README.md)

## Prerequisites

- Python 3.12+. The repository uses [uv](https://docs.astral.sh/uv/) for the virtual environment; `uv python install 3.12` fetches an interpreter if the system one is older.
- Node.js 20.19+ or 22.12+ and npm, matching the locked Vite engine requirements.

## Clone

```bash
git clone https://github.com/vaibhavkapur/Agentic-Commerce.git
cd Agentic-Commerce/projects/Accounts-Payable-Exception-Agent
```

## Backend

```bash
cd backend
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m app.seed            # creates data/ap.db, demo PDFs, two organizations
.venv/bin/uvicorn app.main:app --reload --port 8000
```

The API is at `http://127.0.0.1:8000` (`/health`, interactive docs at `/docs`). Seeded development logins (`POST /auth/dev-login` with `{"email": ...}`, no password):

- `admin@acme.test` (admin), `ap@acme.test` (AP specialist), `budget@acme.test` (budget owner), `approver@acme.test` (approver) in organization Acme Holdings plc.
- `owner@globex.test` (admin) in Globex, for cross-organization checks.

## Frontend

Run these commands in a second terminal from the project directory.

```bash
cd frontend
npm ci
npm run dev                             # http://127.0.0.1:5173, proxies /api to the backend
```

If the API runs on another port, copy `frontend/.env.example` to `frontend/.env.local` and set `VITE_API_PROXY_TARGET`. `npm run build` produces `frontend/dist`.

See [Configuration](configuration.md) for environment variables and [Testing](testing.md) for validation commands.
