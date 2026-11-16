# Tellwind

A daily read on what's moving in your field. A team picks a subject and up to ten topics; every
morning an agent reads free public news plus the team's own files and says, for each topic,
whether it is **rising**, **steady** or **fading**, or that there is **not enough to go on**.
Every call links to the sources behind it.

**Live:** `https://<your-service>.onrender.com` (free plan: the first request after a quiet spell
takes up to a minute while the instance wakes up)

| Demo login | Role | Can |
|---|---|---|
| `owner@demo.tellwind.app` | Owner | everything, including people and settings |
| `member@demo.tellwind.app` | Member | upload files, start runs, change the schedule |
| `viewer@demo.tellwind.app` | Viewer | read briefs, download files |

Password for all three: `tellwind-demo`. The login page has one-click buttons for them.

The demo workspace **DevTools Radar** ("AI developer tools", 10 topics) has 14 daily briefs
(3–16 Nov 2026) built from real news, three team documents uploaded along the way, and a pending
invitation. Its daily schedule is on, so on the live site it keeps going.

---

## Run it locally

Needs Python 3.12, Node 22. An OpenAI key is only needed to run the agent and ask questions; the
demo workspace loads without one.

```bash
cp .env.example .env            # add OPENAI_API_KEY
cd frontend && npm ci && npm run build && cd ..
cd backend
python -m venv .venv && .venv/Scripts/activate   # or: source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --port 8000                 # http://localhost:8000
```

Without `DATABASE_URL` it uses SQLite in `backend/data/`. The demo workspace is imported on first
start. For frontend work, `npm run dev` in `frontend/` proxies `/api` to port 8000.

Or the production setup (app image + Postgres):

```bash
docker compose up --build
```

Tests: `cd backend && python -m pytest`.

Invite links aren't emailed: they are printed to the server log (`INVITE … http://…/invite/<token>`).

### Deploy (Render)

`render.yaml` is a Blueprint: one Docker web service plus a free Postgres. New → Blueprint → this
repo, then paste `OPENAI_API_KEY` when asked. `CRON_SECRET` is generated.

The free instance sleeps after 15 minutes, so `.github/workflows/cron.yml` pings
`/api/cron/tick` hourly to wake it and start runs that are due. To enable it, set the repo
**secret** `CRON_SECRET` (copy it from Render) and the repo **variable** `TELLWIND_URL`.

---

## How the agent decides

The verdict is **not** an LLM's opinion. Models do the reading. A small deterministic scorer
decides, and a model then explains the decision, citing only evidence it was handed.

```
prepare → collect → embed → classify → score → explain → publish
```

1. **Collect.** Hacker News (Algolia API, stories with ≥3 points) and Google News RSS. Both are
   free, need no key, and filter by date. Each topic searches by 3 short phrases. If the team
   didn't give any, the cheap model writes them on the topic's first run. A first run backfills 28 days so the first brief already
   has a baseline. Later runs re-read the last 2 days, because HN points arrive late.
2. **Embed & dedupe.** `text-embedding-3-small`. The same story from several outlets
   (cosine ≥ 0.93 within 3 days) is merged into one item and counts once.
3. **Prefilter.** Similarity to each topic's description decides which (item, topic) pairs are
   worth a model call at all. This removes most of the noise for free.
4. **Classify** (`gpt-5.6-luna`, batches of 12, strict JSON schema). For each candidate topic:
   relevance, a **signal** from −2 (clearly cooling) to +2 (clearly heating up), a quote, and the
   companies shown doing something. The quote must appear **verbatim** in the source, or it is
   dropped. Each item is classified once and stored as `evidence`, so a daily run only pays for
   new items.
