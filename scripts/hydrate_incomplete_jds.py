"""Hydrate incomplete detail-page JDs and persist explicit verification states."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db
import job_cohorts
import job_details


def _hydrate(job: dict) -> dict:
    if job.get("link_kind") == "list":
        detail = job_details.fetch_full_job_description(job)
        if detail and not job_details.is_jd_incomplete({**job, "jd_raw": detail}):
            return {"job": job, "status": "complete", "detail": detail}
        return {"job": job, "status": "list_only", "detail": ""}
    host = urlparse(str(job.get("jd_url") or "")).netloc.casefold()
    if host == "join.qq.com":
        detail, status = job_details.fetch_tencent_job_description_status(
            str(job.get("jd_url") or "")
        )
        return {"job": job, "status": status, "detail": detail}
    if host.endswith("jobs.feishu.cn"):
        detail, status = job_details.fetch_feishu_job_description_status(
            str(job.get("jd_url") or "")
        )
        if status == "official_unavailable":
            return {"job": job, "status": status, "detail": ""}
        if detail:
            status = (
                "official_sparse"
                if job_details.is_jd_incomplete({**job, "jd_raw": detail})
                else "complete"
            )
            return {"job": job, "status": status, "detail": detail}
    if host == "career.huawei.com":
        detail, status = job_details.fetch_huawei_job_description_status(
            str(job.get("jd_url") or "")
        )
        return {"job": job, "status": status, "detail": detail}
    if host.endswith(".zhiye.com"):
        detail, status = job_details.fetch_beisen_job_description_status(
            str(job.get("jd_url") or "")
        )
        return {"job": job, "status": status, "detail": detail}
    detail = job_details.fetch_full_job_description(job)
    if detail and not job_details.is_jd_incomplete({**job, "jd_raw": detail}):
        return {"job": job, "status": "complete", "detail": detail}
    return {"job": job, "status": "fetch_failed", "detail": ""}


def run(
    db_path: Path,
    workers: int,
    include_list: bool = False,
    active_only: bool = False,
) -> dict:
    conn = db.init_db(db_path)
    rows = (
        db.get_active_jobs(conn)
        if active_only
        else [dict(row) for row in conn.execute("SELECT * FROM jobs ORDER BY id")]
    )
    targets = [
        row for row in rows
        if job_cohorts.is_confirmed_current(row)
        and job_details.is_jd_incomplete(row)
        and (include_list or row.get("link_kind") != "list")
        and (
            row.get("jd_status") not in {
                "official_unavailable", "official_sparse", "list_only", "not_required"
            }
            or (include_list and row.get("jd_status") == "list_only")
            or urlparse(str(row.get("jd_url") or "")).netloc.casefold()
            == "join.qq.com"
        )
    ]

    results = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_hydrate, row): row["id"] for row in targets}
        for future in as_completed(futures):
            job_id = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                result = {
                    "job": next(row for row in targets if row["id"] == job_id),
                    "status": "fetch_failed",
                    "detail": "",
                    "error": str(exc),
                }
            job = result["job"]
            if result["detail"]:
                db.update_job_jd(
                    conn,
                    job["id"],
                    result["detail"],
                    jd_url=job.get("jd_url"),
                    link_kind=job.get("link_kind"),
                )
            if result["status"] != "complete":
                db.mark_job_jd_status(conn, job["id"], result["status"])
            results.append({
                "id": job["id"],
                "company": job["company"],
                "title": job["title"],
                "status": result["status"],
                "jd_url": job.get("jd_url") or "",
                "error": result.get("error", ""),
            })

    counts = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    payload = {
        "date": date.today().isoformat(),
        "database": str(db_path),
        "target_count": len(targets),
        "counts": counts,
        "items": sorted(results, key=lambda row: row["id"]),
    }
    output = ROOT / "outputs" / f"jd_hydration_{date.today():%Y%m%d}.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    conn.close()
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "jobs.db")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--include-list", action="store_true")
    parser.add_argument("--active-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(
        run(
            args.db,
            args.workers,
            include_list=args.include_list,
            active_only=args.active_only,
        ),
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
