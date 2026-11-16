"""Item -> topic evidence.

Two stages so a daily run costs cents:

1. **Prefilter** (embeddings, ~free): cosine similarity between each new item
   and each topic. Items that resemble no topic never reach the LLM.
2. **Classify** (cheap model, batched, strict JSON): for each candidate pair the
   model rates relevance and the direction the item points to, quotes the
   sentence it relied on, and lists companies acting in it.

Quotes are checked against the item text; a quote the model made up is
dropped, so whatever the brief shows as "the source says" is really there.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field

import numpy as np

from ..config import get_settings
from . import llm

SIM_THRESHOLD = 0.27  # text-embedding-3-small: unrelated pairs sit around 0.05-0.2
UPLOAD_SIM_THRESHOLD = 0.18
MAX_CANDIDATES = 3
MIN_RELEVANCE = 0.5
BATCH = 12
CONCURRENCY = 4

EVENT_TYPES = [
    "funding",
    "launch",
    "acquisition",
    "partnership",
    "adoption",
    "layoffs",
    "shutdown",
    "research",
    "legal",
    "other",
]


@dataclass
class TopicRef:
    id: str
    name: str
    description: str
    vector: np.ndarray


@dataclass
class ItemRef:
    id: str
    title: str
    text: str
    source: str
    date: str
    is_upload: bool
    vector: np.ndarray


@dataclass
class Assessment:
    item_id: str
    topic_id: str
    relevance: float
    signal: int
    quote: str
    note: str
    quote_verified: bool


@dataclass
class CompanyHit:
    item_id: str
    name: str
    event_type: str
    event: str
    topic_ids: list[str]


@dataclass
class ClassifyResult:
    assessments: list[Assessment] = field(default_factory=list)
    companies: list[CompanyHit] = field(default_factory=list)
    candidates: int = 0  # items that passed the prefilter
    skipped: int = 0  # items rejected by the prefilter
    dropped_quotes: int = 0
    batches: int = 0
    failed_batches: int = 0


def topic_text(subject: str, name: str, description: str, keywords: list[str]) -> str:
    kw = f" Related terms: {', '.join(keywords)}." if keywords else ""
    return f"{subject} - {name}. {description}{kw}".strip()


def item_text(title: str, text: str) -> str:
    return f"{title}\n{text[:1500]}".strip()


def prefilter(items: list[ItemRef], topics: list[TopicRef]) -> dict[str, list[str]]:
    """item id -> candidate topic ids (most similar first)."""
    if not items or not topics:
        return {}
    T = np.vstack([t.vector for t in topics])
    out: dict[str, list[str]] = {}
    for it in items:
        sims = T @ it.vector
        thr = UPLOAD_SIM_THRESHOLD if it.is_upload else SIM_THRESHOLD
        order = np.argsort(-sims)
        cands = [topics[i].id for i in order[:MAX_CANDIDATES] if sims[i] >= thr]
        if it.is_upload:  # a team's own file is worth a look against every close topic
            cands = [topics[i].id for i in order if sims[i] >= thr][: len(topics)]
        if cands:
            out[it.id] = cands
    return out


_NORM = re.compile(r"[\s ]+")


def _norm(s: str) -> str:
    s = s.lower().replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    s = s.replace("—", "-").replace("–", "-")
    return _NORM.sub(" ", s).strip(" .\"'")


def verify_quote(quote: str, title: str, text: str) -> bool:
    q = _norm(quote)
    if len(q) < 8:
        return False
    hay = _norm(title + " \n " + text)
    if q in hay:
        return True
    # Allow the model to elide the middle with "..." as long as every part is real.
    parts = [p for p in re.split(r"\s*(?:\.\.\.|…)\s*", q) if p]
    return len(parts) > 1 and all(len(p) >= 6 and p in hay for p in parts)


SYSTEM = """You are the research analyst behind Tellwind, a daily brief that tells a team which topics in their subject are rising, holding steady or fading.

