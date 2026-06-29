"""Scoring. Free rule-based ranker by default; optional Claude Haiku refinement.

The rule-based ranker is intentionally simple and transparent so you can tune
it. The LLM path (off by default) only scores the top shortlist to keep cost
low — see config.LLMConfig.
"""

from __future__ import annotations

import logging
import re

from .config import Criteria
from .filters import detect_staffing
from .models import Job

log = logging.getLogger("jobpilot.rank")


def _annotate(job: Job, criteria: Criteria) -> None:
    """Flag + demote quality concerns (never drop). Also assign source tier.

    Tier 1 = LinkedIn / Indeed / ZipRecruiter (publisher in tier1_publishers).
    Tier 2 = everything else. Sort is (tier, -score), so Tier 1 always leads.
    """
    flags = list(job.flags)

    # Remote not confirmed → flag + penalize (user is remote-first).
    if job.workplace not in ("remote", "hybrid") and job.remote is not True:
        flags.append("remote unconfirmed")
        job.score = max(0, job.score - getattr(criteria, "remote_penalty", 15))

    # Staffing / consulting body-shop → flag + penalize.
    is_staffing, why = detect_staffing(
        job,
        criteria.consulting_firm_keywords,
        getattr(criteria, "staffing_signals", []),
    )
    if is_staffing:
        flags.append("staffing")
        job.score = max(0, job.score - getattr(criteria, "staffing_penalty", 20))
        log.debug("staffing flag for %s @ %s (%s)", job.title, job.company, why)

    job.flags = flags

    tier1 = {p.lower() for p in getattr(criteria, "tier1_publishers", [])}
    pub = (job.publisher or "").lower()
    job.tier = 1 if any(t in pub for t in tier1) else 2


def _tokens(text: str) -> set[str]:
    return set(t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(t) > 1)


def rule_score(job: Job, criteria: Criteria) -> tuple[int, str]:
    """Transparent 0-100 score from title/keyword overlap, remote, comp, recency."""
    title_tokens = _tokens(job.title)
    body_tokens = _tokens(job.description)
    reasons: list[str] = []
    score = 0

    # Title match against target titles (strongest signal).
    title_hits = [t for t in criteria.titles if _tokens(t) & title_tokens]
    if title_hits:
        score += min(45, 15 * len(title_hits))
        reasons.append(f"title∈{title_hits[:2]}")

    # Keyword presence in body.
    kw_hits = [k for k in criteria.keywords if k.lower() in (job.description or "").lower()]
    if kw_hits:
        score += min(30, 6 * len(kw_hits))
        reasons.append(f"kw×{len(kw_hits)}")

    # Remote bonus.
    if job.workplace == "remote" or job.remote is True:
        score += 15
        reasons.append("remote")
    elif job.workplace == "hybrid":
        score += 5
        reasons.append("hybrid")

    # Comp disclosed is a small positive signal.
    if job.comp:
        score += 5
        reasons.append("comp")

    score = max(0, min(100, score))
    return score, ", ".join(reasons) or "weak match"


def llm_score(jobs: list[Job], criteria: Criteria) -> None:
    """Refine the top shortlist with Claude Haiku. Mutates jobs in place.

    No-ops (leaving rule scores intact) if the SDK/key is unavailable, so the
    pipeline always runs free out of the box.
    """
    try:
        import anthropic  # noqa: F401
    except Exception:
        log.warning("anthropic SDK not installed; skipping LLM scoring")
        return

    import json
    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log.warning("ANTHROPIC_API_KEY not set; skipping LLM scoring")
        return

    from anthropic import Anthropic
    client = Anthropic()

    profile = (
        f"Target titles: {', '.join(criteria.titles)}\n"
        f"Must-have keywords: {', '.join(criteria.keywords)}\n"
        f"Remote-only: {criteria.remote_only}; US-only: {criteria.us_only}"
    )
    schema = {
        "type": "object",
        "properties": {
            "score": {"type": "integer"},
            "reason": {"type": "string"},
            "flags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["score", "reason", "flags"],
        "additionalProperties": False,
    }

    for job in jobs[: criteria.llm.shortlist_size]:
        prompt = (
            f"My job-search profile:\n{profile}\n\n"
            f"Posting:\nTitle: {job.title}\nCompany: {job.company}\n"
            f"Location: {job.location}\nComp: {job.comp}\n"
            f"Description (truncated): {job.description[:1500]}\n\n"
            "Score 0-100 how well this fits my profile. Give a one-line reason "
            "and any red-flag flags (e.g. wrong-seniority, not-remote, "
            "us-ineligible)."
        )
        try:
            resp = client.messages.create(
                model=criteria.llm.model,
                max_tokens=400,
                output_config={"format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": prompt}],
            )
            text = next(b.text for b in resp.content if b.type == "text")
            data = json.loads(text)
            job.score = int(data.get("score", job.score))
            job.reason = data.get("reason", job.reason)
            job.flags = list(data.get("flags", []))
        except Exception as exc:
            log.warning("LLM scoring failed for %s (%s)", job.title, exc)


def rank(jobs: list[Job], criteria: Criteria) -> list[Job]:
    for job in jobs:
        job.score, job.reason = rule_score(job, criteria)
    # Apply the quality floor on the BASE score, before demotion penalties, so a
    # flagged job (staffing / remote-unconfirmed) is demoted but never dropped by
    # the floor. (require_sailpoint in filters.py is the real gate now.)
    kept = [j for j in jobs if j.score >= criteria.min_score]
    for job in kept:
        _annotate(job, criteria)
    if criteria.llm.enabled:
        kept.sort(key=lambda j: (j.tier, -j.score))
        llm_score(kept, criteria)
    # Tier 1 (LinkedIn/Indeed/ZipRecruiter) first, then by score within each tier.
    kept.sort(key=lambda j: (j.tier, -j.score))
    return kept
