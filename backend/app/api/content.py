"""Files, runs, briefs, sources and companies inside a workspace."""

import hashlib
import hmac
from datetime import date, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, File as FileParam, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from ..agent import parsing, runner
from ..config import get_settings
from ..db import get_db
from ..models import Brief, Company, CompanyMention, File, Item, Run, Topic, utcnow
from ..security import WorkspaceAccess, member, viewer

router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["content"])
MAX_UPLOAD = 10 * 1024 * 1024


def file_out(f: File) -> dict:
    return {
        "id": f.id,
        "kind": f.kind,
        "filename": f.filename,
        "content_type": f.content_type,
        "size": f.size,
        "created_at": f.created_at.isoformat(),
        "brief_date": f.brief_date.isoformat() if f.brief_date else None,
        "run_id": f.run_id,
        "parse_status": f.parse_status,
        "chunks": f.chunks,
        "uploaded_by": (f.uploader.name or f.uploader.email) if f.uploader else None,
    }


async def ingest_upload(
    db: AsyncSession,
    workspace_id: str,
    filename: str,
    data: bytes,
    user_id: str | None,
    when: datetime | None = None,
) -> File:
    ext = parsing.extension(filename)
    if ext not in parsing.ALLOWED:
        raise HTTPException(415, "unsupported_type")
    f = File(
        workspace_id=workspace_id,
        kind="upload",
        filename=filename[:255],
        content_type=parsing.ALLOWED[ext],
        size=len(data),
        data=data,
        uploaded_by=user_id,
    )
    if when:
        f.created_at = when
    db.add(f)
    await db.flush()
    try:
        text = parsing.extract_text(filename, data)
        chunks = parsing.chunk_text(text)
        f.parse_status = "ok" if chunks else "empty"
    except parsing.ParseError:
        chunks = []
        f.parse_status = "failed"
    title = parsing.title_of(filename, text) if chunks else filename
    for i, c in enumerate(chunks):
        db.add(
            Item(
                workspace_id=workspace_id,
                source_type="upload",
                source=filename[:120],
                collector="upload",
                url="",
                title=title if i == 0 else f"{title} (part {i + 1})",
                text=c,
                published_at=when or utcnow(),
                file_id=f.id,
                chunk_index=i,
                content_hash=hashlib.sha1(f"{f.id}:{i}".encode()).hexdigest(),
            )
        )
    f.chunks = len(chunks)
    return f


@router.get("/files")
async def list_files(acc: WorkspaceAccess = Depends(viewer), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(File)
            .where(File.workspace_id == acc.workspace.id)
            .order_by(File.created_at.desc(), File.filename)
        )
    ).scalars()
    return {"files": [file_out(f) for f in rows]}


@router.post("/files")
async def upload_file(
    file: UploadFile = FileParam(...),
    acc: WorkspaceAccess = Depends(member),
    db: AsyncSession = Depends(get_db),
):
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "file_too_large")
    if not data:
        raise HTTPException(422, "empty_file")
    f = await ingest_upload(db, acc.workspace.id, file.filename or "upload.txt", data, acc.user.id)
    await db.commit()
    await db.refresh(f, ["uploader"])
    return file_out(f)


@router.get("/files/{file_id}/download")
async def download_file(
    file_id: str,
    inline: bool = False,
    acc: WorkspaceAccess = Depends(viewer),
    db: AsyncSession = Depends(get_db),
):
    f = (
        await db.execute(
            select(File).options(undefer(File.data)).where(
                File.id == file_id, File.workspace_id == acc.workspace.id
            )
        )
    ).scalar()
    if not f:
        raise HTTPException(404, "file_not_found")
    disp = "inline" if inline else "attachment"
    return Response(
        content=f.data,
        media_type=f.content_type,
        headers={
            "Content-Disposition": f"{disp}; filename*=UTF-8''{quote(f.filename)}",
            "X-Content-Type-Options": "nosniff",
            # Brief HTML is our own output, but keep it sandboxed when opened inline.
            "Content-Security-Policy": "sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox",
        },
    )


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: str, acc: WorkspaceAccess = Depends(member), db: AsyncSession = Depends(get_db)
):
    f = await db.get(File, file_id)
    if not f or f.workspace_id != acc.workspace.id:
        raise HTTPException(404, "file_not_found")
    if f.kind != "upload":
        raise HTTPException(400, "only_uploads")
    await db.delete(f)
    await db.commit()
    return {"ok": True}


@router.get("/items")
async def list_items(
    q: str = "",
    source_type: str = "news",
    limit: int = Query(50, le=200),
    offset: int = 0,
    acc: WorkspaceAccess = Depends(viewer),
    db: AsyncSession = Depends(get_db),
):
    cond = [Item.workspace_id == acc.workspace.id, Item.source_type == source_type]
    if source_type == "news":
        cond.append(Item.duplicate_of.is_(None))
    if q:
        like = f"%{q.lower()}%"
        cond.append(or_(func.lower(Item.title).like(like), func.lower(Item.source).like(like)))
    total = (await db.execute(select(func.count()).select_from(Item).where(*cond))).scalar_one()
    rows = (
        await db.execute(
            select(Item).where(*cond).order_by(Item.published_at.desc()).limit(limit).offset(offset)
        )
    ).scalars()
    return {
        "total": total,
        "items": [
            {
                "id": i.id,
                "title": i.title,
                "url": i.url,
                "source": i.source,
                "collector": i.collector,
                "published_at": i.published_at.isoformat(),
                "file_id": i.file_id,
                "also": len((i.meta or {}).get("also", [])),
            }
            for i in rows
        ],
    }


