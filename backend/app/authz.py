"""Tenant and role checks.

The privileged backend connection bypasses Row Level Security, so every request path performs an
explicit membership check here. Case-scoped lookups always filter by organization so that a case
identifier from another tenant behaves as if it did not exist.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import get_current_user
from .db import get_db
from .models import Case, Membership, Role, User


@dataclass
class Principal:
    user: User
    membership: Membership

    @property
    def organization_id(self) -> str:
        return self.membership.organization_id

    @property
    def role(self) -> Role:
        return Role(self.membership.role)

    def has_role(self, *roles: Role) -> bool:
        return self.role in roles


def get_membership(db: Session, organization_id: str, user_id: str) -> Membership | None:
    return db.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id, Membership.user_id == user_id
        )
    )


def require_principal(
    organization_id: str = Path(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Principal:
    membership = get_membership(db, organization_id, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="Not a member of this organization")
    return Principal(user=user, membership=membership)


def require_roles(*roles: Role):
    def dependency(principal: Principal = Depends(require_principal)) -> Principal:
        ensure_roles(principal, roles)
        return principal

    return dependency


def ensure_roles(principal: Principal, roles: Iterable[Role]) -> None:
    roles = tuple(roles)
    if roles and not principal.has_role(*roles):
        raise HTTPException(
            status_code=403,
            detail=f"Requires one of roles: {', '.join(r.value for r in roles)}",
        )


def load_case(db: Session, principal: Principal, case_id: str) -> Case:
    case = db.scalar(
        select(Case).where(Case.id == case_id, Case.organization_id == principal.organization_id)
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case
