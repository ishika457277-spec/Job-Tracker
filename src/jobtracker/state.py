"""Remembers which jobs were already sent. Stored as JSON and committed by the workflow."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Job

KEEP_DAYS = 180


class State:
    def __init__(self, path: Path):
        self.path = path
        self.seen: dict[str, str] = {}
        if path.exists():
            try:
                self.seen = json.loads(path.read_text())
            except json.JSONDecodeError:
                self.seen = {}

    def is_new(self, job: Job) -> bool:
        return job.uid not in self.seen and job.fuzzy not in self.seen

    def mark(self, jobs: list[Job]) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for job in jobs:
            self.seen[job.uid] = now
            self.seen[job.fuzzy] = now

    def save(self) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).isoformat()
        self.seen = {k: v for k, v in self.seen.items() if v >= cutoff}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.seen, indent=0, sort_keys=True))
