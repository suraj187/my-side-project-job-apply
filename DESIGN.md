# JobPilot — Design

A personal job-search assistant, built as **two independent tools that share one profile**.

- **Tool A — Job Finder:** a local Python service that finds and ranks job postings against your resume.
- **Tool B — Autofill:** a Chrome extension that fills application forms from your profile while you review and submit.

Neither tool requires the other. Both read a single `profile.json` derived from your resume.

---

## Goals & non-goals

**Goals**
- Find relevant jobs automatically on a schedule (every 3–6h) from legal aggregator APIs.
- Rank them against your resume with an explanation, so you spend time only on good matches.
- Make applying faster by auto-filling application forms from your profile.
- Keep a human in the loop: **you approve and submit every application.**
- Run entirely on your local machine.

**Non-goals (by design)**
- No fully-automatic submission of applications (ToS risk, low quality, reputational risk).
- No scraping of LinkedIn / Indeed or other sources that prohibit automation.
- No bypassing bot detection or CAPTCHAs.

---

## Shared foundation: the profile

A single structured `profile.json` is the contract between both tools.

- **Capture:** parse your resume **PDF** to pre-fill, then you **correct/complete it in a form**. PDF parsing is convenient but lossy; the form makes it exact.
- **Contents:** name, email, phone, location, links (LinkedIn/GitHub/portfolio), work history (title, company, dates, bullets), education, skills, work authorization, and common EEO/voluntary-disclosure answers.
- **Storage:** `profile.json` on disk + a `profile` row in SQLite. Tool A reads it to match; Tool B reads it to fill.

```
            ┌─────────────┐
            │ profile.json│  ← parsed from resume PDF, corrected in a form
            └──────┬──────┘
          reads    │    reads
        ┌──────────┴──────────┐
   ┌────▼─────┐         ┌──────▼──────┐
   │ Tool A   │         │  Tool B     │
   │ Finder   │         │  Autofill   │
   │ (Python) │         │ (extension) │
   └──────────┘         └─────────────┘
```

---

## Tool A — Job Finder (Python service)

**Pipeline**
1. **Fetch** new postings from aggregator APIs (cron, every 3–6h).
2. **Normalize** into a common job schema; **dedupe** by (title, company, url hash).
3. **Pre-filter (cheap, local):** embed job + resume with `sentence-transformers`; keep the top-N by cosine similarity.
4. **Score (LLM):** Claude scores each shortlisted job 0–100 with a one-line reason and any red flags.
5. **Store** in SQLite; mark status `matched`.
6. **Surface:** local FastAPI dashboard at `localhost:8000` showing the ranked queue; desktop notification on new high-scoring matches.
7. **Review:** you Approve / Skip; status tracked through `matched → approved → applied → interview → rejected/offer`.

**Job sources (legal aggregator APIs)**
- Adzuna (broad, free key, good filters) — primary.
- Greenhouse / Lever / Ashby public board JSON endpoints — also the ATSes Tool B fills, so finding → applying is seamless.
- Remotive / Remote OK (remote roles), USAJobs (US gov) — optional add-ons.

**Tech**
- Python + FastAPI (dashboard + a tiny local API the extension can read the profile from).
- SQLite (single-file, zero setup).
- `sentence-transformers` for local embeddings (free first-pass filter).
- Claude API for scoring + draft generation (only on the shortlist, to control cost).
- Scheduling via cron (simple) or APScheduler (single-process alternative).

**Data model (sketch)**
- `profile` — the structured resume.
- `jobs` — id, source, external_id, title, company, location, url, description, fetched_at, embedding.
- `matches` — job_id, score, reason, flags, status, created_at.
- `applications` — match_id, draft_cover_letter, submitted_at, outcome.

---

## Tool B — Autofill (Chrome extension)

**Behavior**
- Activates on a job application page (any job, whether found via Tool A or by you).
- Detects the ATS form; maps `profile.json` fields → form fields.
- Fills the form; **you review and click submit.** Never auto-submits.

**ATS support order**
1. Greenhouse, Lever, Ashby (predictable field names — high reliability).
2. Later: Workday, Taleo (multi-step, iframes — messier).

**Tech**
- TypeScript, Manifest V3, Chrome first.
- Reads the profile from the local service (`localhost`) or an imported JSON, so there's a single source of truth.

---

## Build phases

- **Phase 0 — Shared profile:** PDF parse → pre-filled form → `profile.json` + SQLite. *(prerequisite for both tools)*
- **Phase 1 — Tool A MVP:** fetch from Adzuna + one board → dedupe → embed pre-filter → LLM score → dashboard queue with approve/skip + status. Links open the job.
- **Phase 2 — Tool A polish:** LLM-drafted cover letters/screening answers, desktop notifications, cron scheduling.
- **Phase 3 — Tool B MVP:** Chrome extension autofill for Greenhouse/Lever/Ashby.
- **Phase 4:** more sources, Workday support, apply→response analytics.

---

## Defaults (overridable)

- **LLM:** Claude API for scoring/drafting; free local embeddings for first-pass filter (cost control). A fully-local model is possible if zero per-run cost is required.
- **Browser:** Chrome first; Firefox later.
- **Notifications:** desktop pop-up for MVP; email digest later.

---

## Risks & guardrails

- **ToS / bans:** only aggregator APIs and public board endpoints; no scraping of sites that forbid it.
- **Human-in-the-loop:** every application is reviewed and submitted by you. No auto-submit.
- **PDF parsing accuracy:** mitigated by the correction form.
- **LLM cost:** mitigated by local pre-filter; only the shortlist hits the API.
- **Privacy:** everything runs locally; resume/profile data stays on your machine.
