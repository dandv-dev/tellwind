"""Demo workspace: export to / import from ``fixtures/demo/demo.json.gz``.

The demo history was produced by running the real agent day by day (see
``scripts/build_demo.py``) and exporting the resulting rows. On startup we
import it if no demo workspace exists, so it survives the free Render
database being recreated and doesn't need the OpenAI key.

Brief HTML files are not stored: they are rebuilt from the brief JSON with the
current frontend template, so the downloadable brief always matches the app.
"""

from __future__ import annotations

import base64
import gzip
import json
import logging
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import Date, LargeBinary, inspect, select
from sqlalchemy.orm import undefer

from .. import db as dbmod
from ..agent import artifacts
from ..config import get_settings
from ..models import (
    Brief,
    Company,
    CompanyMention,
    Evidence,
    File,
    Invitation,
    Item,
    Membership,
    Run,
    Topic,
    TZDateTime,
    User,
    Workspace,
)
from ..security import hash_password

log = logging.getLogger("tellwind.seed")

DEMO_PASSWORD = "tellwind-demo"
# Order matters for foreign keys on import.
TABLES = [Workspace, Topic, File, Item, Evidence, Run, Brief, Company, CompanyMention]
SKIP_COLUMNS = {Item: {"embedding"}, Topic: {"embedding", "embedding_key"}}


def fixture_path() -> Path:
    return get_settings().fixtures_dir / "demo" / "demo.json.gz"


def _dump_value(col, v):
    if v is None:
        return None
    if isinstance(col.type, TZDateTime) or isinstance(v, datetime):
        return v.isoformat()
    if isinstance(col.type, Date) or isinstance(v, date):
        return v.isoformat()
    if isinstance(col.type, LargeBinary):
        return base64.b64encode(v).decode()
    return v


def _load_value(col, v):
    if v is None:
        return None
    if isinstance(col.type, TZDateTime):
        return datetime.fromisoformat(v)
    if isinstance(col.type, Date):
        return date.fromisoformat(v)
    if isinstance(col.type, LargeBinary):
        return base64.b64decode(v)
    return v


def _row(obj, model) -> dict:
    skip = SKIP_COLUMNS.get(model, set())
    return {
        c.key: _dump_value(c, getattr(obj, c.key))
        for c in inspect(model).columns
        if c.key not in skip
    }


async def export_demo(workspace_id: str, users: list[dict], path: Path | None = None) -> Path:
    """users: [{"email", "name", "role"}] in the order they should be listed."""
    path = path or fixture_path()
    out: dict = {"users": users, "tables": {}}
    async with dbmod.SessionLocal() as s:
        for model in TABLES:
            q = select(model)
            if model is Workspace:
                q = q.where(Workspace.id == workspace_id)
            else:
                q = q.where(model.workspace_id == workspace_id)
            if model is File:
                q = q.options(undefer(File.data)).where(File.kind != "brief")
            rows = (await s.execute(q)).scalars().all()
            out["tables"][model.__tablename__] = [_row(r, model) for r in rows]
        invs = (
            await s.execute(
                select(Invitation).where(
                    Invitation.workspace_id == workspace_id, Invitation.status == "pending"
                )
            )
        ).scalars()
        out["invitations"] = [{"email": i.email, "role": i.role} for i in invs]
    # Uploaded_by / created_by point at users; store emails instead of ids.
    async with dbmod.SessionLocal() as s:
        ids = {u.id: u.email for u in (await s.execute(select(User))).scalars()}
    for t in ("files", "runs"):
        for r in out["tables"][t]:
            for k in ("uploaded_by", "created_by"):
                if k in r:
                    r[k] = ids.get(r[k]) if r[k] else None
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    return path


async def seed_demo(path: Path | None = None) -> str | None:
    path = path or fixture_path()
    if not path.exists():
        log.info("no demo fixture at %s", path)
        return None
    async with dbmod.SessionLocal() as s:
        if (await s.execute(select(Workspace.id).where(Workspace.is_demo.is_(True)))).scalar():
            return None
    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)

    async with dbmod.SessionLocal() as s:
        by_email: dict[str, User] = {}
        pw = hash_password(DEMO_PASSWORD)
        for u in data["users"]:
            existing = (await s.execute(select(User).where(User.email == u["email"]))).scalar()
            if not existing:
                existing = User(email=u["email"], name=u["name"], password_hash=pw)
                s.add(existing)
                await s.flush()
            by_email[u["email"]] = existing

        ws_id = None
        for model in TABLES:
            cols = {c.key: c for c in inspect(model).columns}
            for r in data["tables"].get(model.__tablename__, []):
                kw = {k: _load_value(cols[k], v) for k, v in r.items() if k in cols}
                for k in ("uploaded_by", "created_by"):
                    if k in kw:
                        u = by_email.get(kw[k]) if kw[k] else None
                        kw[k] = u.id if u else None
                obj = model(**kw)
                if model is Workspace:
                    ws_id = obj.id
                s.add(obj)
            await s.flush()

        for u in data["users"]:
            s.add(Membership(workspace_id=ws_id, user_id=by_email[u["email"]].id, role=u["role"]))
        for inv in data.get("invitations", []):
            from ..security import new_token

            s.add(Invitation(workspace_id=ws_id, email=inv["email"], role=inv["role"], token=new_token()))

        # Rebuild brief HTML from the stored brief JSON with the current template.
        briefs = (await s.execute(select(Brief).where(Brief.workspace_id == ws_id))).scalars().all()
        for b in briefs:
            f = artifacts.make_file(
                "brief", f"brief-{b.date.isoformat()}.html", "text/html; charset=utf-8", artifacts.brief_html(b.data)
            )
            f.workspace_id, f.run_id, f.brief_date, f.created_at = ws_id, b.run_id, b.date, b.created_at
            s.add(f)
        await s.commit()
    log.info("demo workspace imported (%s)", ws_id)
    return ws_id
