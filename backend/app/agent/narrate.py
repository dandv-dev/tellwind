"""Reasoning text for each topic, with citations that are checked.

The verdict is already decided by ``scoring``; the model's job is to explain it
from the evidence it is shown. It may only cite evidence ids it was given.
After the call a validator drops any citation that isn't one of those ids, and
any point left with no valid citation. If nothing survives, a plain template
built from the numbers and the top sources is used instead, so a brief never
ships an unsupported claim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import get_settings
from . import llm
from .scoring import TopicScore, describe

MAX_EVIDENCE = 10
INLINE_IDS = re.compile(r"\s*[\(\[]\s*E\d+(?:\s*[,;]\s*E\d+)*\s*[\)\]]")


@dataclass
class EvidenceView:
    evidence_id: str
    item_id: str
    title: str
    source: str
    date: str
    signal: int
    relevance: float
    quote: str
    note: str
    is_upload: bool


SYSTEM = """You write the reasoning behind Tellwind's daily brief. Readers are busy and wary of AI: every statement must be traceable to a source.

For each topic you get: the verdict (already decided by a deterministic model - do NOT change or second-guess it), the numbers behind it, and a numbered list of evidence (E1, E2, ...). Explain the verdict using that evidence.

Rules:
- Each reasoning point is one or two plain sentences and cites the evidence ids it rests on. Cite only ids listed for THAT topic.
- Use numbers the way a person would: percentages and counts ("coverage up about 60% on the prior three weeks", "9 of 14 items in the last week"). Never quote raw weighted rates or decimals like 2.438.
- Cite the 1-4 most relevant ids per point, not every id.
- When the team's own files (TEAM FILE) are among the evidence, say what they add.
- For verdict "insufficient", say plainly what is missing (few items, one outlet, nothing recent); do not guess a direction.
- No hype, no filler, no invented facts. 2-4 points per topic.
- summary: one line (max 22 words) a reader can scan.
- watch: what would change the call (max 18 words).
- headline: one or two sentences on what changed since the previous brief, based on the verdict changes given. If this is the first brief, say what stands out."""


def _schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["headline", "topics"],
        "properties": {
            "headline": {"type": "string"},
            "topics": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["topic", "summary", "points", "watch"],
                    "properties": {
                        "topic": {"type": "string"},
                        "summary": {"type": "string"},
                        "points": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["text", "sources"],
                                "properties": {
                                    "text": {"type": "string"},
                                    "sources": {"type": "array", "items": {"type": "string"}},
                                },
                            },
                        },
                        "watch": {"type": "string"},
                    },
                },
            },
        },
    }


@dataclass
class TopicInput:
    topic_id: str
    name: str
    description: str
    score: TopicScore
    previous: str | None
    evidence: list[EvidenceView]


def _fmt_topic(alias: str, t: TopicInput) -> tuple[str, dict[str, str]]:
    d = describe(t.score)
    ev_alias: dict[str, str] = {}
    lines = [
        f"## {alias}: {t.name}",
        f"Verdict: {t.score.verdict} (strength {t.score.strength}, score {t.score.score:+.2f}); "
        f"previous brief: {t.previous or 'none'}",
        f"Coverage last 7 days: {d['recent_per_day']}/day weighted vs {d['baseline_per_day']}/day "
        f"in the 21 days before"
        + (f" ({d['coverage_change_pct']:+d}%)" if d["coverage_change_pct"] is not None else "")
        + f". Direction of evidence: {t.score.tone:+.2f} on a -2..+2 scale "
        f"({t.score.tone_rel:+.2f} vs the subject average).",
        f"Evidence in last 28 days: {t.score.evidence_count} items from {t.score.source_count} "
        f"sources ({t.score.upload_count} from team files), {t.score.recent_count} in last 14 days.",
    ]
    if t.score.reasons:
        lines.append(f"Rule notes: {', '.join(t.score.reasons)}")
    if t.score.capped_days:
        lines.append(f"Unusually busy days capped so they don't dominate: {', '.join(t.score.capped_days)}")
    lines.append("Evidence:")
    for i, e in enumerate(t.evidence):
        a = f"E{i + 1}"
        ev_alias[a] = e.evidence_id
        kind = "TEAM FILE" if e.is_upload else "NEWS"
        q = f' quote: "{e.quote}"' if e.quote else ""
        lines.append(
            f"- {a} [{kind} | {e.source} | {e.date} | signal {e.signal:+d}] {e.title}.{q} ({e.note})"
        )
    return "\n".join(lines), ev_alias


def fallback_points(t: TopicInput) -> tuple[str, list[dict], str]:
    """Template reasoning used if the model's text can't be validated."""
    d = describe(t.score)
    s = t.score
    pts: list[dict] = []
    if s.verdict == "insufficient":
        summary = f"Not enough to go on: {s.evidence_count} items from {s.source_count} sources."
        pts.append({"text": summary, "sources": [e.evidence_id for e in t.evidence[:2]]})
    else:
        chg = d["coverage_change_pct"]
        summary = f"{t.name} is {s.verdict}" + (f"; coverage {chg:+d}% vs prior weeks." if chg is not None else ".")
        top = sorted(t.evidence, key=lambda e: -abs(e.signal))[:3]
        for e in top:
            pts.append({"text": f"{e.source}: {e.title}", "sources": [e.evidence_id]})
    return summary, pts, ""


async def narrate(
    meter: llm.Meter,
    subject: str,
    topics: list[TopicInput],
    changes: list[str],
    first_brief: bool,
) -> tuple[str, dict[str, dict], dict]:
    """Return (headline, topic_id -> {summary, points, watch, validated}, validation stats)."""
    blocks = []
    t_alias: dict[str, TopicInput] = {}
    ev_maps: dict[str, dict[str, str]] = {}
    for i, t in enumerate(topics):
        alias = f"T{i + 1}"
        t_alias[alias] = t
        text, ev_alias = _fmt_topic(alias, t)
        ev_maps[t.topic_id] = ev_alias
        blocks.append(text)
    change_txt = "\n".join(f"- {c}" for c in changes) if changes else "- no verdict changes"
    prompt = (
        f"Subject: {subject}\n"
        + ("This is the workspace's FIRST brief.\n" if first_brief else f"Verdict changes since previous brief:\n{change_txt}\n")
        + "\n"
        + "\n\n".join(blocks)
    )
    stats = {"citations": 0, "dropped_citations": 0, "dropped_points": 0, "fallback_topics": []}
    out: dict[str, dict] = {}
    headline = ""
    try:
        res = await llm.structured(
            meter,
            model=get_settings().model_narrate,
            system=SYSTEM,
            user=prompt,
            schema=_schema(),
            name="brief_reasoning",
            effort="low",
        )
        headline = (res.get("headline") or "").strip()
        rows = {}
        names = {t.name.lower(): a for a, t in t_alias.items()}
        for r in res.get("topics", []):
            key = (r.get("topic") or "").strip()
            m = re.match(r"\s*(T\d+)(?!\d)", key)
            alias = m.group(1) if m else names.get(key.lower())
            if alias:
                rows[alias] = r
            else:
                stats.setdefault("unmatched_topics", []).append(key[:60])
    except llm.LLMError as e:
        stats["error"] = str(e)[:300]
        rows = {}

    for alias, t in t_alias.items():
        r = rows.get(alias)
        ev_alias = ev_maps[t.topic_id]
        points: list[dict] = []
        if r:
            for p in r.get("points", []):
                valid = []
                for s in p.get("sources", []):
                    s = s.strip().strip("[]").split(":")[0].strip()
                    if s in ev_alias:
                        valid.append(ev_alias[s])
                        stats["citations"] += 1
                    else:
                        stats["dropped_citations"] += 1
                text = (p.get("text") or "").strip()
                # Strip inline ids like "(E3)" or "[E1, E2]" - citations are rendered from `sources`.
                text = INLINE_IDS.sub("", text)
                text = re.sub(r"\s+([.,;:])", r"\1", " ".join(text.split()))
                if text and (valid or t.score.verdict == "insufficient"):
                    points.append({"text": text, "sources": list(dict.fromkeys(valid))})
                else:
                    stats["dropped_points"] += 1
        if points:
            out[t.topic_id] = {
                "summary": (r.get("summary") or "").strip(),
                "points": points,
                "watch": (r.get("watch") or "").strip(),
                "validated": True,
            }
        else:
            summary, pts, watch = fallback_points(t)
            stats["fallback_topics"].append(t.name)
            out[t.topic_id] = {"summary": summary, "points": pts, "watch": watch, "validated": False}
    return headline, out, stats
