"""Load user criteria and the company watchlist from YAML."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class LLMConfig:
    enabled: bool = False
    model: str = "claude-haiku-4-5"
    shortlist_size: int = 25       # only this many top jobs hit the API per run


@dataclass
class Criteria:
    titles: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    dealbreaker_keywords: list[str] = field(default_factory=list)
    exclude_companies: list[str] = field(default_factory=list)
    remote_only: bool = True
    allow_hybrid: bool = False
    us_only: bool = True
    min_score: int = 40            # don't surface anything below this
    adzuna_queries: list[str] = field(default_factory=list)
    remotive_queries: list[str] = field(default_factory=list)
    jsearch_queries: list[str] = field(default_factory=list)
    consulting_firm_keywords: list[str] = field(default_factory=list)
    llm: LLMConfig = field(default_factory=LLMConfig)


@dataclass
class Companies:
    greenhouse: list[str] = field(default_factory=list)
    lever: list[str] = field(default_factory=list)
    ashby: list[str] = field(default_factory=list)


@dataclass
class Settings:
    criteria: Criteria
    companies: Companies
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    rapidapi_key: str = ""
    rapidapi_host: str = "jsearch.p.rapidapi.com"


def _load_yaml(path: str) -> dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_settings(criteria_path: str, companies_path: str) -> Settings:
    craw = _load_yaml(criteria_path)
    llm = LLMConfig(**{**LLMConfig().__dict__, **(craw.pop("llm", {}) or {})})
    criteria = Criteria(**{**Criteria().__dict__, **craw})
    criteria.llm = llm

    companies = Companies(**(_load_yaml(companies_path) or {}))

    return Settings(
        criteria=criteria,
        companies=companies,
        adzuna_app_id=os.environ.get("ADZUNA_APP_ID", ""),
        adzuna_app_key=os.environ.get("ADZUNA_APP_KEY", ""),
        rapidapi_key=os.environ.get("RAPIDAPI_KEY", ""),
    )
