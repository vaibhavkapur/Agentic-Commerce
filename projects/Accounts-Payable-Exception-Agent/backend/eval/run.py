"""Evaluation runner.

Usage (from backend/):
    python -m eval.run                       # deterministic baseline on the full corpus
    python -m eval.run --repeats 3           # repeated runs to expose non-determinism
    OPENAI_API_KEY=... python -m eval.run    # the configured model drafts/summaries + proposals

Each run executes the whole pipeline (PDF -> extraction -> agent graph -> exceptions) against a
throwaway database and writes a JSON and Markdown report to eval/reports/.
"""

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="ap-eval-"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP / 'eval.db'}")
os.environ.setdefault("STORAGE_DIR", str(_TMP / "storage"))
os.environ.setdefault("LANGGRAPH_CHECKPOINT_PATH", str(_TMP / "checkpoints.sqlite"))
os.environ.setdefault("AGENT_RUN_MODE", "inline")

from sqlalchemy import select  # noqa: E402

from app.agent import runner  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Case, CaseException, ClarificationDraft, DocumentVersion, Membership, Organization, User  # noqa: E402
from app.services import vendors as vendor_service  # noqa: E402
from app.services.documents import current_documents, effective_fields, field_values  # noqa: E402
from app.storage import build_storage  # noqa: E402
from eval.corpus import CORPUS_VERSION, Scenario, build_corpus  # noqa: E402

SCORED_FIELDS = ["invoice_number", "supplier_name", "invoice_date", "due_date", "po_number", "subtotal_minor",
                 "vat_minor", "total_minor", "bank_account_name", "bank_sort_code", "bank_account_number", "bank_iban"]
IGNORED_CODES = {"SUSPICIOUS_DOCUMENT_TEXT"}  # informational; not scored as an exception


def _setup_org(db, scenario: Scenario, index: int):
    org = Organization(name=f"Eval {index}", slug=f"eval-{index}-{int(time.time()*1000)}")
    db.add(org)
    db.flush()
    user = User(email=f"eval{index}-{org.slug}@eval.test", display_name="Eval User")
    db.add(user)
    db.flush()
    db.add(Membership(organization_id=org.id, user_id=user.id, role="ap_specialist"))
    vendor = vendor_service.create_vendor(db, organization_id=org.id, vendor_code=scenario.vendor_code,
                                          name=scenario.supplier, tax_id=None, actor_id=user.id)
    b = scenario.beneficiary
    vendor_service.add_beneficiary_version(db, vendor=vendor, account_name=b["account_name"], sort_code=b["sort_code"],
                                           account_number=b["account_number"], iban=b["iban"], actor_id=user.id,
                                           verified=True, note="eval")
    db.commit()
    return org, user


def _case_with_documents(db, org, user, reference, documents, storage):
    from app.services.documents import store_document_version

    case = Case(organization_id=org.id, reference=reference, title=reference, created_by=user.id, assigned_to=user.id)
    db.add(case)
    db.flush()
    for kind in ("invoice", "purchase_order", "delivery_confirmation"):
        if kind in documents:
            store_document_version(db, case=case, kind=kind, filename=f"{kind}.pdf", data=documents[kind],
                                   uploaded_by=user.id, storage=storage)
    db.commit()
    return case


