"""Greenhouse public job-board API (company application pages). No key needed.

Endpoint: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
"""

from __future__ import annotations

import html
import re

from ..models import Job
from .base import Source

_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", text or "")).strip()


class GreenhouseSource(Source):
    name = "greenhouse"

    def __init__(self, slug: str):
        self.slug = slug

    def fetch(self) -> list[Job]:
        data = self._get_json(_URL.format(slug=self.slug), {"content": "true"})
        if not data or "jobs" not in data:
            return []
        jobs = []
        for j in data["jobs"]:
            jobs.append(Job(
                source=self.name,
                title=j.get("title", ""),
                company=self.slug,
                url=j.get("absolute_url", ""),
                location=(j.get("location") or {}).get("name", ""),
                description=_strip_html(j.get("content", ""))[:4000],
                posted_at=j.get("updated_at", "") or j.get("first_published", ""),
                external_id=str(j.get("id", "")),
                raw=j,
            ))
        return jobs
