"""Best-effort link validation: confirm apply URLs resolve to real content.

Used by the email digest to flag links that look dead or empty so you don't
click through to an expired posting. Never raises — failures are reported as
"unverified" rather than dropping the job, because some sites block automated
requests (a 403 doesn't always mean the posting is gone).
"""

from __future__ import annotations

import concurrent.futures
import logging

import requests

log = logging.getLogger("jobpilot.linkcheck")

_TIMEOUT = 12
_MIN_BYTES = 1500  # pages smaller than this are treated as empty/placeholder
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
_DEAD_MARKERS = (
    "no longer available", "job not found", "position has been filled",
    "this job has expired", "posting is closed", "404 not found",
    "page not found", "no longer accepting applications",
)


def check_url(url: str) -> tuple[bool, str]:
    """Return (ok, note). ok=True means the link resolved to real content."""
    if not url:
        return False, "no link"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT,
                            allow_redirects=True)
    except Exception:
        return False, "unreachable"
    if resp.status_code >= 400:
        return False, f"HTTP {resp.status_code}"
    body = resp.text or ""
    if len(body) < _MIN_BYTES:
        return False, "page looks empty"
    low = body.lower()
    for marker in _DEAD_MARKERS:
        if marker in low:
            return False, "posting expired"
    return True, "ok"


def check_links(urls: list[str], max_workers: int = 8) -> dict[str, tuple[bool, str]]:
    """Validate many URLs concurrently. Returns {url: (ok, note)}."""
    result: dict[str, tuple[bool, str]] = {}
    uniq = [u for u in dict.fromkeys(urls) if u]
    if not uniq:
        return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(check_url, u): u for u in uniq}
        for fut in concurrent.futures.as_completed(futs):
            u = futs[fut]
            try:
                result[u] = fut.result()
            except Exception:
                result[u] = (False, "check failed")
    return result
