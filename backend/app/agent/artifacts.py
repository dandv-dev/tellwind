"""What a run leaves behind: the brief payload and its files.

* ``brief-<date>.html``: the same React components as the Brief tab, compiled
  into one self-contained HTML file (``frontend`` builds
  ``brief-template.html``; we drop the brief JSON into it).
* ``trace-<date>.md``: how the agent got there.
* ``news-<date>.csv``: the news this run collected.
"""

from __future__ import annotations

import csv
import html
import io
import json
from datetime import date

from ..config import get_settings
from ..models import File, utcnow
from . import scoring

PLACEHOLDER = "<!--BRIEF_DATA-->"
VERDICT_ORDER = {"rising": 0, "steady": 1, "fading": 2, "insufficient": 3}


def default_headline(changes, scores, topics, first: bool) -> str:
    tally: dict[str, list[str]] = {}
    for t in topics:
        tally.setdefault(scores[t.id].verdict, []).append(t.name)
    if first:
        rising = tally.get("rising", [])
        return (
            f"First brief: {len(rising)} of {len(topics)} topics rising"
            + (f", led by {rising[0]}." if rising else ".")
        )
    if not changes:
        return "No verdict changed since the previous brief."
    return "Changed since last brief: " + "; ".join(
        f"{c['name']} {c['from']} → {c['to']}" for c in changes
    ) + "."


def _evidence_out(r: dict) -> dict:
    return {
        "id": r["evidence_id"],
        "item_id": r["item_id"],
        "title": r["title"],
        "url": r["url"],
        "hn_url": r.get("hn_url"),
        "source": r["source"],
        "source_type": r["source_type"],
        "file_id": r["file_id"],
        "file_name": r["file_name"],
        "date": r["date"].isoformat(),
        "signal": r["signal"],
        "relevance": round(r["relevance"], 2),
        "quote": r["quote"],
        "note": r["note"],
        "also": r.get("also", 0),
    }


def brief_data(
    *,
    ws,
    as_of: date,
    run_id: str,
    topics,
    scores,
    series,
    volumes,
    texts,
    previous,
    prev_date,
    headline,
    changes,
    ev_rows,
    topic_sources,
    companies,
) -> dict:
    evidence: dict[str, dict] = {}
    out_topics = []
    by_id = {}
    for rows in ev_rows.values():
        for r in rows:
            by_id[r["evidence_id"]] = r
    for t in topics:
        sc = scores[t.id]
        tx = texts.get(t.id, {})
        cited = [e for p in tx.get("points", []) for e in p["sources"]]
        srcs = list(dict.fromkeys(cited + topic_sources.get(t.id, [])))
        for eid in srcs:
            if eid in by_id:
                evidence[eid] = _evidence_out(by_id[eid])
        metrics = scoring.describe(sc)
        metrics.update(
            evidence_count=sc.evidence_count,
            recent_count=sc.recent_count,
            source_count=sc.source_count,
            upload_count=sc.upload_count,
            attention=sc.attention,
        )
        out_topics.append(
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "verdict": sc.verdict,
                "raw_verdict": sc.raw_verdict,
                "previous_verdict": previous.get(t.id),
                "strength": sc.strength,
                "score": sc.score,
                "metrics": metrics,
                "series": series.get(t.id, []),
                "volume": volumes.get(t.id, []),
                "summary": tx.get("summary", ""),
                "points": tx.get("points", []),
                "watch": tx.get("watch", ""),
                "validated": tx.get("validated", False),
                "sources": [e for e in srcs if e in evidence],
                "companies": companies.get(t.id, []),
                "reasons": sc.reasons,
                "capped_days": sc.capped_days,
            }
        )
    tally = {k: 0 for k in VERDICT_ORDER}
    for t in out_topics:
        tally[t["verdict"]] += 1
    return {
        "version": 1,
        "workspace": {"id": ws.id, "name": ws.name, "subject": ws.subject},
        "date": as_of.isoformat(),
        "previous_date": prev_date.isoformat() if prev_date else None,
        "generated_at": utcnow().isoformat(),
        "run_id": run_id,
        "headline": headline,
        "changes": changes,
        "tally": tally,
        "topics": out_topics,
        "evidence": evidence,
        "method": {
            "recent_days": scoring.RECENT_DAYS,
            "baseline_days": scoring.BASE_DAYS,
            "enter": scoring.ENTER,
            "exit": scoring.EXIT,
        },
    }