def evaluate_scenario(scenario: Scenario, index: int, storage) -> dict:
    with SessionLocal() as db:
        org, user = _setup_org(db, scenario, index)
        if scenario.prior_invoice_number:
            prior = _case_with_documents(db, org, user, "PRIOR", {"invoice": scenario.documents["invoice"]}, storage)
            prior.status = "exported"
            db.commit()
        case = _case_with_documents(db, org, user, scenario.id, scenario.documents, storage)
        started = time.perf_counter()
        run = runner.start_run(db, case, user.id)
        latency = time.perf_counter() - started
        db.expire_all()
        case = db.get(Case, case.id)
        invoice_doc = next(d for d in current_documents(db, case) if d.kind == "invoice")
        values = field_values(effective_fields(db, invoice_doc.id))
        exceptions = list(db.scalars(select(CaseException).where(CaseException.case_id == case.id)))
        drafts = list(db.scalars(select(ClarificationDraft).where(ClarificationDraft.case_id == case.id)))
        docs = {d.id: d for d in db.scalars(select(DocumentVersion).where(DocumentVersion.case_id == case.id))}

        field_results = {}
        for name in SCORED_FIELDS:
            expected = scenario.truth.get(name)
            got = values.get(name)
            field_results[name] = (str(got) if got is not None else None) == (str(expected) if expected is not None else None)
        truth_lines = [(li["description"], li["quantity"], li["unit_price_minor"], li["line_total_minor"]) for li in scenario.truth["line_items"]]
        got_lines = [(li["description"], li["quantity"], li["unit_price_minor"], li["line_total_minor"]) for li in (values.get("line_items") or [])]
        field_results["line_items"] = truth_lines == got_lines

        raised = {e.code for e in exceptions if e.status == "open" and e.code not in IGNORED_CODES}
        expected = scenario.expected_exceptions
        tp, fp, fn = raised & expected, raised - expected, expected - raised

        evidence_checks = []
        for exc in exceptions:
            for link in exc.evidence:
                if link.document_version_id is None:
                    evidence_checks.append(link.record_type is not None)
                    continue
                doc = docs.get(link.document_version_id)
                ok = doc is not None and (link.page is None or 1 <= link.page <= doc.page_count)
                if ok and link.excerpt and link.page and not link.excerpt.startswith("PO total"):
                    first_line = link.excerpt.splitlines()[0].strip()
                    ok = first_line in (doc.text_pages[link.page - 1] or "")
                evidence_checks.append(bool(ok))

        return {
            "scenario": scenario.id, "split": scenario.split, "kind": scenario.kind, "layout": scenario.layout,
            "run_status": run.status, "run_outcome": run.outcome, "error": run.error,
            "latency_seconds": round(latency, 3), "model_calls": run.model_calls, "tool_calls": run.tool_calls,
            "fields": field_results,
            "exceptions": {"expected": sorted(expected), "raised": sorted(raised), "tp": len(tp), "fp": sorted(fp), "fn": sorted(fn)},
            "evidence_refs": {"checked": len(evidence_checks), "correct": sum(evidence_checks)},
            "clarification_drafted": bool(drafts),
            "unnecessary_clarification": bool(drafts) and not scenario.expected_needs_information,
            "missed_clarification": (not drafts) and scenario.expected_needs_information,
            "case_status": case.status,
        }


def summarise(results: list[dict]) -> dict:
    def block(rows: list[dict]) -> dict:
        if not rows:
            return {"n": 0}
        field_total = sum(len(r["fields"]) for r in rows)
        field_correct = sum(sum(1 for v in r["fields"].values() if v) for r in rows)
        tp = sum(r["exceptions"]["tp"] for r in rows)
        fp = sum(len(r["exceptions"]["fp"]) for r in rows)
        fn = sum(len(r["exceptions"]["fn"]) for r in rows)
        ev_checked = sum(r["evidence_refs"]["checked"] for r in rows)
        ev_correct = sum(r["evidence_refs"]["correct"] for r in rows)
        latencies = [r["latency_seconds"] for r in rows]
        return {
            "n": len(rows),
            "field_accuracy": round(field_correct / field_total, 4) if field_total else None,
            "exception_precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "exception_recall": round(tp / (tp + fn), 4) if tp + fn else None,
            "evidence_reference_correctness": round(ev_correct / ev_checked, 4) if ev_checked else None,
            "unnecessary_clarifications": sum(1 for r in rows if r["unnecessary_clarification"]),
            "missed_clarifications": sum(1 for r in rows if r["missed_clarification"]),
            "completion_rate": round(sum(1 for r in rows if r["run_status"] in ("completed", "interrupted")) / len(rows), 4),
            "latency_seconds": {"mean": round(statistics.mean(latencies), 3), "p95": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))], 3)},
            "model_calls_per_case": round(statistics.mean(r["model_calls"] for r in rows), 2),
            "tool_calls_per_case": round(statistics.mean(r["tool_calls"] for r in rows), 2),
        }

    per_field: dict[str, list[bool]] = {}
    for r in results:
        for name, ok in r["fields"].items():
            per_field.setdefault(name, []).append(ok)
    return {
        "all": block(results),
        "dev": block([r for r in results if r["split"] == "dev"]),
        "held_out": block([r for r in results if r["split"] == "held_out"]),
        "by_layout": {layout: block([r for r in results if r["layout"] == layout]) for layout in sorted({r["layout"] for r in results})},
        "field_accuracy_by_field": {name: round(sum(v) / len(v), 4) for name, v in per_field.items()},
        "failures": [
            {"scenario": r["scenario"], "fp": r["exceptions"]["fp"], "fn": r["exceptions"]["fn"],
             "wrong_fields": [k for k, v in r["fields"].items() if not v], "error": r["error"],
             "unnecessary_clarification": r["unnecessary_clarification"]}
            for r in results
            if r["exceptions"]["fp"] or r["exceptions"]["fn"] or r["error"] or r["unnecessary_clarification"]
            or r["missed_clarification"] or not all(r["fields"].values())
        ],
    }


