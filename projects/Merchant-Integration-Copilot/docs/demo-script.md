# Demo Script

[Documentation](index.md) · [Getting Started](getting-started.md) · [Repository README](../README.md)

## Sample Walkthrough

1. Follow [Getting Started](getting-started.md) and open `http://127.0.0.1:5173`.
2. Open **Northstar checkout**, created on first start. Inspect its source and the generated webhook patch.
3. Review the diff and source digest. The initial patch uses deterministic source analysis and has not been executed.
4. Select **Run verification**. Inspect each evidence label. Static analysis can run without credentials; Docker and Stripe report blocked when unconfigured.
5. Download the patch and JSON report. Apply only against the matching original source, using `git apply --check` first as described in [Source Contract](source-contract.md).

## Isolated Verification

Start Docker, run `npm run runner:build`, set `RUNNER_ENABLED=true` in `.env`, and restart the app. Run verification again and inspect the local HMAC fixture results separately from provider results.

Stripe checks exercise the server-controlled adapter and need a sandbox key; they do not prove the merchant integration works end to end. OpenAI generation requires a key and an explicit **OpenAI agent** selection.

## Screenshots

- [Dashboard](dashboard.jpg)
- [Verification](verification.jpg)
