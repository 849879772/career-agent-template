"""Live audit every configured company crawler for formal campus jobs.

This script runs the real crawler for each company, applies the same formal
campus filter used by main.py, and checkpoints JSON/CSV results after every
company. It is intentionally stricter than config validation: a company only
passes when at least one non-intern, non-social job remains after filtering.
"""

import argparse
import csv
import io
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent))

import job_filters  # noqa: E402
from crawlers import CRAWLER_MAP  # noqa: E402

ROOT = Path.cwd()
JSON_PATH = Path("data") / "campus_crawl_audit.json"
CSV_PATH = Path("data") / "campus_crawl_audit.csv"


def _load_companies() -> list[dict]:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    return cfg.get("companies", [])


def _sample(jobs: list[dict], n: int = 5) -> list[dict]:
    return [
        {
            "title": j.get("title", ""),
            "city": j.get("city", ""),
            "url": j.get("jd_url", ""),
        }
        for j in jobs[:n]
    ]


def audit_one(company: dict) -> dict:
    name = company.get("name", "")
    crawler = company.get("crawler", "")
    url = company.get("careers_url", "")
    started = time.time()
    result = {
        "name": name,
        "crawler": crawler,
        "careers_url": url,
        "raw_count": 0,
        "formal_count": 0,
        "dropped_count": 0,
        "verdict": "ERROR",
        "reason": "",
        "formal_samples": [],
        "dropped_samples": [],
        "elapsed_sec": 0.0,
    }
    cls = CRAWLER_MAP.get(crawler)
    if not cls:
        result["verdict"] = "UNREGISTERED"
        result["reason"] = f"unknown crawler: {crawler}"
        return result

    try:
        jobs = cls(name, url).fetch() or []
    except Exception as exc:  # noqa: BLE001
        result["verdict"] = "ERROR"
        result["reason"] = f"{type(exc).__name__}: {exc}"
        result["elapsed_sec"] = round(time.time() - started, 2)
        return result

    formal, dropped = job_filters.filter_formal_campus_jobs(jobs)
    result.update(
        raw_count=len(jobs),
        formal_count=len(formal),
        dropped_count=len(dropped),
        formal_samples=_sample(formal),
        dropped_samples=_sample(dropped),
        elapsed_sec=round(time.time() - started, 2),
    )
    if formal:
        result["verdict"] = "PASS"
    elif jobs:
        result["verdict"] = "ONLY_FILTERED"
        result["reason"] = "crawler returned jobs, but all were filtered as intern/social"
    else:
        result["verdict"] = "EMPTY"
        result["reason"] = "crawler returned 0 jobs"
    return result


def _load_existing() -> dict[str, dict]:
    if not JSON_PATH.exists():
        return {}
    try:
        rows = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return {r["name"]: r for r in rows}


def _save(rows_by_name: dict[str, dict], order: list[str]) -> None:
    rows = [rows_by_name[n] for n in order if n in rows_by_name]
    JSON_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = [
        "name", "crawler", "careers_url", "verdict", "reason",
        "raw_count", "formal_count", "dropped_count", "elapsed_sec",
    ]
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fields})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    companies = _load_companies()
    selected = companies[args.offset:]
    if args.limit:
        selected = selected[:args.limit]
    order = [c["name"] for c in companies]
    rows_by_name = _load_existing() if args.resume else {}
    pending = [c for c in selected if not (args.resume and c["name"] in rows_by_name)]

    print(f"审计 {len(pending)} 家 / 选择范围 {len(selected)} 家（workers={args.workers}, resume={args.resume}）")
    if not pending:
        _save(rows_by_name, order)
        return

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futures = {ex.submit(audit_one, c): c for c in pending}
        done = 0
        for fut in as_completed(futures):
            c = futures[fut]
            done += 1
            try:
                row = fut.result()
            except Exception as exc:  # noqa: BLE001
                row = {
                    "name": c.get("name", ""),
                    "crawler": c.get("crawler", ""),
                    "careers_url": c.get("careers_url", ""),
                    "raw_count": 0,
                    "formal_count": 0,
                    "dropped_count": 0,
                    "verdict": "ERROR",
                    "reason": f"future failed: {type(exc).__name__}: {exc}",
                    "formal_samples": [],
                    "dropped_samples": [],
                    "elapsed_sec": 0.0,
                }
            rows_by_name[row["name"]] = row
            _save(rows_by_name, order)
            print(
                f"[{done}/{len(pending)}] {row['verdict']:<13} "
                f"{row['name']} raw={row['raw_count']} formal={row['formal_count']} "
                f"dropped={row['dropped_count']} {row['reason']}",
                flush=True,
            )


if __name__ == "__main__":
    main()
