from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import User
from ..security import (
    current_user,
    current_user_optional,
    end_session,
    hash_password,
    start_session,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    name: str = Field(default="", max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name or u.email.split("@")[0]}


@router.post("/signup")
async def signup(body: SignupIn, response: Response, db: AsyncSession = Depends(get_db)):
    email = body.email.lower()
    exists = (await db.execute(select(User).where(func.lower(User.email) == email))).scalar()
    if exists:
        raise HTTPException(409, "email_taken")
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    await db.flush()
    await start_session(db, response, user)
    return user_out(user)


@router.post("/login")
async def login(body: LoginIn, response: Response, db: AsyncSession = Depends(get_db)):
    user = (
        await db.execute(select(User).where(func.lower(User.email) == body.email.lower()))
    ).scalar()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "invalid_credentials")
    await start_session(db, response, user)
    return user_out(user)


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    await end_session(db, request, response)
    return {"ok": True}


@router.get("/me")
async def me(user: User | None = Depends(current_user_optional)):
    return {"user": user_out(user) if user else None}


@router.get("/whoami")
async def whoami(user: User = Depends(current_user)):
    return user_out(user)
