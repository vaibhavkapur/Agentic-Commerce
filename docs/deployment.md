# Deployment

[Documentation](index.md) · [Getting Started](getting-started.md) · [Repository README](../README.md)

## Current Status

The application is a local MVP and has not been published as a hosted service. The [original build brief](BUILD_BRIEF.md) describes design intent, not a completed production platform.

## Local Built App

```bash
npm ci
npm run build
npm start
```

The built UI and API are served on `http://127.0.0.1:4318` by default. Local persistence is `.data/projects.json`.

## Hosted Prerequisites

Non-loopback listening requires Supabase authentication. Configure `HOST`, `APP_ORIGIN`, TLS, organization membership, and deployment-specific evaluator isolation before exposing intake. Apply the [migration](../supabase/migration.sql) and use the server-side variables in [Configuration](configuration.md).

## Remaining Scope

validated remote isolation and stronger evaluator tamper resistance; durable hosted worker queue/crash recovery; end-to-end merchant-specific provider checks; transaction-safe event deduplication; normalized Supabase metadata/storage/realtime; hosted security validation; and a statistically meaningful held-out benchmark with cost/usage measurements. Tests cover a second layout and malicious-instruction fixture, not a full benchmark. No GitHub merge, live-account access, or production deployment is enabled.
