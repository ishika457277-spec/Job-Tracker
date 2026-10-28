"""Aggregators and job boards that expose a free API or JSON feed."""
from __future__ import annotations

import os

from ..http import fetch
from ..models import Job, SkipSource
from ..text import strip_html


def remotive(cfg: dict) -> list[Job]:
    jobs: dict[str, Job] = {}
    for term in (cfg.get("searches") or [""])[:4]:  # Remotive asks for few requests
        data = fetch("https://remotive.com/api/remote-jobs", params={"search": term}).json()
        for j in data.get("jobs", []):
            jobs[j["url"]] = Job(
                title=j.get("title", ""),
                company=j.get("company_name", ""),
                url=j["url"],
                source=cfg["name"],
                location=j.get("candidate_required_location", "") or "Remote",
                description=strip_html(j.get("description")),
                posted=j.get("publication_date", ""),
                remote=True,
            )
    return list(jobs.values())


def arbeitnow(cfg: dict) -> list[Job]:
    jobs = []
    for page in range(1, int(cfg.get("pages", 2)) + 1):
        data = fetch("https://www.arbeitnow.com/api/job-board-api", params={"page": page}).json()
        for j in data.get("data", []):
            jobs.append(
                Job(
                    title=j.get("title", ""),
                    company=j.get("company_name", ""),
                    url=j.get("url", ""),
                    source=cfg["name"],
                    location=j.get("location", ""),
                    description=strip_html(j.get("description")),
                    posted=j.get("created_at", ""),
                    remote=j.get("remote"),
                )
            )
    return jobs


def remoteok(cfg: dict) -> list[Job]:
    data = fetch("https://remoteok.com/api").json()
    jobs = []
    for j in data:
        if not isinstance(j, dict) or "position" not in j:  # first element is a legal notice
            continue
        jobs.append(
            Job(
                title=j.get("position", ""),
                company=j.get("company", ""),
                url=j.get("url", ""),
                source=cfg["name"],
                location=j.get("location", "") or "Remote",
                description=strip_html(j.get("description")) + " " + " ".join(j.get("tags") or []),
                posted=j.get("date", ""),
                remote=True,
            )
        )
    return jobs


def himalayas(cfg: dict) -> list[Job]:
    data = fetch("https://himalayas.app/jobs/api", params={"limit": 100}).json()
    jobs = []
    for j in data.get("jobs", []):
        restrictions = j.get("locationRestrictions") or []
        jobs.append(
            Job(
                title=j.get("title", ""),
                company=j.get("companyName", ""),
                url=j.get("applicationLink") or j.get("guid", ""),
                source=cfg["name"],
                location=", ".join(restrictions) if restrictions else "Remote (worldwide)",
                description=strip_html(j.get("description") or j.get("excerpt")),
                posted=j.get("pubDate", ""),
                remote=True,
            )
        )
    return jobs


def jobicy(cfg: dict) -> list[Job]:
    """Tries each tag, then a plain request. One rejected tag does not lose the rest."""
    jobs: dict[str, Job] = {}
    last: Exception | None = None
    for tag in list(cfg.get("tags") or []) + [""]:
        params = {"count": 50}
        if tag:
            params["tag"] = tag
        try:
            data = fetch("https://jobicy.com/api/v2/remote-jobs", params=params).json()
        except Exception as exc:
            last = exc
            continue
        for j in data.get("jobs", []):
            jobs[j["url"]] = Job(
                title=j.get("jobTitle", ""),
                company=j.get("companyName", ""),
                url=j["url"],
                source=cfg["name"],
                location=j.get("jobGeo", "") or "Remote",
                description=strip_html(j.get("jobDescription")),
                posted=j.get("pubDate", ""),
                remote=True,
            )
    if not jobs and last:
        raise last
    return list(jobs.values())


def workingnomads(cfg: dict) -> list[Job]:
    data = fetch("https://www.workingnomads.com/api/exposed_jobs/").json()
    return [
        Job(
            title=j.get("title", ""),
            company=j.get("company_name", ""),
            url=j.get("url", ""),
            source=cfg["name"],
            location=j.get("location", "") or "Remote",
            description=strip_html(j.get("description")) + " " + str(j.get("tags") or ""),
            posted=j.get("pub_date", ""),
            remote=True,
        )
        for j in data
    ]


