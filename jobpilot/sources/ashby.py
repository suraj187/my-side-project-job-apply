"""Ashby public job-board API (company application pages). No key needed.

Endpoint: https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true
"""

from __future__ import annotations

import html
import re

from ..models import Job
from .base import Source

_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", text or "")).strip()


def _comp(job: dict) -> str:
    comp = job.get("compensation") or {}
    summary = comp.get("compensationTierSummary") or comp.get("summary")
    return summary or ""


class AshbySource(Source):
    name = "ashby"

    def __init__(self, slug: str):
        self.slug = slug

    def fetch(self) -> list[Job]:
        data = self._get_json(_URL.format(slug=self.slug), {"includeCompensation": "true"})
        if not data or "jobs" not in data:
            return []
        jobs = []
        for j in data["jobs"]:
            is_remote = j.get("isRemote")
            jobs.append(Job(
                source=self.name,
                title=j.get("title", ""),
                company=self.slug,
                url=j.get("jobUrl", "") or j.get("applyUrl", ""),
                location=j.get("location", ""),
                description=_strip_html(j.get("descriptionHtml", ""))[:4000],
                remote=is_remote if isinstance(is_remote, bool) else None,
                workplace="remote" if is_remote else "",
                comp=_comp(j),
                posted_at=j.get("publishedAt", ""),
                external_id=str(j.get("id", "")),
                raw=j,
            ))
        return jobs
