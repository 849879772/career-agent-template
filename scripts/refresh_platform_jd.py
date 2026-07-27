"""Refresh richer JD fields for API crawlers without inserting new jobs."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crawlers import CRAWLER_MAP
import db


API_CRAWLER_KEYS = {
    "alibaba", "baidu", "boe", "gbits", "hikvision", "huawei", "inovance",
    "jd", "kuaishou", "leihuo", "meituan", "netease", "oppo", "sf",
}


def refresh(db_path: Path) -> dict:
    conn = db.init_db(str(db_path))
    found = updated = 0
    try:
        with (ROOT / "config.yaml").open(encoding="utf-8") as handle:
            companies = yaml.safe_load(handle).get("companies") or []
        for company in companies:
            crawler_key = company.get("crawler")
            if crawler_key not in API_CRAWLER_KEYS:
                continue
            crawler_class = CRAWLER_MAP.get(crawler_key)
            if crawler_class is None:
                continue
            crawler = crawler_class(company["name"], company["careers_url"])
            for job in crawler.fetch():
                job_id = db.find_job_id(conn, job)
                if job_id is None:
                    continue
                found += 1
                updated += int(db.update_job_jd(conn, job_id, job.get("jd_raw", "")))
        return {"matched": found, "updated": updated}
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    args = parser.parse_args()
    print(refresh(args.db.resolve()))


if __name__ == "__main__":
    main()
