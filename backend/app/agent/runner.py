"""One agent run, step by step.

prepare -> collect -> embed -> classify -> score -> explain -> publish

Each step records what it did in ``Run.steps`` (the Runs tab polls it), and
the whole record ends up in the trace file. A run is pinned to an ``as_of``
date: it only ever sees items published up to the end of that day, which is
also how the demo history was produced (the same code replayed day by day).
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

import numpy as np
from sqlalchemy import select, update
from sqlalchemy.orm import undefer

from .. import db as dbmod
from ..config import get_settings
from ..models import (
    Brief,
    Company,
    CompanyMention,
    Evidence,
    File,
    Item,
    Run,
    Topic,
    Workspace,
    utcnow,
)
from . import artifacts, classify, companies, llm, narrate, scoring, sources

log = logging.getLogger("tellwind.runner")

BACKFILL_DAYS = scoring.HORIZON  # first run fetches four weeks
OVERLAP = timedelta(days=2)  # re-read the last two days: late HN votes, slow indexing
DUP_SIM = 0.93
STEP_KEYS = ["prepare", "collect", "embed", "classify", "score", "explain", "publish"]

_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_tasks: set[asyncio.Task] = set()


def end_of_day(d: date) -> datetime:
    return datetime.combine(d + timedelta(days=1), time.min, tzinfo=timezone.utc)


class RunContext:
    def __init__(self, run_id: str, workspace_id: str, as_of: date, cutoff: datetime | None = None):
        self.run_id = run_id
        self.workspace_id = workspace_id
        self.as_of = as_of
        self.meter = llm.Meter()
        self.steps: list[dict] = [{"key": k, "status": "pending", "detail": {}} for k in STEP_KEYS]
        self.trace: dict = {"steps": {}}
        # The run sees nothing published after this moment.
        self.cutoff = cutoff or min(end_of_day(as_of), utcnow())
        # Scoring windows end on the last (mostly) complete day before the cutoff,
        # so a 06:00 run doesn't count a six-hour day as a full one.
        self.score_day = (self.cutoff - timedelta(hours=12)).date()

    def step(self, key: str) -> dict:
        return next(s for s in self.steps if s["key"] == key)

    async def save(self, **fields) -> None:
        async with dbmod.SessionLocal() as s:
            await s.execute(
                update(Run)
                .where(Run.id == self.run_id)
                .values(
                    steps=[dict(x) for x in self.steps],
                    cost_usd=self.meter.cost_usd,
                    usage=self.meter.as_dict(),
                    **fields,
                )
            )
            await s.commit()

    async def begin(self, key: str, message: str = "") -> None:
        st = self.step(key)
        st.update(status="running", started_at=utcnow().isoformat(), message=message)
        await self.save()

    async def progress(self, key: str, message: str) -> None:
        self.step(key)["message"] = message
        await self.save()

    async def finish(self, key: str, message: str = "", **detail) -> None:
        st = self.step(key)
        st.update(status="done", finished_at=utcnow().isoformat(), message=message)
        st["detail"] = detail
        await self.save()


async def start_run(
    workspace_id: str, *, trigger: str, user_id: str | None = None, as_of: date | None = None
) -> Run:
    """Create a queued run and execute it in the background."""
    async with dbmod.SessionLocal() as s:
        busy = (
            await s.execute(
                select(Run).where(
                    Run.workspace_id == workspace_id, Run.status.in_(("queued", "running"))
                )
            )
        ).scalar()
        if busy:
            return busy
        run = Run(
            workspace_id=workspace_id,
            trigger=trigger,
            as_of=as_of or utcnow().date(),
            created_by=user_id,
            steps=[{"key": k, "status": "pending", "detail": {}} for k in STEP_KEYS],
        )
        s.add(run)
        await s.commit()
        await s.refresh(run, ["creator"])  # the caller serialises it after the session closes
    task = asyncio.create_task(execute(run.id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return run


async def execute(run_id: str, cutoff: datetime | None = None) -> None:
    async with dbmod.SessionLocal() as s:
        run = await s.get(Run, run_id)
        if not run:
            return
        ctx = RunContext(run.id, run.workspace_id, run.as_of, cutoff)
    async with _locks[ctx.workspace_id]:
        await ctx.save(status="running", started_at=utcnow())
        try:
            await _pipeline(ctx)
            await ctx.save(status="succeeded", finished_at=utcnow())
        except Exception as e:  # noqa: BLE001 - a run must always end with a status
            log.exception("run %s failed", run_id)
            for st in ctx.steps:
                if st["status"] == "running":
                    st["status"] = "failed"
                    st["message"] = str(e)[:300]
            await ctx.save(
                status="failed",
                finished_at=utcnow(),
                error=f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}",
            )


async def recover_stale_runs() -> int:
    """Runs left 'running' by a restart can't finish; mark them failed."""
    async with dbmod.SessionLocal() as s:
        res = await s.execute(
            update(Run)
            .where(Run.status.in_(("queued", "running")))
            .values(status="failed", error="Interrupted by a server restart", finished_at=utcnow())
        )
        await s.commit()
        return res.rowcount or 0


