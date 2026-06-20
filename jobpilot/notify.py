"""Notification delivery.

- Desktop ping every run (so you know the cron fired, even on 0 new jobs).
- Email only when there are new matches (no inbox spam on empty runs).

Email is configured via environment variables; if they're absent, email is
skipped silently and the desktop/console path still runs.

    SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASS, NOTIFY_EMAIL
"""

from __future__ import annotations

import logging
import os
import smtplib
import subprocess
import sys
from email.mime.text import MIMEText

log = logging.getLogger("jobpilot.notify")


def desktop(title: str, body: str) -> bool:
    """Best-effort desktop notification (macOS / Linux). Never raises."""
    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["osascript", "-e",
                 f'display notification {body!r} with title {title!r}'],
                check=False, capture_output=True,
            )
        else:
            subprocess.run(["notify-send", title, body],
                           check=False, capture_output=True)
        return True
    except Exception as exc:
        log.debug("desktop notify unavailable (%s)", exc)
        return False


def email(subject: str, body: str) -> bool:
    """Send the digest by email if SMTP env vars are set; else skip."""
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    to_addr = os.environ.get("NOTIFY_EMAIL", user or "")

    if not (host and user and password and to_addr):
        log.info("email not configured (SMTP_* env vars); skipping email")
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, [to_addr], msg.as_string())
        log.info("emailed digest to %s", to_addr)
        return True
    except Exception as exc:
        log.warning("email send failed (%s)", exc)
        return False


def notify_run(result, *, want_desktop: bool = True, want_email: bool = True) -> list[str]:
    """Notify about a completed run. Returns the channels that fired."""
    n = len(result.new_jobs)
    title = f"JobPilot: {n} new role{'s' if n != 1 else ''}"
    if result.new_jobs:
        top = result.new_jobs[0]
        summary = f"Top: [{top.score}] {top.title} — {top.company}"
    else:
        summary = "Ran OK — no new matches this run."

    fired: list[str] = []
    if want_desktop and desktop(title, summary):
        fired.append("desktop")
    if want_email and n > 0:
        try:
            with open(result.digest_path, encoding="utf-8") as fh:
                body = fh.read()
        except OSError:
            body = summary
        if email(title, body):
            fired.append("email")
    return fired
