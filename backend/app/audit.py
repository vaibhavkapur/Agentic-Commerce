from sqlalchemy.orm import Session

from .models import AuditEvent


def record(
    db: Session,
    *,
    organization_id: str,
    event_type: str,
    actor_type: str = "user",
    actor_id: str | None = None,
    case_id: str | None = None,
    payload: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=organization_id,
        case_id=case_id,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=event_type,
        payload=payload or {},
    )
    db.add(event)
    return event
