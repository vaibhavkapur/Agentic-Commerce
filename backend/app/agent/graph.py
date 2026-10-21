"""LangGraph investigation workflow.

Nodes: extract_documents -> load_vendor -> match_purchase_order -> check_exceptions ->
       (request_information | prepare_review -> await_approval)

The graph persists its progress in a LangGraph checkpointer and pauses at ``await_approval`` with
``interrupt``. The application database stays authoritative: when the graph is resumed it re-reads
the approval request and only records an outcome that the database supports.
"""

import operator
import sqlite3
from typing import Annotated, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from sqlalchemy import select

from .. import audit
from ..config import get_settings
from ..db import SessionLocal
from ..models import (
    AgentRun,
    ApprovalRequest,
    ApprovalStatus,
    CaseStatus,
    ExtractedField,
    utcnow,
)
from ..services.approvals import current_hash
from ..services.checks import open_blocking, run_checks, sync_exceptions
from ..services.documents import current_document
from . import llm, tools
from .tools import ToolContext


class InvestigationState(TypedDict, total=False):
    case_id: str
    organization_id: str
    run_id: str
    actor_id: str
    documents: list[dict]
    vendor: dict | None
    po_match: dict
    exceptions: list[dict]
    needs_information: bool
    clarification_draft_id: str | None
    summary: str | None
    outcome: str | None
    model_calls: int
    tool_calls: int
    trace: Annotated[list[dict], operator.add]


def _ctx(db, state: InvestigationState) -> ToolContext:
    settings = get_settings()
    return ToolContext(db=db, organization_id=state["organization_id"], case_id=state["case_id"],
                       run_id=state.get("run_id"), max_tool_calls=settings.agent_max_tool_calls,
                       tool_calls=state.get("tool_calls", 0))


def _budget(state: InvestigationState) -> llm.ModelBudget:
    return llm.ModelBudget(max_calls=get_settings().agent_max_model_calls, calls=state.get("model_calls", 0))


def _step(name: str, ctx: ToolContext, budget: llm.ModelBudget, **detail) -> dict:
    return {"tool_calls": ctx.tool_calls, "model_calls": budget.calls,
            "trace": [{"type": "node", "node": name, "at": utcnow().isoformat(), **detail}, *ctx.trace]}


def _case_summary(ctx: ToolContext, documents: list[dict], vendor: dict | None) -> dict:
    by_kind = {d["kind"]: d for d in documents}
    invoice = by_kind.get("invoice", {}).get("fields", {})
    return {
        "case_id": ctx.case_id,
        "invoice_number": invoice.get("invoice_number"),
        "supplier_name": invoice.get("supplier_name"),
        "amount_minor": invoice.get("total_minor"),
        "po_reference": invoice.get("po_number"),
        "vendor": vendor,
        "purchase_order": by_kind.get("purchase_order", {}).get("fields"),
        "delivery": by_kind.get("delivery_confirmation", {}).get("fields"),
    }


# ------------------------------------------------------------------ nodes

def extract_documents(state: InvestigationState) -> dict:
    with SessionLocal() as db:
        ctx, budget = _ctx(db, state), _budget(state)
        documents = tools.list_documents(ctx)
        proposals = 0
        invoice = next((d for d in documents if d["kind"] == "invoice"), None)
        if invoice and get_settings().llm_enabled:
            missing = [n for n in ("invoice_number", "supplier_name", "total_minor") if not invoice["fields"].get(n)]
            if missing:
                proposals = _propose_missing_fields(db, ctx, budget, invoice, missing)
                documents = tools.list_documents(ctx)
        db.commit()
        return {"documents": documents, **_step("extract_documents", ctx, budget,
                                                documents=len(documents), agent_proposals=proposals)}


