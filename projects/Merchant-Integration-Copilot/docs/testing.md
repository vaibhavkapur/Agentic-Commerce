# Testing

[Documentation](index.md) · [Getting Started](getting-started.md) · [Repository README](../README.md)

## Application Checks

From the project directory, after `npm ci`:

```bash
npm test
npm run build
```

The tests in [tests/](../tests/) cover source analysis, archive validation, authorization, evidence, cancellation, and the API workflow. The build type-checks the application and produces `dist/`.

## Docker Acceptance

```bash
npm run runner:build
npm run test:runner
```

Docker must be running. These checks exercise the original sample, the generated patch, another repository layout, the evaluator restrictions, and cancellation. The image is fixed; uploaded dependency scripts are not installed or run.

## Evidence Labels

- **Generated:** a patch exists; execution is not implied.
- **Static analysis:** TypeScript transpiles; not a full typecheck or execution.
- **Isolated application:** the named independent fixtures ran inside Docker.
- **Stripe sandbox:** the controlled adapter made the named actual provider calls.
- **Blocked / failed / cancelled:** a prerequisite or check did not pass.

Regeneration preserves historical runs but excludes them from the new patch's exported report. Source/patch digests, dependency/API versions, prompt version, references, and scenario provenance travel with each report.



See [Configuration](configuration.md) for the Docker fixture contract and the controlled Stripe sandbox adapter. Historical implementation checks are described in [Recorded Test Report](test-report.md); no model benchmark or live provider result is implied by local tests.
