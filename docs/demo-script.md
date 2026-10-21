# Demo Script

[Documentation](index.md) · [Getting Started](getting-started.md) · [Repository README](../README.md)

Start with an invoice that is missing delivery evidence. Let the agent identify the gap and prepare a clarification. Supply the missing document, request approval, and restart the worker while it waits. After approval, upload a revised invoice and show that export is blocked until the new snapshot is approved. Finish with an idempotent export and a complete evidence trail.

The seed data sets this up as case **AP-DEMO-2** (Contoso invoice CC-3310 against PO-8102, no delivery note). After seeding:

1. Sign in as `ap@acme.test`, open AP-DEMO-2. The agent run shows the blocking `DELIVERY_MISSING` exception and a clarification draft addressed to the budget owner.
2. Upload `backend/data/demo/SR-0331-service-confirmation.pdf` as a delivery confirmation and click **Run investigation again**. The exception auto-resolves and the agent stops at `await_approval`.
3. Open **Approval & export** and request approval. Stop and restart the API (or the worker in worker mode); the case still shows the pending request and the interrupted run.
4. Sign in as `approver@acme.test` and approve from the **Approvals** queue. The graph resumes and completes. Signing in as `ap@acme.test` and trying to approve is refused.
5. Back as `ap@acme.test`, upload `backend/data/demo/CC-3310-revised.pdf` as a new invoice version. The approval is marked invalidated ("invoice document version 2 uploaded") and **Export payment instruction** is refused. Re-run checks, waive or resolve the new `PO_AMOUNT_EXCEEDED` finding with a note, request approval, and approve again as the approver.
6. Click **Export payment instruction** twice. The second call returns the same instruction and audit reference. The **Timeline** tab shows every upload, check, draft, decision, invalidation, and the single export.

Start with [Getting Started](getting-started.md); seed-generated PDFs remain local and are not committed.
