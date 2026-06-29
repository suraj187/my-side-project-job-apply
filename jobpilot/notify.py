"""Notification delivery: desktop ping + rich HTML email digest."""

from __future__ import annotations

import html
import logging
import os
import re
import smtplib
import subprocess
import sys
from datetime import datetime, timezone
from email.message import EmailMessage

log = logging.getLogger("jobpilot.notify")

_EMDASH = "—"  # kept as a constant so f-strings stay py3.11-compatible


def desktop(title: str, body: str) -> bool:
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


def _fmt_posted(posted_at: str) -> str:
    if not posted_at:
        return "not listed"
    s = posted_at.strip().replace("Z", "+00:00")
    dt = None
    for cand in (s, s[:19], s[:10]):
        try:
            dt = datetime.fromisoformat(cand)
            break
        except Exception:
            continue
    if dt is None:
        return posted_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - dt).days
    when = dt.strftime("%B %d, %Y")
    rel = "today" if days <= 0 else ("yesterday" if days == 1 else f"{days} days ago")
    return f"{when} ({rel})"


def _humanize_reason(reason: str) -> str:
    parts = []
    if "title" in reason and ("\u2208" in reason or "in[" in reason):
        parts.append("strong title match")
    m = re.search(r"kw\D*(\d+)", reason)
    if m:
        parts.append(f"{m.group(1)} skills matched")
    if "remote" in reason:
        parts.append("remote")
    elif "hybrid" in reason:
        parts.append("hybrid")
    if "comp" in reason:
        parts.append("salary listed")
    return ", ".join(parts) or (reason or "match")


def _snippet(description: str, n: int = 500) -> str:
    d = " ".join((description or "").split())
    return d[:n] + ("\u2026" if len(d) > n else "")


def _score_color(score: int) -> str:
    if score >= 75:
        return "#1a7f37"
    if score >= 55:
        return "#9a6700"
    return "#57606a"


# Boards that lead the digest (Tier 1). Kept here as a display concern so the
# weekly digest (which loads jobs from the DB) tiers identically to a live run.
_TIER1_PUBLISHERS = ("linkedin", "indeed", "ziprecruiter")
_TIER_LABELS = {
    1: "Tier 1 · LinkedIn / Indeed / ZipRecruiter",
    2: "Tier 2 · Other job boards",
}


def _tier_of(job) -> int:
    pub = (getattr(job, "publisher", "") or "").lower()
    return 1 if any(t in pub for t in _TIER1_PUBLISHERS) else 2


def _group_by_tier(jobs):
    """Return [(tier, [jobs])] with Tier 1 first, jobs already score-sorted."""
    buckets: dict[int, list] = {1: [], 2: []}
    for j in jobs:
        buckets[_tier_of(j)].append(j)
    return [(t, buckets[t]) for t in (1, 2) if buckets[t]]


def _flag_badges_html(flags) -> str:
    if not flags:
        return ""
    spans = "".join(
        '<span style="display:inline-block;background:#fff8c5;color:#7d4e00;'
        'border:1px solid #eac54f;border-radius:20px;padding:1px 8px;'
        f'font-size:11px;font-weight:600;margin-right:6px;">⚑ {html.escape(f)}</span>'
        for f in flags
    )
    return f'<div style="margin-top:8px;">{spans}</div>'


def _timeframe(dt) -> str:
    """e.g. 'Jun 22, 2026 (Morning)' — date plus which daily run slot."""
    h = dt.hour
    slot = "Morning" if h < 12 else ("Afternoon" if h < 17 else "Evening")
    return f"{dt.strftime('%b %d, %Y')} ({slot})"


def _link_html(statuses, url) -> str:
    if statuses is None:
        return ""
    ok, note = statuses.get(url, (False, "unverified"))
    if ok:
        return ('<div style="color:#1a7f37;font-size:12px;margin-top:4px;">'
                '✓ Link verified</div>')
    return ('<div style="color:#9a6700;font-size:12px;margin-top:4px;">'
            f'⚠ Link unverified ({html.escape(note)}) — may be expired</div>')


def _job_card_html(j, statuses) -> str:
    color = _score_color(j.score)
    comp_html = (f'<div style="color:#1a7f37;font-size:13px;font-weight:600;margin-top:6px;">\U0001f4b0 {html.escape(j.comp)}</div>'
                 if j.comp else '')
    board = (getattr(j, "publisher", "") or j.source or "").strip()
    board_html = f' &nbsp;\u00b7&nbsp; \U0001f4e2 {html.escape(board)}' if board else ''
    return (
        '<div style="border:1px solid #d0d7de;border-radius:10px;padding:14px 16px;margin:0 0 14px;">'
        '<table style="width:100%;border-collapse:collapse;"><tr>'
        f'<td style="vertical-align:top;padding:0;"><a href="{html.escape(j.url)}" style="font-size:16px;font-weight:600;color:#0969da;text-decoration:none;">{html.escape(j.title)}</a>'
        f'<div style="color:#57606a;font-size:13px;margin-top:4px;">{html.escape(j.company or _EMDASH)} \u00b7 {html.escape(j.location or "Location n/a")} \u00b7 {html.escape(j.workplace or "workplace n/a")}</div></td>'
        f'<td style="vertical-align:top;text-align:right;padding:0;white-space:nowrap;"><span style="display:inline-block;background:{color};color:#ffffff;border-radius:20px;padding:3px 11px;font-size:13px;font-weight:700;">{j.score}</span></td>'
        '</tr></table>'
        f'{_flag_badges_html(j.flags)}'
        f'{comp_html}'
        f'<div style="color:#57606a;font-size:13px;margin-top:6px;">\U0001f552 Posted: {html.escape(_fmt_posted(j.posted_at))}</div>'
        f'<div style="color:#57606a;font-size:13px;margin-top:2px;">\U0001f4cb {html.escape(j.source)}{board_html} &nbsp;\u00b7&nbsp; \u2705 {html.escape(_humanize_reason(j.reason))}</div>'
        f'{_link_html(statuses, j.url)}'
        f'<div style="font-size:13px;line-height:1.55;margin-top:10px;">{html.escape(_snippet(j.description, 500))}</div>'
        f'<div style="margin-top:12px;"><a href="{html.escape(j.url)}" style="display:inline-block;background:#1f883d;color:#ffffff;text-decoration:none;padding:8px 16px;border-radius:6px;font-size:13px;font-weight:600;">Apply / View posting \u2192</a></div>'
        '</div>'
    )


