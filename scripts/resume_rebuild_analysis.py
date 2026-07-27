"""Resume JD hydration, detailed analysis, and report generation for one DB."""

from __future__ import annotations

import argparse
from datetime import date
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import analyzer
import db
import main
import reporter
from profile_config import load_profile


def run(db_path: Path, reports_dir: Path, hydrate: bool = True) -> dict:
    config = main.load_config(str(ROOT / "config.yaml"))
    profile = load_profile(ROOT / "profile.yaml")
    llm_cfg = config.get("deepseek") or config.get("claude") or {}
    _, analysis_model = main._resolve_llm_models(llm_cfg)

    conn = db.init_db(str(db_path))
    try:
        active = db.get_active_jobs(conn)
        pending_before = [
            job for job in active
            if analyzer.needs_detailed_analysis(
                conn, job, profile, analysis_model
            )
        ]
        allow_full = os.environ.get("ALLOW_FULL_PRO_ANALYSIS") == "1"
        results = analyzer.batch_analyze(
            pending_before,
            profile,
            conn,
            model=analysis_model,
            max_tokens=int(llm_cfg.get("analysis_max_tokens", 1200)),
            hydrate=hydrate,
            max_jobs=(
                None if allow_full else int(llm_cfg.get("max_pro_jobs_per_run", 50))
            ),
            max_jobs_per_day=(
                None if allow_full else int(llm_cfg.get("max_pro_jobs_per_day", 100))
            ),
        )
        purged_nonformal = db.purge_nonformal_campus_jobs(conn)
        purged_direction = db.purge_direction_out_jobs(conn)
        purged_incomplete_analysis = db.purge_incomplete_jd_analyses(conn)

        today = date.today().isoformat()
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_data = db.get_active_report_data(conn)
        reporter.generate_report(today, report_data, str(reports_dir))
        reporter.generate_report(
            today,
            {
                "items": db.get_all_jobs_with_analysis(conn),
                "applications": db.get_applications(conn),
                "date": today,
            },
            str(reports_dir),
            out_name="index",
        )
        pending_after = sum(
            analyzer.needs_detailed_analysis(conn, job, profile, analysis_model)
            for job in db.get_active_jobs(conn)
        )
        return {
            "active": len(active),
            "pending_before": len(pending_before),
            "analyzed_this_run": len(results),
            "purged_nonformal": purged_nonformal,
            "purged_direction": purged_direction,
            "purged_incomplete_analysis": purged_incomplete_analysis,
            "pending_after": pending_after,
        }
    finally:
        conn.close()


def main_cli() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--reports-dir", type=Path, required=True)
    parser.add_argument(
        "--skip-hydration",
        action="store_true",
        help="Analyze only JDs already known to be complete.",
    )
    args = parser.parse_args()
    stats = run(args.db.resolve(), args.reports_dir.resolve(), hydrate=not args.skip_hydration)
    print(stats)


if __name__ == "__main__":
    main_cli()
