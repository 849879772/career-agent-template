"""一次性查看全部已抓取/已分析的岗位，生成累计报告并打开。

用法：
    python view_all.py
"""

import json
import os
import webbrowser
from datetime import date
from pathlib import Path

import db as db_module
import reporter


def fetch_all(conn) -> dict:
    """返回 DB 中所有岗位 + 各自的分析（若有）。"""
    rows = conn.execute(
        "SELECT * FROM jobs ORDER BY crawled_at DESC, id DESC"
    ).fetchall()
    items = []
    for row in rows:
        job = dict(row)
        analysis_row = conn.execute(
            "SELECT * FROM job_analysis WHERE job_id = ?", (job["id"],)
        ).fetchone()
        if analysis_row:
            analysis = dict(analysis_row)
            analysis["advantages"] = json.loads(analysis["advantages"] or "[]")
            analysis["gaps"] = json.loads(analysis["gaps"] or "[]")
        else:
            analysis = None
        items.append({"job": job, "analysis": analysis})
    return {"date": "累计全部", "items": items,
            "applications": db_module.get_applications(conn)}


def main():
    db_path = Path(__file__).parent / "data" / "jobs.db"
    if not db_path.exists():
        print(f"找不到数据库：{db_path}，请先运行 main.py")
        return

    conn = db_module.init_db(str(db_path))
    data = fetch_all(conn)
    conn.close()

    if not data["items"]:
        print("数据库里没有岗位记录")
        return

    today = date.today().isoformat()
    # 用今天日期生成，「今日新增」过滤才生效；out_name=index 与线上首页一致
    report_path = reporter.generate_report(today, data, "reports", out_name="index")

    print(f"\n累计报告已生成：{report_path}")
    print(f"  共 {len(data['items'])} 个岗位")
    analyzed = sum(1 for i in data["items"] if i["analysis"])
    print(f"  其中 {analyzed} 个已分析、{len(data['items']) - analyzed} 个未分析")

    if not os.environ.get("CI"):  # CI（含 sync_report workflow）只重生报告，不开浏览器
        webbrowser.open(f"file:///{report_path.replace(os.sep, '/')}")


if __name__ == "__main__":
    main()