def _html(jobs, run_dt, statuses=None) -> str:
    n = len(jobs)
    parts = [
        '<div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:680px;margin:0 auto;padding:8px;color:#1f2328;">',
        f'<h1 style="font-size:20px;margin:0 0 2px;">JobPilot \u2014 {n} SailPoint IAM role{"s" if n != 1 else ""}</h1>',
        f'<p style="color:#57606a;font-size:13px;margin:0 0 18px;">Run: {run_dt.strftime("%A, %B %d, %Y \u00b7 %I:%M %p")}</p>',
    ]
    for tier, group in _group_by_tier(jobs):
        parts.append(
            f'<h2 style="font-size:14px;color:#1f2328;border-bottom:2px solid #d0d7de;'
            f'padding-bottom:4px;margin:22px 0 14px;">{html.escape(_TIER_LABELS[tier])} '
            f'<span style="color:#57606a;font-weight:400;">({len(group)})</span></h2>'
        )
        for j in group:
            parts.append(_job_card_html(j, statuses))
    parts.append('</div>')
    return "".join(parts)


def _text(jobs, run_dt, statuses=None) -> str:
    lines = [f"JobPilot \u2014 {len(jobs)} SailPoint IAM roles",
             run_dt.strftime("Run: %A, %B %d, %Y \u00b7 %I:%M %p"), ""]
    for tier, group in _group_by_tier(jobs):
        lines.append(f"== {_TIER_LABELS[tier]} ({len(group)}) ==")
        lines.append("")
        for j in group:
            flag_str = f"  [{', '.join(j.flags)}]" if j.flags else ""
            lines.append(f"[{j.score}] {j.title} \u2014 {j.company}{flag_str}")
            board = (getattr(j, "publisher", "") or j.source or "")
            lines.append(f"  {j.location or 'Location n/a'} \u00b7 {j.workplace or 'workplace n/a'} \u00b7 {board}")
            if j.comp:
                lines.append(f"  Salary: {j.comp}")
            lines.append(f"  Posted: {_fmt_posted(j.posted_at)}")
            lines.append(f"  Source: {j.source} \u00b7 Why: {_humanize_reason(j.reason)}")
            if statuses is not None:
                ok, note = statuses.get(j.url, (False, "unverified"))
                lines.append(f"  Link: {'verified' if ok else f'unverified ({note}) - may be expired'}")
            snip = _snippet(j.description, 300)
            if snip:
                lines.append(f"  {snip}")
            lines.append(f"  Apply: {j.url}")
            lines.append("")
    return "\n".join(lines)


def send_email(subject: str, text_body: str, html_body: str | None = None) -> bool:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = re.sub(r"\s", "", os.environ.get("SMTP_PASS", ""))
    to_addr = os.environ.get("NOTIFY_EMAIL", user or "")

    if not (host and user and password and to_addr):
        log.info("email not configured (SMTP_* env vars); skipping email")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        log.info("emailed digest to %s", to_addr)
        return True
    except Exception as exc:
        log.warning("email send failed (%s)", exc)
        return False


def notify_run(result, *, want_desktop: bool = True, want_email: bool = True,
               want_validate: bool = True) -> list[str]:
    jobs = result.new_jobs
    n = len(jobs)
    run_dt = datetime.now()
    subject = f"JobPilot - {n} Jobs to apply \u00b7 {_timeframe(run_dt)}"
    summary = (f"Top: [{jobs[0].score}] {jobs[0].title} \u2014 {jobs[0].company}"
               if jobs else "Ran OK \u2014 no new matches this run.")

    fired: list[str] = []
    if want_desktop and desktop(subject, summary):
        fired.append("desktop")
    if want_email and n > 0:
        statuses = None
        if want_validate:
            try:
                from .linkcheck import check_links
                statuses = check_links([j.url for j in jobs])
            except Exception as exc:
                log.warning("link validation skipped (%s)", exc)
        if send_email(subject, _text(jobs, run_dt, statuses),
                      _html(jobs, run_dt, statuses)):
            fired.append("email")
    return fired


def notify_weekly(jobs: list, *, want_email: bool = True) -> list[str]:
    """Send weekly digest email showing all jobs with their current status."""
    n = len(jobs)
    run_dt = datetime.now()
    subject = f"JobPilot — Weekly Summary · {_timeframe(run_dt)}"
    summary = (f"This week: {n} matching role(s)" if n > 0
              else "No new matches this week.")

    fired: list[str] = []
    if want_email and n > 0:
        statuses = None
        # Note: weekly digest doesn't do link validation (runs only once/week)
        if send_email(subject, _text(jobs, run_dt, statuses),
                      _html(jobs, run_dt, statuses)):
            fired.append("email")
    return fired
