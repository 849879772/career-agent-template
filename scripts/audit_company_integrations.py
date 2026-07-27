"""Read-only health audit for every configured recruitment integration.

The audit deliberately does not call the AI analyzer or write to SQLite.  It
checks the configured entry, runs the production crawler, applies the formal
campus-job filter, samples a direct job link, and records cohort distribution.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sqlite3
import sys
import time
from multiprocessing import get_context
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from crawlers import CRAWLER_MAP  # noqa: E402
from job_filters import cohort_year, filter_formal_campus_jobs  # noqa: E402

DEFAULT_OUT = ROOT / "outputs" / "company_integration_audit.csv"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
FIELDS = [
    "company", "crawler", "careers_url", "checked_at", "entry_http", "entry_final_url",
    "raw_jobs", "formal_jobs", "filtered_jobs", "cohort_2027", "cohort_previous",
    "cohort_unknown", "detail_jobs", "sample_title", "sample_job_url", "sample_link_http",
    "sample_link_final_url", "status", "action", "error",
]


def _check_url(url: str) -> tuple[str, str]:
    if not url:
        return "missing", ""
    try:
        response = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        return str(response.status_code), response.url
    except requests.RequestException as exc:
        return f"request_error:{type(exc).__name__}", ""


def _empty_result(entry: dict[str, str]) -> dict[str, Any]:
    return {
        "company": entry["name"], "crawler": entry["crawler"], "careers_url": entry["careers_url"],
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "entry_http": "", "entry_final_url": "", "raw_jobs": 0, "formal_jobs": 0,
        "filtered_jobs": 0, "cohort_2027": 0, "cohort_previous": 0, "cohort_unknown": 0,
        "detail_jobs": 0, "sample_title": "", "sample_job_url": "", "sample_link_http": "",
        "sample_link_final_url": "", "status": "", "action": "", "error": "",
    }


def audit_company(entry: dict[str, str]) -> dict[str, Any]:
    result = _empty_result(entry)
    result["entry_http"], result["entry_final_url"] = _check_url(entry["careers_url"])
    crawler_cls = CRAWLER_MAP.get(entry["crawler"])
    if crawler_cls is None:
        result.update(status="CRAWLER_UNKNOWN", action="修复 config.yaml 中的 crawler 键", error="crawler 未注册")
        return result

    try:
        raw_jobs = crawler_cls(entry["name"], entry["careers_url"]).fetch() or []
    except Exception as exc:  # noqa: BLE001
        result.update(
            status="CRAWLER_ERROR",
            action="检查官网入口、WAF 和对应 crawler 解析规则",
            error=f"{type(exc).__name__}: {exc}",
        )
        return result

    formal_jobs, filtered_jobs = filter_formal_campus_jobs(raw_jobs)
    result["raw_jobs"] = len(raw_jobs)
    result["formal_jobs"] = len(formal_jobs)
    result["filtered_jobs"] = len(filtered_jobs)
    cohorts = [cohort_year(job) for job in formal_jobs]
    result["cohort_2027"] = sum(year == 2027 for year in cohorts)
    result["cohort_previous"] = sum(year is not None and year < 2027 for year in cohorts)
    result["cohort_unknown"] = sum(year is None for year in cohorts)

    detail_jobs = [job for job in formal_jobs if job.get("link_kind", "detail") == "detail" and job.get("jd_url")]
    result["detail_jobs"] = len(detail_jobs)
    if detail_jobs:
        sample = detail_jobs[0]
        result["sample_title"] = str(sample.get("title") or "")
        result["sample_job_url"] = str(sample.get("jd_url") or "")
        result["sample_link_http"], result["sample_link_final_url"] = _check_url(result["sample_job_url"])

    if not raw_jobs:
        result.update(status="EMPTY", action="重新确认官网校招入口，并用项目 crawler 定位失效原因")
    elif not formal_jobs:
        result.update(status="FILTERED_ALL", action="确认该入口是否只有实习或社招；不要将其作为正式校招来源")
    elif result["cohort_2027"] == 0 and result["cohort_previous"] > 0:
        result.update(
            status="PREVIOUS_ONLY_REVIEW",
            action="人工确认今年是否尚未开招；若官网已有 27 届，重新发现当前校招入口并替换旧链接",
        )
    elif not detail_jobs:
        result.update(status="LIST_ONLY", action="岗位可抓取但没有直达详情链接；补充详情 URL 解析后再展示投递入口")
    elif not result["sample_link_http"].startswith("2"):
        result.update(
            status="DETAIL_REACHABILITY_REVIEW",
            action="样本详情页请求未返回 2xx；确认是否 WAF、登录跳转或详情链接规则失效",
        )
    elif result["cohort_2027"] == 0 and result["cohort_unknown"]:
        result.update(status="COHORT_UNKNOWN", action="来源可用；招聘页未明确届别，开招后复查届别标签")
    else:
        result.update(status="HEALTHY", action="无需处理")
    return result


def _load_companies() -> list[dict[str, str]]:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}
    rows = [
        {"name": item["name"], "careers_url": item["careers_url"], "crawler": item["crawler"]}
        for item in config.get("companies", [])
        if item.get("name") and item.get("careers_url") and item.get("crawler")
    ]
    # A later entry is the newest integration for the same canonical company.
    # Keep one worker per company so stale aliases cannot overwrite its audit.
    return list({item["name"]: item for item in rows}.values())


def _write_report(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    out_path.with_suffix(".json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _audit_worker(entry: dict[str, str], result_queue: Any) -> None:
    """Run one crawler in an isolated process so a broken renderer cannot stall the batch."""
    try:
        result_queue.put((entry["name"], audit_company(entry)))
    except Exception as exc:  # noqa: BLE001
        row = _empty_result(entry)
        row.update(status="AUDIT_ERROR", action="检查审计脚本和 crawler", error=f"{type(exc).__name__}: {exc}")
        result_queue.put((entry["name"], row))


def main() -> int:
    parser = argparse.ArgumentParser(description="只读审计 config.yaml 的公司招聘接入")
    parser.add_argument("--workers", type=int, default=8, help="并发 crawler 数，默认 8")
    parser.add_argument("--limit", type=int, help="仅审计前 N 家，用于试跑")
    parser.add_argument("--company", action="append", default=[], help="仅审计名称包含该文本的公司，可重复")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="CSV 输出路径")
    parser.add_argument("--timeout", type=int, default=75, help="单家公司最长秒数，默认 75")
    parser.add_argument("--resume", action="store_true", help="保留已有输出，继续审计尚未完成的公司")
    parser.add_argument("--only-no-job-db", action="store_true", help="仅审计数据库中还没有岗位的公司")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "jobs.db", help="用于零岗位筛选的数据库")
    args = parser.parse_args()

    companies = _load_companies()
    if args.only_no_job_db:
        conn = sqlite3.connect(args.db)
        companies_with_jobs = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT company FROM jobs WHERE company <> ''"
            )
        }
        conn.close()
        companies = [
            item for item in companies if item["name"] not in companies_with_jobs
        ]
    if args.company:
        terms = [term.lower() for term in args.company]
        companies = [item for item in companies if any(term in item["name"].lower() for term in terms)]
    if args.limit:
        companies = companies[:args.limit]
    previous_rows: dict[str, dict[str, Any]] = {}
    json_path = args.out.with_suffix(".json")
    if args.resume and json_path.exists():
        try:
            previous_rows = {row["company"]: row for row in json.loads(json_path.read_text(encoding="utf-8"))}
        except (OSError, ValueError, KeyError):
            previous_rows = {}
        companies = [item for item in companies if item["name"] not in previous_rows]
    if not companies:
        print("没有匹配的公司。")
        return 2

    total = len(companies) + len(previous_rows)
    print(f"开始只读审计 {len(companies)} 家待检公司（总计 {total}），最大并发 {args.workers}；不会调用 AI 或写入岗位数据库。", flush=True)
    rows_by_name = dict(previous_rows)
    pending = iter(companies)
    active: dict[str, tuple[Any, dict[str, str], float]] = {}
    context = get_context("spawn")
    result_queue = context.Queue()
    completed = len(rows_by_name)
    pending_exhausted = False

    while active or not pending_exhausted:
        while len(active) < max(1, args.workers):
            try:
                entry = next(pending)
            except StopIteration:
                pending_exhausted = True
                break
            process = context.Process(target=_audit_worker, args=(entry, result_queue))
            process.start()
            active[entry["name"]] = (process, entry, time.monotonic())

        try:
            name, row = result_queue.get(timeout=0.25)
            process, entry, _started = active.pop(name)
            process.join(timeout=1)
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
        except Exception:  # Queue timeout; check for hung workers below.
            pass
        else:
            rows_by_name[name] = row
            completed += 1
            _write_report(list(rows_by_name.values()), args.out)
            print(f"[{completed}/{total}] {name}: {row['status']} ({row['formal_jobs']} 正式岗位, 27届 {row['cohort_2027']})", flush=True)

        now = time.monotonic()
        for name, (process, entry, started) in list(active.items()):
            if now - started <= args.timeout:
                continue
            process.terminate()
            process.join(timeout=3)
            row = _empty_result(entry)
            row.update(
                status="AUDIT_TIMEOUT",
                action="页面或 crawler 超时；单独排查该公司入口和渲染规则",
                error=f"超过 {args.timeout} 秒未完成",
            )
            active.pop(name)
            rows_by_name[name] = row
            completed += 1
            _write_report(list(rows_by_name.values()), args.out)
            print(f"[{completed}/{total}] {name}: AUDIT_TIMEOUT (超过 {args.timeout}s)", flush=True)

    all_companies = _load_companies()
    rows = [rows_by_name[item["name"]] for item in all_companies if item["name"] in rows_by_name]
    _write_report(rows, args.out)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print("审计完成：" + "；".join(f"{status} {count}" for status, count in sorted(counts.items())))
    print(f"CSV：{args.out}")
    print(f"JSON：{args.out.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