async def _pipeline(ctx: RunContext) -> None:
    async with dbmod.SessionLocal() as s:
        ws = await s.get(Workspace, ctx.workspace_id)
        topics = list(
            (
                await s.execute(
                    select(Topic)
                    .options(undefer(Topic.embedding))
                    .where(Topic.workspace_id == ws.id, Topic.archived.is_(False))
                    .order_by(Topic.position)
                )
            ).scalars()
        )
        if not topics:
            raise RuntimeError("The watchlist is empty. Add topics in Team > Settings first.")

        # Prepare: search phrases + topic vectors
        await ctx.begin("prepare", "Reading watchlist")
        generated = await _ensure_keywords(ctx, ws, topics)
        topic_vecs = await _ensure_topic_vectors(ctx, ws, topics)
        await s.commit()
        await ctx.finish(
            "prepare",
            f"{len(topics)} topics",
            topics=[{"name": t.name, "keywords": t.keywords} for t in topics],
            generated_keywords=generated,
        )

        # Collect
        await ctx.begin("collect", "Fetching news")
        backfill = ws.collected_until is None
        if ws.collected_until is None:
            start = end_of_day(ctx.as_of) - timedelta(days=BACKFILL_DAYS)
        else:
            start = ws.collected_until - OVERLAP
        end = ctx.cutoff
        calls: list[dict] = []
        new_items: list[Item] = []
        if start < end:
            phrases = {t.id: (t.keywords or [t.name])[:3] for t in topics}
            res = await sources.collect(phrases, start, end, backfill=backfill)
            calls = res.calls
            new_items = await _store_items(s, ws.id, ctx.run_id, res.items)
            ws = await s.get(Workspace, ws.id)
            ws.collected_until = end
            await s.commit()
        by_collector: dict[str, int] = defaultdict(int)
        for it in new_items:
            by_collector[it.collector] += 1
        errors = [c for c in calls if c.get("error")]
        await ctx.finish(
            "collect",
            f"{len(new_items)} new items" + (f", {len(errors)} source errors" if errors else ""),
            window={"from": start.isoformat(), "to": end.isoformat(), "backfill": backfill},
            new_items=len(new_items),
            by_collector=dict(by_collector),
            calls=calls,
        )

        # Embed + near-duplicates
        await ctx.begin("embed", "Embedding new items")
        horizon_start = end_of_day(ctx.as_of) - timedelta(days=scoring.HORIZON)
        pending = list(
            (
                await s.execute(
                    select(Item)
                    .options(undefer(Item.embedding))
                    .where(
                        Item.workspace_id == ws.id,
                        Item.classified_at.is_(None),
                        Item.published_at < ctx.cutoff,
                    )
                )
            ).scalars()
        )
        need_vec = [it for it in pending if it.embedding is None]
        if need_vec:
            vecs = await llm.embed(ctx.meter, [classify.item_text(i.title, i.text) for i in need_vec])
            for it, v in zip(need_vec, vecs):
                it.embedding = llm.to_bytes(v)
            await s.commit()
        dups = await _mark_duplicates(s, ws.id, [i for i in pending if i.source_type == "news"])
        # Items older than the horizon can no longer move a verdict: skip them.
        stale = [i for i in pending if i.published_at < horizon_start and i.duplicate_of is None]
        for i in stale:
            i.classified_at = utcnow()
        await s.commit()
        await ctx.finish(
            "embed",
            f"{len(need_vec)} embedded, {dups} near-duplicates merged",
            embedded=len(need_vec),
            duplicates=dups,
            too_old=len(stale),
        )

        # Classify
        await ctx.begin("classify", "Reading sources")
        todo = [
            i
            for i in pending
            if i.duplicate_of is None and i.published_at >= horizon_start and i.classified_at is None
        ]
        refs = [
            classify.ItemRef(
                id=i.id,
                title=i.title,
                text=i.text,
                source=i.source,
                date=i.published_at.date().isoformat(),
                is_upload=i.source_type == "upload",
                vector=llm.from_bytes(i.embedding),
            )
            for i in todo
        ]
        trefs = [
            classify.TopicRef(id=t.id, name=t.name, description=t.description, vector=topic_vecs[t.id])
            for t in topics
        ]

        async def cls_progress(done: int, total: int):
            await ctx.progress("classify", f"Reading sources: batch {done}/{total}")

        cres = await classify.classify(ctx.meter, ws.subject, trefs, refs, cls_progress)
        for a in cres.assessments:
            s.add(
                Evidence(
                    workspace_id=ws.id,
                    item_id=a.item_id,
                    topic_id=a.topic_id,
                    relevance=a.relevance,
                    signal=a.signal,
                    quote=a.quote,
                    note=a.note,
                    run_id=ctx.run_id,
                )
            )
        now = utcnow()
        for i in todo:
            i.classified_at = now
        await s.flush()
        n_mentions = await _store_companies(s, ws.id, cres.companies, {i.id: i for i in todo})
        await s.commit()
        uploads_read = sum(1 for r in refs if r.is_upload)
        await ctx.finish(
            "classify",
            f"{len(cres.assessments)} pieces of evidence from {len(todo)} items",
            items=len(todo),
            uploads=uploads_read,
            prefilter_passed=cres.candidates,
            prefilter_skipped=cres.skipped,
            evidence=len(cres.assessments),
            unverified_quotes_dropped=cres.dropped_quotes,
            batches=cres.batches,
            failed_batches=cres.failed_batches,
            company_mentions=n_mentions,
        )

        # Score
        await ctx.begin("score", "Weighing evidence")
        points_by_topic, ev_rows = await _load_points(s, ws.id, [t.id for t in topics], ctx)
        prev_brief = (
            await s.execute(
                select(Brief)
                .where(Brief.workspace_id == ws.id, Brief.date < ctx.as_of)
                .order_by(Brief.date.desc())
                .limit(1)
            )
        ).scalar()
        previous = {}
        if prev_brief:
            previous = {t["id"]: t["verdict"] for t in prev_brief.data.get("topics", [])}
        all_pts = {t.id: points_by_topic.get(t.id, []) for t in topics}
        norm = scoring.collector_norm(await _collector_totals(s, ws.id, ctx))
        scores, series, volumes, subj_tone = scoring.score_all(all_pts, ctx.score_day, previous, norm)
        await ctx.finish(
            "score",
            ", ".join(
                f"{v} {k}"
                for k, v in _tally(s_.verdict for s_ in scores.values()).items()
            ),
            subject_tone=round(subj_tone, 3),
            topics={t.name: scores[t.id].verdict for t in topics},
        )

        # Explain
        await ctx.begin("explain", "Writing the reasoning")
        inputs = []
        topic_sources: dict[str, list[str]] = {}
        for t in topics:
            views = _pick_evidence(ev_rows.get(t.id, []), ctx.score_day)
            topic_sources[t.id] = [v.evidence_id for v in _all_recent(ev_rows.get(t.id, []), ctx.score_day)]
            inputs.append(
                narrate.TopicInput(
                    topic_id=t.id,
                    name=t.name,
                    description=t.description,
                    score=scores[t.id],
                    previous=previous.get(t.id),
                    evidence=views,
                )
            )
        changes = []
        for t in topics:
            p = previous.get(t.id)
            if p and p != scores[t.id].verdict:
                changes.append(
                    {"topic_id": t.id, "name": t.name, "from": p, "to": scores[t.id].verdict}
                )
        change_lines = [f"{c['name']}: {c['from']} -> {c['to']}" for c in changes]
        headline, texts, vstats = await narrate.narrate(
            ctx.meter, ws.subject, inputs, change_lines, first_brief=prev_brief is None
        )
        if not headline:
            headline = artifacts.default_headline(changes, scores, topics, prev_brief is None)
        await ctx.finish(
            "explain",
            f"{vstats['citations']} citations checked",
            **vstats,
        )

        # Publish
        await ctx.begin("publish", "Writing brief and trace")
        comp = await _companies_for_brief(s, ws.id, [t.id for t in topics], ctx)
        data = artifacts.brief_data(
            ws=ws,
            as_of=ctx.as_of,
            run_id=ctx.run_id,
            topics=topics,
            scores=scores,
            series=series,
            volumes=volumes,
            texts=texts,
            previous=previous,
            prev_date=prev_brief.date if prev_brief else None,
            headline=headline,
            changes=changes,
            ev_rows=ev_rows,
            topic_sources=topic_sources,
            companies=comp,
        )
        data["data_through"] = ctx.score_day.isoformat()
        brief = (
            await s.execute(
                select(Brief).where(Brief.workspace_id == ws.id, Brief.date == ctx.as_of)
            )
        ).scalar()
        if brief:
            brief.data, brief.run_id, brief.created_at = data, ctx.run_id, utcnow()
        else:
            brief = Brief(workspace_id=ws.id, run_id=ctx.run_id, date=ctx.as_of, data=data)
            s.add(brief)
        await s.flush()
        ctx.step("publish").update(status="done", finished_at=utcnow().isoformat(), message="Brief published")
        data["cost_usd"] = ctx.meter.cost_usd
        brief.data = dict(data)
        run_row = await s.get(Run, ctx.run_id)
        files = artifacts.run_files(
            data=data,
            run=run_row,
            steps=ctx.steps,
            meter=ctx.meter,
            scores=scores,
            topics=topics,
            inputs=inputs,
            new_items=new_items,
            ev_rows=ev_rows,
        )
        for f in files:
            f.workspace_id = ws.id
            f.run_id = ctx.run_id
            f.brief_date = ctx.as_of
            s.add(f)
        await s.commit()
        await ctx.save(brief_id=brief.id)


