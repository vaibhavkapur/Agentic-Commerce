"""Print the PostgreSQL DDL for the SQLAlchemy models (used for supabase/migrations)."""

from __future__ import annotations

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app import models  # noqa: F401  (registers the tables on Base.metadata)
from app.db import Base

HEADER = """\
-- Accounts Payable Exception Agent — initial schema for Supabase/PostgreSQL.
-- Generated from backend/app/models.py (SQLAlchemy metadata, postgresql dialect).
-- Regenerate after model changes with:
--   cd backend && .venv/bin/python -m scripts.export_schema > supabase/migrations/0001_initial.sql
--
-- The API connects with the service role / database owner and enforces tenancy
-- in application code (every query is scoped by organization membership).
-- Row Level Security is enabled below so that anon/authenticated roles using
-- the Supabase client directly cannot read these tables at all.
"""


def main() -> None:
    dialect = postgresql.dialect()
    chunks: list[str] = [HEADER]
    for table in Base.metadata.sorted_tables:
        chunks.append(str(CreateTable(table).compile(dialect=dialect)).strip() + ";")
        for index in table.indexes:
            chunks.append(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")
    chunks.append("-- Deny direct access from browser roles; only the API (service role) reads/writes.")
    chunks.extend(f"ALTER TABLE {table.name} ENABLE ROW LEVEL SECURITY;" for table in Base.metadata.sorted_tables)
    print("\n\n".join(chunks))


if __name__ == "__main__":
    main()
