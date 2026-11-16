"""The scorer is the part that decides verdicts, so it gets the most tests."""

from datetime import date, timedelta

from app.agent import scoring
from app.agent.scoring import Point, score_topic

AS_OF = date(2026, 11, 16)
OUTLETS = ["a.com", "b.com", "c.com", "d.com", "e.com"]


def steady_points(per_day: int = 2, days: int = 28, signal: int = 0, start: int = 0) -> list[Point]:
    """A topic with the same coverage every day for four weeks."""
    pts = []
    n = 0
    for i in range(days):
        d = AS_OF - timedelta(days=i)
        for _ in range(per_day):
            pts.append(Point(f"i{start + n}", d, 0.8, signal, OUTLETS[n % len(OUTLETS)]))
            n += 1
    return pts


def test_flat_coverage_is_steady():
    s = score_topic(steady_points(), AS_OF)
    assert s.verdict == "steady"
    assert abs(s.score) < scoring.ENTER


def test_more_coverage_and_positive_signal_is_rising():
    base = steady_points(per_day=1)
    recent = [
        Point(f"r{i}", AS_OF - timedelta(days=i % 7), 0.9, 2, OUTLETS[i % 5]) for i in range(30)
    ]
    s = score_topic(base + recent, AS_OF)
    assert s.verdict == "rising"
    assert s.strength in ("moderate", "strong")


def test_one_noisy_day_does_not_flip_the_verdict():
    """A single burst of 40 articles on one day (a launch, a viral thread) is capped."""
    base = steady_points(per_day=2)
    burst = [Point(f"b{i}", AS_OF - timedelta(days=2), 0.9, 1, OUTLETS[i % 5]) for i in range(40)]
    s = score_topic(base + burst, AS_OF, previous="steady")
    assert (AS_OF - timedelta(days=2)).isoformat() in s.capped_days
    assert s.verdict == "steady", s

    # Without the cap the same day would have been enough for a call.
    uncapped = scoring._day_caps
    try:
        scoring._day_caps = lambda vol: [1.0] * len(vol)
        assert score_topic(base + burst, AS_OF, previous="steady").verdict == "rising"
    finally:
        scoring._day_caps = uncapped


def test_hysteresis_holds_a_call_until_the_score_clearly_drops():
    base = steady_points(per_day=3)
    mild = [Point(f"m{i}", AS_OF - timedelta(days=i % 7), 0.8, 1, OUTLETS[i % 5]) for i in range(5)]
    s_new = score_topic(base + mild, AS_OF, previous="steady")
    s_held = score_topic(base + mild, AS_OF, previous="rising")
    assert scoring.EXIT <= s_new.score < scoring.ENTER, s_new.score
    assert s_new.verdict == "steady"
    assert s_held.verdict == "rising"
    assert "held_by_hysteresis" in s_held.reasons


def test_direct_flip_from_rising_to_fading_is_damped():
    base = steady_points(per_day=3, signal=0)
    # Coverage dries up in the last week: just past the fading bar.
    pts = [p for p in base if (AS_OF - p.day).days >= 7]
    pts += [Point("x1", AS_OF - timedelta(days=1), 0.8, 0, "a.com"), Point("x2", AS_OF, 0.8, 0, "b.com")]
    s = score_topic(pts, AS_OF, previous="rising")
    if s.raw_verdict == "fading" and abs(s.score) < scoring.ENTER + 0.1:
        assert s.verdict == "steady"
        assert "flip_damped" in s.reasons
    else:  # strong reversal: allowed through
        assert s.verdict == "fading"


def test_too_little_evidence_is_not_enough_to_go_on():
    pts = [Point("a", AS_OF, 1.0, 2, "a.com"), Point("b", AS_OF - timedelta(days=1), 1.0, 2, "b.com")]
    s = score_topic(pts, AS_OF)
    assert s.verdict == "insufficient"
    assert "too_few_items" in s.reasons
    assert s.strength == "none"


def test_a_single_outlet_is_not_enough_to_go_on():
    pts = [Point(f"p{i}", AS_OF - timedelta(days=i), 1.0, 2, "only.com") for i in range(10)]
    s = score_topic(pts, AS_OF)
    assert s.verdict == "insufficient"
    assert "single_source" in s.reasons


def test_nothing_recent_is_not_enough_to_go_on():
    pts = [Point(f"p{i}", AS_OF - timedelta(days=20 + i % 5), 1.0, 1, OUTLETS[i % 5]) for i in range(10)]
    s = score_topic(pts, AS_OF)
    assert s.verdict == "insufficient"
    assert "nothing_recent" in s.reasons


def test_team_file_saying_cooling_lowers_the_score():
    news = steady_points(per_day=2, signal=1)
    before = score_topic(news, AS_OF)
    note = Point("file-chunk", AS_OF - timedelta(days=3), 0.9, -2, "file:analyst-note", is_upload=True)
    after = score_topic(news + [note, Point("file-chunk-2", AS_OF - timedelta(days=3), 0.9, -2, "file:analyst-note", is_upload=True)], AS_OF)
    assert after.score < before.score - 0.05
    assert after.upload_count == 2
    # A team file outweighs a single news item with the same signal.
    one_news = score_topic(news + [Point("n", AS_OF - timedelta(days=3), 0.9, -2, "z.com")], AS_OF)
    assert after.score < one_news.score


def test_upload_is_not_counted_as_coverage_volume():
    news = steady_points()
    up = [Point(f"u{i}", AS_OF, 1.0, 0, "file:x", is_upload=True) for i in range(20)]
    assert scoring.daily_volume(news + up, AS_OF) == scoring.daily_volume(news, AS_OF)


def test_google_news_normalisation_removes_the_age_bias():
    """Older Google News articles drop out of search: raw counts would look like growth."""
    pts = []
    totals = {}
    n = 0
    for i in range(28):
        d = AS_OF - timedelta(days=i)
        k = 3 if i < 7 else 1  # three times as many recent results for EVERY topic
        totals[("gnews", d)] = 30 * k
        for _ in range(k):
            pts.append(Point(f"g{n}", d, 0.8, 0, OUTLETS[n % 5], collector="gnews"))
            n += 1
    raw = score_topic(pts, AS_OF)
    normed = score_topic(pts, AS_OF, norm=scoring.collector_norm(totals))
    assert raw.verdict == "rising"
    assert normed.verdict == "steady"


def test_subject_tone_is_relative():
    """When every topic gets upbeat coverage, upbeat coverage alone isn't a rising call."""
    upbeat = {f"t{k}": steady_points(per_day=2, signal=2, start=k * 1000) for k in range(4)}
    scores, *_ = scoring.score_all(upbeat, AS_OF)
    assert all(s.verdict == "steady" for s in scores.values())