@router.get("/items/{item_id}")
async def get_item(item_id: str, acc: WorkspaceAccess = Depends(viewer), db: AsyncSession = Depends(get_db)):
    i = await db.get(Item, item_id)
    if not i or i.workspace_id != acc.workspace.id:
        raise HTTPException(404, "item_not_found")
    return {
        "id": i.id,
        "title": i.title,
        "text": i.text,
        "url": i.url,
        "source": i.source,
        "source_type": i.source_type,
        "file_id": i.file_id,
        "chunk_index": i.chunk_index,
        "published_at": i.published_at.isoformat(),
        "meta": i.meta,
    }


def run_out(r: Run, full: bool = False) -> dict:
    out = {
        "id": r.id,
        "trigger": r.trigger,
        "status": r.status,
        "as_of": r.as_of.isoformat(),
        "cost_usd": round(r.cost_usd or 0, 4),
        "created_at": r.created_at.isoformat(),
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "by": (r.creator.name or r.creator.email) if r.creator else None,
        "brief_id": r.brief_id,
        "steps": [
            {k: v for k, v in s.items() if k != "detail" or full} for s in (r.steps or [])
        ],
    }
    if r.status == "failed":
        out["error"] = (r.error or "").split("\n")[0][:300]
    return out


@router.get("/runs")
async def list_runs(
    limit: int = Query(30, le=100), acc: WorkspaceAccess = Depends(viewer), db: AsyncSession = Depends(get_db)
):
    rows = (
        await db.execute(
            select(Run)
            .where(Run.workspace_id == acc.workspace.id)
            .order_by(Run.created_at.desc())
            .limit(limit)
        )
    ).scalars()
    return {"runs": [run_out(r) for r in rows]}


@router.post("/runs")
async def start_run(acc: WorkspaceAccess = Depends(member)):
    r = await runner.start_run(acc.workspace.id, trigger="manual", user_id=acc.user.id)
    return run_out(r)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, acc: WorkspaceAccess = Depends(viewer), db: AsyncSession = Depends(get_db)):
    r = await db.get(Run, run_id)
    if not r or r.workspace_id != acc.workspace.id:
        raise HTTPException(404, "run_not_found")
    return run_out(r, full=True)


@router.get("/briefs")
async def list_briefs(acc: WorkspaceAccess = Depends(viewer), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(Brief.date, Brief.id, Brief.data)
            .where(Brief.workspace_id == acc.workspace.id)
            .order_by(Brief.date.desc())
        )
    ).all()
    # Each day carries its verdict mix and how many calls changed, so the day
    # picker can show the shape of the last weeks at a glance.
    return {
        "dates": [
            {
                "date": d.isoformat(),
                "id": i,
                "tally": (data or {}).get("tally", {}),
                "changes": len((data or {}).get("changes", [])),
            }
            for d, i, data in rows
        ]
    }


@router.get("/briefs/latest")
async def latest_brief(acc: WorkspaceAccess = Depends(viewer), db: AsyncSession = Depends(get_db)):
    b = (
        await db.execute(
            select(Brief).where(Brief.workspace_id == acc.workspace.id).order_by(Brief.date.desc()).limit(1)
        )
    ).scalar()
    return {"brief": _brief_out(b) if b else None}


@router.get("/briefs/{day}")
async def brief_by_date(day: date, acc: WorkspaceAccess = Depends(viewer), db: AsyncSession = Depends(get_db)):
    b = (
        await db.execute(select(Brief).where(Brief.workspace_id == acc.workspace.id, Brief.date == day))
    ).scalar()
    if not b:
        raise HTTPException(404, "brief_not_found")
    return {"brief": _brief_out(b)}


def _brief_out(b: Brief) -> dict:
    return {"id": b.id, "date": b.date.isoformat(), "run_id": b.run_id, **b.data}


@router.get("/companies/{company_id}")
async def company_detail(
    company_id: str, acc: WorkspaceAccess = Depends(viewer), db: AsyncSession = Depends(get_db)
):
    c = await db.get(Company, company_id)
    if not c or c.workspace_id != acc.workspace.id:
        raise HTTPException(404, "company_not_found")
    rows = (
        await db.execute(
            select(CompanyMention, Item, Topic.name)
            .join(Item, Item.id == CompanyMention.item_id)
            .outerjoin(Topic, Topic.id == CompanyMention.topic_id)
            .where(CompanyMention.company_id == c.id)
            .order_by(Item.published_at.desc())
        )
    ).all()
    mentions: dict[str, dict] = {}
    for m, it, tname in rows:
        e = mentions.setdefault(
            it.id,
            {
                "item_id": it.id,
                "title": it.title,
                "url": it.url,
                "source": it.source,
                "source_type": it.source_type,
                "file_id": it.file_id,
                "date": it.published_at.date().isoformat(),
                "alias": m.alias,
                "event_type": m.event_type,
                "event": m.event,
                "topics": [],
            },
        )
        if tname and tname not in e["topics"]:
            e["topics"].append(tname)
    return {"id": c.id, "name": c.name, "aliases": c.aliases, "mentions": list(mentions.values())}


cron_router = APIRouter(prefix="/api/cron", tags=["cron"])


@cron_router.post("/tick")
async def cron_tick(x_cron_secret: str = Header(default="")):
    """Called by an external scheduler (GitHub Actions) to wake the free instance."""
    if not hmac.compare_digest(x_cron_secret, get_settings().cron_secret):
        raise HTTPException(403, "forbidden")
    from ..scheduler import run_due

    started = await run_due()
    return {"started": started}
