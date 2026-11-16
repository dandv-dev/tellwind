"""Build the demo workspace by replaying the real agent day by day.

    python scripts/build_demo.py            # full build, ~20 min, ~$1 of OpenAI
    python scripts/build_demo.py --days 2   # quick check

What it does:
1. creates the demo users, the workspace and its watchlist in a scratch SQLite db;
2. for each day from 3 to 16 November 2026 it uploads the documents dated
   before that morning, then runs the agent exactly as the 06:00 schedule
   would: same code, with the run's cutoff set to 06:00 UTC that day so it
   only sees news published before then (real news from Hacker News, Google
   News and GDELT for those dates);
3. shifts run/file timestamps to the simulated run time and exports
   everything to fixtures/demo/demo.json.gz, which the app imports on startup.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SEED_DEMO", "false")
os.environ.setdefault("SCHEDULER_ENABLED", "false")

from sqlalchemy import select, update  # noqa: E402

from app import db as dbmod  # noqa: E402
from app.agent import runner  # noqa: E402
from app.api.content import ingest_upload  # noqa: E402
from app.config import REPO_DIR  # noqa: E402
from app.models import (  # noqa: E402
    Brief,
    Evidence,
    File,
    Invitation,
    Item,
    Membership,
    Run,
    Topic,
    User,
    Workspace,
)
from app.security import hash_password, new_token  # noqa: E402
from app.seed.demo import DEMO_PASSWORD, export_demo  # noqa: E402

import demo_documents  # noqa: E402

UTC = timezone.utc
FIRST_DAY = date(2026, 11, 3)
LAST_DAY = date(2026, 11, 16)
RUN_TIME = (6, 0)

USERS = [
    {"email": "owner@demo.tellwind.app", "name": "Maya Okafor", "role": "owner"},
    {"email": "member@demo.tellwind.app", "name": "Jonas Lindqvist", "role": "member"},
    {"email": "tom@demo.tellwind.app", "name": "Tom Ellis", "role": "member"},
    {"email": "viewer@demo.tellwind.app", "name": "Priya Raman", "role": "viewer"},
]
PENDING_INVITE = {"email": "sara@demo.tellwind.app", "role": "viewer"}

WORKSPACE = {
    "name": "DevTools Radar",
    "subject": "AI developer tools",
    "subject_description": "Tools that use AI to help software teams write, review, test and ship code.",
}

TOPICS = [
    ("Coding agents", "Autonomous AI agents that take a task and write, change and test code on their own.",
     ["coding agent", "AI coding agents", "autonomous software engineer"]),
    ("AI code editors", "Editors and IDEs built around AI assistance and agent features.",
     ["AI code editor", "AI IDE", "AI-native editor"]),
    ("Terminal & CLI agents", "AI agents that work from the command line and in CI.",
     ["CLI coding agent", "terminal AI agent", "command line AI agent"]),
    ("Model Context Protocol", "MCP servers and clients connecting AI agents to tools and data.",
     ["Model Context Protocol", "MCP server", "MCP servers"]),
    ("AI code review", "AI that reviews pull requests and suggests changes.",
     ["AI code review", "AI pull request review", "automated code review"]),
    ("AI testing & QA", "AI that writes, runs and maintains tests and finds bugs.",
     ["AI test generation", "AI testing tool", "AI QA agent"]),
    ("Local & open coding models", "Open-weight and self-hosted models used for coding.",
     ["local LLM coding", "open-weight coding model", "open source coding model"]),
    ("Vibe coding & app builders", "Prompt-to-app builders and vibe coding platforms.",
     ["vibe coding", "AI app builder", "prompt to app"]),
    ("AI code security", "Security of AI-generated code and of coding agents themselves.",
     ["AI generated code security", "coding agent security", "prompt injection agent"]),
    ("Code benchmarks & evals", "Benchmarks and evaluations of AI coding ability.",
     ["SWE-bench", "coding benchmark LLM", "code generation benchmark"]),
]

UPLOAD_TIMES = {
    "Engineering leadership survey Q4 2026.pdf": (datetime(2026, 11, 4, 14, 10, tzinfo=UTC), "owner@demo.tellwind.app"),
    "Analyst note - app builders cooling.docx": (datetime(2026, 11, 9, 16, 45, tzinfo=UTC), "member@demo.tellwind.app"),
    "MCP pilot notes.txt": (datetime(2026, 11, 12, 11, 30, tzinfo=UTC), "tom@demo.tellwind.app"),
}


async def setup() -> tuple[str, dict[str, str]]:
    await dbmod.create_all()
    async with dbmod.SessionLocal() as s:
        ids = {}
        pw = hash_password(DEMO_PASSWORD)
        for u in USERS:
            user = User(email=u["email"], name=u["name"], password_hash=pw)
            s.add(user)
            await s.flush()
            ids[u["email"]] = user.id
        ws = Workspace(**WORKSPACE, is_demo=True, schedule_enabled=True, schedule_time="06:00")
        ws.created_at = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
        s.add(ws)
        await s.flush()
        for u in USERS:
            m = Membership(workspace_id=ws.id, user_id=ids[u["email"]], role=u["role"])
            s.add(m)
        for i, (name, desc, kw) in enumerate(TOPICS):
            s.add(Topic(workspace_id=ws.id, name=name, description=desc, keywords=kw, position=i,
                        created_at=ws.created_at))
        s.add(Invitation(workspace_id=ws.id, email=PENDING_INVITE["email"], role=PENDING_INVITE["role"],
                         token=new_token(), invited_by=ids["owner@demo.tellwind.app"]))
        await s.commit()
        return ws.id, ids


async def upload_due(ws_id: str, ids: dict[str, str], docs_dir: Path, before: datetime, done: set[str]):
    async with dbmod.SessionLocal() as s:
        for fname, (when, email) in UPLOAD_TIMES.items():
            if fname in done or when >= before:
                continue
            data = (docs_dir / fname).read_bytes()
            await ingest_upload(s, ws_id, fname, data, ids[email], when=when)
            done.add(fname)
            print(f"  uploaded {fname} ({when:%d %b %H:%M})")
        await s.commit()


async def shift_times(run_id: str, run_at: datetime) -> None:
    """Make a replayed run look like it happened at its scheduled time."""
    async with dbmod.SessionLocal() as s:
        run = await s.get(Run, run_id)
        offset = run_at - run.started_at
        run.created_at = run_at
        run.started_at = run_at
        run.finished_at = run.finished_at + offset if run.finished_at else None
        steps = []
        for st in run.steps:
            st = dict(st)
            for k in ("started_at", "finished_at"):
                if st.get(k):
                    st[k] = (datetime.fromisoformat(st[k]) + offset).isoformat()
            steps.append(st)
        run.steps = steps
        done_at = run.finished_at or run_at
        await s.execute(update(File).where(File.run_id == run_id).values(created_at=done_at))
        await s.execute(update(Brief).where(Brief.run_id == run_id).values(created_at=done_at))
        await s.execute(update(Item).where(Item.collected_run_id == run_id).values(collected_at=run_at))
        await s.execute(update(Evidence).where(Evidence.run_id == run_id).values(created_at=run_at))
        b = (await s.execute(select(Brief).where(Brief.run_id == run_id))).scalar()
        if b:
            b.data = {**b.data, "generated_at": done_at.isoformat()}
        await s.commit()


async def main(days: int | None, db_path: Path, out: Path) -> None:
    if db_path.exists():
        db_path.unlink()
    dbmod.configure(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    docs_dir = REPO_DIR / "fixtures" / "demo" / "uploads"
    demo_documents.build(docs_dir)
    ws_id, ids = await setup()
    uploaded: set[str] = set()
    total = 0.0
    day = FIRST_DAY
    n = 0
    while day <= LAST_DAY and (days is None or n < days):
        run_at = datetime(day.year, day.month, day.day, *RUN_TIME, tzinfo=UTC)
        print(f"{day}: run at {run_at:%H:%M}")
        await upload_due(ws_id, ids, docs_dir, run_at, uploaded)
        async with dbmod.SessionLocal() as s:
            run = Run(workspace_id=ws_id, trigger="schedule", as_of=day,
                      steps=[{"key": k, "status": "pending", "detail": {}} for k in runner.STEP_KEYS])
            s.add(run)
            await s.commit()
            run_id = run.id
        await runner.execute(run_id, cutoff=run_at)
        async with dbmod.SessionLocal() as s:
            run = await s.get(Run, run_id)
            total += run.cost_usd
            summary = {st["key"]: st.get("message", "") for st in run.steps}
            print(f"  {run.status} ${run.cost_usd:.4f}  collect: {summary['collect']} | "
                  f"classify: {summary['classify']} | score: {summary['score']}")
            if run.status != "succeeded":
                print(run.error)
                raise SystemExit(1)
        await shift_times(run_id, run_at)
        async with dbmod.SessionLocal() as s:
            ws = await s.get(Workspace, ws_id)
            ws.last_scheduled_on = day
            await s.commit()
        day += timedelta(days=1)
        n += 1
    print(f"total cost ${total:.4f}")
    path = await export_demo(ws_id, USERS, out)
    print(f"exported to {path} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=None)
    ap.add_argument("--db", default=str(Path(__file__).resolve().parent.parent / "data" / "demo_build.db"))
    ap.add_argument("--out", default=str(REPO_DIR / "fixtures" / "demo" / "demo.json.gz"))
    a = ap.parse_args()
    asyncio.run(main(a.days, Path(a.db), Path(a.out)))
