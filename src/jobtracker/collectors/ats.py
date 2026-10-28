"""Public job-board JSON endpoints used by many companies (no auth needed)."""
from __future__ import annotations

from ..http import fetch
from ..models import Job
from ..text import strip_html


def greenhouse(cfg: dict) -> list[Job]:
    board = cfg["board"]
    data = fetch(
        f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", params={"content": "true"}
    ).json()
    return [
        Job(
            title=j.get("title", ""),
            company=cfg.get("company", board),
            url=j.get("absolute_url", ""),
            source=cfg["name"],
            location=(j.get("location") or {}).get("name", ""),
            description=strip_html(j.get("content")),
            posted=j.get("updated_at", ""),
        )
        for j in data.get("jobs", [])
    ]


def lever(cfg: dict) -> list[Job]:
    board = cfg["board"]
    data = fetch(f"https://api.lever.co/v0/postings/{board}", params={"mode": "json"}).json()
    jobs = []
    for j in data:
        cats = j.get("categories") or {}
        jobs.append(
            Job(
                title=j.get("text", ""),
                company=cfg.get("company", board),
                url=j.get("hostedUrl", ""),
                source=cfg["name"],
                location=cats.get("location", "") or "",
                description=(j.get("descriptionPlain") or strip_html(j.get("description")))[:6000],
                posted=j.get("createdAt", ""),
                remote=True if (j.get("workplaceType") == "remote") else None,
            )
        )
    return jobs


def ashby(cfg: dict) -> list[Job]:
    board = cfg["board"]
    data = fetch(f"https://api.ashbyhq.com/posting-api/job-board/{board}").json()
    jobs = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        jobs.append(
            Job(
                title=j.get("title", ""),
                company=cfg.get("company", board),
                url=j.get("jobUrl", ""),
                source=cfg["name"],
                location=j.get("location", "") or "",
                description=(j.get("descriptionPlain") or strip_html(j.get("descriptionHtml")))[:6000],
                posted=j.get("publishedAt", ""),
                remote=j.get("isRemote"),
            )
        )
    return jobs


def smartrecruiters(cfg: dict) -> list[Job]:
    company_id = cfg["board"]
    data = fetch(
        f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings", params={"limit": 100}
    ).json()
    jobs = []
    for j in data.get("content", []):
        loc = j.get("location") or {}
        place = ", ".join(x for x in (loc.get("city"), loc.get("country", "").upper()) if x)
        jobs.append(
            Job(
                title=j.get("name", ""),
                company=cfg.get("company", company_id),
                url=f"https://jobs.smartrecruiters.com/{company_id}/{j.get('id', '')}",
                source=cfg["name"],
                location=place,
                posted=j.get("releasedDate", ""),
                remote=loc.get("remote"),
            )
        )
    return jobs
