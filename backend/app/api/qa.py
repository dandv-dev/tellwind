"""Questions about the brief: the workspace's own sources first, the web second.

1. Retrieve: embed the question, rank the workspace's items by cosine
   similarity (uploads not yet embedded are embedded on the spot) and keep the
   closest ones, plus the brief the user was looking at as context.
2. Answer from the workspace: the model gets numbered sources [1..n] and must
   attach source numbers to every claim. It also says whether those sources were
   enough to answer.
3. If they weren't, ask again with OpenAI's web search tool. The web answer's
   URL citations become extra sources labelled "web".
4. Validate: a workspace claim survives only if it cites at least one source
   that was actually given to the model. Claims without a valid source are
   dropped, so everything left on screen is backed by something you can open.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from ..agent import classify, llm
from ..agent.sources import domain_of
from ..config import get_settings
from ..db import get_db
from ..models import Brief, Item, Question, utcnow
from ..security import WorkspaceAccess, viewer

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["qa"])

TOP_K = 12
MIN_SIM = 0.22
LAZY_EMBED_CAP = 200
DAILY_LIMIT = 40  # questions per workspace per day: keeps the API bill bounded
SNIPPET = 700

SYSTEM = """You answer a team's question about their field using ONLY the numbered sources given.

Rules:
- Split the answer into short claims (1-2 sentences each). Every claim lists the numbers of the
  sources that support it in `refs`. Never cite a source that doesn't support the claim.
- Do not use outside knowledge. If the sources don't cover something, leave it out.
- Set `enough` to false when the sources can't answer the core of the question (missing facts,
  too old, off-topic); then `missing` says in a few words what to look for on the web.
- The brief summary is context about the team's current verdicts; it is not a source and cannot
  be cited.
- Answer in the language of the question. Plain, specific wording; numbers as people write them.
- At most 5 claims."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["claims", "enough", "missing"],
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "refs"],
                "properties": {
                    "text": {"type": "string"},
                    "refs": {"type": "array", "items": {"type": "integer"}},
                },
            },
        },
        "enough": {"type": "boolean"},
        "missing": {"type": "string"},
    },
}

WEB_SYSTEM = """You complete a team's answer with recent information from the web.
Search the web, then write 2-4 short factual sentences that answer the question. Every sentence
must be supported by a page you found. Answer in the language of the question. No headings, no
lists, no preamble."""


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    brief_date: date | None = None


def question_out(q: Question) -> dict:
    return {
        "id": q.id,
        "question": q.question,
        "created_at": q.created_at.isoformat(),
        "cost_usd": round(q.cost_usd, 5),
        "answer": q.answer,
    }


@router.get("/questions")
async def list_questions(acc: WorkspaceAccess = Depends(viewer), db: AsyncSession = Depends(get_db)):
    qs = (
        await db.execute(
            select(Question)
            .where(Question.workspace_id == acc.workspace.id)
            .order_by(Question.created_at.desc())
            .limit(20)
        )
    ).scalars()
    return {"questions": [question_out(q) for q in qs]}


@router.post("/ask")
async def ask(body: AskIn, acc: WorkspaceAccess = Depends(viewer), db: AsyncSession = Depends(get_db)):
    ws = acc.workspace
    since = utcnow() - timedelta(days=1)
    asked = (
        await db.execute(
            select(func.count()).where(Question.workspace_id == ws.id, Question.created_at >= since)
        )
    ).scalar_one()
    if asked >= DAILY_LIMIT:
        raise HTTPException(429, "question_limit")
    if not get_settings().openai_api_key:
        raise HTTPException(503, "no_api_key")

    meter = llm.Meter()
    brief = await _brief(db, ws.id, body.brief_date)
    try:
        answer = await answer_question(db, meter, ws.id, ws.subject, body.question.strip(), brief)
    except Exception as e:  # noqa: BLE001 - the UI shows a short message, the log has the rest
        log.exception("question failed")
        answer = {"claims": [], "sources": [], "used_web": False, "error": "failed"}

    q = Question(
        workspace_id=ws.id,
        user_id=acc.user.id,
        brief_id=brief.id if brief else None,
        question=body.question.strip(),
        answer=answer,
        cost_usd=meter.cost_usd,
    )
    db.add(q)
    await db.commit()
    return question_out(q)