5. **Score** (`app/agent/scoring.py`, pure Python, no LLM):
   - *attention*: log ratio of the last 7 days' weighted coverage to the 21 days before, smoothed;
   - *tone*: decay-weighted mean signal, **relative to the subject average** (so a generally
     upbeat news cycle doesn't make everything "rising");
   - `score = 0.6·tanh(attention/0.8) + 0.4·tone_rel`, in −1…1.

   Noise control:
   - any single day is capped at 2.5× a typical busy day;
   - **hysteresis**: a new call needs |score| ≥ 0.22, an existing call holds until the score drops
     back below 0.12, and a direct rising↔fading flip needs an extra margin.

   **Not enough to go on** when there are fewer than 4 items in 28 days, fewer than 2 in the last
   14, or only one outlet.

   **Team files** count as evidence with 3× weight and a 21-day half-life (news: 7 days). They are
   a considered view, not a headline.

   **Collection bias.** Google News returns ~3× more articles for last week than for a month ago.
   Its daily counts are therefore normalised by how much it returned for the whole subject that
   day. Without this, every topic looked like it was rising after a backfill.
6. **Explain** (`gpt-5.6-terra`). The model gets the verdict, the numbers and up to 10 evidence
   items per topic (E1…E10), and writes 2–4 points, a one-line summary, "what would change the
   call" and the headline. A validator maps E-ids back to real evidence and drops invented ones.
   A point with no valid citation is dropped. A topic with no surviving points gets template text,
   flagged in the UI.
7. **Publish.** The brief JSON, plus two files per run in Files:
   - `brief-YYYY-MM-DD.html`: standalone, built from the same React components as the Brief tab
     (`vite-plugin-singlefile`) with the data embedded, so it works offline;
   - `trace-YYYY-MM-DD.md`: every query and its hit count, what was found, each topic's numbers and
     the rules that fired, citation checks, and cost per model.

**Cost.** A daily run on 10 topics is about **$0.045**; a first run with the 28-day backfill is
about $0.16. The whole 14-day demo cost $0.76.

### Extras

- **Who's driving it.** Companies come out of the classification step at no extra cost. Spellings
  are merged by a normalised key (case, punctuation, legal suffixes, TLDs: "Stripe, Inc." =
  "stripe.com" = "Stripe"), then fuzzy-matched. Very short names are never fuzzy-matched. Opening
  a company shows every mention with its source.
- **Ask about this brief.**
  - The question is embedded and matched against the workspace's own items; team files get a
    small boost.
  - terra answers from those numbered sources only and says whether they were enough. If not,
    luna answers from a web search; each sentence keeps the pages annotated on it, and uncited
    sentences are dropped.
  - Workspace citations are validated the same way as in the brief. Sources are labelled
    *Workspace* or *Web*.
  - Cost: about $0.01 per question, or about $0.04 when the web is searched. There is a daily cap
    per workspace.

## Architecture, and why

```
frontend/   Vite + React 19 + TS, TanStack Query, i18next (en/ru/uk), Tailwind v4, motion
  src/brief/      Brief components, shared by the tab, the landing demo and the standalone HTML
backend/    FastAPI, SQLAlchemy 2 (async), asyncpg / aiosqlite
  app/agent/      collectors, parsing, classify, scoring, narrate, artifacts, runner
  app/api/        auth, workspaces/roles/invites, files/runs/briefs, Q&A
  app/seed/       demo import/export
fixtures/demo/  the demo workspace (gzipped JSON)
```

- **One service, one origin.** FastAPI serves `/api` and the built SPA, so there's no CORS and
  cookie sessions just work. Render's free plan gives one web service, and this fits it.
- **Server-side sessions** in an httpOnly, SameSite=Lax cookie; passwords hashed with argon2.
  Every workspace endpoint depends on `require_role(min_role)`. Someone outside the workspace gets
  **404**, not 403, so they can't tell it exists. The UI hides what a role can't do, but the
  backend enforces it independently (see `tests/test_access.py`).
- **Files are stored in Postgres** (`bytea`). Render's disk is wiped on every deploy and restart,
  and these files are small.
- **Runs are asyncio tasks** in the web process, with one run per workspace at a time. A run
  interrupted by a restart is marked failed at startup. A job queue would be the next step, but on
  the free plan it would be one more thing to keep awake.
- **Scheduling.** An in-process loop, a catch-up on startup, and the GitHub Actions ping. A day is
  claimed atomically (`last_scheduled_on`), so the three can't double-run.
- **Deterministic scoring.** It is testable, explainable in the trace, and stable from day to day.
  An LLM asked "is this rising?" gives a different answer each morning.
- **The demo is the real agent replayed.** `scripts/build_demo.py` runs the same pipeline once per
  day for 3–16 Nov, with the cutoff at 06:00 each day. Real news, real model calls, real costs.
  The three team documents (`scripts/demo_documents.py`) are uploaded at their dates, and one of
  them says app builders are cooling, which shows in the briefs that follow. The result is
  exported to `fixtures/demo/demo.json.gz` and imported on startup. The demo therefore survives a
  fresh database and doesn't depend on an API key.

## What's not done / known limits

- No email: invite links go to the server log, as the brief allows. Anyone can sign up; there is no
  email verification or password reset.
- No migrations yet (`create_all` at startup). The next schema change needs Alembic.
- Google News items are titles and short snippets, not full articles, so classification is only
  as good as the snippet. GDELT was tried as a third source but rate-limited too often to rely on.
- PDFs without a text layer (scans) aren't OCR'd; such an upload is marked as having no readable
  text and doesn't feed the brief.
- Company merging has no LLM confirmation step for borderline spellings. It errs towards keeping
  companies separate.
- Schedule times are UTC. There's no per-user time zone.
- No rate limiting on login. Q&A has a per-workspace daily cap.
- Tests cover the scorer, the citation and quote validators, company merging, and the role matrix.
  The agent pipeline has no end-to-end test with a mocked OpenAI client; it was checked by running
  it (the demo build is that run).
- The free Postgres on Render expires after 30 days.

## Time spent

_TODO: fill in._
