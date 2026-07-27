"""Audit one live job-link sample per company and link kind.

This is deliberately read-only: it never crawls or changes the database.  It
helps distinguish public job detail pages from list pages, login redirects and
unreachable links before changing crawler behaviour.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db import is_listing_url

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"


def samples(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT company, link_kind, title, jd_url
           FROM jobs
           WHERE jd_url <> ''
           GROUP BY company, link_kind
           ORDER BY company, link_kind"""
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def check(sample: dict) -> dict:
    result = dict(sample)
    url = sample["jd_url"]
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"},
            timeout=20,
            allow_redirects=True,
            stream=True,
        )
        result["status"] = response.status_code
        result["final_url"] = response.url
        result["redirected"] = "yes" if response.url != url else "no"
        final = response.url.casefold()
        if "login" in final or "passport" in final:
            result["verdict"] = "login_redirect"
        elif is_listing_url(response.url):
            result["verdict"] = "list_route"
        elif 200 <= response.status_code < 400:
            result["verdict"] = "reachable"
        else:
            result["verdict"] = "http_error"
    except requests.RequestException as exc:
        result["status"] = ""
        result["final_url"] = ""
        result["redirected"] = ""
        result["verdict"] = "request_failed"
        result["error"] = str(exc)[:180]
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/jobs.db")
    parser.add_argument("--out", default="outputs/job_link_audit.csv")
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()

    rows = samples(Path(args.db))
    checked: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(check, row) for row in rows]
        for future in as_completed(futures):
            checked.append(future.result())

    checked.sort(key=lambda row: (row["company"], row["link_kind"]))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = ["company", "link_kind", "title", "jd_url", "status", "final_url", "redirected", "verdict", "error"]
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(checked)

    summary: dict[str, int] = {}
    for row in checked:
        summary[row["verdict"]] = summary.get(row["verdict"], 0) + 1
    print(f"audited={len(checked)} output={output}")
    print(summary)


if __name__ == "__main__":
    main()
