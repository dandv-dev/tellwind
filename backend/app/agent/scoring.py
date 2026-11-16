"""Deterministic verdicts. No LLM decides whether a topic is rising.

For each topic we look at everything the workspace has gathered over the last
four weeks and combine two measurable things:

* **attention** - how much coverage the topic got in the last 7 days compared
  with the 21 days before (log ratio, smoothed so tiny counts don't explode);
* **tone** - what the evidence says about the topic's direction (each piece of
  evidence carries a classifier signal from -2 "clearly cooling" to +2 "clearly
  heating"), relative to the subject's average so a generally upbeat news
  cycle doesn't make every topic "rising".

Noise control:
* a single day can't dominate: daily weight is capped (winsorised) at a
  multiple of the topic's typical day;
* verdicts have hysteresis: entering "rising"/"fading" needs a clear score,
  leaving it needs the score to fall back past a lower bar;
* with too little evidence the verdict is "insufficient" instead of a guess.

Uploaded files count as evidence with a higher weight and a slower decay: a
team's own report is a considered view, not a passing headline.

Collection bias: Google News search returns fewer articles the older they get
(we measured ~60/week for the latest week against ~20/week a month back), which
would make every topic look like it is rising after a first-run backfill. So a
Google News item's volume is scaled by how much Google News returned for the
whole subject that day (``norm``): its counts become a share of that source's
coverage. Hacker News keeps a complete archive and is counted as is.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

RECENT_DAYS = 7
BASE_DAYS = 21
HORIZON = RECENT_DAYS + BASE_DAYS  # 28
SERIES_DAYS = 21

ATTN_SMOOTH = 0.5  # pseudo-count per day added to both rates
TONE_SMOOTH = 1.5  # pseudo-weight pulling tone towards 0
NEWS_HALF_LIFE = 7.0
UPLOAD_HALF_LIFE = 21.0
UPLOAD_WEIGHT = 3.0

W_ATTENTION = 0.6
W_TONE = 0.4

ENTER = 0.22
EXIT = 0.12

MIN_EVIDENCE = 4  # in the horizon
MIN_RECENT = 2  # in the last 14 days
MIN_SOURCES = 2  # distinct outlets / files


@dataclass
class Point:
    """One piece of evidence about one topic, as the scorer sees it."""

    item_id: str
    day: date
    relevance: float
    signal: int
    source: str  # outlet domain or file id
    is_upload: bool = False
    engagement: float = 0.0
    collector: str = ""

    @property
    def base_weight(self) -> float:
        if self.is_upload:
            return UPLOAD_WEIGHT * self.relevance
        boost = min(1.5, math.log10(1 + self.engagement) / 2) if self.engagement else 0.0
        return self.relevance * (1.0 + boost)


@dataclass
class TopicScore:
    verdict: str  # rising | steady | fading | insufficient
    score: float  # -1 .. 1
    strength: str  # none | weak | moderate | strong
    attention: float
    tone: float  # raw weighted mean signal, -2..2
    tone_rel: float  # relative to the subject average
    recent_rate: float
    base_rate: float
    evidence_count: int
    recent_count: int
    source_count: int
    upload_count: int
    capped_days: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)  # machine-readable rule hits
    raw_verdict: str = ""  # verdict before hysteresis


def _decay(age_days: float, half_life: float) -> float:
    return 0.5 ** (max(age_days, 0.0) / half_life)


Norm = dict[tuple[str, date], float]


def collector_norm(totals: dict[tuple[str, date], int], collectors: tuple[str, ...] = ("gnews",)) -> Norm:
    """Per (collector, day) factor: mean daily total / that day's total (floored, capped)."""
    out: Norm = {}
    for c in collectors:
        days = {d: n for (cc, d), n in totals.items() if cc == c}
        if not days:
            continue
        mean = sum(days.values()) / len(days)
        floor = max(1.0, 0.3 * mean)
        for d, n in days.items():
            out[(c, d)] = min(3.0, mean / max(n, floor))
    return out


