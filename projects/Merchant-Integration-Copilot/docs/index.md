# Merchant Integration Copilot

A local workspace for inspecting Express payment integrations, generating reviewable patches, and reporting exactly what has been verified.

[Get Started](getting-started.md) · [API Reference](api-reference.md) · [Repository README](../README.md)

## Key Features

- Responsive dashboard, project search/filters, run history, documentation, and service settings.
- ZIP intake with traversal, symlink, special-file, duplicate-path, credential-pattern, file-count, and expanded-size validation. Source is read into bounded memory, never extracted to the host.
- Immutable source snapshots, SHA-256 digests, dependency and route inspection.
- Deterministic repair of supported Express JSON/raw-body ordering bugs across paths and route names. Ambiguous layouts are refused.
- Payment module scaffolding with stable idempotency keys, server-owned example prices, asynchronous states, and explicit application-specific decisions. Mounting, ownership, pricing, and durable effects require merchant review.
- Optional single-agent generation using the OpenAI Agents SDK, scoped inspection/docs tools, validated structured output, bounded turns/time, and trace exporting disabled.
- Allowlisted official documentation retrieval with timestamps. Unavailable references remain marked as not retrieved.
- Unified/split diffs, source explorer, patch downloads, JSON evidence reports, background verification, and cancellation.
- Loopback-only local mode, Host/origin checks, custom-header mutation protection, generation limits, and optional Supabase authentication, organization authorization, and persistence.

## Tech Stack and Scope

React / TypeScript / Express with local JSON persistence, optional OpenAI Agents SDK, Docker evaluator, Stripe sandbox adapter, and Supabase Auth/PostgreSQL. Patches and verification evidence carry source digests. Hosted multi-tenant execution and production deployment are not complete.

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
- [Source Contract](source-contract.md)
- [Original Build Brief](BUILD_BRIEF.md)

## Project Structure

- `src/` — React workspace, client, shared types, responsive styling.
- `server/` — API, archives, source analysis, agent, storage, verification.
- `runner/` — fixed container and independent local HTTP harness.
- `supabase/` — organization/membership/project schema and RLS.
- `tests/` — source, archive, authorization, evidence, cancellation, API workflow.
- `docs/` — implementation guides, screenshots, and the original `BUILD_BRIEF.md` proposal.

## Related Projects

These companion projects run independently.

- [Accounts Payable Exception Agent](../../Accounts-Payable-Exception-Agent/)
- [Payment Incident Investigator](../../Payment-Incident-Investigator/)
