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

# Boards that should land in Tier 1. If a job is mirrored to one of these via
# apply_options, prefer that publisher so it gets prioritized.
_TIER1_PUBLISHERS = ("linkedin", "indeed", "ziprecruiter")


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

        data = None
        for attempt in (1, 2):
            try:
                resp = requests.get(_URL, params=params, headers=headers, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                break
            except requests.exceptions.Timeout:
                log.warning("jsearch: timeout on '%s' (attempt %d/2)", query, attempt)
                continue
            except Exception as exc:
                log.warning("jsearch: failed to fetch query '%s' (%s)", query, exc)
                return []
        if data is None:
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
                location=self._location(j),
                description=(j.get("job_description", "") or "")[:4000],
                remote=bool(j.get("job_is_remote")),
                workplace=self._workplace(j),
                comp=self._extract_salary(j),
                posted_at=j.get("job_posted_publish_date", ""),
                external_id=j.get("job_id", ""),
                publisher=self._publisher(j),
                raw=j,
            ))
        return jobs

    def _publisher(self, job: dict[str, Any]) -> str:
        """Which board this came from. Prefer a Tier-1 board (LinkedIn/Indeed/
        ZipRecruiter) if the job is mirrored to one via apply_options, else fall
        back to the primary job_publisher."""
        primary = job.get("job_publisher", "") or ""
        options = job.get("apply_options") or []
        for opt in options:
            pub = (opt.get("publisher", "") or "")
            if any(t in pub.lower() for t in _TIER1_PUBLISHERS):
                return pub
        return primary

    def _location(self, job: dict[str, Any]) -> str:
        """Build a readable location from JSearch's structured fields."""
        parts = [job.get("job_city"), job.get("job_state"), job.get("job_country")]
        loc = ", ".join(p for p in parts if p)
        if loc:
            return loc
        return job.get("job_location", "") or ""

    def _workplace(self, job: dict[str, Any]) -> str:
        """Use JSearch's structured remote flag; fall back to '' (unknown) so
        the pipeline's location heuristics decide rather than the query keyword."""
        if job.get("job_is_remote"):
            return "remote"
        return ""

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
