"""Repair legacy GenericRender rows whose city field contains whole card copy."""

from __future__ import annotations

import argparse
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

from crawlers.generic_render import GenericRenderCrawler


_POLLUTION_MARKERS = (
    "岗位职责", "工作地点", "查看详情", "立即申请", "职位类别", "全部职位",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "jobs.db")
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "outputs" / "render_city_repair_20260725.json",
    )
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    render_companies = {
        item["name"]
        for item in config.get("companies", [])
        if item.get("crawler") == "render"
    }
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = [
        dict(row)
        for row in conn.execute("SELECT id, company, title, city FROM jobs")
        if row["company"] in render_companies
    ]
    changes = []
    for row in rows:
        old = str(row.get("city") or "")
        if len(old) <= 20 and not any(marker in old for marker in _POLLUTION_MARKERS):
            continue
        new = GenericRenderCrawler._extract_job_city(row["title"], old)
        if new != old:
            changes.append(
                {
                    "id": row["id"],
                    "company": row["company"],
                    "title": row["title"],
                    "old_city": old,
                    "new_city": new,
                }
            )

    summary = {"rows_checked": len(rows), "changes": changes, "dry_run": args.dry_run}
    if not args.dry_run and changes:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = args.db.with_name(f"{args.db.name}.bak_before_city_repair_{stamp}")
        conn.commit()
        shutil.copy2(args.db, backup)
        conn.executemany(
            "UPDATE jobs SET city = ? WHERE id = ?",
            [(item["new_city"], item["id"]) for item in changes],
        )
        conn.commit()
        summary["backup"] = str(backup.resolve())
        summary["integrity_check"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**summary, "changes": len(changes)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
