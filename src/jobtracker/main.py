from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import llm, notify
from .collectors import collect_all
from .filters import apply_filters, dedupe
from .state import State

ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str | None) -> dict:
    cfg_path = Path(path) if path else ROOT / "config" / "config.yaml"
    return yaml.safe_load(cfg_path.read_text())


def cmd_doctor(cfg: dict, data_dir: Path) -> int:
    """Hit every source once and report what works. Run this first, and after edits."""
    _, stats = collect_all(cfg["sources"])
    width = max(len(s["name"]) for s in stats)
    for s in stats:
        detail = f"{s['count']} listings" if s["status"] in ("ok", "empty") else s["error"]
        print(f"{s['status']:8} {s['name']:<{width}}  {detail}")
    counts = {k: sum(1 for s in stats if s["status"] == k) for k in ("ok", "empty", "error", "skipped")}
    print(f"\n{counts}")
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "health.json").write_text(json.dumps(stats, indent=1))
    return 0


def cmd_run(cfg: dict, data_dir: Path, dry_run: bool, use_llm: bool) -> int:
    state = State(data_dir / "seen.json")
    jobs, stats = collect_all(cfg["sources"])
    print(f"collected {len(jobs)} listings from {len(stats)} sources")

    kept = dedupe(apply_filters(jobs, cfg["profile"]))
    new = [j for j in kept if state.is_new(j)]
    print(f"{len(kept)} pass hard filters, {len(new)} not seen before")

    llm_cfg = cfg.get("llm", {})
    key = os.environ.get("GEMINI_API_KEY")
    new.sort(key=lambda j: -j.score)
    if use_llm and llm_cfg.get("enabled") and key and new:
        pool = new[: int(llm_cfg.get("max_per_run", 40))]
        n = llm.score_jobs(pool, llm_cfg, key)
        print(f"LLM scored {n}/{len(pool)}")
        floor = float(llm_cfg.get("min_score", 6))
        # Jobs the LLM scored below the floor are dropped; unscored ones keep the rule-based rank.
        new = [j for j in new if j.llm_score is None or j.llm_score >= floor]
        new.sort(key=lambda j: -(j.llm_score if j.llm_score is not None else j.score))
    elif llm_cfg.get("enabled") and use_llm and not key:
        print("GEMINI_API_KEY not set: using rule-based ranking only")

    shown = new[: int(cfg.get("max_digest", 30))]
    digest = notify.build_digest(shown, stats, len(new))
    print("\n" + digest)

    if dry_run:
        print("\n(dry run: nothing sent, state not saved)")
        return 0

    notify.write_files(digest, data_dir)
    sent = mailed = False
    try:
        sent = notify.telegram(shown, stats, len(new))
    except Exception as exc:  # a delivery hiccup must not lose today's state
        print(f"telegram failed: {exc}")
    try:
        mailed = notify.email(digest)
    except Exception as exc:
        print(f"email failed: {exc}")
    if not (sent or mailed):
        print("no delivery channel worked: digest is in data/latest_digest.md and the Actions summary")
    print(f"telegram={sent} email={mailed}")

    state.mark(shown)  # jobs held back stay unseen and surface tomorrow
    state.save()
    (data_dir / "last_run.txt").write_text(datetime.now(timezone.utc).isoformat() + "\n")
    (data_dir / "health.json").write_text(json.dumps(stats, indent=1))

    working = sum(1 for s in stats if s["status"] == "ok")
    return 1 if working == 0 else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="jobtracker")
    p.add_argument("command", choices=["run", "doctor"])
    p.add_argument("--config")
    p.add_argument("--dry-run", action="store_true", help="print the digest, send nothing")
    p.add_argument("--no-llm", action="store_true")
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    data_dir = ROOT / "data"
    if args.command == "doctor":
        return cmd_doctor(cfg, data_dir)
    return cmd_run(cfg, data_dir, args.dry_run, not args.no_llm)


if __name__ == "__main__":
    sys.exit(main())
