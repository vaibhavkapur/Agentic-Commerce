"""Bearer-token authentication.

Tokens are HS256 JWTs with the standard Supabase Auth claims (`sub`, `email`, `aud`). In a hosted
deployment the secret is the Supabase project JWT secret, so tokens issued by Supabase Auth
verify directly. In development the API can mint tokens for seeded users (`/auth/dev-login`).
"""

from datetime import timedelta

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User, utcnow


def create_token(user: User) -> str:
    settings = get_settings()
    now = utcnow()
    payload = {
        "sub": user.id,
        "email": user.email,
        "aud": settings.auth_jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.auth_token_ttl_seconds)).timestamp()),
        "role": "authenticated",
    }
    return jwt.encode(payload, settings.auth_jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=["HS256"],
            audience=settings.auth_jwt_audience,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}"
        ) from exc


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    claims = decode_token(header.split(" ", 1)[1].strip())
    user = db.get(User, claims["sub"])
    if user is None:
        # A valid Supabase token for a user we have not seen yet: provision the user record.
        # Access to any organization still requires an explicit membership.
        email = claims.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Token has no email claim")
        user = User(id=claims["sub"], email=email, display_name=email.split("@")[0])
        db.add(user)
        db.commit()
    return user