def daily_volume(points: list[Point], as_of: date, days: int = HORIZON, norm: Norm | None = None) -> list[float]:
    vol = [0.0] * days
    start = as_of - timedelta(days=days - 1)
    for p in points:
        if p.is_upload:
            continue
        i = (p.day - start).days
        if 0 <= i < days:
            f = norm.get((p.collector, p.day), 1.0) if norm else 1.0
            vol[i] += p.base_weight * f
    return vol


def _day_caps(vol: list[float]) -> list[float]:
    """Per-day scale factors that cap any single day at ~2.5x a typical busy day."""
    nonzero = sorted(v for v in vol if v > 0)
    if not nonzero:
        return [1.0] * len(vol)
    p75 = nonzero[min(len(nonzero) - 1, int(0.75 * len(nonzero)))]
    cap = max(3.0, 2.5 * p75)
    return [min(1.0, cap / v) if v > 0 else 1.0 for v in vol]


def tone_of(points: list[Point], as_of: date) -> float:
    """Raw weighted mean signal, decayed by age (used for the subject average)."""
    num = den = 0.0
    for p in points:
        age = (as_of - p.day).days
        if age < 0 or age >= HORIZON:
            continue
        w = p.base_weight * _decay(age, UPLOAD_HALF_LIFE if p.is_upload else NEWS_HALF_LIFE)
        num += w * p.signal
        den += w
    return num / (den + TONE_SMOOTH)


def score_topic(
    points: list[Point],
    as_of: date,
    *,
    subject_tone: float = 0.0,
    previous: str | None = None,
    norm: Norm | None = None,
) -> TopicScore:
    start = as_of - timedelta(days=HORIZON - 1)
    pts = [p for p in points if start <= p.day <= as_of]

    vol = daily_volume(pts, as_of, norm=norm)
    caps = _day_caps(vol)
    capped_days = [
        (start + timedelta(days=i)).isoformat() for i, c in enumerate(caps) if c < 0.999
    ]
    capped = [v * c for v, c in zip(vol, caps)]
    base_rate = sum(capped[:BASE_DAYS]) / BASE_DAYS
    recent_rate = sum(capped[BASE_DAYS:]) / RECENT_DAYS
    attention = math.log((recent_rate + ATTN_SMOOTH) / (base_rate + ATTN_SMOOTH))
    attention = max(-2.0, min(2.0, attention))

    num = den = 0.0
    for p in pts:
        age = (as_of - p.day).days
        if p.is_upload:
            w = p.base_weight * _decay(age, UPLOAD_HALF_LIFE)
        else:
            w = p.base_weight * caps[(p.day - start).days] * _decay(age, NEWS_HALF_LIFE)
        num += w * p.signal
        den += w
    tone = num / (den + TONE_SMOOTH)
    tone_rel = tone - subject_tone

    score = W_ATTENTION * math.tanh(attention / 0.8) + W_TONE * max(-1.0, min(1.0, tone_rel))
    score = max(-1.0, min(1.0, score))

    recent14 = as_of - timedelta(days=13)
    evidence_count = len(pts)
    recent_count = sum(1 for p in pts if p.day >= recent14)
    sources = {p.source for p in pts}
    upload_count = sum(1 for p in pts if p.is_upload)

    reasons: list[str] = []
    if evidence_count < MIN_EVIDENCE:
        reasons.append("too_few_items")
    if recent_count < MIN_RECENT:
        reasons.append("nothing_recent")
    if len(sources) < MIN_SOURCES:
        reasons.append("single_source")

    if score >= ENTER:
        raw = "rising"
    elif score <= -ENTER:
        raw = "fading"
    else:
        raw = "steady"

    verdict = raw
    if reasons:
        verdict = "insufficient"
    elif raw == "steady" and previous == "rising" and score >= EXIT:
        verdict = "rising"
        reasons.append("held_by_hysteresis")
    elif raw == "steady" and previous == "fading" and score <= -EXIT:
        verdict = "fading"
        reasons.append("held_by_hysteresis")
    elif raw in ("rising", "fading") and previous in ("rising", "fading") and raw != previous:
        # A direct flip rising <-> fading needs the score well past the bar.
        if abs(score) < ENTER + 0.1:
            verdict = "steady"
            reasons.append("flip_damped")

    mag = abs(score)
    if verdict in ("insufficient", "steady"):
        strength = "none" if verdict == "insufficient" else ("weak" if mag < 0.12 else "moderate")
    else:
        strength = "weak" if mag < 0.35 else "moderate" if mag < 0.6 else "strong"

    return TopicScore(
        verdict=verdict,
        score=round(score, 4),
        strength=strength,
        attention=round(attention, 4),
        tone=round(tone, 4),
        tone_rel=round(tone_rel, 4),
        recent_rate=round(recent_rate, 3),
        base_rate=round(base_rate, 3),
        evidence_count=evidence_count,
        recent_count=recent_count,
        source_count=len(sources),
        upload_count=upload_count,
        capped_days=capped_days,
        reasons=reasons,
        raw_verdict=raw,
    )