def _tally(verdicts) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in verdicts:
        out[v] = out.get(v, 0) + 1
    return out


KEYWORD_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["topics"],
    "properties": {
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["topic", "phrases"],
                "properties": {
                    "topic": {"type": "string"},
                    "phrases": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}


async def _ensure_keywords(ctx: RunContext, ws: Workspace, topics: list[Topic]) -> list[str]:
    missing = [t for t in topics if not t.keywords]
    if not missing:
        return []
    prompt = (
        f"Subject: {ws.subject}\n{ws.subject_description}\n\n"
        "For each topic give 3 news search phrases that journalists actually put in English "
        "headlines about it: 1-3 words each, e.g. the usual short name, an abbreviation, a common "
        "synonym (for 'Buy now, pay later': 'BNPL', 'buy now pay later', 'pay in four'). Each phrase "
        "is searched as an exact phrase, so don't stack qualifiers like 'adoption', 'trends' or "
        "'regulation' onto it. Avoid single generic words. Topics:\n"
        + "\n".join(f"- {t.name}: {t.description}" for t in missing)
    )
    res = await llm.structured(
        ctx.meter,
        model=get_settings().model_classify,
        system="You build precise news search queries.",
        user=prompt,
        schema=KEYWORD_SCHEMA,
        name="search_phrases",
        effort="low",
    )
    by_name = {r["topic"].strip().lower(): r["phrases"] for r in res.get("topics", [])}
    done = []
    for t in missing:
        phrases = [p.strip() for p in by_name.get(t.name.lower(), []) if p.strip()]
        # The topic's own name is always searched too: generated phrases can be too narrow.
        t.keywords = _dedupe_ci([t.name, *phrases])[:3]
        done.append(t.name)
    return done


def _dedupe_ci(phrases: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for p in phrases:
        k = " ".join(p.lower().replace(",", " ").split())
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


async def _ensure_topic_vectors(ctx: RunContext, ws: Workspace, topics: list[Topic]) -> dict[str, np.ndarray]:
    import hashlib

    texts = {
        t.id: classify.topic_text(ws.subject, t.name, t.description, t.keywords or []) for t in topics
    }
    keys = {tid: hashlib.sha1(txt.encode()).hexdigest() for tid, txt in texts.items()}
    stale = [t for t in topics if t.embedding_key != keys[t.id] or t.embedding is None]
    if stale:
        vecs = await llm.embed(ctx.meter, [texts[t.id] for t in stale])
        for t, v in zip(stale, vecs):
            t.embedding = llm.to_bytes(v)
            t.embedding_key = keys[t.id]
    return {t.id: llm.from_bytes(t.embedding) for t in topics}


async def _store_items(s, workspace_id: str, run_id: str, raw: list[sources.RawItem]) -> list[Item]:
    seen_hash: dict[str, sources.RawItem] = {}
    seen_url: set[str] = set()
    for r in raw:
        h = sources.content_hash(r)
        u = sources.normalize_url(r.url)
        if h in seen_hash or u in seen_url:
            continue
        seen_hash[h] = r
        seen_url.add(u)
    if not seen_hash:
        return []
    existing_hashes = set(
        (
            await s.execute(
                select(Item.content_hash).where(
                    Item.workspace_id == workspace_id, Item.content_hash.in_(list(seen_hash))
                )
            )
        ).scalars()
    )
    existing_urls = set(
        (
            await s.execute(
                select(Item.url).where(
                    Item.workspace_id == workspace_id,
                    Item.url.in_([r.url for r in seen_hash.values()]),
                )
            )
        ).scalars()
    )
    out = []
    for h, r in seen_hash.items():
        if h in existing_hashes or r.url in existing_urls:
            continue
        it = Item(
            workspace_id=workspace_id,
            source_type="news",
            source=r.source[:120],
            collector=r.collector,
            url=r.url,
            title=r.title[:1000],
            text=r.text,
            published_at=r.published_at,
            collected_run_id=run_id,
            content_hash=h,
            engagement=r.engagement,
            meta={**r.meta, "query": r.query},
        )
        s.add(it)
        out.append(it)
    await s.flush()
    return out


async def _mark_duplicates(s, workspace_id: str, items: list[Item]) -> int:
    """Same story, different outlet: keep the earliest, point the rest at it."""
    if not items:
        return 0
    lo = min(i.published_at for i in items) - timedelta(days=3)
    hi = max(i.published_at for i in items) + timedelta(days=3)
    pool = list(
        (
            await s.execute(
                select(Item)
                .options(undefer(Item.embedding))
                .where(
                    Item.workspace_id == workspace_id,
                    Item.source_type == "news",
                    Item.duplicate_of.is_(None),
                    Item.published_at >= lo,
                    Item.published_at <= hi,
                )
            )
        ).scalars()
    )
    pool = [p for p in pool if p.embedding is not None]
    if len(pool) < 2:
        return 0
    pool.sort(key=lambda i: i.published_at)
    M = np.vstack([llm.from_bytes(p.embedding) for p in pool])
    new_ids = {i.id for i in items}
    sims = M @ M.T
    count = 0
    for k, p in enumerate(pool):
        if p.id not in new_ids or p.duplicate_of:
            continue
        for j in range(k):
            q = pool[j]
            if q.duplicate_of or abs((p.published_at - q.published_at).days) > 3:
                continue
            if sims[k, j] >= DUP_SIM:
                p.duplicate_of = q.id
                p.classified_at = utcnow()
                also = list(q.meta.get("also", []))[:20]
                also.append({"source": p.source, "url": p.url, "title": p.title})
                q.meta = {**q.meta, "also": also}
                count += 1
                break
    return count


async def _store_companies(s, workspace_id: str, hits, items_by_id: dict[str, Item]) -> int:
    if not hits:
        return 0
    rows = list((await s.execute(select(Company).where(Company.workspace_id == workspace_id))).scalars())
    known = {c.norm: c for c in rows}
    n = 0
    seen: set[tuple] = set()
    for h in hits:
        key = companies.resolve(h.name, {k: c.id for k, c in known.items()})
        if key is None:
            nk = companies.norm_key(h.name)
            if not nk:
                continue
            c = Company(workspace_id=workspace_id, name=companies.display_name([h.name]), norm=nk, aliases=[h.name])
            s.add(c)
            await s.flush()
            known[nk] = c
        else:
            c = known[key]
            if h.name not in (c.aliases or []):
                c.aliases = [*(c.aliases or []), h.name]
                c.name = companies.display_name(c.aliases)
        item = items_by_id.get(h.item_id)
        for tid in h.topic_ids or [None]:
            k = (c.id, h.item_id, tid)
            if k in seen:
                continue
            seen.add(k)
            s.add(
                CompanyMention(
                    workspace_id=workspace_id,
                    company_id=c.id,
                    item_id=h.item_id,
                    topic_id=tid,
                    alias=h.name,
                    event_type=h.event_type,
                    event=h.event,
                    event_date=item.published_at.date() if item else None,
                )
            )
            n += 1
    return n


async def _load_points(s, workspace_id: str, topic_ids: list[str], ctx: RunContext):
    """All evidence that can influence this brief (horizon + sparkline window)."""
    since = end_of_day(ctx.as_of) - timedelta(days=scoring.HORIZON + scoring.SERIES_DAYS)
    rows = list(
        (
            await s.execute(
                select(Evidence)
                .join(Item, Item.id == Evidence.item_id)
                .where(
                    Evidence.workspace_id == workspace_id,
                    Evidence.topic_id.in_(topic_ids),
                    Item.published_at >= since,
                    Item.published_at < ctx.cutoff,
                    Item.duplicate_of.is_(None),
                )
            )
        ).scalars()
    )
    files = {}
    file_ids = {e.item.file_id for e in rows if e.item.file_id}
    if file_ids:
        files = dict(
            (await s.execute(select(File.id, File.filename).where(File.id.in_(file_ids)))).all()
        )
    points: dict[str, list[scoring.Point]] = defaultdict(list)
    ev_rows: dict[str, list[dict]] = defaultdict(list)
    for e in rows:
        it = e.item
        is_up = it.source_type == "upload"
        src = (f"file:{it.file_id}" if is_up else it.source) or "unknown"
        points[e.topic_id].append(
            scoring.Point(
                item_id=it.id,
                day=it.published_at.date(),
                relevance=e.relevance,
                signal=e.signal,
                source=src,
                is_upload=is_up,
                engagement=it.engagement,
                collector=it.collector,
            )
        )
        ev_rows[e.topic_id].append(
            {
                "evidence_id": e.id,
                "item_id": it.id,
                "title": it.title,
                "url": it.url,
                "source": files.get(it.file_id, it.source) if is_up else it.source,
                "source_type": it.source_type,
                "collector": it.collector,
                "file_id": it.file_id,
                "file_name": files.get(it.file_id),
                "date": it.published_at.date(),
                "signal": e.signal,
                "relevance": e.relevance,
                "quote": e.quote,
                "note": e.note,
                "engagement": it.engagement,
                "also": len(it.meta.get("also", [])) if it.meta else 0,
                "hn_url": (it.meta or {}).get("hn_url"),
                "chunk_index": it.chunk_index,
            }
        )
    return points, ev_rows


async def _collector_totals(s, workspace_id: str, ctx: RunContext) -> dict[tuple[str, date], int]:
    """How many distinct news items each collector returned per day."""
    since = end_of_day(ctx.as_of) - timedelta(days=scoring.HORIZON + scoring.SERIES_DAYS)
    rows = (
        await s.execute(
            select(Item.collector, Item.published_at).where(
                Item.workspace_id == workspace_id,
                Item.source_type == "news",
                Item.duplicate_of.is_(None),
                Item.published_at >= since,
                Item.published_at < ctx.cutoff,
            )
        )
    ).all()
    out: dict[tuple[str, date], int] = defaultdict(int)
    for collector, published in rows:
        out[(collector, published.date())] += 1
    return dict(out)


def _weight(r: dict, as_of: date) -> float:
    age = (as_of - r["date"]).days
    w = r["relevance"] * (3.0 if r["source_type"] == "upload" else 1.0)
    w *= 1 + min(1.5, np.log10(1 + (r["engagement"] or 0)) / 2) + 0.2 * r["also"]
    half = 21 if r["source_type"] == "upload" else 7
    return w * (0.5 ** (max(age, 0) / half)) * (1 + 0.25 * abs(r["signal"]))


def _all_recent(rows: list[dict], as_of: date) -> list[narrate.EvidenceView]:
    lo = as_of - timedelta(days=scoring.HORIZON - 1)
    keep = [r for r in rows if lo <= r["date"] <= as_of]
    keep.sort(key=lambda r: -_weight(r, as_of))
    return [_view(r) for r in keep[:40]]


def _pick_evidence(rows: list[dict], as_of: date) -> list[narrate.EvidenceView]:
    """The evidence the narrator sees: strongest recent items, team files always included."""
    lo = as_of - timedelta(days=scoring.HORIZON - 1)
    pool = [r for r in rows if lo <= r["date"] <= as_of]
    uploads = sorted((r for r in pool if r["source_type"] == "upload"), key=lambda r: -_weight(r, as_of))[:3]
    news = sorted((r for r in pool if r["source_type"] != "upload"), key=lambda r: -_weight(r, as_of))
    picked = uploads + news[: narrate.MAX_EVIDENCE - len(uploads)]
    picked.sort(key=lambda r: r["date"], reverse=True)
    return [_view(r) for r in picked]


def _view(r: dict) -> narrate.EvidenceView:
    return narrate.EvidenceView(
        evidence_id=r["evidence_id"],
        item_id=r["item_id"],
        title=r["title"],
        source=r["source"],
        date=r["date"].isoformat(),
        signal=r["signal"],
        relevance=r["relevance"],
        quote=r["quote"],
        note=r["note"],
        is_upload=r["source_type"] == "upload",
    )


async def _companies_for_brief(s, workspace_id: str, topic_ids: list[str], ctx: RunContext) -> dict[str, list[dict]]:
    lo = ctx.score_day - timedelta(days=scoring.HORIZON - 1)
    rows = (
        await s.execute(
            select(CompanyMention, Company, Item)
            .join(Company, Company.id == CompanyMention.company_id)
            .join(Item, Item.id == CompanyMention.item_id)
            .where(
                CompanyMention.workspace_id == workspace_id,
                CompanyMention.topic_id.in_(topic_ids),
                Item.published_at < ctx.cutoff,
                CompanyMention.event_date >= lo,
            )
        )
    ).all()
    per: dict[str, dict[str, dict]] = defaultdict(dict)
    for m, c, it in rows:
        entry = per[m.topic_id].setdefault(
            c.id, {"id": c.id, "name": c.name, "aliases": c.aliases or [], "events": []}
        )
        entry["events"].append(
            {
                "type": m.event_type,
                "event": m.event,
                "date": m.event_date.isoformat() if m.event_date else None,
                "item_id": it.id,
                "title": it.title,
                "url": it.url,
                "source": it.source,
                "alias": m.alias,
            }
        )
    out: dict[str, list[dict]] = {}
    for tid, comps in per.items():
        lst = list(comps.values())
        for c in lst:
            c["events"].sort(key=lambda e: e["date"] or "", reverse=True)
            c["events"] = c["events"][:8]
        lst.sort(key=lambda c: (-len(c["events"]), c["name"].lower()))
        out[tid] = lst[:8]
    return out
