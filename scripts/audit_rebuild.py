"""Audit a rebuilt jobs database before it replaces the formal database."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import analyzer
import job_details
import job_filters
from profile_config import load_profile


SUSPICIOUS_COMPANY_MARKERS = (
    "实习僧", "hr邮箱", "未官宣", "五天内投", "尽早投", "不抱希望",
)
SUSPICIOUS_HOSTS = {"youtube.com", "www.youtube.com", "linkedin.com", "www.linkedin.com"}


def _loads(value, default):
    try:
        return json.loads(value) if value else default
    except (TypeError, json.JSONDecodeError):
        return default


def _load_applications(path: Path) -> list[dict] | None:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, list) else None


def _count_applications(path: Path) -> int:
    payload = _load_applications(path)
    return len(payload) if payload is not None else -1


def audit(db_path: Path, applications_path: Path) -> dict:
    with (ROOT / "config.yaml").open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    profile = load_profile(ROOT / "profile.yaml")
    analysis_model = (config.get("deepseek") or {}).get("analysis_model", "deepseek-v4-pro")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        jobs = [dict(row) for row in conn.execute("SELECT * FROM jobs")]
        analyses = {
            row["job_id"]: dict(row)
            for row in conn.execute("SELECT * FROM job_analysis")
        }
    finally:
        conn.close()

    application_rows = _load_applications(applications_path)
    applications = len(application_rows) if application_rows is not None else -1
    job_ids = {job["id"] for job in jobs}
    dangling_application_ids = [
        row.get("job_id")
        for row in (application_rows or [])
        if row.get("job_id") is not None and row.get("job_id") not in job_ids
    ]

    incomplete_ids = {job["id"] for job in jobs if job_details.is_jd_incomplete(job)}
    nonformal = [job for job in jobs if not job_filters.is_formal_campus_job(job)]
    direction_out = [job for job in jobs if job_filters.is_direction_out_job(job)]

    metadata_errors = []
    score_errors = []
    analysis_on_incomplete = []
    score_buckets = Counter()
    for job in jobs:
        row = analyses.get(job["id"])
        if row is None:
            continue
        if job["id"] in incomplete_ids:
            analysis_on_incomplete.append(job["id"])
        expected = analyzer.analysis_metadata(job, profile, analysis_model)
        for field, value in expected.items():
            if row.get(field) != value:
                metadata_errors.append({"job_id": job["id"], "field": field})

        score = int(row.get("match_score") or 0)
        breakdown = _loads(row.get("score_breakdown"), {})
        evidence = _loads(row.get("evidence"), [])
        level = row.get("evidence_level") or "insufficient"
        component_sum = 0
        for name, maximum in analyzer._SCORE_COMPONENT_LIMITS.items():
            value = breakdown.get(name)
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= maximum:
                score_errors.append({
                    "job_id": job["id"],
                    "reason": f"invalid_component:{name}",
                })
                continue
            component_sum += value
        if set(breakdown) != set(analyzer._SCORE_COMPONENT_LIMITS):
            score_errors.append({"job_id": job["id"], "reason": "component_keys"})
        if not 0 <= score <= min(100, component_sum):
            score_errors.append({"job_id": job["id"], "reason": "component_ceiling"})
        if level not in analyzer._EVIDENCE_CAPS:
            score_errors.append({"job_id": job["id"], "reason": "evidence_level"})
        elif score > analyzer._EVIDENCE_CAPS[level]:
            score_errors.append({"job_id": job["id"], "reason": "evidence_cap"})
        missing_core = sum(
            item.get("relation") == "missing" and item.get("requirement_type") == "core"
            for item in evidence if isinstance(item, dict)
        )
        direct_core = sum(
            item.get("relation") == "direct" and item.get("requirement_type") == "core"
            for item in evidence if isinstance(item, dict)
        )
        if missing_core >= 2 and score > 64:
            score_errors.append({"job_id": job["id"], "reason": "two_missing_core"})
        elif missing_core == 1 and score > 74:
            score_errors.append({"job_id": job["id"], "reason": "one_missing_core"})
        if direct_core == 0 and score > 64:
            score_errors.append({"job_id": job["id"], "reason": "no_direct_core"})
        if score >= 90 and direct_core < 2:
            score_errors.append({"job_id": job["id"], "reason": "high_score_direct_core"})
        if score >= 90:
            score_buckets["90+"] += 1
        elif score >= 80:
            score_buckets["80-89"] += 1
        elif score >= 60:
            score_buckets["60-79"] += 1
        else:
            score_buckets["0-59"] += 1

    suspicious_links = [
        {"id": job["id"], "company": job["company"], "url": job["jd_url"]}
        for job in jobs
        if urlparse(job.get("jd_url") or "").netloc.casefold() in SUSPICIOUS_HOSTS
    ]
    suspicious_companies = sorted({
        job["company"] for job in jobs
        if any(marker.casefold() in job["company"].casefold() for marker in SUSPICIOUS_COMPANY_MARKERS)
    })

    tier_counts = Counter(analyzer.analysis_screening_tier(job) for job in jobs)
    pending_complete = sum(
        job["id"] not in incomplete_ids
        and job["id"] not in analyses
        and analyzer.analysis_screening_tier(job) == "A"
        for job in jobs
    )
    blocking = {
        "applications_file_invalid": int(application_rows is None),
        "dangling_application_job_ids": len(dangling_application_ids),
        "nonformal_jobs": len(nonformal),
        "direction_out_jobs": len(direction_out),
        "invalid_external_job_links": len(suspicious_links),
        "analysis_on_incomplete_jd": len(analysis_on_incomplete),
        "analysis_metadata_errors": len(metadata_errors),
        "score_rule_errors": len(score_errors),
        "tier_a_complete_jd_without_analysis": max(0, pending_complete),
    }
    return {
        "passed": all(value == 0 for value in blocking.values()),
        "database": str(db_path),
        "counts": {
            "jobs": len(jobs),
            "complete_jd": len(jobs) - len(incomplete_ids),
            "jd_pending": len(incomplete_ids),
            "analyses": len(analyses),
            "applications": applications,
            "companies_with_jobs": len({job["company"] for job in jobs}),
            "screening_tiers": dict(tier_counts),
        },
        "score_buckets": dict(score_buckets),
        "blocking_checks": blocking,
        "warnings": {
            "suspicious_links": suspicious_links,
            "suspicious_company_names": suspicious_companies,
            "dangling_application_job_ids": dangling_application_ids,
        },
        "samples": {
            "nonformal": [{"id": job["id"], "company": job["company"], "title": job["title"]} for job in nonformal[:20]],
            "direction_out": [{"id": job["id"], "company": job["company"], "title": job["title"]} for job in direction_out[:20]],
            "metadata_errors": metadata_errors[:20],
            "score_errors": score_errors[:20],
        },
    }


def write_outputs(result: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "rebuild_audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    counts = result["counts"]
    checks = result["blocking_checks"]
    lines = [
        "# 重建数据库验收报告",
        "",
        f"- 结论：{'通过' if result['passed'] else '未通过'}",
        f"- 岗位：{counts['jobs']}",
        f"- 完整 JD：{counts['complete_jd']}",
        f"- JD 待补全：{counts['jd_pending']}",
        f"- 已分析：{counts['analyses']}",
        f"- 投递记录：{counts['applications']}",
        f"- 有岗位公司：{counts['companies_with_jobs']}",
        "",
        "## 阻断检查",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in checks.items())
    lines.extend(["", "## 分数分布", ""])
    lines.extend(f"- {key}: {value}" for key, value in result["score_buckets"].items())
    lines.extend([
        "",
        "## 警告",
        "",
        f"- 异常外链：{len(result['warnings']['suspicious_links'])}",
        f"- 含备注的公司名：{len(result['warnings']['suspicious_company_names'])}",
    ])
    (output_dir / "rebuild_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--applications",
        type=Path,
        default=ROOT / "data" / "applications.json",
    )
    args = parser.parse_args()
    result = audit(args.db.resolve(), args.applications.resolve())
    write_outputs(result, args.output_dir.resolve())
    print(json.dumps({"passed": result["passed"], **result["counts"], **result["blocking_checks"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
