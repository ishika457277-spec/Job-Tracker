from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from jobtracker import collectors, notify
from jobtracker.collectors import ats, boards, feeds
from jobtracker.filters import apply_filters, dedupe
from jobtracker.models import Job
from jobtracker.state import State
from jobtracker.text import normalize_url, parse_date, strip_html

CFG = yaml.safe_load((Path(__file__).parents[1] / "config" / "config.yaml").read_text())
PROFILE = CFG["profile"]
NOW = datetime.now(timezone.utc)


class Fake:
    def __init__(self, payload=None, text="", content=b""):
        self._p, self.text, self.content = payload, text, content

    def json(self):
        return self._p


def job(title, loc="", desc="", company="Acme", url=None, posted="", remote=None):
    return Job(title=title, company=company, url=url or f"https://x.test/{title}", source="t",
               location=loc, description=desc, posted=posted, remote=remote)


# ---------- helpers ----------
def test_normalize_url_strips_tracking():
    assert normalize_url("https://A.com/j/1/?utm_source=x&id=5#frag") == "https://a.com/j/1?id=5"


def test_strip_html_handles_escaped_markup():
    assert strip_html("&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;") == "Hello world"


def test_parse_date_variants():
    assert parse_date("2026-10-01T00:00:00Z").year == 2026
    assert parse_date(1760000000000).year == 2025  # epoch ms
    assert parse_date("Wed, 01 Oct 2026 10:00:00 GMT").month == 10
    assert parse_date("garbage") is None


# ---------- filters ----------
def test_policy_job_in_japan_passes():
    out = apply_filters([job("AI Policy Associate", "Tokyo, Japan")], PROFILE, NOW)
    assert len(out) == 1 and out[0].score > 0


def test_senior_title_is_dropped():
    assert apply_filters([job("Senior Policy Analyst", "Tokyo")], PROFILE, NOW) == []


def test_unrelated_title_is_dropped():
    assert apply_filters([job("Plumber", "Tokyo")], PROFILE, NOW) == []


def test_remote_us_only_is_dropped_but_worldwide_kept():
    assert apply_filters([job("Policy Analyst", "Remote - United States", remote=True)], PROFILE, NOW) == []
    assert len(apply_filters([job("Policy Analyst", "Remote (Worldwide)", remote=True)], PROFILE, NOW)) == 1


def test_us_remote_allowed_if_target_country_also_listed():
    out = apply_filters([job("Policy Analyst", "Remote - United States or Japan", remote=True)], PROFILE, NOW)
    assert len(out) == 1


def test_onsite_elsewhere_is_dropped():
    assert apply_filters([job("Policy Analyst", "Austin, Texas")], PROFILE, NOW) == []


def test_unknown_location_kept_when_configured():
    assert len(apply_filters([job("Policy Fellow", "")], PROFILE, NOW)) == 1


def test_old_postings_dropped():
    old = (NOW - timedelta(days=200)).isoformat()
    assert apply_filters([job("Policy Fellow", "Tokyo", posted=old)], PROFILE, NOW) == []


def test_text_hits_can_rescue_a_vague_title():
    desc = "You will work on ai governance, responsible ai and digital rights."
    assert len(apply_filters([job("Program Coordinator", "India", desc=desc)], PROFILE, NOW)) == 1


def test_word_boundary_matching():
    # "lead" is a dealbreaker, "leadership" must not trigger it
    assert len(apply_filters([job("Research Fellow, Leadership Studies", "India")], PROFILE, NOW)) == 1


def test_dedupe_by_url_and_by_company_title():
    a = job("Policy Fellow", "India", url="https://x.test/a?utm_source=1")
    b = job("Policy Fellow", "India", url="https://x.test/a")
    c = job("Policy  Fellow!", "India", url="https://other.test/z")
    for j in (a, b, c):
        j.score = 1
    assert len(dedupe([a, b, c])) == 1


# ---------- state ----------
def test_state_roundtrip(tmp_path):
    j = job("Policy Fellow", "India")
    s = State(tmp_path / "seen.json")
    assert s.is_new(j)
    s.mark([j])
    s.save()
    assert not State(tmp_path / "seen.json").is_new(j)


# ---------- collectors (network mocked) ----------
def test_greenhouse(monkeypatch):
    payload = {"jobs": [{"title": "Policy Fellow", "absolute_url": "https://g.test/1",
                         "location": {"name": "Tokyo"}, "content": "&lt;p&gt;ai governance&lt;/p&gt;",
                         "updated_at": "2026-10-20T00:00:00Z"}]}
    monkeypatch.setattr(ats, "fetch", lambda *a, **k: Fake(payload))
    jobs = ats.greenhouse({"name": "X", "board": "x", "company": "X Co"})
    assert jobs[0].location == "Tokyo" and jobs[0].description == "ai governance"


