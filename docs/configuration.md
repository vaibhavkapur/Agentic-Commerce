# Configuration

[Documentation](index.md) · [Getting Started](getting-started.md) · [Repository README](../README.md)

Copy `.env.example` to `.env`, configure services on the server, and restart. Never use `VITE_` variables for secrets.

### OpenAI

Set `OPENAI_API_KEY` and optionally `OPENAI_MODEL` (default `gpt-4.1`). Select **OpenAI agent** in the project plan. The Node 20-compatible Agents SDK is pinned to `0.3.0`. Accepted source text is sent to OpenAI only in this mode. The service limits each task to 12 turns, 6,000 output tokens per response, and 90 seconds, with 20 generation attempts per organization per hour. Tracing is disabled.

Model-backed generation was not exercised without a key. Official references: [Agents SDK](https://developers.openai.com/api/docs/guides/agents/sdk), [agent definitions](https://developers.openai.com/api/docs/guides/agents/define-agents).

### Docker evaluator

Start Docker, run `npm run runner:build`, set `RUNNER_ENABLED=true`, and restart.

The controller runs the fixed `ralio-runner:1` image with no network, no host mounts or engine socket mount, no capabilities, a read-only root, a non-root UID, 0.5 CPU, 192 MB memory, 48 processes, bounded tmpfs, 64 KB output, and a 30-second deadline. Source enters through stdin. Merchant dependency installation and scripts are never run. Cancellation kills the controller and requests forced container removal.

The immutable harness in `runner/evaluate.mjs` is outside the candidate workspace. It starts the candidate as a child with output discarded, then sends HTTP requests. It checks valid signatures, tampered payloads, invalid signatures, and repeated delivery. These are **local HMAC fixtures**, not provider calls.

The supported fixture contract requires an Express app exported as `default` or `app`, a literal webhook route containing `webhook` in the entry file, and environment-based Stripe credentials. Duplicate-effect checking requires `/test/fulfillments` returning `{ "count": 1 }`; without it that scenario is blocked. This endpoint is for test fixtures only. The harness pins Express 5.1.0, Stripe 18.5.0, and TypeScript 5.9.2 independently of uploaded dependency declarations.

The image and fixtures were validated locally with Docker 29.8.0: the original sample fails, its patch passes all four scenarios, a second repository layout passes, network access and host/socket access are denied, the root is read-only, and cancellation removes the container. Keep intake local until deployment-specific adversarial isolation testing passes. This is a local controller, not a production multi-tenant execution service.

### Stripe

Set `STRIPE_SECRET_KEY` to a sandbox key beginning with `sk_test_`. Live/restricted keys are refused. The server-controlled adapter creates $1 test PaymentIntents and exercises additional action, decline, and idempotent retry. It records provider IDs and uses API version `2025-08-27.basil` via Stripe 18.5.0.

These checks verify the **controlled adapter**, not the merchant's end-to-end integration. They are labeled separately throughout the product. No Stripe calls were made during implementation because no key was configured.

References: [webhooks](https://docs.stripe.com/events/manage-webhook-endpoints), [idempotency](https://docs.stripe.com/api/idempotent_requests), [Payment Intents lifecycle](https://docs.stripe.com/payments/paymentintents/lifecycle).

### Supabase

Apply `supabase/migration.sql` once in a new project. Set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY`. Partial configuration fails closed. Through the Supabase administrator console, create an Auth user, organization, and membership. The UI supports email/password sign-in.

The API validates token and membership for each project/artifact request, and scopes every database operation even with the service role. Clients have RLS-protected reads and no direct writes. An `x-organization-id` header selects among actual memberships; the UI defaults to the first organization.

This MVP stores bounded project documents, source, patches, and evidence in PostgreSQL JSONB. Supabase Storage/Realtime are not integrated; progress uses polling. Hosted authentication/RLS were not exercised without a configured Supabase project. The schema does not claim to implement all normalized entities from the proposal.

Non-loopback listening requires Supabase. Configure `HOST`, `APP_ORIGIN`, TLS, and isolation before external deployment. The application has not been published externally.
