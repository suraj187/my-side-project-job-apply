"""Normalized job model shared across all sources."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from urllib.parse import urlsplit


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


@dataclass
class Job:
    """A single posting, normalized into one shape regardless of source."""

    source: str                      # "greenhouse", "adzuna", ...
    title: str
    company: str
    url: str
    location: str = ""
    description: str = ""
    remote: Optional[bool] = None    # None = unknown
    workplace: str = ""              # "remote" | "hybrid" | "onsite" | ""
    comp: str = ""                   # free-text comp if the source provides it
    posted_at: str = ""              # ISO-ish string if available
    external_id: str = ""
    publisher: str = ""              # board it came from: "LinkedIn", "Indeed", ...
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    # Filled in later by the pipeline:
    score: int = 0
    reason: str = ""
    flags: list[str] = field(default_factory=list)
    tier: int = 2                    # 1 = LinkedIn/Indeed/ZipRecruiter, 2 = other

    @property
    def dedup_key(self) -> str:
        """Stable key so the same role from two sources collapses to one row."""
        host_path = ""
        try:
            parts = urlsplit(self.url)
            host_path = (parts.netloc + parts.path).rstrip("/").lower()
        except Exception:
            host_path = (self.url or "").lower()
        basis = f"{_slug(self.title)}|{_slug(self.company)}|{host_path}"
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()

    def to_row(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("raw", None)
        d["flags"] = ",".join(self.flags)
        d["remote"] = None if self.remote is None else int(self.remote)
        d["dedup_key"] = self.dedup_key
        return d
