"""Re-screen the formal database, persist A/B/C tiers, and optionally purge C."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import shutil
import sqlite3
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import analyzer
import db
import job_filters
from profile_config import load_profile


def _load_profile(config_path: Path) -> tuple[dict, str, int]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    llm = config.get("deepseek") or config.get("claude") or {}
    model = llm.get("screening_model") or llm.get("model") or "deepseek-v4-flash"
    max_tokens = int(llm.get("screening_max_tokens", 600))
    return load_profile(ROOT / "profile.yaml"), model, max_tokens


def _load_jobs(conn: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in conn.execute("SELECT * FROM jobs ORDER BY id")]


def classify(
    jobs: list[dict],
    profile: dict,
    model: str,
    max_tokens: int,
    *,
    local_only: bool,
) -> list[tuple[dict, str]]:
    forced_c = {
        job["id"]
        for job in jobs
        if not job_filters.is_formal_campus_job(job)
        or job_filters.is_direction_out_job(job)
    }
    candidates = [job for job in jobs if job["id"] not in forced_c]
    if local_only:
        tiers = [
            analyzer.local_screening_tier(job, profile) for job in candidates
        ]
    else:
        tiers = analyzer.classify_job_tiers(
            candidates,
            profile,
            model=model,
            max_tokens=max_tokens,
        )
    decisions = list(zip(candidates, tiers))
    decisions.extend((job, "C") for job in jobs if job["id"] in forced_c)
    return decisions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "jobs.db")
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--model")
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument("--local-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--purge-c", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    profile, configured_model, configured_max_tokens = _load_profile(args.config)
    model = args.model or configured_model
    max_tokens = args.max_tokens or configured_max_tokens
    conn = db.init_db(str(args.db))
    jobs = _load_jobs(conn)
    decisions = classify(
        jobs,
        profile,
        model,
        max_tokens,
        local_only=args.local_only,
    )
    counts = Counter(tier for _, tier in decisions)

    summary = {
        "database": str(args.db.resolve()),
        "screening_version": analyzer.SCREENING_VERSION,
        "model": "local-only" if args.local_only else model,
        "jobs": len(jobs),
        "tiers": dict(counts),
        "purged_c": 0,
        "purged_b_analyses": 0,
        "dry_run": args.dry_run,
    }
    if not args.dry_run:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = args.db.with_name(f"{args.db.name}.bak_before_tier_backfill_{stamp}")
        conn.commit()
        shutil.copy2(args.db, backup)
        db.save_screening_tiers(conn, decisions, analyzer.SCREENING_VERSION)
        db.update_existing_job_screening_tiers(conn, decisions)
        if args.purge_c:
            summary["purged_c"] = db.purge_screening_tier_c_jobs(conn)
            summary["purged_b_analyses"] = db.purge_screening_tier_b_analyses(conn)
        summary["backup"] = str(backup.resolve())
        summary["integrity_check"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.close()

    output = args.out or (
        ROOT / "outputs" / f"screening_tier_backfill_{datetime.now():%Y%m%d}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
