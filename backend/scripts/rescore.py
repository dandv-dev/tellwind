"""Re-score an existing database offline (no API calls): verdicts per day.

    python scripts/rescore.py data/demo_build.db [--no-norm]
"""

import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.agent import scoring  # noqa: E402


def main(db: str, use_norm: bool) -> None:
    c = sqlite3.connect(db)
    topics = c.execute("select id, name from topics where archived=0 order by position").fetchall()
    rows = c.execute(
        """select e.topic_id, i.id, i.published_at, e.relevance, e.signal, i.source, i.source_type,
                  i.file_id, i.engagement, i.collector
           from evidence e join items i on i.id = e.item_id where i.duplicate_of is null"""
    ).fetchall()
    pts = defaultdict(list)
    for tid, iid, pub, rel, sig, src, st, fid, eng, col in rows:
        d = datetime.fromisoformat(pub).date()
        pts[tid].append(
            scoring.Point(iid, d, rel, sig, f"file:{fid}" if st == "upload" else src, st == "upload", eng or 0, col)
        )
    totals = defaultdict(int)
    for col, pub in c.execute("select collector, published_at from items where source_type='news' and duplicate_of is null"):
        totals[(col, datetime.fromisoformat(pub).date())] += 1
    norm = scoring.collector_norm(totals) if use_norm else None
    prev: dict[str, str] = {}
    d = date(2026, 11, 3)
    print(" " * 12 + " ".join(f"{n[:10]:>10}" for _, n in topics))
    while d <= date(2026, 11, 15):
        all_pts = {tid: pts.get(tid, []) for tid, _ in topics}
        scores, *_ = scoring.score_all(all_pts, d, prev, norm)
        prev = {k: v.verdict for k, v in scores.items()}
        cells = [f"{scores[t].verdict[:4]}{scores[t].score:+.2f}" for t, _ in topics]
        tally = {v: sum(1 for s in scores.values() if s.verdict == v) for v in ("rising", "steady", "fading")}
        print(f"{d} " + " ".join(f"{x:>10}" for x in cells), tally)
        d += timedelta(days=1)


if __name__ == "__main__":
    main(sys.argv[1], "--no-norm" not in sys.argv)
