# Recorded Test Report

[Documentation](index.md) · [Getting Started](getting-started.md) · [Repository README](../README.md)

## Historical Baseline

The following measurements were recorded in the project before this documentation reorganization, on 20 October 2026. They are historical results, not a new test run.


Each required check above has an automated test in `backend/tests` (33 tests, all passing with `pytest`). They cover cross-organization API and signed-file access, submitter self-approval, changed-beneficiary and open-blocker export refusal, approval invalidation on revised evidence, graph restart during the approval interrupt, replayed approval and export requests, and prompt-injection text in uploaded PDFs.

The evaluation harness (`backend/eval`) generates `corpus-v1`: 10 scenario kinds (clean, arithmetic error, PO overage, PO number mismatch, incomplete delivery, missing delivery, duplicate, changed beneficiary, unknown supplier, embedded instructions) rendered as PDFs in two development layouts (`classic`, `compact`) and one held-out layout (`formal`), with held-out supplier names. Latest run of the deterministic baseline, 50 scenarios × 2 repeats:

| Split | n | Field acc. | Exc. precision | Exc. recall | Evidence refs | Unnecessary clarif. | Completion | Latency mean/p95 (s) | Model calls |
|---|---|---|---|---|---|---|---|---|---|
| dev | 60 | 1.0 | 1.0 | 1.0 | 1.0 | 0 | 1.0 | 0.008/0.011 | 0 |
| held_out | 40 | 1.0 | 1.0 | 1.0 | 1.0 | 0 | 1.0 | 0.007/0.010 | 0 |

Caveats: the corpus is synthetic text-based PDFs produced by this repository's own generator, so the extractor and the documents share conventions; the numbers show the pipeline is consistent, not that it generalizes to scanned or supplier-specific layouts. The model-backed run (`OPENAI_API_KEY` set) has not been executed here, so no model cost figures are reported. Full reports with per-field and per-layout breakdowns and the failure list are written to `backend/eval/reports/` by `python -m eval.run`.

See [the recorded report](reports/20261020T014812Z.md) and [Testing](testing.md) to reproduce the evaluation.

## Publication Validation

Documentation links, common guide structure, tracked-file exclusions, and preservation of application source passed publication checks. Application code is unchanged by the documentation reorganization.

## Verification on 21 October 2026

- Backend: 33 tests passed with `python -m pytest -q -p no:cacheprovider`.
- Frontend: `npm run build` passed (TypeScript and Vite).
- Model-backed evaluation, hosted Supabase, and bank/provider integrations were not run.

These checks reused the supplied local dependency installations. They do not establish a fresh dependency install or production readiness.
