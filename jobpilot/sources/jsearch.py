"""JSearch API (LinkedIn + Indeed + Glassdoor + ZipRecruiter aggregator).

Endpoint: https://jsearch.p.rapidapi.com/search
Requires RapidAPI key. Aggregates LinkedIn, Indeed, Glassdoor, ZipRecruiter, etc.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from ..models import Job
from .base import Source

log = logging.getLogger("jobpilot.sources.jsearch")

_URL = "https://jsearch.p.rapidapi.com/search"

# Domains that appear as employer_name but are just job-board/aggregator tech stacks.
# Jobs from these "employers" are junk re-listings, not real postings.
_JUNK_EMPLOYER_PATTERNS = (
    "railway.app",
    "vercel.app",
    "netlify.app",
    "ngrok.io",
    "herokuapp.com",
    "render.com",
)


class JSearchSource(Source):
    name = "jsearch"

    def __init__(self, queries: list[str], rapidapi_key: str, limit: int = 10):
        self.queries = queries or []
        self.rapidapi_key = rapidapi_key
        self.limit = limit

    def fetch(self) -> list[Job]:
        if not self.rapidapi_key or not self.queries:
            return []

        jobs = []
        for q in self.queries:
            try:
                data = self._fetch_query(q)
                jobs.extend(data)
            except Exception as exc:
                log.warning("jsearch query failed (%s: %s)", q, exc)
        return jobs

    def _fetch_query(self, query: str) -> list[Job]:
        """Fetch a single query; returns normalized Job list."""
        headers = {
            "x-rapidapi-key": self.rapidapi_key,
            "x-rapidapi-host": "jsearch.p.rapidapi.com",
            "User-Agent": "JobPilot/0.1 (personal job finder)",
        }

        params = {
            "query": query,
            "page": 1,
            "num_pages": 1,
            "country": "US",
            "employment_type": "FULLTIME",
        }

        try:
            resp = requests.get(_URL, params=params, headers=headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            log.warning("jsearch: failed to fetch query '%s' (%s)", query, exc)
            return []

        jobs = []
        for j in (data or {}).get("data", []):
            if not j.get("job_apply_link"):
                continue
            employer = j.get("employer_name", "") or ""
            if any(pat in employer.lower() for pat in _JUNK_EMPLOYER_PATTERNS):
                log.debug("jsearch: skip junk employer '%s'", employer)
                continue
            jobs.append(Job(
                source=self.name,
                title=j.get("job_title", ""),
                company=j.get("employer_name", ""),
                url=j.get("job_apply_link", ""),
                location=j.get("job_location", ""),
                description=(j.get("job_description", "") or "")[:4000],
                workplace=self._detect_workplace(j.get("job_description", "")),
                comp=self._extract_salary(j),
                posted_at=j.get("job_posted_publish_date", ""),
                external_id=j.get("job_id", ""),
                raw=j,
            ))
        return jobs

    def _detect_workplace(self, description: str) -> str:
        """Infer workplace type from description (remote/hybrid/onsite)."""
        desc_lower = (description or "").lower()
        if "remote" in desc_lower:
            if "hybrid" in desc_lower or "partially" in desc_lower:
                return "hybrid"
            return "remote"
        return "onsite"

    def _extract_salary(self, job: dict[str, Any]) -> str:
        """Extract salary range if available."""
        min_sal = job.get("job_salary_min")
        max_sal = job.get("job_salary_max")
        if min_sal and max_sal:
            try:
                return f"${int(min_sal):,} - ${int(max_sal):,}"
            except (ValueError, TypeError):
                pass
        return ""
