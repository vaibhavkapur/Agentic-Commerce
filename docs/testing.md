# Testing

[Documentation](index.md) · [Getting Started](getting-started.md) · [Repository README](../README.md)

```bash
cd backend
.venv/bin/pytest                        # includes the required application checks
.venv/bin/ruff check .
.venv/bin/python -m eval.run --repeats 2   # writes eval/reports/<run-id>.{json,md} and latest.md
cd ../frontend && npm run typecheck
```

`eval.run` exits non-zero if any scenario fails. Use `--seed`, `--per-kind-dev`, and `--per-kind-held-out` to change the corpus; the report records the corpus version, seed, model, prompt version, and repeat count.

## Evaluation Design and Acceptance Criteria

Create a versioned corpus of synthetic invoices and supporting documents. Separate development cases from held-out suppliers and document layouts. Run the actual model as well as a deterministic baseline, recording the model, prompt, fixture version, and repeated-run settings.

Measure field-extraction accuracy, exception precision and recall, evidence-reference correctness, unnecessary clarification requests, completion rate, latency, and model cost per case. Report sample sizes and failures alongside aggregate results.

Required application checks:

- Cross-organization access is denied through both API and storage paths.
- A submitter cannot approve their own request.
- Changed beneficiary details and unresolved blocking exceptions prevent export.
- Revised evidence invalidates an existing approval.
- Restarting during an approval interruption preserves the case and pending decision.
- Replayed approval and export requests do not create duplicate effects.
- Malicious document text cannot change permissions or bypass approval.

Passing these checks demonstrates the tested scenarios, not a general guarantee of production safety.

Recorded historical measurements and their limitations are in [Recorded Test Report](test-report.md).