async def _brief(db: AsyncSession, ws_id: str, day: date | None) -> Brief | None:
    stmt = select(Brief).where(Brief.workspace_id == ws_id)
    stmt = stmt.where(Brief.date == day) if day else stmt.order_by(Brief.date.desc()).limit(1)
    return (await db.execute(stmt)).scalar()


def brief_context(brief: Brief | None) -> str:
    if not brief:
        return "(no brief yet)"
    d = brief.data
    lines = [f"Brief of {d.get('date')}: {d.get('headline', '')}"]
    for t in d.get("topics", []):
        lines.append(f"- {t['name']}: {t['verdict']} ({t.get('strength', '')}). {t.get('summary', '')}")
    return "\n".join(lines)


async def retrieve(db: AsyncSession, meter: llm.Meter, ws_id: str, question: str, as_of: date | None) -> list[Item]:
    stmt = (
        select(Item)
        .options(undefer(Item.embedding))
        .where(Item.workspace_id == ws_id, Item.duplicate_of.is_(None))
    )
    items = list((await db.execute(stmt)).scalars())
    if as_of:  # questions about an older brief shouldn't see the future
        items = [i for i in items if i.published_at.date() <= as_of]
    if not items:
        return []

    missing = [i for i in items if i.embedding is None][:LAZY_EMBED_CAP]
    if missing:
        vecs = await llm.embed(meter, [classify.item_text(i.title, i.text) for i in missing])
        for it, v in zip(missing, vecs):
            it.embedding = llm.to_bytes(v)
        await db.flush()

    pool = [i for i in items if i.embedding is not None]
    qv = (await llm.embed(meter, [question]))[0]
    M = np.vstack([llm.from_bytes(i.embedding) for i in pool])
    sims = M @ qv
    # Team files get a small nudge: they are the team's own considered view.
    sims = sims + np.array([0.03 if i.source_type == "upload" else 0.0 for i in pool])
    order = np.argsort(-sims)
    return [pool[k] for k in order[:TOP_K] if sims[k] >= MIN_SIM]


def _source_line(n: int, it: Item) -> str:
    when = it.published_at.date().isoformat()
    kind = "team file" if it.source_type == "upload" else it.source or domain_of(it.url or "")
    text = (it.text or "").strip().replace("\n", " ")[:SNIPPET]
    return f"[{n}] {it.title} ({kind}, {when})\n{text}"


def _workspace_source(n: int, it: Item) -> dict:
    return {
        "ref": n,
        "kind": "workspace",
        "title": it.title,
        "url": it.url or "",
        "source": "team file" if it.source_type == "upload" else (it.source or domain_of(it.url or "")),
        "date": it.published_at.date().isoformat(),
        "file_id": it.file_id,
        "item_id": it.id,
    }


