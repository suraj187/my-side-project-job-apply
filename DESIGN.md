# JobPilot — Design

A personal, **US-remote-first job finder** that runs on your machine. It polls
job boards and company application pages, deduplicates, filters to remote/US,
ranks each role against your criteria, stores them so each run only surfaces
what's **new**, and notifies you.

**Scope decision:** autofill is intentionally **out**. You already use
Simplify/JobRight for filling application forms — duplicating that adds no
value. JobPilot solves the harder daily problem: reliably surfacing the *right*
remote listings. When you click an apply link, Simplify takes over.

---

## Goals & non-goals

**Goals**
- Surface fresh, relevant **remote US** roles automatically, 3×/day.
- Rank against your criteria with a plain-language reason per job.
- Pull from both channels: **job boards** (Adzuna, Remotive) *and* **company
  application pages** (Greenhouse, Lever, Ashby — the forms you actually apply on).
- Never show the same job twice; notify you when (and only when) there's something new.
- Run locally, free by default, with optional paid upgrades.

**Non-goals**
- No autofill / auto-submit (Simplify owns that).
- No scraping of sites that forbid it (LinkedIn/Indeed only via a licensed
  aggregator, optional).

---

## What you target

No fixed "dream company" list. The goal is **good companies with good pay,
good benefits, and good work-life balance — remote only, for now.** That shapes
the strategy:

- **Broad remote sources do the heavy lifting:** Remotive (remote-only board)
  and Adzuna (remote queries) surface roles across many companies.
- **A curated watchlist of remote-friendly, well-compensated companies** (that
  post on Greenhouse/Lever/Ashby) catches their roles the moment they post,
  before aggregators index them. This list is maintained for you — you don't
  have to name companies.
- **Ranking rewards** disclosed comp and (later) WLB/benefits signals; hard
  filters drop on-site and non-US roles.

---

## Pipeline

```
 cron 9am / 2pm / 9pm
        │
        ▼
   ┌─────────┐   Adzuna · Remotive · Greenhouse/Lever/Ashby watchlist
   │ Fetchers│   (one interface — adding a source is a config flip)
   └────┬────┘
        ▼
   ┌─────────┐   normalize → one job schema
   │  Dedup  │   collapse reposts / cross-source duplicates (dedup_key)
   └────┬────┘
        ▼
   ┌─────────┐   HARD filters: remote-only, US-only, dealbreaker keywords
   │ Filter  │   (this is what removes the noise other feeds bury you in)
   └────┬────┘
        ▼
   ┌─────────┐   rule-based score (free) + optional Claude Haiku on the
   │  Rank   │   shortlist → 0-100 + reason + red-flag flags
   └────┬────┘
        ▼
   ┌─────────┐   SQLite: status new/seen/applied/skipped; "what's new" detection
   │  Store  │
   └────┬────┘
        ▼
   ┌─────────┐   daily markdown digest +
   │ Notify  │   desktop ping every run (confirms cron fired) +
   └─────────┘   email when there are new matches
```

Each job entry carries: **score, title, company, location, workplace, comp (if
disclosed), why-it-fits, red-flag flags, and a direct apply link.**

---

## Components (implemented)

| Module | Role |
|---|---|
| `jobpilot/sources/*` | Greenhouse, Lever, Ashby, Remotive, Adzuna fetchers (one `Source` interface) |
| `jobpilot/models.py` | Normalized `Job` + stable `dedup_key` |
| `jobpilot/filters.py` | Remote / US / hybrid detection + hard dealbreaker filters |
| `jobpilot/rank.py` | Transparent rule-based scorer; optional Claude Haiku refinement |
| `jobpilot/db.py` | SQLite store; tracks status + "new since last run" |
| `jobpilot/pipeline.py` | Orchestrates fetch→filter→dedup→rank→store→digest |
| `jobpilot/notify.py` | Desktop ping + email (SMTP via env vars) |
| `jobpilot/cli.py` | `run` / `list` commands |

---

## Tech & defaults

- **Python 3.11**, `requests` + `PyYAML`, **SQLite** (single file).
- **Scoring:** rule-based and free by default; **Claude Haiku 4.5** refinement
  is opt-in (`llm.enabled: true` + `ANTHROPIC_API_KEY`), and only the top
  shortlist hits the API to keep cost low.
- **Delivery:** local markdown digest + desktop notification; email digest when
  SMTP env vars are set.
- **Schedule:** cron at 9am / 2pm / 9pm.
- **Filters:** `remote_only: true`, `us_only: true`, `allow_hybrid: false`
  (toggle hybrid on later with a metro allowlist + comp floor).

---

## Sources & cost

| Source | Channel | Key? | Cost |
|---|---|---|---|
| Greenhouse / Lever / Ashby | Company application pages | No | Free |
| Remotive | Remote job board | No | Free |
| Adzuna | Broad job board | Free key | Free tier (~250 req/day) |
| Claude Haiku 4.5 | Ranking refinement | API key | ~$5–15/mo, optional |
| *(later)* JSearch | LinkedIn/Indeed via Google for Jobs | Paid | ~$25/mo, optional |

**Free core: ~$0/mo.** With Haiku scoring: **~$5–15/mo.** With LinkedIn/Indeed
added: **~$30–40/mo.** Fetchers sit behind one interface, so upgrading is a
config flip, not a rewrite.

---

## Build phases

- **Phase 1 — DONE.** Fetch → filter → dedup → rank → store → daily digest +
  notifications. Runs free; verified end-to-end offline (`run --dry-run`).
- **Phase 2 — next.** Parse your résumé → `profile.json`; turn on Haiku scoring
  so "why it fits" reflects your actual background. Curate the remote-friendly
  company watchlist.
- **Phase 3.** Local dashboard (mark applied/skipped); richer email formatting.
- **Phase 4.** 👍/👎 feedback tuning; optional JSearch for LinkedIn/Indeed;
  hybrid allowlist + comp floor.

---

## Risks & guardrails

- **ToS:** only aggregator APIs and public company-board endpoints; LinkedIn/
  Indeed solely via a licensed aggregator if added.
- **Noise vs. coverage:** hard filters cut noise; if a niche is thin, no tool
  manufactures listings — the honest limit of any finder.
- **Maintenance tail:** company slugs/APIs shift occasionally; low but non-zero.
- **Privacy:** everything runs locally; your résumé/criteria stay on your machine.
