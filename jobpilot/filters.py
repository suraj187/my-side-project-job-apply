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


def is_us(job: Job) -> bool:
    """True if the posting looks US-eligible (incl. worldwide-remote)."""
    blob = " ".join([_norm(job.location), _norm(job.description[:600])])
    if any(m in blob for m in _US_MARKERS):
        return True
    if any(m in blob for m in _GLOBAL_MARKERS):
        return True  # worldwide remote includes the US
    tokens = set(re.split(r"[^a-z]+", blob))
    if tokens & _US_STATES:
        return True
    # Abbreviations are noisy; only trust them next to a comma/paren or "remote".
    if re.search(r"\b(" + "|".join(_US_STATE_ABBR) + r")\b", _norm(job.location)):
        return True
    return False


def passes_hard_filters(job: Job, criteria) -> tuple[bool, str]:
    """Apply dealbreakers. Returns (kept, reason_if_dropped)."""
    wp = detect_workplace(job)
    job.workplace = wp or job.workplace

    if criteria.remote_only and wp == "onsite":
        return False, "onsite (remote_only)"
    if criteria.remote_only and wp == "hybrid" and not criteria.allow_hybrid:
        return False, "hybrid (remote_only, hybrid off)"
    if criteria.us_only and not is_us(job):
        return False, "not US-eligible"

    blob = " ".join([_norm(job.title), _norm(job.company), _norm(job.description[:1200])])
    for word in criteria.dealbreaker_keywords:
        if word and word.lower() in blob:
            return False, f"dealbreaker: {word}"

    if criteria.exclude_companies:
        if _norm(job.company) in {c.lower() for c in criteria.exclude_companies}:
            return False, "excluded company"

    if criteria.consulting_firm_keywords:
        for firm in criteria.consulting_firm_keywords:
            if firm and firm.lower() in blob:
                return False, f"consulting firm: {firm}"

    return True, ""
