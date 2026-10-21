"""Starts, executes, and resumes investigation runs.

In ``inline`` mode runs execute inside the API process (useful for development and tests). In
``worker`` mode the API only records intent (a queued run or a pending resume) and ``app.worker``
executes it, so the API can restart independently of the agent.
"""

import threading
import traceback

from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import SessionLocal
from ..models import AgentRun, Case, RunStatus, utcnow
from .graph import build_graph, open_checkpointer
from .tools import BudgetExceeded

_lock = threading.Lock()
_graph = None


def get_graph():
    """Process-wide compiled graph bound to the SQLite checkpointer."""
    global _graph
    with _lock:
        if _graph is None:
            _graph = build_graph(open_checkpointer())
        return _graph


def reset_graph() -> None:
    """Drop the in-memory graph so the next call rebuilds it from the persisted checkpoint store.
    Used by tests to simulate a worker restart."""
    global _graph
    with _lock:
        _graph = None


def start_run(db: Session, case: Case, actor_id: str) -> AgentRun:
    settings = get_settings()
    active = db.scalar(select(AgentRun).where(AgentRun.case_id == case.id,
                                              AgentRun.status.in_([RunStatus.QUEUED.value, RunStatus.RUNNING.value])))
    if active:
        return active
    run = AgentRun(organization_id=case.organization_id, case_id=case.id, thread_id="", started_by=actor_id,
                   model_name=settings.openai_model if settings.llm_enabled else "deterministic",
                   prompt_version=settings.agent_prompt_version if settings.llm_enabled else None)
    db.add(run)
    db.flush()
    run.thread_id = f"{case.id}:{run.id}"
    # Supersede earlier interrupted runs: a new investigation replaces the old waiting one.
    for old in db.scalars(select(AgentRun).where(AgentRun.case_id == case.id, AgentRun.id != run.id,
                                                 AgentRun.status == RunStatus.INTERRUPTED.value)):
        old.status = RunStatus.COMPLETED.value
        old.outcome = "superseded"
        old.finished_at = utcnow()
    audit.record(db, organization_id=case.organization_id, case_id=case.id, actor_id=actor_id,
                 event_type="agent_run_started", payload={"run_id": run.id, "mode": settings.agent_run_mode})
    db.commit()
    if settings.agent_run_mode == "inline":
        execute_run(run.id)
        db.expire_all()
        run = db.get(AgentRun, run.id)
    return run


def execute_run(run_id: str) -> AgentRun:
    graph = get_graph()
    with SessionLocal() as db:
        run = db.get(AgentRun, run_id)
        run.status = RunStatus.RUNNING.value
        run.started_at = utcnow()
        config = {"configurable": {"thread_id": run.thread_id}}
        initial = {"case_id": run.case_id, "organization_id": run.organization_id, "run_id": run.id,
                   "actor_id": run.started_by, "model_calls": 0, "tool_calls": 0, "trace": []}
        db.commit()
    try:
        existing = graph.get_state(config)
        if existing.values and existing.next:
            graph.invoke(None, config=config)  # continue a partially executed thread after a crash
        else:
            graph.invoke(initial, config=config)
    except BudgetExceeded as exc:
        return _finish(run_id, status=RunStatus.FAILED.value, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        return _finish(run_id, status=RunStatus.FAILED.value, error=f"{exc}\n{traceback.format_exc()}")
    return _sync_from_checkpoint(run_id)


def resume_run(db: Session, case: Case, payload: dict) -> AgentRun | None:
    """Resume the case's waiting run after a human decision. Returns None if nothing is waiting."""
    run = db.scalar(select(AgentRun).where(AgentRun.case_id == case.id,
                                           AgentRun.status == RunStatus.INTERRUPTED.value)
                    .order_by(AgentRun.created_at.desc()))
    if run is None:
        return None
    if get_settings().agent_run_mode == "inline":
        db.commit()
        return execute_resume(run.id, payload)
    run.pending_resume = payload
    return run


def execute_resume(run_id: str, payload: dict) -> AgentRun:
    graph = get_graph()
    with SessionLocal() as db:
        run = db.get(AgentRun, run_id)
        config = {"configurable": {"thread_id": run.thread_id}}
        run.status = RunStatus.RUNNING.value
        run.pending_resume = None
        db.commit()
    try:
        graph.invoke(Command(resume=payload), config=config)
    except Exception as exc:  # noqa: BLE001
        return _finish(run_id, status=RunStatus.FAILED.value, error=f"{exc}\n{traceback.format_exc()}")
    return _sync_from_checkpoint(run_id)


def _sync_from_checkpoint(run_id: str) -> AgentRun:
    graph = get_graph()
    with SessionLocal() as db:
        run = db.get(AgentRun, run_id)
        snapshot = graph.get_state({"configurable": {"thread_id": run.thread_id}})
        values = snapshot.values or {}
        run.trace = values.get("trace", [])
        run.model_calls = values.get("model_calls", 0)
        run.tool_calls = values.get("tool_calls", 0)
        run.outcome = values.get("outcome")
        if snapshot.next:  # paused at an interrupt
            run.status = RunStatus.INTERRUPTED.value
        else:
            run.status = RunStatus.COMPLETED.value
            run.finished_at = utcnow()
        audit.record(db, organization_id=run.organization_id, case_id=run.case_id, actor_type="agent",
                     actor_id=run.id, event_type="agent_run_" + run.status,
                     payload={"run_id": run.id, "outcome": run.outcome, "model_calls": run.model_calls,
                              "tool_calls": run.tool_calls})
        db.commit()
        return run


def _finish(run_id: str, *, status: str, error: str | None) -> AgentRun:
    with SessionLocal() as db:
        run = db.get(AgentRun, run_id)
        run.status = status
        run.error = error
        run.finished_at = utcnow()
        audit.record(db, organization_id=run.organization_id, case_id=run.case_id, actor_type="agent",
                     actor_id=run.id, event_type="agent_run_failed", payload={"run_id": run.id, "error": (error or "")[:500]})
        db.commit()
        return run
