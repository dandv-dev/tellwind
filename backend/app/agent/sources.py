"""Free public news collectors: Hacker News (Algolia), GDELT DOC 2.0, Google News RSS.

Each collector takes search phrases and a time window and returns ``RawItem``s.
They never raise on network trouble: failures come back as error strings so a
run can carry on with the sources that answered and record what failed.
"""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import html
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus, urlsplit, urlunsplit, parse_qsl, urlencode

import feedparser
import httpx

# GDELT has dated archives with real links, but in testing it answered 429 or
# timed out on most calls even at one request per 6 s, which made runs slow and
# coverage uneven between days (bad for a volume-based trend). Off by default.
USE_GDELT = False

UA = "TellwindBot/0.1 (+https://github.com/; news trend research)"
TIMEOUT = httpx.Timeout(25.0, connect=10.0)


@dataclass
class RawItem:
    title: str
    url: str
    source: str  # human label: outlet domain or "Hacker News"
    collector: str  # hn | gdelt | gnews
    published_at: datetime
    text: str = ""
    engagement: float = 0.0
    meta: dict = field(default_factory=dict)
    query: str = ""


@dataclass
class CollectResult:
    items: list[RawItem]
    calls: list[dict]  # what was asked, for the trace


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean_text(s: str) -> str:
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", s or ""))).strip()


def domain_of(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def normalize_url(url: str) -> str:
    p = urlsplit(url.strip())
    q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(("utm_", "ref", "fbclid", "gclid"))]
    host = p.netloc.lower().removeprefix("www.")
    return urlunsplit(("https", host, p.path.rstrip("/"), urlencode(q), ""))


def normalize_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"^(show hn|ask hn|launch hn|tell hn)\s*:\s*", "", t)
    t = re.sub(r"[^a-z0-9а-яёіїєґ ]+", " ", t)
    return _WS.sub(" ", t).strip()


def content_hash(item: RawItem) -> str:
    return hashlib.sha1(("t:" + normalize_title(item.title)).encode()).hexdigest()


async def hacker_news(
    http: httpx.AsyncClient, phrases: list[str], start: datetime, end: datetime, per_query: int = 50
) -> CollectResult:
    items: list[RawItem] = []
    calls: list[dict] = []
    s, e = int(start.timestamp()), int(end.timestamp())
    for phrase in phrases:
        params = {
            "query": phrase,
            "tags": "story",
            # The vote filter goes into the query so the hit limit applies after it.
            "numericFilters": f"created_at_i>={s},created_at_i<{e},points>=3",
            "hitsPerPage": per_query,
        }
        call = {"collector": "hn", "query": phrase}
        try:
            r = await http.get("https://hn.algolia.com/api/v1/search", params=params)
            r.raise_for_status()
            hits = r.json().get("hits", [])
        except (httpx.HTTPError, ValueError) as ex:
            call["error"] = str(ex)[:200]
            calls.append(call)
            continue
        kept = 0
        for h in hits:
            points = h.get("points") or 0
            comments = h.get("num_comments") or 0
            hn_url = f"https://news.ycombinator.com/item?id={h['objectID']}"
            url = h.get("url") or hn_url
            items.append(
                RawItem(
                    title=clean_text(h.get("title") or ""),
                    url=url,
                    source=domain_of(url) if h.get("url") else "news.ycombinator.com",
                    collector="hn",
                    published_at=datetime.fromtimestamp(h["created_at_i"], timezone.utc),
                    text=clean_text(h.get("story_text") or "")[:2000],
                    engagement=float(points) + 0.5 * comments,
                    meta={"hn_url": hn_url, "points": points, "comments": comments},
                    query=phrase,
                )
            )
            kept += 1
        call["found"] = kept
        calls.append(call)
    return CollectResult(items, calls)


_gdelt_lock = asyncio.Lock()
_gdelt_last = 0.0
GDELT_SPACING = 6.0  # GDELT asks for at most one request every 5 seconds


def _gdelt_query(phrases: list[str]) -> str:
    terms = []
    for p in phrases:
        p = re.sub(r'[()"]', " ", p).strip()
        if len(p) < 4:
            continue
        terms.append(f'"{p}"' if " " in p else p)
    if not terms:
        return ""
    q = terms[0] if len(terms) == 1 else "(" + " OR ".join(terms) + ")"
    return q + " sourcelang:english"


