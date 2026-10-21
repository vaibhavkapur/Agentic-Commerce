# Deployment

[Documentation](index.md) · [Getting Started](getting-started.md) · [Repository README](../README.md)

## Current Status

This is a local MVP. A hosted demo, deployment automation, and operational logging are not included. The local workflow is described in [Getting Started](getting-started.md).

## Hosted Configuration

Use [Configuration](configuration.md) to select PostgreSQL and private Supabase Storage, apply the schema, set the JWT verification secret, and disable development login. Keep service-role and model keys on the backend. Configure the frontend API base and server CORS origins for the deployed host.

`AGENT_RUN_MODE=worker` queues investigations for `python -m app.worker`; the API and worker need access to the same application data and SQLite checkpoint store. This is not a distributed checkpoint service. The frontend currently polls; Supabase Realtime subscriptions are not implemented.

Before a hosted release, validate authentication, tenant isolation, storage policies, migrations, backup/restore, worker restarts, TLS, monitoring, and rate limits in that environment. [Testing](testing.md) covers the existing local checks. Exporting an instruction does not execute a payment.
