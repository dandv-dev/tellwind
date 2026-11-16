import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_db
from ..models import ROLES, Brief, Invitation, Membership, Topic, User, Workspace
from ..security import WorkspaceAccess, current_user, member, new_token, owner, viewer
from .auth import user_out

log = logging.getLogger("tellwind.invites")
router = APIRouter(prefix="/api", tags=["workspaces"])

MAX_TOPICS = 10


class TopicIn(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=600)
    keywords: list[str] = Field(default_factory=list, max_length=6)


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    subject: str = Field(min_length=2, max_length=200)
    subject_description: str = Field(default="", max_length=1000)
    topics: list[TopicIn] = Field(default_factory=list, max_length=MAX_TOPICS)


class WorkspacePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    subject: str | None = Field(default=None, min_length=2, max_length=200)
    subject_description: str | None = Field(default=None, max_length=1000)


class TopicsIn(BaseModel):
    topics: list[TopicIn] = Field(max_length=MAX_TOPICS)


class ScheduleIn(BaseModel):
    enabled: bool
    time: str

    @field_validator("time")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("time must be HH:MM")
        return v


class InviteIn(BaseModel):
    email: EmailStr
    role: str = "member"

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        if v not in ROLES:
            raise ValueError("bad role")
        return v


class RoleIn(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        if v not in ROLES:
            raise ValueError("bad role")
        return v


def topic_out(t: Topic) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "keywords": t.keywords or [],
        "position": t.position,
    }


async def active_topics(db: AsyncSession, workspace_id: str) -> list[Topic]:
    return list(
        (
            await db.execute(
                select(Topic)
                .where(Topic.workspace_id == workspace_id, Topic.archived.is_(False))
                .order_by(Topic.position)
            )
        ).scalars()
    )


def workspace_out(ws: Workspace, role: str, topics: list[Topic] | None = None) -> dict:
    out = {
        "id": ws.id,
        "name": ws.name,
        "subject": ws.subject,
        "subject_description": ws.subject_description,
        "role": role,
        "is_demo": ws.is_demo,
        "schedule": {"enabled": ws.schedule_enabled, "time": ws.schedule_time},
        "created_at": ws.created_at.isoformat(),
    }
    if topics is not None:
        out["topics"] = [topic_out(t) for t in topics]
    return out


def invitation_out(inv: Invitation, ws: Workspace | None = None) -> dict:
    out = {
        "id": inv.id,
        "email": inv.email,
        "role": inv.role,
        "status": inv.status,
        "created_at": inv.created_at.isoformat(),
    }
    if ws is not None:
        out["workspace"] = {"id": ws.id, "name": ws.name, "subject": ws.subject}
    return out


async def _apply_topics(db: AsyncSession, ws: Workspace, topics: list[TopicIn]) -> None:
    names = [t.name.strip().lower() for t in topics]
    if len(set(names)) != len(names):
        raise HTTPException(422, "duplicate_topic")
    existing = {t.id: t for t in await active_topics(db, ws.id)}
    keep: set[str] = set()
    for pos, t in enumerate(topics):
        cur = existing.get(t.id) if t.id else None
        if cur:
            changed = cur.name != t.name.strip() or cur.description != t.description.strip()
            cur.name, cur.description = t.name.strip(), t.description.strip()
            cur.keywords = [k.strip() for k in t.keywords if k.strip()] or cur.keywords
            cur.position = pos
            if changed:
                cur.embedding_key = ""  # re-embed on next run
            keep.add(cur.id)
        else:
            db.add(
                Topic(
                    workspace_id=ws.id,
                    name=t.name.strip(),
                    description=t.description.strip(),
                    keywords=[k.strip() for k in t.keywords if k.strip()],
                    position=pos,
                )
            )
    # Removed topics are archived, not deleted, so old briefs still resolve.
    for tid, t in existing.items():
        if tid not in keep:
            t.archived = True