async def gdelt(
    http: httpx.AsyncClient, phrases: list[str], start: datetime, end: datetime, max_records: int = 75
) -> CollectResult:
    global _gdelt_last
    q = _gdelt_query(phrases)
    call: dict = {"collector": "gdelt", "query": q}
    if not q:
        return CollectResult([], [])
    params = {
        "query": q,
        "mode": "artlist",
        "format": "json",
        "maxrecords": max_records,
        "sort": "hybridrel",
        "startdatetime": start.strftime("%Y%m%d%H%M%S"),
        "enddatetime": end.strftime("%Y%m%d%H%M%S"),
    }
    data = None
    for attempt in range(2):
        async with _gdelt_lock:
            wait = GDELT_SPACING - (time.monotonic() - _gdelt_last)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                r = await http.get(
                    "https://api.gdeltproject.org/api/v2/doc/doc", params=params, timeout=45.0
                )
                _gdelt_last = time.monotonic()
                if r.status_code == 429:
                    raise httpx.HTTPStatusError("rate limited", request=r.request, response=r)
                r.raise_for_status()
                data = r.json() if r.text.strip().startswith("{") else {"articles": []}
                break
            except (httpx.HTTPError, ValueError) as ex:
                _gdelt_last = time.monotonic()
                call["error"] = (str(ex) or type(ex).__name__)[:200]
                await asyncio.sleep(5 + attempt * 5)
    if data is None:
        return CollectResult([], [call])
    call.pop("error", None)
    items = []
    for a in data.get("articles", []):
        if a.get("language", "English") != "English":
            continue
        try:
            when = datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        items.append(
            RawItem(
                title=clean_text(a.get("title") or ""),
                url=a["url"],
                source=a.get("domain") or domain_of(a["url"]),
                collector="gdelt",
                published_at=when,
                meta={"country": a.get("sourcecountry", "")},
                query=q,
            )
        )
    call["found"] = len(items)
    return CollectResult(items, [call])


async def google_news(
    http: httpx.AsyncClient, phrases: list[str], start: datetime, end: datetime
) -> CollectResult:
    terms = [f'"{p}"' if " " in p else p for p in phrases if p.strip()]
    if not terms:
        return CollectResult([], [])
    after = (start - timedelta(days=1)).strftime("%Y-%m-%d")
    before = (end + timedelta(days=1)).strftime("%Y-%m-%d")
    q = f"({' OR '.join(terms)}) after:{after} before:{before}"
    call: dict = {"collector": "gnews", "query": q}
    url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=en-US&gl=US&ceid=US:en"
    try:
        r = await http.get(url)
        r.raise_for_status()
    except httpx.HTTPError as ex:
        call["error"] = str(ex)[:200]
        return CollectResult([], [call])
    feed = feedparser.parse(r.content)
    items = []
    for e in feed.entries:
        if not getattr(e, "published_parsed", None):
            continue
        when = datetime.fromtimestamp(calendar.timegm(e.published_parsed), timezone.utc)
        if not (start <= when < end):
            continue
        outlet = getattr(getattr(e, "source", None), "title", "") or ""
        outlet_href = getattr(getattr(e, "source", None), "href", "") or ""
        title = clean_text(e.title)
        if outlet and title.endswith(" - " + outlet):
            title = title[: -len(outlet) - 3]
        items.append(
            RawItem(
                title=title,
                url=e.link,  # news.google.com link that forwards to the article
                source=domain_of(outlet_href) if outlet_href else (outlet or "news.google.com"),
                collector="gnews",
                published_at=when,
                text="",
                meta={"outlet": outlet},
                query=q,
            )
        )
    call["found"] = len(items)
    return CollectResult(items, [call])


def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": UA}, follow_redirects=True)


def slices(start: datetime, end: datetime, days: int = 7) -> list[tuple[datetime, datetime]]:
    out = []
    cur = start
    while cur < end:
        nxt = min(end, cur + timedelta(days=days))
        out.append((cur, nxt))
        cur = nxt
    return out


async def collect(
    topic_phrases: dict[str, list[str]], start: datetime, end: datetime, *, backfill: bool = False
) -> CollectResult:
    """Run every collector for every topic's phrases over [start, end).

    Long windows are cut into weekly slices with the same per-query limits a
    daily run uses, so a first-run backfill samples coverage the same way
    later runs do. Otherwise the baseline would look thinner than the recent
    week and every topic would appear to be rising.
    """
    sem = asyncio.Semaphore(6)

    async def limited(coro):
        async with sem:
            return await coro

    async with http_client() as http:
        tasks = []
        for a, b in slices(start, end):
            for phrases in topic_phrases.values():
                tasks.append(limited(hacker_news(http, phrases, a, b, 100)))
                tasks.append(limited(google_news(http, phrases, a, b)))
                if USE_GDELT:
                    tasks.append(gdelt(http, phrases, a, b, 75))
        results = await asyncio.gather(*tasks)
    items: list[RawItem] = []
    calls: list[dict] = []
    for r in results:
        items.extend(i for i in r.items if i.title)
        calls.extend(r.calls)
    return CollectResult(items, calls)
