"""Hard rules first. Cheap, deterministic, and keeps the LLM step small."""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from .models import Job
from .text import parse_date

REMOTE_WORDS = ("remote", "anywhere", "worldwide", "global", "work from home", "distributed")


def _match(text: str, term: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])", text) is not None


def _hits(text: str, terms: list[str]) -> list[str]:
    low = (text or "").lower()
    return [t for t in terms or [] if _match(low, t)]


def evaluate(job: Job, cfg: dict, now: datetime, drops: Counter | None = None) -> Job | None:
    """Return the job (score and reasons filled in) or None if it fails a hard rule.

    On-topic means ONE of:
      1. a domain word in the title (include_title_any), or
      2. a generic role word in the title (generic_title_any, e.g. research, intern)
         plus a domain word in the text, or no text at all (title-only careers pages), or
      3. at least min_text_hits domain phrases in the text (include_text_any).
    """

    def drop(reason: str) -> None:
        if drops is not None:
            drops[reason] += 1
        return None

    blob = f"{job.title} {job.description}"
    reasons: list[str] = []

    if _hits(job.title, cfg.get("exclude_title_any")):
        return drop("senior or excluded title")
    if _hits(blob, cfg.get("exclude_text_any")):
        return drop("excluded text (years, PhD, citizenship)")

    title_hits = _hits(job.title, cfg.get("include_title_any"))
    generic_hits = _hits(job.title, cfg.get("generic_title_any"))
    text_hits = _hits(blob, cfg.get("include_text_any"))
    generic_ok = bool(generic_hits) and (
        len(text_hits) >= int(cfg.get("generic_min_text_hits", 1)) or not job.description
    )
    if not (title_hits or generic_ok or len(text_hits) >= int(cfg.get("min_text_hits", 3))):
        return drop("not on topic")

    # Age
    posted = parse_date(job.posted)
    max_age = cfg.get("max_age_days")
    if posted and max_age and now - posted > timedelta(days=int(max_age)):
        return drop("too old")

    # Location
    loc = (job.location or "").lower()
    targets = _hits(loc, cfg.get("locations_any"))
    remote_like = job.remote is True or any(w in loc for w in REMOTE_WORDS)
    score = 3.0 * min(len(title_hits), 2) + min(len(generic_hits), 1) + min(len(text_hits), 4)

    if targets:
        score += 2
        reasons.append(f"location: {targets[0]}")
    elif remote_like and cfg.get("allow_remote", True):
        if any(p in loc for p in cfg.get("remote_exclude_any", [])):
            return drop("remote but region-restricted")
        score += 1
        reasons.append("remote")
    elif not loc:
        if cfg.get("unknown_location", "keep") != "keep":
            return drop("location unknown")
        reasons.append("location unspecified")
    else:
        return drop("wrong location")

    shown = title_hits or generic_hits
    if shown:
        reasons.append("title: " + ", ".join(shown[:2]))
    job.score = score
    job.reasons = reasons
    return job


def apply_filters(
    jobs: list[Job], cfg: dict, now: datetime | None = None, drops: Counter | None = None
) -> list[Job]:
    now = now or datetime.now(timezone.utc)
    return [j for j in (evaluate(job, cfg, now, drops) for job in jobs) if j is not None]


def dedupe(jobs: list[Job]) -> list[Job]:
    """Drop repeats by URL and by company+title, keeping the best-scored copy."""
    seen_uid, seen_fuzzy, out = set(), set(), []
    for job in sorted(jobs, key=lambda j: -j.score):
        if job.uid in seen_uid or job.fuzzy in seen_fuzzy:
            continue
        seen_uid.add(job.uid)
        seen_fuzzy.add(job.fuzzy)
        out.append(job)
    return out
