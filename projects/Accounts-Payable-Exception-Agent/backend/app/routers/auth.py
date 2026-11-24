from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import create_token, get_current_user
from ..config import get_settings
from ..db import get_db
from ..models import Membership, Organization, User
from ..schemas import DevLoginRequest, organization_out, user_out

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/dev-login")
def dev_login(body: DevLoginRequest, db: Session = Depends(get_db)):
    """Issue a token for a seeded user. Disabled unless DEV_LOGIN_ENABLED=true."""
    settings = get_settings()
    if not settings.dev_login_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return {"access_token": create_token(user), "token_type": "bearer", "user": user_out(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    memberships = db.scalars(select(Membership).where(Membership.user_id == user.id))
    orgs = []
    for membership in memberships:
        org = db.get(Organization, membership.organization_id)
        orgs.append(organization_out(org, membership))
    return {"user": user_out(user), "organizations": orgs}
