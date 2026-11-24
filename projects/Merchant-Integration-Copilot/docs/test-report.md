# Recorded Test Report

[Documentation](index.md) · [Getting Started](getting-started.md) · [Repository README](../README.md)

## Historical Implementation Checks

The original project documentation records local Docker validation with Docker 29.8.0: the original sample failed, its patch passed four webhook scenarios, a second repository layout passed, network and host/socket access were denied, the root filesystem was read-only, and cancellation removed the container. These are historical statements from implementation; no standalone machine-readable run report was supplied with this folder.

OpenAI generation, actual Stripe sandbox calls, and hosted Supabase authentication/RLS were not exercised in that record. No statistically meaningful held-out benchmark or model cost result is claimed.

## Publication Validation

Documentation links, common guide structure, tracked-file exclusions, and preservation of application source passed publication checks. Application code is unchanged by the documentation reorganization. Use [Testing](testing.md) to run current acceptance checks.

## Verification on 21 October 2026

- `npm test`: 20 tests passed, including the local API acceptance workflow.
- `npm run build`: TypeScript checking and Vite production build passed.
- Docker acceptance, OpenAI generation, Stripe sandbox calls, and hosted Supabase were not rerun.

These checks reused the supplied local dependency installations. They do not establish a fresh dependency install or production readiness.