def themuse(cfg: dict) -> list[Job]:
    jobs = []
    for page in range(0, int(cfg.get("pages", 2))):
        data = fetch(
            "https://www.themuse.com/api/public/jobs",
            params={"page": page, "location": "Flexible / Remote"},
        ).json()
        for j in data.get("results", []):
            jobs.append(
                Job(
                    title=j.get("name", ""),
                    company=(j.get("company") or {}).get("name", ""),
                    url=(j.get("refs") or {}).get("landing_page", ""),
                    source=cfg["name"],
                    location=", ".join(l.get("name", "") for l in j.get("locations", [])),
                    description=strip_html(j.get("contents")),
                    posted=j.get("publication_date", ""),
                )
            )
    return jobs


def hn_whoishiring(cfg: dict) -> list[Job]:
    hits = fetch(
        "https://hn.algolia.com/api/v1/search_by_date",
        params={"tags": "story,author_whoishiring", "hitsPerPage": 6},
    ).json().get("hits", [])
    story = next(
        (
            h
            for h in hits
            if "who is hiring" in h.get("title", "").lower()
            and "freelancer" not in h.get("title", "").lower()
        ),
        None,
    )
    if not story:
        return []
    tree = fetch(f"https://hn.algolia.com/api/v1/items/{story['objectID']}").json()
    jobs = []
    for c in tree.get("children", []):
        raw = c.get("text") or ""
        if not raw:
            continue
        header = strip_html(raw.split("<p>")[0], limit=300)
        body = strip_html(raw)
        jobs.append(
            Job(
                title=header[:140],
                company=header.split("|")[0].strip()[:60],
                url=f"https://news.ycombinator.com/item?id={c['id']}",
                source=cfg["name"],
                location=header,
                description=body,
                posted=c.get("created_at", ""),
                remote="remote" in body.lower(),
            )
        )
    return jobs


def reliefweb(cfg: dict) -> list[Job]:
    appname = os.environ.get("RELIEFWEB_APPNAME")
    if not appname:
        raise SkipSource("set RELIEFWEB_APPNAME (free, request one at reliefweb.int/help/api)")
    body = {
        "limit": 100,
        "sort": ["date.created:desc"],
        "fields": {"include": ["title", "url", "source.name", "country.name", "body", "date.created"]},
    }
    data = fetch("https://api.reliefweb.int/v2/jobs", params={"appname": appname}, method="POST", json=body).json()
    jobs = []
    for item in data.get("data", []):
        f = item.get("fields", {})
        jobs.append(
            Job(
                title=f.get("title", ""),
                company=", ".join(s.get("name", "") for s in f.get("source", [])),
                url=f.get("url", ""),
                source=cfg["name"],
                location=", ".join(c.get("name", "") for c in f.get("country", [])),
                description=strip_html(f.get("body")),
                posted=(f.get("date") or {}).get("created", ""),
            )
        )
    return jobs


def adzuna(cfg: dict) -> list[Job]:
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        raise SkipSource("set ADZUNA_APP_ID and ADZUNA_APP_KEY (free at developer.adzuna.com)")
    jobs = []
    for country in cfg.get("countries", ["in"]):
        for term in cfg.get("what", [""]):
            data = fetch(
                f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
                params={
                    "app_id": app_id,
                    "app_key": app_key,
                    "results_per_page": 50,
                    "what": term,
                    "sort_by": "date",
                },
            ).json()
            for j in data.get("results", []):
                jobs.append(
                    Job(
                        title=j.get("title", ""),
                        company=(j.get("company") or {}).get("display_name", ""),
                        url=j.get("redirect_url", ""),
                        source=cfg["name"],
                        location=(j.get("location") or {}).get("display_name", ""),
                        description=strip_html(j.get("description")),
                        posted=j.get("created", ""),
                    )
                )
    return jobs


def jooble(cfg: dict) -> list[Job]:
    key = os.environ.get("JOOBLE_API_KEY")
    if not key:
        raise SkipSource("set JOOBLE_API_KEY (free at jooble.org/api/about)")
    jobs = []
    for term in cfg.get("what", [""]):
        data = fetch(
            f"https://jooble.org/api/{key}",
            method="POST",
            json={"keywords": term, "location": cfg.get("location", "")},
        ).json()
        for j in data.get("jobs", []):
            jobs.append(
                Job(
                    title=j.get("title", ""),
                    company=j.get("company", ""),
                    url=j.get("link", ""),
                    source=cfg["name"],
                    location=j.get("location", ""),
                    description=strip_html(j.get("snippet")),
                    posted=j.get("updated", ""),
                )
            )
    return jobs