You get a batch of sources (news items or chunks of the team's own files) and the team's watchlist of topics. For every source, assess ONLY the candidate topics listed for it.

For each candidate topic return:
- relevance (0-1): how directly the source is about this topic. 1 = the topic is the main subject; 0.5 = a substantive part of it; below 0.5 = passing mention or unrelated. Be strict.
- signal: what the source says about the topic's MOMENTUM (adoption, investment, attention, activity), not whether the news is good or bad in tone:
  +2 clear evidence the topic is heating up (major launch, big funding, rapid adoption, many new entrants)
  +1 some evidence of growth or activity
   0 neutral mention, no indication of direction
  -1 some evidence of slowing (delays, scepticism, declining use, pullback)
  -2 clear evidence the topic is cooling (shutdowns, abandonment, sharp decline, reports saying it is fading)
  A security incident or criticism about a topic still counts as +1 attention if it makes the topic more prominent, unless it says people are moving away from it.
- quote: one short sentence or phrase copied VERBATIM from the source (title or text) that best supports your assessment. Do not paraphrase. If nothing fits, use the title verbatim.
- note: max 20 words, why you rated it so.

Omit topics with relevance below 0.5 entirely.

Also list companies or organisations (businesses, labs, foundations, government bodies; NOT products, browsers, models or open-source repos - attribute a product to its maker, e.g. "Chrome" -> Google) the source shows DOING something (raising money, launching, acquiring, partnering, adopting, cutting, shutting down, publishing research, being sued). Use the name as written in the source. event: max 15 words, what they did. topics: the topic ids it relates to. Skip companies only mentioned in passing. Return empty lists when nothing applies."""


def _schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["items"],
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["ref", "assessments", "companies"],
                    "properties": {
                        "ref": {"type": "string"},
                        "assessments": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["topic", "relevance", "signal", "quote", "note"],
                                "properties": {
                                    "topic": {"type": "string"},
                                    "relevance": {"type": "number"},
                                    "signal": {"type": "integer", "enum": [-2, -1, 0, 1, 2]},
                                    "quote": {"type": "string"},
                                    "note": {"type": "string"},
                                },
                            },
                        },
                        "companies": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "event_type", "event", "topics"],
                                "properties": {
                                    "name": {"type": "string"},
                                    "event_type": {"type": "string", "enum": EVENT_TYPES},
                                    "event": {"type": "string"},
                                    "topics": {"type": "array", "items": {"type": "string"}},
                                },
                            },
                        },
                    },
                },
            }
        },
    }


def _build_prompt(
    subject: str, topics: list[TopicRef], batch: list[ItemRef], cands: dict[str, list[str]]
) -> tuple[str, dict[str, str], dict[str, str]]:
    t_alias = {t.id: f"T{i + 1}" for i, t in enumerate(topics)}
    i_alias = {it.id: f"S{i + 1}" for i, it in enumerate(batch)}
    lines = [f"Subject: {subject}", "", "Watchlist topics:"]
    for t in topics:
        desc = f" - {t.description}" if t.description else ""
        lines.append(f"{t_alias[t.id]}: {t.name}{desc}")
    lines += ["", "Sources:"]
    for it in batch:
        kind = "TEAM FILE" if it.is_upload else "NEWS"
        limit = 1600 if it.is_upload else 700
        lines.append(
            f"\n[{i_alias[it.id]}] {kind} | {it.source} | {it.date}\n"
            f"Title: {it.title}\n"
            + (f"Text: {it.text[:limit]}\n" if it.text else "")
            + f"Candidate topics: {', '.join(t_alias[c] for c in cands[it.id])}"
        )
    return "\n".join(lines), {v: k for k, v in t_alias.items()}, {v: k for k, v in i_alias.items()}


async def classify(
    meter: llm.Meter,
    subject: str,
    topics: list[TopicRef],
    items: list[ItemRef],
    progress=None,
) -> ClassifyResult:
    res = ClassifyResult()
    cands = prefilter(items, topics)
    res.candidates = len(cands)
    res.skipped = len(items) - len(cands)
    todo = [it for it in items if it.id in cands]
    by_id = {it.id: it for it in todo}
    batches = [todo[i : i + BATCH] for i in range(0, len(todo), BATCH)]
    res.batches = len(batches)
    sem = asyncio.Semaphore(CONCURRENCY)
    model = get_settings().model_classify
    done = 0

    async def run(batch: list[ItemRef]):
        nonlocal done
        prompt, t_back, i_back = _build_prompt(subject, topics, batch, cands)
        async with sem:
            try:
                out = await llm.structured(
                    meter,
                    model=model,
                    system=SYSTEM,
                    user=prompt,
                    schema=_schema(),
                    name="classification",
                    effort="low",
                )
            except llm.LLMError:
                res.failed_batches += 1
                return
            finally:
                done += 1
                if progress:
                    await progress(done, len(batches))
        for row in out.get("items", []):
            item_id = i_back.get(row.get("ref", ""))
            if not item_id:
                continue
            it = by_id[item_id]
            allowed = set(cands[item_id])
            for a in row.get("assessments", []):
                tid = t_back.get(a.get("topic", ""))
                if not tid or tid not in allowed:
                    continue
                rel = float(a.get("relevance", 0))
                if rel < MIN_RELEVANCE:
                    continue
                quote = (a.get("quote") or "").strip()
                ok = verify_quote(quote, it.title, it.text)
                if not ok:
                    res.dropped_quotes += 1
                    quote = ""
                res.assessments.append(
                    Assessment(
                        item_id=item_id,
                        topic_id=tid,
                        relevance=min(1.0, max(0.0, rel)),
                        signal=int(a.get("signal", 0)),
                        quote=quote[:400],
                        note=(a.get("note") or "")[:300],
                        quote_verified=ok,
                    )
                )
            for c in row.get("companies", []):
                name = (c.get("name") or "").strip()
                if not name or len(name) > 120:
                    continue
                res.companies.append(
                    CompanyHit(
                        item_id=item_id,
                        name=name,
                        event_type=c.get("event_type", "other"),
                        event=(c.get("event") or "")[:300],
                        topic_ids=[t_back[t] for t in c.get("topics", []) if t in t_back],
                    )
                )

    await asyncio.gather(*(run(b) for b in batches))
    return res