@router.get("/workspaces")
async def list_workspaces(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(Workspace, Membership.role)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .where(Membership.user_id == user.id)
            .order_by(Workspace.is_demo.desc(), Workspace.created_at.desc())
        )
    ).all()
    ids = [ws.id for ws, _ in rows]
    counts = dict(
        (
            await db.execute(
                select(Membership.workspace_id, func.count())
                .where(Membership.workspace_id.in_(ids))
                .group_by(Membership.workspace_id)
            )
        ).all()
    ) if ids else {}
    latest: dict[str, Brief] = {}
    if ids:
        sub = (
            select(Brief.workspace_id, func.max(Brief.date).label("d"))
            .where(Brief.workspace_id.in_(ids))
            .group_by(Brief.workspace_id)
            .subquery()
        )
        for b in (
            await db.execute(
                select(Brief).join(
                    sub, (Brief.workspace_id == sub.c.workspace_id) & (Brief.date == sub.c.d)
                )
            )
        ).scalars():
            latest[b.workspace_id] = b
    out = []
    for ws, role in rows:
        w = workspace_out(ws, role)
        w["members"] = counts.get(ws.id, 0)
        b = latest.get(ws.id)
        if b:
            tally: dict[str, int] = {}
            for t in b.data.get("topics", []):
                tally[t["verdict"]] = tally.get(t["verdict"], 0) + 1
            w["latest_brief"] = {"date": b.date.isoformat(), "tally": tally}
        out.append(w)

    invites = (
        await db.execute(
            select(Invitation, Workspace)
            .join(Workspace, Workspace.id == Invitation.workspace_id)
            .where(func.lower(Invitation.email) == user.email.lower(), Invitation.status == "pending")
            .order_by(Invitation.created_at.desc())
        )
    ).all()
    return {
        "workspaces": out,
        "invitations": [invitation_out(i, ws) for i, ws in invites if ws.id not in ids],
    }


