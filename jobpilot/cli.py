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


def _cmd_list(args) -> None:
    db = DB(args.db)
    try:
        for row in db.recent(status=args.status, limit=args.limit):
            print(f"[{row['score']:3d}] {row['title']} — {row['company']} "
                  f"({row['status']})  {row['url']}")
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
    pr.set_defaults(func=_cmd_run)

    pl = sub.add_parser("list", help="list stored jobs")
    pl.add_argument("--status", default=None)
    pl.add_argument("--limit", type=int, default=50)
    pl.set_defaults(func=_cmd_list)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
