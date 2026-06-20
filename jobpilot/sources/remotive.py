"""Remotive remote-jobs API (job board). No key needed; all roles are remote.

Endpoint: https://remotive.com/api/remote-jobs?search=...&limit=...
"""

from __future__ import annotations

import html
import re

from ..models import Job
from .base import Source

_URL = "https://remotive.com/api/remote-jobs"


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", text or "")).strip()


class RemotiveSource(Source):
    name = "remotive"

    def __init__(self, queries: list[str], limit: int = 50):
        self.queries = queries or [""]
        self.limit = limit

    def fetch(self) -> list[Job]:
        jobs = []
        for q in self.queries:
            params = {"limit": self.limit}
            if q:
                params["search"] = q
            data = self._get_json(_URL, params)
            for j in (data or {}).get("jobs", []):
                jobs.append(Job(
                    source=self.name,
                    title=j.get("title", ""),
                    company=j.get("company_name", ""),
                    url=j.get("url", ""),
                    location=j.get("candidate_required_location", ""),
                    description=_strip_html(j.get("description", ""))[:4000],
                    remote=True,
                    workplace="remote",
                    comp=j.get("salary", "") or "",
                    posted_at=j.get("publication_date", ""),
                    external_id=str(j.get("id", "")),
                    raw=j,
                ))
        return jobs