_MD_LINK_PAREN = re.compile(r"\s*\(\s*\[[^\]]*\]\([^)]*\)\s*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
# A sentence boundary: end punctuation, optionally followed by inline "([site](url))" citations
# (they belong to the sentence before), then whitespace and a capital letter.
_SENT = re.compile(r"(?<=[.!?])((?:\s*\(\[[^\]]*\]\([^)]*\)\))*)\s+(?=[A-ZА-ЯЁІЇЄҐ0-9\"“«])")


def web_claims(text: str, citations: list[dict], first_ref: int) -> tuple[list[dict], list[dict]]:
    """Turn a web-search answer into claims, each citing the pages annotated on its span."""
    spans = []
    start = 0
    for m in _SENT.finditer(text):
        end = m.start() + len(m.group(1))
        spans.append((text[start:end], start, end))
        start = m.end()
    if text[start:].strip():
        spans.append((text[start:], start, len(text)))

    sources: list[dict] = []
    by_url: dict[str, int] = {}
    claims: list[dict] = []
    for sentence, start, end in spans:
        refs: list[int] = []
        for c in citations:
            if c["start"] < end and c["end"] > start:
                url = c["url"].split("?utm_")[0]
                if url not in by_url:
                    by_url[url] = first_ref + len(sources)
                    sources.append(
                        {
                            "ref": by_url[url],
                            "kind": "web",
                            "title": c.get("title") or url,
                            "url": url,
                            "source": domain_of(url),
                            "date": None,
                            "file_id": None,
                            "item_id": None,
                        }
                    )
                if by_url[url] not in refs:
                    refs.append(by_url[url])
        clean = _MD_LINK.sub(r"\1", _MD_LINK_PAREN.sub("", sentence)).replace("**", "").strip()
        if refs and clean:  # an uncited sentence isn't shown
            claims.append({"text": clean, "refs": refs})
    return claims, sources


def validate_claims(claims: list[dict], valid_refs: set[int]) -> list[dict]:
    out = []
    for c in claims:
        refs = [r for r in dict.fromkeys(c.get("refs") or []) if r in valid_refs]
        text = (c.get("text") or "").replace("**", "").strip()
        if refs and text:
            out.append({"text": text, "refs": refs})
    return out


def renumber(claims: list[dict], sources: list[dict]) -> tuple[list[dict], list[dict]]:
    """Keep only cited sources, numbered 1..n in order of first citation."""
    order: dict[int, int] = {}
    for c in claims:
        for r in c["refs"]:
            order.setdefault(r, len(order) + 1)
    by_ref = {s["ref"]: s for s in sources}
    new_sources = [{**by_ref[old], "ref": new} for old, new in order.items() if old in by_ref]
    new_claims = [{"text": c["text"], "refs": [order[r] for r in c["refs"]]} for c in claims]
    return new_claims, new_sources


async def answer_question(
    db: AsyncSession, meter: llm.Meter, ws_id: str, subject: str, question: str, brief: Brief | None
) -> dict:
    s = get_settings()
    as_of = brief.date if brief else None
    items = await retrieve(db, meter, ws_id, question, as_of)

    ws_sources = [_workspace_source(n, it) for n, it in enumerate(items, 1)]
    claims: list[dict] = []
    enough = False
    missing = question
    if items:
        user = (
            f"Subject: {subject}\n\n{brief_context(brief)}\n\nQuestion: {question}\n\nSources:\n\n"
            + "\n\n".join(_source_line(n, it) for n, it in enumerate(items, 1))
        )
        out = await llm.structured(
            meter, model=s.model_answer, system=SYSTEM, user=user, schema=SCHEMA, name="answer", max_output_tokens=4000
        )
        claims = validate_claims(out.get("claims", []), {x["ref"] for x in ws_sources})
        enough = bool(out.get("enough")) and bool(claims)
        missing = out.get("missing") or question

    sources = list(ws_sources)
    used_web = False
    if not enough:
        used_web = True
        known = "\n".join(f"- {c['text']}" for c in claims) or "(nothing relevant)"
        # The cheap model reads the search results: they arrive as input tokens.
        text, cites = await llm.with_web_search(
            meter,
            model=s.model_classify,
            system=WEB_SYSTEM,
            user=f"Subject: {subject}\nQuestion: {question}\nLook for: {missing}\n\nThe team's own sources already say:\n{known}",
        )
        wc, wsrc = web_claims(text, cites, first_ref=len(ws_sources) + 1)
        claims += wc
        sources += wsrc

    claims, sources = renumber(claims, sources)
    result: dict = {"claims": claims, "sources": sources, "used_web": used_web}
    if not claims:
        result["error"] = "not_enough"
    return result