def _propose_missing_fields(db, ctx: ToolContext, budget: llm.ModelBudget, invoice: dict, missing: list[str]) -> int:
    """Ask the model for fields the rules could not find. Proposals are stored as a separate source
    with page references and are validated like any other claim."""
    from pydantic import BaseModel, Field

    class Proposal(BaseModel):
        name: str
        value: str
        page: int = Field(ge=1)
        excerpt: str

    class Proposals(BaseModel):
        fields: list[Proposal]

    doc = current_document(db, ctx.case(), "invoice")
    text = "\n\n".join(f"--- page {i} ---\n{tools.get_document_text(ctx, doc.id, i)}" for i in range(1, doc.page_count + 1))
    budget.charge()
    model = llm._chat().with_structured_output(Proposals)
    result = model.invoke([
        ("system", llm.SYSTEM_PROMPT),
        ("human", f"Find these fields in the invoice text: {', '.join(missing)}. For *_minor fields give integer "
                  f"pence. Quote the exact line as excerpt and give its page.\n<evidence name=\"invoice\">\n{text}\n</evidence>"),
    ])
    stored = 0
    for proposal in result.fields:
        if proposal.name not in missing or not 1 <= proposal.page <= doc.page_count:
            continue
        if proposal.excerpt.strip() not in (doc.text_pages[proposal.page - 1] or ""):
            continue  # the model must cite text that is actually on that page
        value_json = None
        if proposal.name.endswith("_minor"):
            from ..money import parse_minor
            value_json = parse_minor(proposal.value)
            if value_json is None:
                continue
        db.add(ExtractedField(organization_id=ctx.organization_id, document_version_id=doc.id,
                              name=proposal.name, value_text=proposal.value if value_json is None else str(value_json),
                              value_json=value_json, page=proposal.page, excerpt=proposal.excerpt,
                              confidence=0.6, source="agent_proposal", revision=1))
        stored += 1
    db.flush()
    return stored


def load_vendor(state: InvestigationState) -> dict:
    with SessionLocal() as db:
        ctx, budget = _ctx(db, state), _budget(state)
        vendor = tools.get_vendor_record(ctx)
        case = ctx.case()
        case.vendor_id = vendor["vendor_id"] if vendor else None
        case.beneficiary_id = vendor["beneficiary"]["id"] if vendor and vendor.get("beneficiary") else None
        db.commit()
        return {"vendor": vendor, **_step("load_vendor", ctx, budget, matched=bool(vendor))}


def match_purchase_order(state: InvestigationState) -> dict:
    with SessionLocal() as db:
        ctx, budget = _ctx(db, state), _budget(state)
        by_kind = {d["kind"]: d for d in state.get("documents", [])}
        invoice = by_kind.get("invoice", {}).get("fields", {})
        po = by_kind.get("purchase_order", {}).get("fields")
        match: dict = {"invoice_po_reference": invoice.get("po_number"), "po_on_file": po is not None}
        if po:
            match.update({
                "po_number": po.get("po_number"),
                "po_total_minor": po.get("total_minor"),
                "invoice_total_minor": invoice.get("total_minor"),
                "line_matches": llm.propose_line_matches(invoice.get("line_items") or [], po.get("line_items") or [], budget),
            })
            ambiguous = [m for m in match["line_matches"] if m["confidence"] < 1.0]
            match["ambiguity"] = [f"{m['invoice_description']}: {m['reason']}" for m in ambiguous]
        db.commit()
        return {"po_match": match, **_step("match_purchase_order", ctx, budget, po_on_file=po is not None)}


def check_exceptions(state: InvestigationState) -> dict:
    with SessionLocal() as db:
        ctx, budget = _ctx(db, state), _budget(state)
        case = ctx.case()
        _, findings = run_checks(db, case)
        sync_exceptions(db, case, findings, agent_run_id=state.get("run_id"), actor_id=state.get("actor_id"))
        exceptions = tools.list_exceptions(ctx)
        needs_information = any(e["status"] == "open" and e["needs_information"] for e in exceptions)
        if case.status in (CaseStatus.OPEN.value, CaseStatus.NEEDS_INFORMATION.value, CaseStatus.READY_FOR_REVIEW.value):
            case.status = CaseStatus.INVESTIGATING.value
        db.commit()
        return {"exceptions": exceptions, "needs_information": needs_information,
                **_step("check_exceptions", ctx, budget, findings=[f.code for f in findings])}


def route_after_checks(state: InvestigationState) -> str:
    return "request_information" if state.get("needs_information") else "prepare_review"


def request_information(state: InvestigationState) -> dict:
    with SessionLocal() as db:
        ctx, budget = _ctx(db, state), _budget(state)
        case = ctx.case()
        open_items = [{"code": e["code"], "title": e["title"], "detail": e["detail"],
                       "po_ref": state.get("po_match", {}).get("invoice_po_reference")}
                      for e in state.get("exceptions", []) if e["status"] == "open" and e["needs_information"]]
        summary = _case_summary(ctx, state.get("documents", []), state.get("vendor"))
        draft = llm.draft_clarification(summary, open_items, budget)
        draft_id = tools.save_clarification_draft(ctx, **draft)
        case.status = CaseStatus.NEEDS_INFORMATION.value
        audit.record(db, organization_id=ctx.organization_id, case_id=ctx.case_id, actor_type="agent",
                     actor_id=state.get("run_id"), event_type="clarification_drafted",
                     payload={"draft_id": draft_id, "items": [i["code"] for i in open_items]})
        db.commit()
        return {"clarification_draft_id": draft_id, "outcome": "information_requested",
                **_step("request_information", ctx, budget, draft_id=draft_id)}


