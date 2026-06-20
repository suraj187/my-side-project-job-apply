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
| LLM scoring (Claude Haiku) | Ranking refinement | `ANTHROPIC_API_KEY` | ~$5–15/mo, optional |

Adzuna and LLM scoring are **off until you provide keys** — the tool runs free
out of the box on company boards + Remotive.

## Scheduling (3×/day: 9am, 2pm, 9pm)

```cron
0 9,14,21 * * *  cd /path/to/jobpilot && /usr/bin/python3 -m jobpilot.cli run >> jobpilot.log 2>&1
```

## Status

- [x] Phase 1 — fetch → filter → dedup → rank → store → daily markdown digest
- [ ] Phase 2 — LLM scoring wired to your parsed resume (scaffolded, off by default)
- [ ] Phase 3 — desktop notifications + local dashboard
- [ ] Phase 4 — 👍/👎 feedback tuning; optional JSearch (LinkedIn/Indeed)
