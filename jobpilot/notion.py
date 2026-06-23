"""Notion integration: sync jobs to/from Notion database."""

from __future__ import annotations

import logging
from typing import Any

import requests

from .models import Job

log = logging.getLogger("jobpilot.notion")

_NOTION_API_URL = "https://api.notion.com/v1"
_NOTION_VERSION = "2025-09-03"


def sync_jobs_to_notion(
    jobs: list[Job],
    notion_token: str,
    notion_database_id: str,
    job_id_map: dict[str, str] | None = None,
) -> dict[str, str]:
    """Push jobs from SQLite to Notion database.

    Returns mapping of {job.dedup_key: notion_row_id} for new/updated rows.
    job_id_map is dict of {dedup_key: notion_row_id} for existing jobs (to avoid dupes).
    """
    if not notion_token or not notion_database_id:
        log.debug("notion: sync disabled (no credentials)")
        return {}

    if not jobs:
        return {}

    job_id_map = job_id_map or {}
    updated: dict[str, str] = {}

    for job in jobs:
        try:
            # Skip if already synced in this cycle
            if job.dedup_key in job_id_map:
                log.debug(
                    "notion: job already synced (dedup_key=%s)", job.dedup_key
                )
                continue

            # Create page in Notion
            notion_row_id = _create_notion_job(job, notion_token, notion_database_id)
            if notion_row_id:
                updated[job.dedup_key] = notion_row_id
                log.debug("notion: created row %s for %s @ %s",
                         notion_row_id, job.title, job.company)
        except Exception as exc:
            log.warning("notion: failed to sync %s @ %s (%s)",
                       job.title, job.company, exc)

    return updated


def fetch_notion_statuses(
    notion_token: str,
    notion_database_id: str,
    job_id_map: dict[str, str],
) -> dict[str, str]:
    """Fetch job statuses from Notion database.

    Args:
        notion_token: Notion API token
        notion_database_id: Database ID
        job_id_map: {dedup_key: notion_row_id} for jobs to fetch

    Returns: {dedup_key: status_value} (e.g., "Applied", "Rejected", "New")
    """
    if not notion_token or not notion_database_id or not job_id_map:
        return {}

    statuses: dict[str, str] = {}

    for dedup_key, row_id in job_id_map.items():
        try:
            status = _fetch_notion_status(row_id, notion_token)
            if status:
                statuses[dedup_key] = status
        except Exception as exc:
            log.warning("notion: failed to fetch status for row %s (%s)",
                       row_id, exc)

    return statuses


def _create_notion_job(
    job: Job,
    notion_token: str,
    notion_database_id: str,
) -> str | None:
    """Create a page in Notion database for a job. Returns notion_row_id."""
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }

    # Build Additional information text
    additional_info = f"Score {job.score} · {job.source} · posted {job.posted_at or 'unknown'}"
    if job.reason:
        additional_info += f" · {job.reason}"

    payload = {
        "parent": {"database_id": notion_database_id},
        "properties": {
            "Company": {"title": [{"text": {"content": job.company or "Unknown"}}]},
            "Role": {"rich_text": [{"text": {"content": job.title or ""}}]},
            "Link": {"url": job.url or None},
            "Status": {"select": {"name": "New"}},
            "Additional information": {
                "rich_text": [{"text": {"content": additional_info}}]
            },
        },
    }

    try:
        resp = requests.post(
            f"{_NOTION_API_URL}/pages",
            json=payload,
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("id", "")
    except Exception as exc:
        log.warning("notion: POST /pages failed (%s)", exc)
        return None


def _fetch_notion_status(row_id: str, notion_token: str) -> str | None:
    """Fetch the Status property of a Notion page."""
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": _NOTION_VERSION,
    }

    try:
        resp = requests.get(
            f"{_NOTION_API_URL}/pages/{row_id}",
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        props = data.get("properties", {})
        status = props.get("Status", {})
        select = status.get("select")
        if select:
            return select.get("name")
    except Exception as exc:
        log.warning("notion: GET /pages/%s failed (%s)", row_id, exc)

    return None