def prepare_review(state: InvestigationState) -> dict:
    with SessionLocal() as db:
        ctx, budget = _ctx(db, state), _budget(state)
        case = ctx.case()
        summary_input = _case_summary(ctx, state.get("documents", []), state.get("vendor"))
        summary_input["purchase_order_match"] = state.get("po_match")
        summary = llm.summarize_case(ctx, summary_input, state.get("exceptions", []), budget)
        run = db.get(AgentRun, state["run_id"]) if state.get("run_id") else None
        if run:
            run.summary = summary
        blockers = open_blocking(db, case)
        case.status = CaseStatus.INVESTIGATING.value if blockers else CaseStatus.READY_FOR_REVIEW.value
        audit.record(db, organization_id=ctx.organization_id, case_id=ctx.case_id, actor_type="agent",
                     actor_id=state.get("run_id"), event_type="review_prepared",
                     payload={"open_blockers": [b.code for b in blockers], "status": case.status})
        db.commit()
        return {"summary": summary, **_step("prepare_review", ctx, budget, blockers=len(blockers))}


def await_approval(state: InvestigationState) -> dict:
    # Pause until a human decision arrives. The payload we receive is a hint only; authority is
    # re-established from the database below.
    resume = interrupt({"case_id": state["case_id"], "waiting_for": "approval decision"})
    with SessionLocal() as db:
        ctx, budget = _ctx(db, state), _budget(state)
        case = ctx.case()
        request_id = (resume or {}).get("approval_request_id")
        request = db.scalar(select(ApprovalRequest).where(ApprovalRequest.id == request_id,
                                                           ApprovalRequest.case_id == case.id)) if request_id else None
        if request is None:
            outcome = "no_valid_approval_request"
        elif request.status == ApprovalStatus.REJECTED.value:
            outcome = "rejected"
        elif request.status != ApprovalStatus.APPROVED.value:
            outcome = f"approval_{request.status}"
        elif request.expires_at <= utcnow():
            outcome = "approval_expired"
        elif current_hash(db, case, request) != request.snapshot_hash:
            outcome = "approval_stale"
        elif open_blocking(db, case):
            outcome = "blocking_exceptions_present"
        else:
            outcome = "approved_and_verified"
        audit.record(db, organization_id=ctx.organization_id, case_id=ctx.case_id, actor_type="agent",
                     actor_id=state.get("run_id"), event_type="agent_resumed_after_decision",
                     payload={"approval_request_id": request_id, "outcome": outcome})
        db.commit()
        return {"outcome": outcome, **_step("await_approval", ctx, budget, outcome=outcome)}


# ------------------------------------------------------------------ graph assembly

def build_graph(checkpointer):
    graph = StateGraph(InvestigationState)
    graph.add_node("extract_documents", extract_documents)
    graph.add_node("load_vendor", load_vendor)
    graph.add_node("match_purchase_order", match_purchase_order)
    graph.add_node("check_exceptions", check_exceptions)
    graph.add_node("request_information", request_information)
    graph.add_node("prepare_review", prepare_review)
    graph.add_node("await_approval", await_approval)
    graph.add_edge(START, "extract_documents")
    graph.add_edge("extract_documents", "load_vendor")
    graph.add_edge("load_vendor", "match_purchase_order")
    graph.add_edge("match_purchase_order", "check_exceptions")
    graph.add_conditional_edges("check_exceptions", route_after_checks,
                                {"request_information": "request_information", "prepare_review": "prepare_review"})
    graph.add_edge("request_information", END)
    graph.add_edge("prepare_review", "await_approval")
    graph.add_edge("await_approval", END)
    return graph.compile(checkpointer=checkpointer)


def open_checkpointer(path=None) -> SqliteSaver:
    path = path or get_settings().langgraph_checkpoint_path
    conn = sqlite3.connect(str(path), check_same_thread=False)
    return SqliteSaver(conn)
