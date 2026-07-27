"""Audit stored jobs for internships, early batches, and review-only mentions."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import job_filters  # noqa: E402


SPECIAL_PROGRAM_WORDS = (
    "青云计划", "Super Sparks", "TOP Talent", "T-Star", "TGT", "PonyStar",
    "飞凡计划", "超新星计划", "清华顶尖人才专项",
)


def _excerpt(text: str, needle: str = "实习", radius: int = 90) -> str:
    compact = " ".join((text or "").split())
    pos = compact.find(needle)
    if pos < 0:
        return compact[: radius * 2]
    return compact[max(0, pos - radius): pos + len(needle) + radius]


def _classification(job: dict) -> tuple[str, str] | None:
    intern = job_filters.internship_reason(job)
    if intern:
        return "确认排除：实习岗位", intern
    early = job_filters.early_batch_reason(job)
    if early:
        return "确认排除：提前批岗位", early
    body = str(job.get("jd_raw") or "")
    if "实习" in body:
        return "复核保留：仅提及实习经历", "未命中实习岗位强规则"
    text = " ".join(str(job.get(field) or "") for field in ("title", "job_type", "jd_raw"))
    if any(word.lower() in text.lower() for word in SPECIAL_PROGRAM_WORDS):
        return "复核保留：专项人才计划", "未明确标注提前批或实习"
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "jobs.db"))
    parser.add_argument("--active-days", type=int, default=3)
    parser.add_argument("--output-prefix")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    jobs = [dict(row) for row in conn.execute("SELECT * FROM jobs ORDER BY company, title")]
    conn.close()

    latest_seen = max((str(job.get("last_seen_at") or "")[:10] for job in jobs), default="")
    cutoff = ""
    if latest_seen:
        cutoff = (datetime.fromisoformat(latest_seen) - timedelta(days=args.active_days - 1)).date().isoformat()

    rows = []
    for job in jobs:
        classification = _classification(job)
        if not classification:
            continue
        status, reason = classification
        body = str(job.get("jd_raw") or "")
        rows.append({
            "范围": "近三日活跃" if str(job.get("last_seen_at") or "")[:10] >= cutoff else "历史非活跃",
            "结论": status,
            "原因": reason,
            "岗位ID": job.get("id"),
            "公司": job.get("company") or "",
            "岗位": job.get("title") or "",
            "招聘类型": job.get("job_type") or "",
            "最后抓取": job.get("last_seen_at") or "",
            "岗位地址": job.get("jd_url") or "",
            "正文片段": _excerpt(body, "实习" if "实习" in body else "提前批"),
        })

    prefix = Path(args.output_prefix) if args.output_prefix else (
        ROOT / "outputs" / f"formal_campus_content_audit_{date.today():%Y%m%d}"
    )
    prefix.parent.mkdir(parents=True, exist_ok=True)
    csv_path = prefix.with_suffix(".csv")
    json_path = prefix.with_suffix(".json")
    md_path = prefix.with_suffix(".md")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)

    active = [row for row in rows if row["范围"] == "近三日活跃"]
    summary = {
        "数据库岗位数": len(jobs),
        "数据库最新抓取日期": latest_seen,
        "活跃窗口起始日期": cutoff,
        "活跃复核项": dict(Counter(row["结论"] for row in active)),
        "全库复核项": dict(Counter(row["结论"] for row in rows)),
        "活跃排除公司": dict(Counter(
            row["公司"] for row in active if row["结论"].startswith("确认排除")
        )),
    }
    json_path.write_text(json.dumps({"summary": summary, "items": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 正式校招内容详细筛查",
        "",
        f"- 数据库岗位：**{len(jobs)}**",
        f"- 最新抓取日期：**{latest_seen}**",
        f"- 活跃窗口：**{cutoff} 至 {latest_seen}**",
        "",
        "## 近三日活跃岗位结论",
        "",
    ]
    for label, count in Counter(row["结论"] for row in active).most_common():
        lines.append(f"- {label}：**{count}**")
    lines.extend(["", "## 确认排除项按公司分布", ""])
    excluded = Counter(row["公司"] for row in active if row["结论"].startswith("确认排除"))
    for company, count in excluded.most_common():
        lines.append(f"- {company}：{count}")
    lines.extend([
        "",
        "## 判定说明",
        "",
        "- 只有标题、招聘类型、URL、页面元数据、明确实习项目或当前实习周期要求命中时，才判为实习岗位。",
        "- ‘有实习经历者优先’只进入人工复核保留项，不会据此删除正式岗位。",
        "- 只有标题、招聘类型、正文或 URL 明确出现提前批/提前招聘/提前选拔/预招聘时，才判为提前批。",
        "- 青云、TOP Talent、Super Sparks 等专项计划若标注正式且未出现提前批/实习，继续保留。",
        "- 完整逐岗位明细见同名 CSV 与 JSON。",
    ])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(md_path)


if __name__ == "__main__":
    main()
