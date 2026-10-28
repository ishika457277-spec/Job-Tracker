"""Small helpers: HTML stripping, URL normalising, date parsing, fuzzy keys."""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

_TRACKING_PREFIXES = ("utm_", "ref", "source", "gh_src", "lever-source", "fbclid", "gclid")


def strip_html(raw: str | None, limit: int = 6000) -> str:
    if not raw:
        return ""
    text = BeautifulSoup(html.unescape(raw), "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)[:limit]


def normalize_url(url: str | None) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query)
        if not k.lower().startswith(_TRACKING_PREFIXES)
    ]
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), "")
    )


def fuzzy_key(company: str, title: str) -> str:
    """Same job listed on two boards usually shares company + title."""
    squash = lambda s: re.sub(r"[^a-z0-9]+", "", (s or "").lower())
    return f"{squash(company)}|{squash(title)}"


def parse_date(value) -> datetime | None:
    """Accepts ISO strings, RFC 2822 strings, and epoch seconds/milliseconds."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            n = float(value)
            if n > 1e11:  # milliseconds
                n /= 1000
            return datetime.fromtimestamp(n, tz=timezone.utc)
        s = str(value).strip()
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            d = parsedate_to_datetime(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception:
        return None