def score_series(
    points: list[Point], as_of: date, subject_tones: dict[date, float], days: int = SERIES_DAYS, norm: Norm | None = None
) -> list[dict]:
    """Score recomputed for each of the last ``days`` days: the trend sparkline."""
    out = []
    for i in range(days - 1, -1, -1):
        d = as_of - timedelta(days=i)
        s = score_topic(points, d, subject_tone=subject_tones.get(d, 0.0), norm=norm)
        out.append({"date": d.isoformat(), "score": s.score})
    return out


def subject_tone(all_points: dict[str, list[Point]], as_of: date) -> float:
    """Average tone across topics that have enough evidence to have a tone."""
    tones = [tone_of(pts, as_of) for pts in all_points.values() if len(pts) >= MIN_EVIDENCE]
    return sum(tones) / len(tones) if tones else 0.0


def score_all(
    all_points: dict[str, list[Point]],
    as_of: date,
    previous: dict[str, str] | None = None,
    norm: Norm | None = None,
) -> tuple[dict[str, TopicScore], dict[str, list[dict]], dict[str, list[float]], float]:
    """Score every topic; returns (scores, score series, daily volumes, subject tone)."""
    previous = previous or {}
    tones = {
        as_of - timedelta(days=i): subject_tone(all_points, as_of - timedelta(days=i))
        for i in range(SERIES_DAYS)
    }
    scores: dict[str, TopicScore] = {}
    series: dict[str, list[dict]] = {}
    volumes: dict[str, list[float]] = {}
    for tid, pts in all_points.items():
        scores[tid] = score_topic(pts, as_of, subject_tone=tones[as_of], previous=previous.get(tid), norm=norm)
        series[tid] = score_series(pts, as_of, tones, norm=norm)
        volumes[tid] = [round(v, 3) for v in daily_volume(pts, as_of, norm=norm)]
    return scores, series, volumes, tones[as_of]


def describe(s: TopicScore) -> dict:
    """Plain numbers the narrator and the UI can show."""
    change = None
    if s.base_rate > 0:
        change = round((s.recent_rate - s.base_rate) / s.base_rate * 100)
    return {
        "coverage_change_pct": change,
        "recent_per_day": s.recent_rate,
        "baseline_per_day": s.base_rate,
        "tone": s.tone,
        "tone_vs_subject": s.tone_rel,
    }


def group_by_topic(rows: list[tuple[str, Point]]) -> dict[str, list[Point]]:
    out: dict[str, list[Point]] = defaultdict(list)
    for tid, p in rows:
        out[tid].append(p)
    return out
