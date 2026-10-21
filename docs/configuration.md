# Configuration

[Documentation](index.md) · [Getting Started](getting-started.md) · [Repository README](../README.md)

Copy `backend/.env.example` to `backend/.env` and uncomment what you need. Every setting has a development default. The important ones:

- `DATABASE_URL` — `postgresql+psycopg://...` for Supabase PostgreSQL (install the extra with `uv pip install --python .venv/bin/python -e ".[postgres]"` and apply `backend/supabase/migrations/0001_initial.sql` first).
- `AUTH_JWT_SECRET` — set to the Supabase project JWT secret so tokens issued by Supabase Auth verify; set `DEV_LOGIN_ENABLED=false` outside local development.
- `STORAGE_BACKEND=supabase`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_STORAGE_BUCKET` — private bucket for uploads. The service role key is read by the API only and never sent to the browser.
- `OPENAI_API_KEY`, `OPENAI_MODEL` — enable model-backed drafting and summaries; omit for the deterministic baseline.
- `AGENT_RUN_MODE=worker` plus `.venv/bin/python -m app.worker` — run investigations in a separate process with the same checkpoint database.

`.env` files are ignored by git. Do not put provider or service role keys in `frontend/`; the browser only ever holds the user's own session token.

The complete variable templates are [backend/.env.example](../backend/.env.example) and [frontend/.env.example](../frontend/.env.example). Defaults are defined in [config.py](../backend/app/config.py).
