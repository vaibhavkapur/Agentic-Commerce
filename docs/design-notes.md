# Product and Design Notes

[Documentation](index.md) · [Getting Started](getting-started.md) · [Repository README](../README.md)

These sections preserve the original product goals and target design. For current behavior, use [Architecture](architecture.md); planned features are not automatically implemented.

## The problem

An invoice can be legitimate but still unsuitable for payment: its amount may exceed the purchase order, the delivery may be incomplete, or its beneficiary details may differ from the approved vendor record. Finance teams must gather documents, compare versions, explain discrepancies, and obtain the right approval.

This product turns that investigation into a shared case with source evidence, explicit decisions, and a reviewable payment instruction.

### Example

A supplier submits a GBP 2,400 invoice against a GBP 2,000 purchase order. Only part of the shipment has arrived, and the invoice lists a different bank account. The agent identifies all three discrepancies, cites the supporting records, and prepares a clarification request. It cannot change the approved beneficiary or authorize payment.

## Who it serves

- Accounts payable specialists who assemble and investigate cases.
- Budget owners who confirm purchase and delivery information.
- Finance approvers who review the exact proposed payment.
- Administrators who manage organization membership and approved vendor records.

## MVP scope

- One currency: GBP, with amounts stored as integer minor units.
- PDF invoice, purchase-order, and delivery-confirmation uploads.
- A structured, administrator-managed register of approved vendors and beneficiaries.
- Extraction of invoice number, supplier, line items, totals, dates, and payment details, with document and page references.
- Checks for duplicate invoices, inconsistent totals, purchase-order mismatches, incomplete delivery, and changed beneficiary details.
- A case workspace with clarification drafts, comments, evidence, and an approval queue.
- A fixed approval policy: an authorized approver must be different from the submitter.
- Export of an approved payment instruction as JSON and a human-readable summary.

The first release ends at instruction export. It does not submit bank payments, independently verify bank-account ownership, calculate tax liability, or integrate with a complete accounting system. A later provider-sandbox milestone can consume the approved instruction through a separately validated adapter.

## Agent design

Use **Python and LangGraph** for the investigation workflow. Suggested nodes are `extract_documents`, `load_vendor`, `match_purchase_order`, `check_exceptions`, `request_information`, `prepare_review`, and `await_approval`.

The model can:

- Interpret inconsistent document layouts and supplier descriptions.
- Propose document matches and explain ambiguity.
- Choose which permitted evidence-retrieval tool to call next.
- Draft focused clarification requests and a cited case summary.

Ordinary application code must:

- Validate extraction schemas and monetary values.
- Enforce organization access, approval roles, and separation of duties.
- Calculate totals and detect exact duplicates.
- Enforce beneficiary restrictions and approval freshness.
- Create exports and record authoritative case transitions.

LangGraph checkpoints persist investigation progress and interruptions. The application database remains authoritative for approvals, exported instructions, and document versions. Resuming a graph must recheck current authority before exporting anything.

Uploaded documents and retrieved content are evidence, not instructions for the agent. An instruction embedded in a PDF must not change the agent's permissions or tools.

## Product experience

- **Inbox:** assigned cases, outstanding evidence, and approval requests.
- **Case view:** documents alongside extracted fields, with corrections recorded as new versions.
- **Exception review:** each finding, its evidence, and its resolution history.
- **Approval view:** the exact instruction, unresolved blockers, and approver identity.
- **Timeline:** document changes, model activity, human decisions, and export events.

The interface must distinguish extracted claims, verified records, agent recommendations, and human decisions.

## Implementation milestones

1. **Case workspace:** schema, authentication, memberships, private uploads, and a basic React case view. — done
2. **Evidence pipeline:** document extraction, source references, corrections, and deterministic checks. — done
3. **Agent investigation:** LangGraph tools, clarification drafts, persistent checkpoints, and run traces. — done
4. **Approval and export:** version-bound decisions, separation of duties, idempotent export, and audit history. — done
5. **Evaluation and deployment:** held-out cases and access tests are done; hosted demo, deployment automation, and operational logging are not.
6. **Optional payment sandbox:** choose an accessible provider, implement its adapter, and verify submission/recovery behavior separately from the instruction-export MVP. — not started
