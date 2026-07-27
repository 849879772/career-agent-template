"""Audit cohort separation, JD policy, and analysis invariants."""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db
import job_cohorts
import job_details


def run(db_path: Path) -> dict:
    conn = db.init_db(db_path)
    rows = [dict(row) for row in conn.execute(
        """SELECT job.*, analysis.id AS analysis_id,
                  analysis.match_score, analysis.analysis_status
           FROM jobs AS job
           LEFT JOIN job_analysis AS analysis ON analysis.job_id = job.id
           ORDER BY job.id"""
    )]
    conn.close()

    buckets = Counter()
    sources = Counter()
    jd_statuses = Counter()
    current_incomplete = []
    invalid_analysis = []
    incomplete_analysis = []
    invalid_screening = []
    for job in rows:
        current = job_cohorts.is_confirmed_current(job)
        if current:
            bucket = "current_2027"
        elif (
            job.get("cohort_status") == "confirmed"
            and 0 < int(job.get("cohort") or 0) <= 2026
        ):
            bucket = "previous"
        else:
            bucket = "unknown"
        buckets[bucket] += 1
        sources[str(job.get("cohort_source") or "未记录")] += 1
        jd_statuses[f"{bucket}:{job.get('jd_status') or 'empty'}"] += 1

        incomplete = job_details.is_jd_incomplete(job)
        if current and incomplete:
            current_incomplete.append({
                "id": job["id"],
                "company": job["company"],
                "title": job["title"],
                "jd_status": job.get("jd_status") or "",
                "jd_url": job.get("jd_url") or "",
            })
        if job.get("analysis_id") and not current:
            invalid_analysis.append(job["id"])
        if job.get("analysis_id") and incomplete:
            incomplete_analysis.append(job["id"])
        if not current and str(job.get("screening_tier") or "").strip():
            invalid_screening.append(job["id"])

    payload = {
        "date": date.today().isoformat(),
        "database": str(db_path),
        "jobs": len(rows),
        "cohorts": dict(buckets),
        "cohort_sources": dict(sources),
        "jd_statuses": dict(jd_statuses),
        "current_2027_jd_complete": buckets["current_2027"] - len(current_incomplete),
        "current_2027_jd_incomplete": len(current_incomplete),
        "analyses": sum(bool(row.get("analysis_id")) for row in rows),
        "invalid_noncurrent_analyses": len(invalid_analysis),
        "invalid_incomplete_jd_analyses": len(incomplete_analysis),
        "invalid_noncurrent_screening_tiers": len(invalid_screening),
        "current_incomplete_items": current_incomplete,
    }
    output_json = ROOT / "outputs" / f"cohort_pipeline_audit_{date.today():%Y%m%d}.json"
    output_md = ROOT / "outputs" / f"cohort_pipeline_audit_{date.today():%Y%m%d}.md"
    output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# 届别与 JD 流程验收",
        "",
        f"- 岗位总数：{payload['jobs']}",
        f"- 确认 27 届：{buckets['current_2027']}",
        f"- 确认往届：{buckets['previous']}",
        f"- 届别待确认：{buckets['unknown']}",
        f"- 27 届完整 JD：{payload['current_2027_jd_complete']}",
        f"- 27 届待补全 JD：{payload['current_2027_jd_incomplete']}",
        f"- 已评分：{payload['analyses']}",
        f"- 非 27 届违规评分：{payload['invalid_noncurrent_analyses']}",
        f"- JD 不完整违规评分：{payload['invalid_incomplete_jd_analyses']}",
        f"- 非 27 届残留筛选分级：{payload['invalid_noncurrent_screening_tiers']}",
        "",
        "## 27 届待补全",
    ]
    if current_incomplete:
        lines.extend(
            f"- {item['company']}｜{item['title']}｜{item['jd_status']}｜{item['jd_url']}"
            for item in current_incomplete
        )
    else:
        lines.append("- 无")
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(
        run(ROOT / "data" / "jobs.db"),
        ensure_ascii=False,
        indent=2,
    ))