def to_markdown(report: dict) -> str:
    s = report["summary"]
    lines = [f"# Evaluation report {report['run_id']}", "",
             f"- Corpus: `{report['corpus_version']}` (seed {report['seed']}), {report['scenarios']} scenarios x {report['repeats']} repeat(s)",
             f"- Model: `{report['model']}`; prompt `{report['prompt_version']}`; run mode `{report['mode']}`",
             f"- Generated: {report['generated_at']}", "",
             "| Split | n | Field acc. | Exc. precision | Exc. recall | Evidence refs | Unnecessary clarif. | Completion | Latency mean/p95 (s) | Model calls |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for split in ("all", "dev", "held_out"):
        b = s[split]
        if b["n"]:
            lines.append(f"| {split} | {b['n']} | {b['field_accuracy']} | {b['exception_precision']} | {b['exception_recall']} | "
                         f"{b['evidence_reference_correctness']} | {b['unnecessary_clarifications']} | {b['completion_rate']} | "
                         f"{b['latency_seconds']['mean']}/{b['latency_seconds']['p95']} | {b['model_calls_per_case']} |")
    lines += ["", "## By layout", ""]
    for layout, b in s["by_layout"].items():
        lines.append(f"- `{layout}`: n={b['n']}, field accuracy {b['field_accuracy']}, precision {b['exception_precision']}, recall {b['exception_recall']}")
    lines += ["", "## Field accuracy", ""]
    lines += [f"- `{name}`: {acc}" for name, acc in s["field_accuracy_by_field"].items()]
    lines += ["", f"## Failures ({len(s['failures'])})", ""]
    if not s["failures"]:
        lines.append("None.")
    for f in s["failures"]:
        lines.append(f"- `{f['scenario']}`: fp={f['fp']} fn={f['fn']} wrong_fields={f['wrong_fields']}"
                     + (" unnecessary_clarification" if f["unnecessary_clarification"] else "")
                     + (f" error={f['error'][:120]}" if f["error"] else ""))
    lines += ["", "These numbers describe the synthetic corpus only; they are not a guarantee about production documents."]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--per-kind-dev", type=int, default=3)
    parser.add_argument("--per-kind-held-out", type=int, default=2)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "reports")
    args = parser.parse_args()

    init_db()
    settings = get_settings()
    storage = build_storage()
    corpus = build_corpus(seed=args.seed, per_kind_dev=args.per_kind_dev, per_kind_held_out=args.per_kind_held_out)
    results = []
    for repeat in range(args.repeats):
        for index, scenario in enumerate(corpus):
            result = evaluate_scenario(scenario, index + repeat * len(corpus), storage)
            result["repeat"] = repeat
            results.append(result)
            status = "ok" if not (result["exceptions"]["fp"] or result["exceptions"]["fn"]) else "MISMATCH"
            print(f"[{repeat}] {scenario.id:<32} {status:<8} raised={result['exceptions']['raised']}")

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report = {
        "run_id": run_id, "generated_at": datetime.now(UTC).isoformat(), "corpus_version": CORPUS_VERSION,
        "seed": args.seed, "scenarios": len(corpus), "repeats": args.repeats,
        "model": settings.openai_model if settings.llm_enabled else "deterministic-baseline",
        "prompt_version": settings.agent_prompt_version if settings.llm_enabled else None, "mode": settings.agent_run_mode,
        "manifest": [s.manifest() for s in corpus], "results": results, "summary": summarise(results),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{run_id}.json").write_text(json.dumps(report, indent=2, default=str))
    (args.out / f"{run_id}.md").write_text(to_markdown(report))
    (args.out / "latest.md").write_text(to_markdown(report))
    print(f"\nWrote {args.out / run_id}.json and .md")
    print(to_markdown(report))
    return 0 if not report["summary"]["failures"] else 1


if __name__ == "__main__":
    sys.exit(main())
