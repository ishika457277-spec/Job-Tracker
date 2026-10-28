"""RSS/Atom feeds and a selector-free scraper for plain careers pages."""
from __future__ import annotations

import re
from urllib.parse import urljoin

import feedparser
from bs4 import BeautifulSoup

from ..http import fetch
from ..models import Job
from ..text import strip_html

_NAV_WORDS = re.compile(
    r"^(home|about|contact|donate|privacy|terms|cookies?|login|sign ?in|subscribe|newsletter|"
    r"read more|learn more|apply( now)?|menu|search|skip to content|careers?|jobs?|"
    r"work with us|open positions|all (jobs|positions))$",
    re.I,
)


def rss(cfg: dict) -> list[Job]:
    r = fetch(cfg["url"])
    feed = feedparser.parse(r.content)
    jobs = []
    for e in feed.entries:
        title, company = e.get("title", ""), cfg.get("company", "")
        if cfg.get("title_has_company") and ":" in title:  # "Company: Role" style feeds
            company, title = (p.strip() for p in title.split(":", 1))
        jobs.append(
            Job(
                title=title,
                company=company or feed.feed.get("title", ""),
                url=e.get("link", ""),
                source=cfg["name"],
                location=e.get("region", "") or cfg.get("default_location", ""),
                description=strip_html(e.get("summary") or e.get("description")),
                posted=e.get("published", "") or e.get("updated", ""),
            )
        )
    return jobs


def page(cfg: dict) -> list[Job]:
    """Collect every plausible job link on a careers page.

    No per-site selectors: we keep anchors whose text looks like a role title and
    let the title filter downstream decide what is relevant. Pages that render
    their listings with JavaScript will return 0 links; `doctor` flags those.
    Optional cfg keys: href_contains (substring that job links share).
    """
    r = fetch(cfg["url"])
    soup = BeautifulSoup(r.text, "html.parser")
    needle = cfg.get("href_contains")
    seen, jobs = set(), []
    for a in soup.find_all("a", href=True):
        text = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        href = urljoin(cfg["url"], a["href"])
        if not (8 <= len(text) <= 140) or _NAV_WORDS.match(text):
            continue
        if needle and needle not in href:
            continue
        if href.startswith(("mailto:", "tel:", "javascript:")) or href in seen:
            continue
        seen.add(href)
        jobs.append(
            Job(
                title=text,
                company=cfg.get("company", cfg["name"]),
                url=href,
                source=cfg["name"],
                location=cfg.get("default_location", ""),
            )
        )
    return jobs
