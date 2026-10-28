from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..models import Job, SkipSource
from . import ats, boards, feeds

COLLECTORS = {
    "greenhouse": ats.greenhouse,
    "lever": ats.lever,
    "ashby": ats.ashby,
    "smartrecruiters": ats.smartrecruiters,
    "remotive": boards.remotive,
    "arbeitnow": boards.arbeitnow,
    "remoteok": boards.remoteok,
    "himalayas": boards.himalayas,
    "jobicy": boards.jobicy,
    "workingnomads": boards.workingnomads,
    "themuse": boards.themuse,
    "hn_whoishiring": boards.hn_whoishiring,
    "reliefweb": boards.reliefweb,
    "adzuna": boards.adzuna,
    "jooble": boards.jooble,
    "rss": feeds.rss,
    "page": feeds.page,
}


def _run_one(src: dict) -> tuple[dict, list[Job]]:
    stat = {"name": src["name"], "type": src["type"], "status": "ok", "count": 0, "error": ""}
    try:
        jobs = COLLECTORS[src["type"]](src)
        stat["count"] = len(jobs)
        if not jobs:
            stat["status"] = "empty"
        return stat, jobs
    except SkipSource as exc:
        stat.update(status="skipped", error=str(exc))
    except KeyError as exc:
        stat.update(status="error", error=f"bad config or unknown type: {exc}")
    except Exception as exc:  # one broken source must never stop the run
        stat.update(status="error", error=str(exc)[:200])
    return stat, []


def collect_all(sources: list[dict], workers: int = 8) -> tuple[list[Job], list[dict]]:
    enabled = [s for s in sources if s.get("enabled", True)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_run_one, enabled))
    jobs = [j for _, js in results for j in js]
    return jobs, [stat for stat, _ in results]
