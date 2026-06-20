"""Adzuna job-search API (broad job board). Free key required.

Set ADZUNA_APP_ID and ADZUNA_APP_KEY in the environment.
Endpoint: https://api.adzuna.com/v1/api/jobs/us/search/1
Note: free tier is rate-limited (~25/min, ~250/day) — keep queries lean.
"""

from __future__ import annotations

from ..models import Job
from .base import Source

_URL = "https://api.adzuna.com/v1/api/jobs/us/search/1"


class AdzunaSource(Source):
    name = "adzuna"

    def __init__(self, app_id: str, app_key: str, queries: list[str],
                 results_per_query: int = 50, max_days_old: int = 7):
        self.app_id = app_id
        self.app_key = app_key
        self.queries = queries or ["software engineer"]
        self.results_per_query = results_per_query
        self.max_days_old = max_days_old

    def fetch(self) -> list[Job]:
        jobs = []
        for q in self.queries:
            params = {
                "app_id": self.app_id,
                "app_key": self.app_key,
                "what": q,
                "results_per_page": self.results_per_query,
                "max_days_old": self.max_days_old,
                "content-type": "application/json",
            }
            data = self._get_json(_URL, params)
            for j in (data or {}).get("results", []):
                company = (j.get("company") or {}).get("display_name", "")
                location = (j.get("location") or {}).get("display_name", "")
                jobs.append(Job(
                    source=self.name,
                    title=j.get("title", ""),
                    company=company,
                    url=j.get("redirect_url", ""),
                    location=location,
                    description=(j.get("description") or "")[:4000],
                    posted_at=j.get("created", ""),
                    external_id=str(j.get("id", "")),
                    raw=j,
                ))
        return jobs
