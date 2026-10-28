from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .text import fuzzy_key, normalize_url


class SkipSource(Exception):
    """Raised by a collector that cannot run (e.g. a missing free API key)."""


@dataclass
class Job:
    title: str
    company: str
    url: str
    source: str
    location: str = ""
    description: str = ""
    posted: object = ""  # raw value; parsed later by text.parse_date
    remote: bool | None = None
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    llm_score: float | None = None

    @property
    def uid(self) -> str:
        key = normalize_url(self.url) or f"{self.company}|{self.title}|{self.location}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]

    @property
    def fuzzy(self) -> str:
        return fuzzy_key(self.company, self.title)
