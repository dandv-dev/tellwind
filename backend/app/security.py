import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_db
from .models import ROLES, Membership, Session, User, Workspace, utcnow

COOKIE = "tw_session"
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


async def start_session(db: AsyncSession, response: Response, user: User) -> None:
    s = get_settings()
    sess = Session(
        id=new_token(), user_id=user.id, expires_at=utcnow() + timedelta(days=s.session_days)
    )
    db.add(sess)
    await db.commit()
    response.set_cookie(
        COOKIE,
        sess.id,
        max_age=s.session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=s.cookie_secure,
        path="/",
    )


async def end_session(db: AsyncSession, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        sess = await db.get(Session, token)
        if sess:
            await db.delete(sess)
            await db.commit()
    response.delete_cookie(COOKIE, path="/")


async def current_user_optional(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    sess = await db.get(Session, token)
    if not sess or sess.expires_at < utcnow():
        return None
    return sess.user


async def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not_authenticated")
    return user


def role_at_least(role: str, minimum: str) -> bool:
    return ROLES.index(role) >= ROLES.index(minimum)


class WorkspaceAccess:
    """Resolved workspace + the caller's role in it."""

    def __init__(self, workspace: Workspace, membership: Membership, user: User):
        self.workspace = workspace
        self.membership = membership
        self.user = user

    @property
    def role(self) -> str:
        return self.membership.role


def require_role(minimum: str):
    """Dependency factory. Outsiders get 404 so workspace ids don't leak."""

    async def dep(
        workspace_id: str,
        user: User = Depends(current_user),
        db: AsyncSession = Depends(get_db),
    ) -> WorkspaceAccess:
        m = (
            await db.execute(
                select(Membership).where(
                    Membership.workspace_id == workspace_id, Membership.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        ws = await db.get(Workspace, workspace_id) if m else None
        if m is None or ws is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "workspace_not_found")
        if not role_at_least(m.role, minimum):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient_role")
        return WorkspaceAccess(ws, m, user)

    return dep


viewer = require_role("viewer")
member = require_role("member")
owner = require_role("owner")
