# Database

[Documentation](index.md) · [Getting Started](getting-started.md) · [Repository README](../README.md)

## Local Store

[server/store.ts](../server/store.ts) persists projects in `.data/projects.json` for local mode. A project holds its source snapshot, inspection, generated patch, and verification runs. The directory is ignored by Git. Source and patch digests identify the version associated with each report.

## Supabase

Apply `supabase/migration.sql` once in a new project. Set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY`. Partial configuration fails closed. Through the Supabase administrator console, create an Auth user, organization, and membership. The UI supports email/password sign-in.

The API validates token and membership for each project/artifact request, and scopes every database operation even with the service role. Clients have RLS-protected reads and no direct writes. An `x-organization-id` header selects among actual memberships; the UI defaults to the first organization.

This MVP stores bounded project documents, source, patches, and evidence in PostgreSQL JSONB. Supabase Storage/Realtime are not integrated; progress uses polling. Hosted authentication/RLS were not exercised without a configured Supabase project. The schema does not claim to implement all normalized entities from the proposal.

Non-loopback listening requires Supabase. Configure `HOST`, `APP_ORIGIN`, TLS, and isolation before external deployment. The application has not been published externally.

The [migration](../supabase/migration.sql) defines `organizations`, `memberships`, and `copilot_projects`. Project data is stored as bounded JSONB documents with an organization identifier. API queries remain organization-scoped even when using the service-role key. Clients have RLS-protected reads and no direct writes.

Active verification controllers and generation rate limits live in process memory. A durable hosted queue and crash-recovery design remain roadmap items; PostgreSQL persistence alone does not provide them.
