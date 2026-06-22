# JobPilot — Build & Architecture Journal

A detailed record of **what JobPilot is**, **how it's built**, **every setup step
we ran**, and **what worked vs. what didn't** during bring-up. Written so a future
you (or anyone) can rebuild this from scratch and avoid the same dead-ends.

- Owner profile: SailPoint IAM Engineer (IIQ + ISC), ~6 yrs, US-remote-first
- Repo branch: `claude/sweet-bohr-hp31cm`
- Machine: macOS laptop, Python 3.12+ in a project venv

---

## 1. What it does (one paragraph)

JobPilot runs 3×/day (9am, 2pm, 9pm), fetches remote/US IAM jobs from job boards,
filters out noise and dealbreakers, deduplicates, ranks by a transparent rule-based
score, stores results in SQLite (so it knows what's "new"), and emails a formatted
HTML digest with direct apply links. It is a **finder**, not an autofill tool —
JobRight/Simplify handle the actual application.

---

## 2. Architecture

### Pipeline (per run)

```
fetch  →  filter  →  dedup  →  rank  →  store  →  digest  →  notify
```

| Stage | Module | What happens |
|---|---|---|
| fetch | `jobpilot/sources/*` | Pull postings from Remotive + Adzuna (and Greenhouse/Lever/Ashby if configured). Each source normalizes into one `Job` shape. |
| filter | `jobpilot/filters.py` | Drop non-remote / non-US / dealbreaker-keyword jobs. Detects remote/hybrid/onsite and US-eligibility heuristically. |
| dedup | `jobpilot/models.py` (`dedup_key`) | Stable SHA1 of `title + company + url-host/path` collapses the same role seen twice. |
| rank | `jobpilot/rank.py` | Transparent 0–100 score from title/keyword/remote/comp signals. Optional Claude Haiku refinement on the top 25 (off by default). |
| store | `jobpilot/db.py` | SQLite upsert keyed by `dedup_key`; tracks status (new/seen/applied/skipped) and timestamps. Returns whether each job is new. |
| digest | `jobpilot/pipeline.py` (`_write_digest`) | Writes a Markdown digest file per day for archive. |
| notify | `jobpilot/notify.py` | Desktop ping every run; HTML email **only when there are new jobs**. |

### Key design choices

- **Config-driven** (`config/criteria.yaml`): titles, keywords, dealbreakers,
  filters, and per-source queries live in YAML so ranking can be tuned without
  touching code. This file is **git-ignored** (it's personal) — the template is
  `config/criteria.example.yaml`.
- **Free by default**: Remotive needs no key; Adzuna uses a free tier key; LLM
  scoring is off unless `ANTHROPIC_API_KEY` is set. LLM only scores the top 25
  per run, bounding cost to ~$3–4/mo if ever enabled.
- **"New since last run"** comes from the SQLite dedup table — this is what makes
  the daily email feel relevant instead of repeating the same listings.
- **Backfill window**: Adzuna pulls `max_days_old: 7`, so a missed run loses
  nothing — the next run still surfaces the week's new postings.

### Modules

```
jobpilot/
  cli.py          # entry point: `run` and `list` subcommands
  pipeline.py     # orchestrates the stages; --dry-run uses offline fixtures
  models.py       # Job dataclass + stable dedup_key
  filters.py      # remote/US detection + hard dealbreaker filtering
  rank.py         # rule_score (free) + optional llm_score (top 25)
  db.py           # SQLite storage + new/seen/applied/skipped status
  notify.py       # desktop + HTML email digest (+ link validation)
  linkcheck.py    # concurrent best-effort apply-link validation
  config.py       # dataclasses + load_settings() from YAML
  sources/
    base.py       # Source interface + shared HTTP helper
    remotive.py   # remote board (no key)
    adzuna.py     # broad board (free key; parses salary_min/max)
    greenhouse.py / lever.py / ashby.py  # company boards (optional)
```

---

## 3. Sources & cost

| Source | Channel | Key? | Cost |
|---|---|---|---|
| Remotive | Remote job board | No | Free |
| Adzuna | Broad job board | Free key (`ADZUNA_APP_ID`/`ADZUNA_APP_KEY`) | Free tier (~250/day) |
| Greenhouse / Lever / Ashby | Company application pages | No | Free |
| LLM scoring (Claude Haiku) | Ranking refinement | `ANTHROPIC_API_KEY` | ~$3–4/mo, optional, off |

---

## 4. Setup — every step we actually ran

> Commands are macOS/zsh. Project lives at
> `~/desktop/project/my-side-project-job-apply`.

### 4.1 Clone & branch
```bash
git clone https://github.com/suraj187/my-side-project-job-apply.git
cd my-side-project-job-apply
git checkout claude/sweet-bohr-hp31cm
```

### 4.2 Python environment (venv)
```bash
python3 --version                 # `python` alone isn't on PATH; use python3
python3 -m venv venv
source venv/bin/activate          # now `python` works inside the venv
pip install PyYAML requests       # avoids the system-Python install block
```

### 4.3 Adzuna keys
```bash
export ADZUNA_APP_ID=xxxxxxxx     # NOTE: no spaces around '='
export ADZUNA_APP_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 4.4 Criteria (personal, git-ignored)
```bash
# Built from the résumé: SailPoint IIQ + ISC, mid-to-senior, exclude architect/
# principal/manager/sales/writer noise. Filters: remote_only, us_only.
# Lives at config/criteria.yaml (NOT committed — see .gitignore).
```
Tuning loop we used: start `min_score: 0` to see everything, expand
`dealbreaker_keywords` to kill noise (sales, writer, analyst, architect,
principal, consultant, frontend…), then raise `min_score` to ~45. Result on a
typical run: **~204 fetched → ~6 high-quality IAM matches**.

### 4.5 Email (Gmail App Password)
```bash
# Generate a 16-char App Password at https://myaccount.google.com/apppasswords
cat >> ~/.zshrc << 'EOF'

export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=you@gmail.com
export SMTP_PASS=your16charapppassword
export NOTIFY_EMAIL=you@gmail.com
EOF
source ~/.zshrc
```

### 4.6 Run it
```bash
python -m jobpilot.cli --db ~/.jobpilot.db run --notify --digest-dir ~/job-digests
```

### 4.7 Schedule with cron
```bash
# 1) Secrets in a file cron can read (captured from the current shell):
cat > ~/.jobpilot.env << EOF
export ADZUNA_APP_ID='$ADZUNA_APP_ID'
export ADZUNA_APP_KEY='$ADZUNA_APP_KEY'
export SMTP_HOST='$SMTP_HOST'
export SMTP_PORT='$SMTP_PORT'
export SMTP_USER='$SMTP_USER'
export SMTP_PASS='$SMTP_PASS'
export NOTIFY_EMAIL='$NOTIFY_EMAIL'
EOF
chmod 600 ~/.jobpilot.env

# 2) Wrapper script (cron doesn't load ~/.zshrc):
PROJ="$(pwd)"
cat > "$PROJ/run_jobpilot.sh" << EOF
#!/bin/bash
source "\$HOME/.jobpilot.env"
mkdir -p "\$HOME/job-digests"
cd "$PROJ"
"$PROJ/venv/bin/python" -m jobpilot.cli --db "\$HOME/.jobpilot.db" run --notify --digest-dir "\$HOME/job-digests" >> "\$HOME/job-digests/cron.log" 2>&1
EOF
chmod +x "$PROJ/run_jobpilot.sh"

# 3) Install the schedule (no editor opens):
( crontab -l 2>/dev/null | grep -v run_jobpilot.sh ; echo "0 9,14,21 * * * $PROJ/run_jobpilot.sh" ) | crontab -
crontab -l
```
Then grant **System Settings → Privacy & Security → Full Disk Access →
`/usr/sbin/cron`** (Cmd+Shift+G to type the path), toggle ON. Without this, cron
is silently blocked on modern macOS.

---

## 5. What worked vs. what didn't

### ❌ Didn't work → ✅ Fix

| Problem | Cause | Fix |
|---|---|---|
| `python: command not found` | macOS ships `python3`, not `python` | Use `python3`; inside the venv `python` works |
| `pip3 install` → *externally-managed-environment* | Homebrew/system Python is locked (PEP 668) | Use a **venv**, then `pip install` |
| `export VAR= value` → "not an identifier" | Space after `=` | No spaces: `export VAR=value` |
| nano paste failed; no **End** key on Mac | nano + Mac keyboard | Skip the editor — append with `cat >> file << 'EOF' … EOF` |
| `git add config/criteria.yaml` ignored | It's **git-ignored by design** (personal config) | Keep it local; commit `criteria.example.yaml` only |
| First run kept 0 jobs | `criteria.yaml` didn't exist yet / `sed` ran on a missing file | Create it via heredoc, then tune |
| Architect/principal/sales jobs slipped through | Dealbreakers too generic ("architect only") | Use bare terms ("architect", "principal", "sales", "consultant"…); filter checks title+company+description |
| Email: `'ascii' codec can't encode '\xa0'` | **`SMTP_PASS` contained non-breaking spaces** copied from the Gmail App-Password display | Strip whitespace from the password: `re.sub(r"\s", "", SMTP_PASS)` |
| Email tries with `Header()` / `send_message()` / `policy=` | Symptom-chasing the encoding error; also a name clash (`email` module vs local `email()` function) | Root cause was the password, not the body; switched to `EmailMessage` + `set_content` + `add_alternative(html)` |
| ASCII-sanitizing the body | Mangled the digest (`title∈`→`titlein`, `·`→`.`) | Dropped sanitization once the password was fixed; send real UTF-8 HTML |
| Code edits "not taking effect" | Stale `__pycache__` bytecode | `find . -name __pycache__ -type d -exec rm -rf {} +` |

### ✅ What worked well
- **venv + `requests`/`PyYAML`** — clean, no system-Python fights.
- **Heredocs (`cat > file << 'EOF'`)** — reliable way to write files without an editor.
- **`EmailMessage.set_content(text)` + `add_alternative(html, subtype="html")`** —
  proper multipart UTF-8 email; renders as cards in Gmail, plaintext fallback elsewhere.
- **Adzuna `salary_min/max` → `comp`** — surfaces pay in the digest.
- **Wrapper script sourcing `~/.jobpilot.env`** — gives cron the env it otherwise lacks.
- **Non-interactive `crontab -` install** — no vim, no surprises; `grep -v` prevents dupes.
- **Rule-based ranking first** — transparent and tunable before spending on any LLM.

---

## 6. Day-to-day operation

- **Nothing to run manually.** Cron fires at 9am / 2pm / 9pm.
- **Keep the laptop awake** around those times. cron does **not** catch up after
  sleep — but no jobs are lost (7-day backfill + dedup), so a missed 9am simply
  arrives at 2pm.
- **You only read the emails.** Subject looks like:
  `JobPilot - N Jobs to apply · Jun 22, 2026 (Morning)`.
- Logs: `~/job-digests/cron.log`. Archived digests: `~/job-digests/digest-YYYY-MM-DD.md`.
- DB: `~/.jobpilot.db`.

### cron vs. launchd
Keeping **cron** for now (laptop is usually on during the day). If missed morning
runs become annoying, switch to **launchd** (`StartCalendarInterval`), which runs
missed jobs on wake and needs no Full Disk Access prompt.

---

## 7. Queued / future work

- [ ] **Email subject** — done: now includes date + time-of-day slot.
- [ ] **Link validation** — done: digest flags verified vs. unverified/expired
      apply links (`linkcheck.py`). Could later **drop** dead links instead of
      just flagging.
- [ ] **Résumé-aware Haiku scoring** (Phase 2) — score top 25 against the parsed
      résumé for sharper ranking.
- [ ] **Local dashboard** (Phase 3) — mark applied/skipped.
- [ ] **👍/👎 feedback tuning** (Phase 4); optional JSearch (LinkedIn/Indeed).
- [ ] Other tweaks to be specified.