def test_lever_and_ashby(monkeypatch):
    monkeypatch.setattr(ats, "fetch", lambda *a, **k: Fake(
        [{"text": "Research Associate", "hostedUrl": "https://l.test/1", "categories": {"location": "Seoul"},
          "descriptionPlain": "desc", "createdAt": 1760000000000}]))
    assert ats.lever({"name": "L", "board": "l"})[0].location == "Seoul"
    monkeypatch.setattr(ats, "fetch", lambda *a, **k: Fake(
        {"jobs": [{"title": "Policy Analyst", "jobUrl": "https://a.test/1", "location": "Remote",
                   "isRemote": True, "descriptionPlain": "d", "publishedAt": "2026-10-01"},
                  {"title": "Hidden", "jobUrl": "https://a.test/2", "isListed": False}]}))
    out = ats.ashby({"name": "A", "board": "a"})
    assert len(out) == 1 and out[0].remote is True


def test_remotive_and_remoteok(monkeypatch):
    monkeypatch.setattr(boards, "fetch", lambda *a, **k: Fake(
        {"jobs": [{"title": "Policy Lead", "company_name": "C", "url": "https://r.test/1",
                   "candidate_required_location": "Worldwide", "description": "<p>x</p>",
                   "publication_date": "2026-10-01T00:00:00"}]}))
    assert boards.remotive({"name": "R", "searches": ["policy"]})[0].company == "C"
    monkeypatch.setattr(boards, "fetch", lambda *a, **k: Fake(
        [{"legal": "notice"}, {"position": "Researcher", "company": "Z", "url": "https://o.test/1",
                               "tags": ["ai"], "description": "", "date": "2026-10-01T00:00:00+00:00"}]))
    assert len(boards.remoteok({"name": "O"})) == 1


def test_missing_key_is_skipped_not_failed(monkeypatch):
    monkeypatch.delenv("RELIEFWEB_APPNAME", raising=False)
    jobs, stats = collectors.collect_all([{"name": "RW", "type": "reliefweb"}])
    assert jobs == [] and stats[0]["status"] == "skipped"


def test_one_broken_source_does_not_stop_others(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("HTTP 500")
    monkeypatch.setattr(ats, "fetch", boom)
    monkeypatch.setattr(boards, "fetch", lambda *a, **k: Fake(
        [{"position": "Researcher", "company": "Z", "url": "https://o.test/1", "tags": [], "description": "", "date": ""}]))
    jobs, stats = collectors.collect_all([
        {"name": "Bad", "type": "greenhouse", "board": "nope"},
        {"name": "Good", "type": "remoteok"},
    ])
    assert len(jobs) == 1
    assert {s["name"]: s["status"] for s in stats} == {"Bad": "error", "Good": "ok"}


def test_rss_company_title_split(monkeypatch):
    xml = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>WWR</title>
    <item><title>Acme: Policy Researcher</title><link>https://w.test/1</link>
    <description>&lt;p&gt;hi&lt;/p&gt;</description><pubDate>Wed, 01 Oct 2026 10:00:00 GMT</pubDate></item>
    </channel></rss>"""
    monkeypatch.setattr(feeds, "fetch", lambda *a, **k: Fake(content=xml))
    out = feeds.rss({"name": "W", "url": "u", "title_has_company": True})
    assert (out[0].company, out[0].title) == ("Acme", "Policy Researcher")


def test_page_scraper_filters_nav_links(monkeypatch):
    html = """<a href="/about">About</a><a href="/jobs/1">Policy Research Fellow</a>
    <a href="/jobs/1">Policy Research Fellow</a><a href="mailto:a@b.c">Email us today</a>
    <a href="https://ext.test/2">Programme Officer, Digital Rights</a>"""
    monkeypatch.setattr(feeds, "fetch", lambda *a, **k: Fake(text=html))
    out = feeds.page({"name": "P", "url": "https://org.test/careers", "company": "Org"})
    assert [j.title for j in out] == ["Policy Research Fellow", "Programme Officer, Digital Rights"]
    assert out[0].url == "https://org.test/jobs/1"


# ---------- digest ----------
def test_digest_mentions_problem_sources():
    stats = [{"name": "A", "status": "ok", "count": 3, "error": ""},
             {"name": "B", "status": "error", "count": 0, "error": "HTTP 404"},
             {"name": "C", "status": "skipped", "count": 0, "error": "key"}]
    j = job("Policy Fellow", "Tokyo")
    j.reasons = ["remote"]
    text = notify.build_digest([j], stats, total_new=5)
    assert "4 more held" in text and "B (error)" in text and "Skipped (no key): C" in text


def test_config_has_30_plus_sources():
    assert len(CFG["sources"]) >= 30
    assert all(s["type"] in collectors.COLLECTORS for s in CFG["sources"])


def test_config_is_well_formed():
    """Catches YAML slips such as an unquoted name containing a comma."""
    from jobtracker.main import load_config

    cfg = load_config(None)
    names = [s["name"] for s in cfg["sources"]]
    assert all(isinstance(n, str) for n in names)
    assert len(set(names)) == len(names)
    assert len(names) >= 30
    assert all(s["type"] in collectors.COLLECTORS for s in cfg["sources"])
