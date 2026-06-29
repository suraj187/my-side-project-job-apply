"""Command-line entry point.

  python -m jobpilot.cli run --dry-run       # offline smoke test
  python -m jobpilot.cli run                  # real fetch (needs config)
  python -m jobpilot.cli list --status new    # show stored matches
"""

from __future__ import annotations

import argparse
import logging
import os

from .config import load_settings
from .db import DB
from .pipeline import run

_DEFAULT_CRITERIA = "config/criteria.yaml"
_DEFAULT_COMPANIES = "config/companies.yaml"
_DEFAULT_DB = "jobpilot.db"


def _cmd_run(args) -> None:
    settings = load_settings(args.criteria, args.companies)
    result = run(settings, args.db, digest_dir=args.digest_dir, dry_run=args.dry_run)
    print(f"Fetched {result.fetched} · kept {result.after_filter} · "
          f"NEW {len(result.new_jobs)}")
    for j in result.new_jobs[:20]:
        print(f"  [{j.score:3d}] {j.title} — {j.company}  ({j.workplace or '?'})")
    print(f"Digest: {result.digest_path}")
    if args.notify:
        from .notify import notify_run
        fired = notify_run(result)
        print(f"Notified via: {', '.join(fired) or 'none (channels unavailable)'}")


def _cmd_list(args) -> None:
    db = DB(args.db)
    try:
        for row in db.recent(status=args.status, limit=args.limit):
            print(f"[{row['score']:3d}] {row['title']} — {row['company']} "
                  f"({row['status']})  {row['url']}")
    finally:
        db.close()


def _cmd_weekly(args) -> None:
    """Send weekly digest email with all jobs from past 7 days."""
    from datetime import datetime, timedelta, timezone
    from .models import Job
    from .notify import notify_weekly

    db = DB(args.db)
    try:
        # Get all jobs from past 7 days
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        rows = db.conn.execute(
            "SELECT * FROM jobs WHERE first_seen >= ? ORDER BY score DESC",
            (cutoff,)
        ).fetchall()

        jobs = [Job(
            source=row["source"],
            title=row["title"],
            company=row["company"],
            url=row["url"],
            location=row["location"],
            description="",
            remote=bool(dict(row).get("remote", False)),
            workplace=row["workplace"],
            comp=row["comp"],
            posted_at=row["posted_at"],
            external_id=row["external_id"],
            publisher=dict(row).get("publisher", "") or "",
            score=row["score"],
            reason=row["reason"],
            flags=(row["flags"].split(",") if dict(row).get("flags") else []),
        ) for row in rows]

        print(f"Weekly digest: {len(jobs)} jobs from past 7 days")
        fired = notify_weekly(jobs)
        print(f"Notified via: {', '.join(fired) or 'none (channels unavailable)'}")
    finally:
        db.close()


def main(argv=None) -> None:
    logging.basicConfig(level=os.environ.get("JOBPILOT_LOG", "INFO"),
                        format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="jobpilot")
    p.add_argument("--criteria", default=_DEFAULT_CRITERIA)
    p.add_argument("--companies", default=_DEFAULT_COMPANIES)
    p.add_argument("--db", default=_DEFAULT_DB)
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run", help="fetch, rank, and store jobs")
    pr.add_argument("--dry-run", action="store_true", help="use offline fixtures")
    pr.add_argument("--digest-dir", default="digests")
    pr.add_argument("--notify", action="store_true",
                    help="send desktop ping + email (if SMTP_* env vars set)")
    pr.set_defaults(func=_cmd_run)

    pl = sub.add_parser("list", help="list stored jobs")
    pl.add_argument("--status", default=None)
    pl.add_argument("--limit", type=int, default=50)
    pl.set_defaults(func=_cmd_list)

    pw = sub.add_parser("weekly", help="send weekly digest email (past 7 days)")
    pw.set_defaults(func=_cmd_weekly)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
