"""Lever public postings API (company application pages). No key needed.

Endpoint: https://api.lever.co/v0/postings/{slug}?mode=json
"""

from __future__ import annotations

from ..models import Job
from .base import Source

_URL = "https://api.lever.co/v0/postings/{slug}"

_WORKPLACE = {"remote": "remote", "on-site": "onsite", "onsite": "onsite", "hybrid": "hybrid"}


class LeverSource(Source):
    name = "lever"

    def __init__(self, slug: str):
        self.slug = slug

    def fetch(self) -> list[Job]:
        data = self._get_json(_URL.format(slug=self.slug), {"mode": "json"})
        if not isinstance(data, list):
            return []
        jobs = []
        for j in data:
            cats = j.get("categories") or {}
            wp = _WORKPLACE.get(str(j.get("workplaceType", "")).lower(), "")
            jobs.append(Job(
                source=self.name,
                title=j.get("text", ""),
                company=self.slug,
                url=j.get("hostedUrl", "") or j.get("applyUrl", ""),
                location=cats.get("location", ""),
                description=(j.get("descriptionPlain") or j.get("description") or "")[:4000],
                workplace=wp,
                posted_at=str(j.get("createdAt", "")),
                external_id=str(j.get("id", "")),
                raw=j,
            ))
        return jobs
