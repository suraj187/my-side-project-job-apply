"""Heuristics for remote / US detection and hard filtering."""

from __future__ import annotations

import re

from .models import Job

# US states + common US location markers.
_US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
    "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "ohio", "oklahoma", "oregon",
    "pennsylvania", "tennessee", "texas", "utah", "vermont", "virginia",
    "washington", "wisconsin", "wyoming",
}
_US_STATE_ABBR = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id",
    "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms",
    "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
    "wi", "wy", "dc",
}
_US_MARKERS = ("united states", "usa", "u.s.", "u.s", "us only", "us-based",
               "us based", "remote us", "remote, us", "anywhere in the us")
_GLOBAL_MARKERS = ("worldwide", "anywhere", "global", "remote - global")
_REMOTE_MARKERS = ("remote", "work from home", "wfh", "distributed")
_HYBRID_MARKERS = ("hybrid",)


def _norm(text: str) -> str:
    return (text or "").lower()


def detect_workplace(job: Job) -> str:
    """Return 'remote' | 'hybrid' | 'onsite' | '' best-effort."""
    if job.workplace in ("remote", "hybrid", "onsite"):
        return job.workplace
    blob = " ".join([_norm(job.location), _norm(job.title), _norm(job.description[:600])])
    if any(m in blob for m in _HYBRID_MARKERS):
        return "hybrid"
    if any(m in blob for m in _REMOTE_MARKERS):
        return "remote"
    return ""


def is_sailpoint(job: Job, markers) -> bool:
    """True if the role's primary tool is SailPoint (IIQ or ISC).

    Title may say "IAM Engineer/Developer" — what matters is that a SailPoint
    product marker appears in the title or description.
    """
    blob = " ".join([_norm(job.title), _norm(job.description)])
    return any(m and m.lower() in blob for m in markers)


def detect_staffing(job: Job, firm_keywords, signals) -> tuple[bool, str]:
    """Detect staffing/consulting body-shops by firm name or staffing language.

    Returns (is_staffing, why). Used to flag + demote (not drop) per user choice.
    """
    company = _norm(job.company)
    for firm in firm_keywords or []:
        if firm and firm.lower() in company:
            return True, f"firm: {firm}"
    blob = " ".join([_norm(job.title), _norm(job.description[:1500])])
    for sig in signals or []:
        if sig and sig.lower() in blob:
            return True, f"signal: {sig}"
    return False, ""


def is_us(job: Job) -> bool:
    """True if the posting looks US-eligible (incl. worldwide-remote)."""
    loc = _norm(job.location)
    blob = " ".join([loc, _norm(job.description[:600])])
    if any(m in blob for m in _US_MARKERS):
        return True
    if any(m in blob for m in _GLOBAL_MARKERS):
        return True  # worldwide remote includes the US
    # A bare "us"/"usa" token in the *location* field (e.g. "Remote - US", "US")
    # almost always means United States. Aggregators (JSearch) often report
    # remote US roles this way, so don't drop them as "not US-eligible".
    if set(re.split(r"[^a-z]+", loc)) & {"us", "usa"}:
        return True
    tokens = set(re.split(r"[^a-z]+", blob))
    if tokens & _US_STATES:
        return True
    # Abbreviations are noisy; only trust them next to a comma/paren or "remote".
    if re.search(r"\b(" + "|".join(_US_STATE_ABBR) + r")\b", loc):
        return True
    return False


def passes_hard_filters(job: Job, criteria) -> tuple[bool, str]:
    """Apply true dealbreakers (drop). Returns (kept, reason_if_dropped).

    Remote and staffing are NOT dealbreakers anymore — they're flagged + demoted
    in rank.py so the user still sees them. The hard drops here are:
      - not SailPoint-related (the primary tool must be SailPoint), if enabled
      - not US-eligible (work authorization), if us_only
      - dealbreaker keywords / explicitly excluded companies
    """
    # Resolve workplace early so rank.py can flag remote-unconfirmed jobs.
    job.workplace = detect_workplace(job) or job.workplace

    if getattr(criteria, "require_sailpoint", False):
        markers = getattr(criteria, "sailpoint_markers", []) or []
        if markers and not is_sailpoint(job, markers):
            return False, "not SailPoint"

    if criteria.us_only and not is_us(job):
        return False, "not US-eligible"

    blob = " ".join([_norm(job.title), _norm(job.company), _norm(job.description[:1200])])
    for word in criteria.dealbreaker_keywords:
        if word and word.lower() in blob:
            return False, f"dealbreaker: {word}"

    if criteria.exclude_companies:
        if _norm(job.company) in {c.lower() for c in criteria.exclude_companies}:
            return False, "excluded company"

    return True, ""
