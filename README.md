# JobPilot

A personal, **US-remote-first job finder**. It polls job boards (Adzuna,
Remotive) *and* company application pages (Greenhouse, Lever, Ashby — the same
forms you apply through), deduplicates, filters to remote/US, ranks each role
against your criteria, and stores them so every run surfaces only what's **new**.

Autofill is intentionally **not** part of this — use Simplify/JobRight for that
when you click through. This tool solves the harder daily problem: reliably
surfacing the *right* listings.

See [`DESIGN.md`](DESIGN.md) for the full architecture and cost breakdown.

## Quick start

```bash
pip install -r requirements.txt

# 1. Configure
cp config/criteria.example.yaml  config/criteria.yaml
cp config/companies.example.yaml config/companies.yaml
# edit both to taste

# 2. Smoke test (offline, no keys, no cost)
python -m jobpilot.cli run --dry-run

# 3. Real run (free sources: company boards + Remotive)
python -m jobpilot.cli run

# 4. Browse what's stored
python -m jobpilot.cli list --status new
```

## Sources & cost

| Source | Channel | Key? | Cost |
|---|---|---|---|
| Greenhouse / Lever / Ashby | Company application pages | No | Free |
| Remotive | Remote job board | No | Free |
| Adzuna | Broad job board | Free key (`ADZUNA_APP_ID`/`ADZUNA_APP_KEY`) | Free tier |
| JSearch | LinkedIn + Indeed + Glassdoor via RapidAPI | `RAPIDAPI_KEY` | Free tier (~10 req/day) |
| LLM scoring (Claude Haiku) | Ranking refinement | `ANTHROPIC_API_KEY` | ~$5–15/mo, optional |

Adzuna, JSearch, and LLM scoring are **off until you provide keys** — the tool runs free
out of the box on company boards + Remotive.

### RapidAPI / JSearch setup (optional)

To enable LinkedIn + Indeed + Glassdoor integration:

1. **Sign up free at [RapidAPI](https://rapidapi.com/)** and subscribe to JSearch (free tier = ~10 requests/day).
2. **Get your API key** from the RapidAPI dashboard (under your profile).
3. **Export the key** in your shell:
   ```bash
   export RAPIDAPI_KEY=your_rapidapi_key_here
   ```
4. **Add JSearch queries** to `config/criteria.yaml`:
   ```yaml
   jsearch_queries:
     - remote sailpoint engineer
     - remote iam engineer
   ```
5. **Optional: Filter consulting firms** that often masquerade as direct-hire:
   ```yaml
   consulting_firm_keywords:
     - teksystems
     - cognizant
     - infosys
     - accenture
     - deloitte
     - wipro
     - tcs
   ```

## Notifications

`--notify` sends a **desktop ping every run** (so you know the cron fired) and
**emails the digest only when there are new matches**. Email needs these env
vars (Gmail: use an App Password):

```bash
export SMTP_HOST=smtp.gmail.com SMTP_PORT=587
export SMTP_USER=you@gmail.com SMTP_PASS=your_app_password
export NOTIFY_EMAIL=you@gmail.com
```

## Scheduling (3×/day: 9am, 2pm, 9pm)

```cron
0 9,14,21 * * *  cd /path/to/jobpilot && /usr/bin/python3 -m jobpilot.cli run --notify >> jobpilot.log 2>&1
```

### cron vs. launchd (macOS laptops)

We currently use **cron**. Trade-off worth knowing:

- **cron** only fires if the Mac is **awake at the exact time** (9/2/9). If the
  laptop is asleep/off at 9am, that run is **skipped** — it does *not* catch up
  on wake. No jobs are lost, though: each run pulls the last 7 days, so the next
  run that fires still surfaces everything new (dedup prevents repeats). Practical
  effect: open the laptop by ~10am and the 2pm run delivers the morning's jobs.
- **launchd** (`StartCalendarInterval`) **runs missed jobs the moment the Mac
  wakes**, so you never miss a slot. More setup; no Full Disk Access prompt.

Decision: keeping cron for now since the laptop is usually on during the day.
Revisit launchd after a few weeks if missed morning runs become annoying.

## Status

- [x] Phase 1 — fetch → filter → dedup → rank → store → daily digest + notifications
- [ ] Phase 2 — Haiku scoring wired to your parsed résumé (scaffolded, off by default)
- [ ] Phase 3 — local dashboard (mark applied/skipped); richer email
- [ ] Phase 4 — 👍/👎 feedback tuning; optional JSearch (LinkedIn/Indeed)