def brief_html(data: dict) -> str:
    tpl_path = get_settings().static_dir / "brief-template.html"
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    tag = f'<script id="brief-data" type="application/json">{payload}</script>'
    if tpl_path.exists():
        tpl = tpl_path.read_text(encoding="utf-8")
        if PLACEHOLDER in tpl:
            return tpl.replace(PLACEHOLDER, tag)
    return _plain_html(data)


def _plain_html(d: dict) -> str:
    """Fallback when the frontend template hasn't been built (local dev)."""
    e = html.escape
    rows = []
    for t in d["topics"]:
        pts = "".join(f"<li>{e(p['text'])}</li>" for p in t["points"])
        rows.append(
            f"<section><h2>{e(t['name'])} - {e(t['verdict'])} ({e(t['strength'])})</h2>"
            f"<p>{e(t['summary'])}</p><ul>{pts}</ul></section>"
        )
    return (
        f"<!doctype html><meta charset=utf-8><title>Tellwind brief {e(d['date'])}</title>"
        f"<h1>{e(d['workspace']['subject'])} - {e(d['date'])}</h1><p>{e(d['headline'])}</p>"
        + "".join(rows)
    )


def trace_md(*, data, run, steps, meter, scores, topics, inputs, new_items) -> str:
    L: list[str] = []
    w = L.append
    w(f"# How the {data['date']} brief was made")
    w("")
    w(f"Workspace: **{data['workspace']['name']}**, subject: **{data['workspace']['subject']}**  ")
    w(f"Run `{run.id}` ({run.trigger}), as of {run.as_of.isoformat()}, cost **${meter.cost_usd:.4f}**")
    w("")
    w("## 1. What the agent looked at")
    st = {s["key"]: s for s in steps}
    c = st["collect"]["detail"]
    win = c.get("window", {})
    w(
        f"News window {win.get('from', '?')} → {win.get('to', '?')}"
        + (" (first run: backfilled three weeks)" if win.get("backfill") else "")
        + f". {c.get('new_items', 0)} new items: "
        + ", ".join(f"{k} {v}" for k, v in c.get("by_collector", {}).items())
    )
    w("")
    w("| Source | Query | Found | Error |")
    w("|---|---|---|---|")
    for call in c.get("calls", []):
        q = call.get("query", "").replace("|", "\\|")
        w(f"| {call['collector']} | `{q}` | {call.get('found', '')} | {call.get('error', '')} |")
    w("")
    em = st["embed"]["detail"]
    cl = st["classify"]["detail"]
    w("## 2. What it found")
    w(
        f"- {em.get('embedded', 0)} items embedded; {em.get('duplicates', 0)} were the same story from "
        f"another outlet and were merged; {em.get('too_old', 0)} were older than four weeks and skipped."
    )
    w(
        f"- {cl.get('items', 0)} items read ({cl.get('uploads', 0)} chunks of team files). "
        f"{cl.get('prefilter_passed', 0)} resembled a topic closely enough to be classified; "
        f"{cl.get('prefilter_skipped', 0)} did not."
    )
    w(
        f"- {cl.get('evidence', 0)} pieces of evidence recorded. {cl.get('unverified_quotes_dropped', 0)} "
        f"quotes could not be found word for word in their source and were removed."
    )
    if cl.get("failed_batches"):
        w(f"- {cl['failed_batches']} classification batches failed and will be retried next run.")
    w(f"- {cl.get('company_mentions', 0)} company mentions extracted.")
    w("")
    w("## 3. Why each topic came down where it did")
    w("")
    w(
        f"Score = {scoring.W_ATTENTION} × tanh(attention / 0.8) + {scoring.W_TONE} × tone vs subject, "
        f"in [-1, 1]. Attention compares weighted coverage in the last {scoring.RECENT_DAYS} days with "
        f"the {scoring.BASE_DAYS} days before. Rising ≥ {scoring.ENTER}, fading ≤ -{scoring.ENTER}; an "
        f"existing rising/fading verdict holds until the score falls back past ±{scoring.EXIT}. "
        f"Fewer than {scoring.MIN_EVIDENCE} items, nothing in 14 days or a single source means "
        f"'insufficient'."
    )
    w("")
    w("| Topic | Verdict | Score | Attention | Tone (vs subject) | Items / sources / files | Notes |")
    w("|---|---|---|---|---|---|---|")
    for t in topics:
        s = scores[t.id]
        w(
            f"| {t.name} | **{s.verdict}** ({s.strength}) | {s.score:+.2f} | {s.attention:+.2f} "
            f"| {s.tone:+.2f} ({s.tone_rel:+.2f}) | {s.evidence_count} / {s.source_count} / {s.upload_count} "
            f"| {', '.join(s.reasons) or '-'} |"
        )
    w("")
    tmap = {t["id"]: t for t in data["topics"]}
    for inp in inputs:
        t = tmap[inp.topic_id]
        w(f"### {t['name']}: {t['verdict']}")
        prev = t.get("previous_verdict")
        if prev:
            w(f"Previous brief: {prev}.  ")
        if t.get("capped_days"):
            w(f"Busy days capped: {', '.join(t['capped_days'])}.  ")
        w("")
        for p in t["points"]:
            refs = ", ".join(f"[{i + 1}]" for i, eid in enumerate(inp.evidence) if eid.evidence_id in p["sources"])
            w(f"- {p['text']} {refs}")
        if not t["validated"]:
            w("- *(model reasoning failed validation; template text used)*")
        w("")
        w("Evidence shown to the narrator:")
        w("")
        for i, ev in enumerate(inp.evidence):
            kind = "team file" if ev.is_upload else ev.source
            q = f' "{ev.quote}"' if ev.quote else ""
            w(f"{i + 1}. [{ev.date}, {kind}, signal {ev.signal:+d}] {ev.title}{q}")
        w("")
    ex = st["explain"]["detail"]
    w("## 4. Checks on the reasoning")
    w(
        f"- {ex.get('citations', 0)} citations matched evidence in the workspace; "
        f"{ex.get('dropped_citations', 0)} did not and were removed; "
        f"{ex.get('dropped_points', 0)} unsupported points dropped."
    )
    if ex.get("fallback_topics"):
        w(f"- Template text used for: {', '.join(ex['fallback_topics'])}")
    w("")
    w("## 5. Cost")
    w("")
    w("| Model | Calls | Input tokens | Cached | Output tokens |")
    w("|---|---|---|---|---|")
    for m, u in meter.usage.items():
        w(f"| {m} | {u['calls']} | {u['input']} | {u['cached']} | {u['output']} |")
    w("")
    w(f"Total: **${meter.cost_usd:.4f}**")
    return "\n".join(L) + "\n"


def news_csv(items) -> str:
    buf = io.StringIO()
    wr = csv.writer(buf)
    wr.writerow(["published_at", "collector", "source", "title", "url"])
    for it in sorted(items, key=lambda i: i.published_at):
        wr.writerow([it.published_at.isoformat(), it.collector, it.source, it.title, it.url])
    return buf.getvalue()


def make_file(kind: str, filename: str, content_type: str, body: str) -> File:
    data = body.encode("utf-8")
    return File(kind=kind, filename=filename, content_type=content_type, size=len(data), data=data)


def run_files(*, data, run, steps, meter, scores, topics, inputs, new_items, ev_rows) -> list[File]:
    d = data["date"]
    files = [
        make_file("brief", f"brief-{d}.html", "text/html; charset=utf-8", brief_html(data)),
        make_file(
            "trace",
            f"trace-{d}.md",
            "text/markdown; charset=utf-8",
            trace_md(
                data=data,
                run=run,
                steps=steps,
                meter=meter,
                scores=scores,
                topics=topics,
                inputs=inputs,
                new_items=new_items,
            ),
        ),
    ]
    if new_items:
        files.append(make_file("news", f"news-{d}.csv", "text/csv; charset=utf-8", news_csv(new_items)))
    return files
