"""Base class + shared HTTP helper for sources."""

from __future__ import annotations

import logging
from typing import Any

import requests

from ..models import Job

log = logging.getLogger("jobpilot.sources")

_TIMEOUT = 20
_HEADERS = {"User-Agent": "JobPilot/0.1 (personal job finder)"}


class Source:
    name = "base"

    def fetch(self) -> list[Job]:  # pragma: no cover - interface
        raise NotImplementedError

    def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        try:
            resp = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # network/JSON errors shouldn't kill the run
            log.warning("%s: failed to fetch %s (%s)", self.name, url, exc)
            return None
