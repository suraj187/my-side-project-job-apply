"""The run pipeline: fetch → filter → dedup → rank → store → digest."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from .config import Settings
from .db import DB
from .filters import passes_hard_filters
from .models import Job
from .rank import rank
from .sources import build_sources

log = logging.getLogger("jobpilot.pipeline")


@dataclass
class RunResult:
    fetched: int
    after_filter: int
    new_jobs: list[Job]
    digest_path: str


def _sample_jobs() -> list[Job]:
    """Offline fixtures for --dry-run (no network/keys needed)."""
    return [
        Job(source="greenhouse", title="Senior Backend Engineer (Remote, US)",
            company="acme", url="https://boards.greenhouse.io/acme/jobs/1",
            location="Remote - United States", workplace="remote",
            description="Python, FastAPI, distributed systems. Remote US.",
            comp="$170k-$210k"),
        Job(source="remotive", title="Full Stack Engineer",
            company="Globex", url="https://remotive.com/jobs/2",
            location="USA only", workplace="remote", remote=True,
            description="React, Node, Postgres. Remote within the US."),
        Job(source="lever", title="Staff Engineer",
            company="initech", url="https://jobs.lever.co/initech/3",
            location="London, UK", workplace="onsite",
            description="On-site in London. Not remote."),
    ]


def run(settings: Settings, db_path: str, digest_dir: str = ".",
        dry_run: bool = False) -> RunResult:
    # 1. Fetch
    if dry_run:
        jobs = _sample_jobs()
    else:
        jobs = []
        for src in build_sources(settings):
            got = src.fetch()
            log.info("%s: %d jobs", src.name, len(got))
            jobs.extend(got)
    fetched = len(jobs)

    # 2. In-run dedup — collapse same job seen from multiple sources/queries.
    # Primary key: dedup_key (SHA1 of title+company+url). Catches exact same URL.
    # Secondary key: (title_slug, company_slug). Catches same role posted under
    # different Adzuna/JSearch listing IDs (same title+company, different URL).
    from .models import _slug as _s
    seen_keys: set[str] = set()
    seen_title_company: set[tuple[str, str]] = set()
    unique_jobs: list[Job] = []
    for job in jobs:
        k = job.dedup_key
        tc = (_s(job.title), _s(job.company))
        if k in seen_keys or tc in seen_title_company:
            log.debug("in-run dedup: skip %s @ %s", job.title, job.company)
            continue
        seen_keys.add(k)
        seen_title_company.add(tc)
        unique_jobs.append(job)
    jobs = unique_jobs

    # 3. Hard filters (dealbreakers)
    kept: list[Job] = []
    for job in jobs:
        ok, why = passes_hard_filters(job, settings.criteria)
        if ok:
            kept.append(job)
        else:
            log.debug("drop %s @ %s: %s", job.title, job.company, why)

    # 4. Rank (rule-based, plus optional LLM on the shortlist)
    kept = rank(kept, settings.criteria)
    kept = [j for j in kept if j.score >= settings.criteria.min_score]

    # 5. Store + detect what's new
    db = DB(db_path)
    new_jobs: list[Job] = []
    try:
        for job in kept:
            if db.upsert(job):
                new_jobs.append(job)

        # 5b. Sync new jobs to Notion (optional)
        if settings.notion_api_key and settings.notion_database_id:
            try:
                from .notion import sync_jobs_to_notion
                job_id_map = db.get_notion_id_map()
                updated = sync_jobs_to_notion(
                    new_jobs,
                    settings.notion_api_key,
                    settings.notion_database_id,
                    job_id_map,
                )
                for dedup_key, notion_row_id in updated.items():
                    db.set_notion_row_id(dedup_key, notion_row_id)
            except Exception as exc:
                log.warning("notion sync failed (%s)", exc)
    finally:
        db.close()

    # 6. Digest of new matches
    digest_path = _write_digest(new_jobs, digest_dir)
    return RunResult(fetched=fetched, after_filter=len(kept),
                     new_jobs=new_jobs, digest_path=digest_path)


def _write_digest(new_jobs: list[Job], digest_dir: str) -> str:
    import os
    os.makedirs(digest_dir, exist_ok=True)
    path = os.path.join(digest_dir, f"digest-{date.today().isoformat()}.md")
    lines = [f"# JobPilot digest — {date.today().isoformat()}",
             "", f"**{len(new_jobs)} new matching role(s).**", ""]
    for j in new_jobs:
        flags = f" — ⚑ {', '.join(j.flags)}" if j.flags else ""
        comp = f" · {j.comp}" if j.comp else ""
        lines.append(f"### [{j.score}] {j.title} — {j.company}")
        lines.append(f"{j.location} · {j.workplace or 'workplace n/a'}{comp}{flags}")
        lines.append(f"_{j.reason}_")
        lines.append(f"<{j.url}>")
        lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path
