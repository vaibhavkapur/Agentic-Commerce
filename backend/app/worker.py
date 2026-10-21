"""Agent worker: executes queued runs and pending resumes. Run with ``python -m app.worker``.

Set AGENT_RUN_MODE=worker on the API so that it only records intent. Restarting this process is
safe at any point: LangGraph checkpoints hold graph progress and the database holds every decision.
"""

import logging
import time

from sqlalchemy import select

from .agent import runner
from .db import SessionLocal, init_db
from .models import AgentRun, RunStatus

log = logging.getLogger("ap.worker")


def poll_once() -> int:
    handled = 0
    with SessionLocal() as db:
        queued = list(db.scalars(select(AgentRun).where(AgentRun.status == RunStatus.QUEUED.value)
                                 .order_by(AgentRun.created_at)))
        resumes = list(db.scalars(select(AgentRun).where(AgentRun.status == RunStatus.INTERRUPTED.value,
                                                         AgentRun.pending_resume.is_not(None))))
        # Runs left RUNNING by a crash are retried from their checkpoint.
        stale = list(db.scalars(select(AgentRun).where(AgentRun.status == RunStatus.RUNNING.value)))
    for run in queued:
        log.info("executing run %s", run.id)
        runner.execute_run(run.id)
        handled += 1
    for run in resumes:
        log.info("resuming run %s", run.id)
        runner.execute_resume(run.id, run.pending_resume)
        handled += 1
    for run in stale:
        log.warning("recovering run %s left running", run.id)
        runner.execute_run(run.id)
        handled += 1
    return handled


def main(interval_seconds: float = 2.0) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    init_db()
    log.info("worker started")
    while True:
        try:
            if not poll_once():
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            break
        except Exception:  # noqa: BLE001
            log.exception("worker iteration failed")
            time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
