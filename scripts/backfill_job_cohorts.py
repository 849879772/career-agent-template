"""Recheck official campus entry pages and persist cohort evidence."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db
import job_cohorts


def run(db_path: Path, config_path: Path, active_only: bool, workers: int) -> dict:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    companies = config.get("companies") or []
    conn = db.init_db(db_path)
    jobs = (
        db.get_active_jobs(conn)
        if active_only
        else [dict(row) for row in conn.execute("SELECT * FROM jobs ORDER BY id")]
    )
    classified = job_cohorts.annotate_crawled_jobs(
        companies,
        jobs,
        workers=workers,
        refresh_campaigns=True,
    )
    for job in classified:
        db.update_job_cohort(conn, job["id"], job)
    removed = db.purge_noncurrent_cohort_analyses(conn)

    counts = Counter()
    sources = Counter()
    for job in classified:
        if job_cohorts.is_confirmed_current(job):
            bucket = "current_2027"
        elif (
            job.get("cohort_status") == "confirmed"
            and 0 < int(job.get("cohort") or 0) <= 2026
        ):
            bucket = "previous"
        else:
            bucket = "unknown"
        counts[bucket] += 1
        sources[str(job.get("cohort_source") or "未记录")] += 1

    invalid_analysis = conn.execute(
        """SELECT COUNT(*)
           FROM job_analysis AS analysis
           INNER JOIN jobs AS job ON job.id = analysis.job_id
           WHERE job.cohort <> ? OR job.cohort_status <> 'confirmed'""",
        (job_cohorts.CURRENT_COHORT,),
    ).fetchone()[0]
    conn.close()

    payload = {
        "date": date.today().isoformat(),
        "database": str(db_path),
        "scope": "active" if active_only else "all",
        "jobs_checked": len(classified),
        "counts": dict(counts),
        "evidence_sources": dict(sources),
        "removed_noncurrent_analyses": removed,
        "invalid_analysis_rows": invalid_analysis,
    }
    output = ROOT / "outputs" / f"cohort_audit_{date.today():%Y%m%d}.json"
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "jobs.db")
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    print(json.dumps(
        run(args.db, args.config, not args.all, args.workers),
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
