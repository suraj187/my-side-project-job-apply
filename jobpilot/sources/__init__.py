"""Job sources. Each returns a list[Job]; the pipeline merges + dedupes them."""

from __future__ import annotations

from .greenhouse import GreenhouseSource
from .lever import LeverSource
from .ashby import AshbySource
from .remotive import RemotiveSource
from .adzuna import AdzunaSource

__all__ = [
    "GreenhouseSource",
    "LeverSource",
    "AshbySource",
    "RemotiveSource",
    "AdzunaSource",
    "build_sources",
]


def build_sources(settings):
    """Instantiate every configured source from settings."""
    sources = []
    c = settings.companies
    for slug in c.greenhouse:
        sources.append(GreenhouseSource(slug))
    for slug in c.lever:
        sources.append(LeverSource(slug))
    for slug in c.ashby:
        sources.append(AshbySource(slug))
    if settings.criteria.remotive_queries:
        sources.append(RemotiveSource(settings.criteria.remotive_queries))
    if settings.adzuna_app_id and settings.adzuna_app_key:
        sources.append(AdzunaSource(
            settings.adzuna_app_id,
            settings.adzuna_app_key,
            settings.criteria.adzuna_queries,
        ))
    return sources