@router.post("/workspaces")
async def create_workspace(
    body: WorkspaceIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    ws = Workspace(
        name=body.name.strip(),
        subject=body.subject.strip(),
        subject_description=body.subject_description.strip(),
    )
    db.add(ws)
    await db.flush()
    db.add(Membership(workspace_id=ws.id, user_id=user.id, role="owner"))
    await _apply_topics(db, ws, body.topics)
    await db.commit()
    return workspace_out(ws, "owner", await active_topics(db, ws.id))


@router.get("/workspaces/{workspace_id}")
async def get_workspace(acc: WorkspaceAccess = Depends(viewer), db: AsyncSession = Depends(get_db)):
    return workspace_out(acc.workspace, acc.role, await active_topics(db, acc.workspace.id))


@router.patch("/workspaces/{workspace_id}")
async def patch_workspace(
    body: WorkspacePatch, acc: WorkspaceAccess = Depends(owner), db: AsyncSession = Depends(get_db)
):
    ws = acc.workspace
    for field in ("name", "subject", "subject_description"):
        v = getattr(body, field)
        if v is not None:
            setattr(ws, field, v.strip())
    await db.commit()
    return workspace_out(ws, acc.role, await active_topics(db, ws.id))


@router.put("/workspaces/{workspace_id}/topics")
async def put_topics(
    body: TopicsIn, acc: WorkspaceAccess = Depends(owner), db: AsyncSession = Depends(get_db)
):
    await _apply_topics(db, acc.workspace, body.topics)
    await db.commit()
    return {"topics": [topic_out(t) for t in await active_topics(db, acc.workspace.id)]}


@router.put("/workspaces/{workspace_id}/schedule")
async def put_schedule(
    body: ScheduleIn, acc: WorkspaceAccess = Depends(member), db: AsyncSession = Depends(get_db)
):
    acc.workspace.schedule_enabled = body.enabled
    acc.workspace.schedule_time = body.time
    await db.commit()
    return {"enabled": body.enabled, "time": body.time}


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(acc: WorkspaceAccess = Depends(owner), db: AsyncSession = Depends(get_db)):
    if acc.workspace.is_demo:
        raise HTTPException(400, "demo_workspace")
    await db.delete(acc.workspace)
    await db.commit()
    return {"ok": True}


@router.get("/workspaces/{workspace_id}/members")
async def list_members(acc: WorkspaceAccess = Depends(viewer), db: AsyncSession = Depends(get_db)):
    ms = (
        await db.execute(
            select(Membership)
            .where(Membership.workspace_id == acc.workspace.id)
            .order_by(Membership.created_at)
        )
    ).scalars()
    out = {
        "members": [
            {"id": m.id, "role": m.role, "user": user_out(m.user), "joined_at": m.created_at.isoformat()}
            for m in ms
        ],
        "invitations": [],
    }
    if acc.role == "owner":
        invs = (
            await db.execute(
                select(Invitation)
                .where(Invitation.workspace_id == acc.workspace.id, Invitation.status == "pending")
                .order_by(Invitation.created_at.desc())
            )
        ).scalars()
        out["invitations"] = [invitation_out(i) for i in invs]
    return out


async def _owner_count(db: AsyncSession, workspace_id: str) -> int:
    return (
        await db.execute(
            select(func.count()).where(
                Membership.workspace_id == workspace_id, Membership.role == "owner"
            )
        )
    ).scalar_one()


async def _get_membership(db: AsyncSession, workspace_id: str, membership_id: str) -> Membership:
    m = await db.get(Membership, membership_id)
    if not m or m.workspace_id != workspace_id:
        raise HTTPException(404, "member_not_found")
    return m


@router.patch("/workspaces/{workspace_id}/members/{membership_id}")
async def change_role(
    membership_id: str,
    body: RoleIn,
    acc: WorkspaceAccess = Depends(owner),
    db: AsyncSession = Depends(get_db),
):
    m = await _get_membership(db, acc.workspace.id, membership_id)
    if m.role == "owner" and body.role != "owner" and await _owner_count(db, m.workspace_id) <= 1:
        raise HTTPException(400, "last_owner")
    m.role = body.role
    await db.commit()
    return {"id": m.id, "role": m.role}


@router.delete("/workspaces/{workspace_id}/members/{membership_id}")
async def remove_member(
    membership_id: str, acc: WorkspaceAccess = Depends(owner), db: AsyncSession = Depends(get_db)
):
    m = await _get_membership(db, acc.workspace.id, membership_id)
    if m.role == "owner" and await _owner_count(db, m.workspace_id) <= 1:
        raise HTTPException(400, "last_owner")
    await db.delete(m)
    await db.commit()
    return {"ok": True}


@router.post("/workspaces/{workspace_id}/invitations")
async def invite(
    body: InviteIn, acc: WorkspaceAccess = Depends(owner), db: AsyncSession = Depends(get_db)
):
    email = body.email.lower()
    already = (
        await db.execute(
            select(Membership)
            .join(User, User.id == Membership.user_id)
            .where(Membership.workspace_id == acc.workspace.id, func.lower(User.email) == email)
        )
    ).scalar()
    if already:
        raise HTTPException(409, "already_member")
    # Re-inviting replaces the pending invitation (e.g. to change the role).
    await db.execute(
        delete(Invitation).where(
            Invitation.workspace_id == acc.workspace.id,
            func.lower(Invitation.email) == email,
            Invitation.status == "pending",
        )
    )
    inv = Invitation(
        workspace_id=acc.workspace.id,
        email=email,
        role=body.role,
        token=new_token(),
        invited_by=acc.user.id,
    )
    db.add(inv)
    await db.commit()
    link = f"{get_settings().public_url.rstrip('/')}/invite/{inv.token}"
    # No real email: the invite link goes to the server log.
    log.warning("INVITE %s to '%s' as %s: %s", email, acc.workspace.name, body.role, link)
    return invitation_out(inv)


@router.delete("/workspaces/{workspace_id}/invitations/{invitation_id}")
async def revoke_invite(
    invitation_id: str, acc: WorkspaceAccess = Depends(owner), db: AsyncSession = Depends(get_db)
):
    inv = await db.get(Invitation, invitation_id)
    if not inv or inv.workspace_id != acc.workspace.id:
        raise HTTPException(404, "invitation_not_found")
    inv.status = "revoked"
    await db.commit()
    return {"ok": True}


# Invitations, seen from the invitee's side
async def _my_invite(db: AsyncSession, user: User, invitation_id: str) -> Invitation:
    inv = await db.get(Invitation, invitation_id)
    if not inv or inv.email.lower() != user.email.lower() or inv.status != "pending":
        raise HTTPException(404, "invitation_not_found")
    return inv


@router.get("/invitations/token/{token}")
async def invite_by_token(token: str, db: AsyncSession = Depends(get_db)):
    inv = (await db.execute(select(Invitation).where(Invitation.token == token))).scalar()
    if not inv:
        raise HTTPException(404, "invitation_not_found")
    ws = await db.get(Workspace, inv.workspace_id)
    return invitation_out(inv, ws)


@router.post("/invitations/{invitation_id}/accept")
async def accept_invite(
    invitation_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    inv = await _my_invite(db, user, invitation_id)
    exists = (
        await db.execute(
            select(Membership).where(
                Membership.workspace_id == inv.workspace_id, Membership.user_id == user.id
            )
        )
    ).scalar()
    if not exists:
        db.add(Membership(workspace_id=inv.workspace_id, user_id=user.id, role=inv.role))
    inv.status = "accepted"
    await db.commit()
    return {"workspace_id": inv.workspace_id}


@router.post("/invitations/{invitation_id}/decline")
async def decline_invite(
    invitation_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    inv = await _my_invite(db, user, invitation_id)
    inv.status = "declined"
    await db.commit()
    return {"ok": True}
