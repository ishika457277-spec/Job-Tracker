"""Digest building and delivery: Telegram, optional email, and files/job summary."""
from __future__ import annotations

import html
import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from .http import fetch
from .models import Job


def _line(job: Job) -> str:
    rating = f"{job.llm_score:.0f}/10" if job.llm_score is not None else f"rules {job.score:.0f}"
    loc = f" ({job.location[:60]})" if job.location else ""
    why = "; ".join(job.reasons[:3])
    return f"{job.title} - {job.company}{loc}\n[{rating}] {why}\n{job.url}"


def health_footer(stats: list[dict]) -> str:
    bad = [s for s in stats if s["status"] in ("error", "empty")]
    skipped = [s for s in stats if s["status"] == "skipped"]
    ok = sum(1 for s in stats if s["status"] == "ok")
    parts = [f"Sources: {ok}/{len(stats)} returned listings"]
    if bad:
        parts.append("Problems: " + ", ".join(f"{s['name']} ({s['status']})" for s in bad))
    if skipped:
        parts.append("Skipped (no key): " + ", ".join(s["name"] for s in skipped))
    return "\n".join(parts)


def build_digest(jobs: list[Job], stats: list[dict], total_new: int) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    head = f"Job digest {today}: {len(jobs)} shown"
    if total_new > len(jobs):
        head += f" ({total_new - len(jobs)} more held for tomorrow)"
    body = "\n\n".join(_line(j) for j in jobs) if jobs else "No new matching listings today."
    return f"{head}\n\n{body}\n\n{health_footer(stats)}"


def write_files(digest: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "latest_digest.md").write_text(digest)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as fh:
            fh.write("```\n" + digest + "\n```\n")


def _chunks(jobs: list[Job], head: str, foot: str, limit: int = 3800) -> list[str]:
    out, cur = [], head + "\n"
    for job in jobs:
        block = (
            f'\n<a href="{html.escape(job.url, quote=True)}">{html.escape(job.title)}</a> - '
            f"{html.escape(job.company)}"
            + (f" ({html.escape(job.location[:60])})" if job.location else "")
            + f"\n{html.escape('; '.join(job.reasons[:3]))}\n"
        )
        if len(cur) + len(block) > limit:
            out.append(cur)
            cur = ""
        cur += block
    out.append(cur + "\n" + html.escape(foot))
    return out


def telegram(jobs: list[Job], stats: list[dict], total_new: int) -> bool:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    head = f"<b>Job digest: {len(jobs)} new</b>" + (
        f" ({total_new - len(jobs)} held for tomorrow)" if total_new > len(jobs) else ""
    )
    if not jobs:
        head = "<b>No new matching jobs today</b>"
    for msg in _chunks(jobs, head, health_footer(stats)):
        fetch(
            f"https://api.telegram.org/bot{token}/sendMessage",
            method="POST",
            json={
                "chat_id": chat,
                "text": msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )
    return True


def email(digest: str) -> bool:
    user, pw, to = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS"), os.environ.get("EMAIL_TO")
    if not (user and pw and to):
        return False
    msg = EmailMessage()
    msg["Subject"] = digest.splitlines()[0]
    msg["From"], msg["To"] = user, to
    msg.set_content(digest)
    with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtp.gmail.com"), 465) as server:
        server.login(user, pw)
        server.send_message(msg)
    return True
