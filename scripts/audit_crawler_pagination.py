"""Inspect pagination safeguards for every configured crawler without calling AI."""

from __future__ import annotations

import csv
import inspect
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crawlers import CRAWLER_MAP  # noqa: E402


def _classify(crawler_key: str) -> dict[str, str]:
    crawler_cls = CRAWLER_MAP.get(crawler_key)
    if crawler_cls is None:
        return {"strategy": "UNKNOWN", "page_size": "", "max_pages": "", "risk": "未注册 crawler"}

    # Subclasses such as Xiaomi and ByteDance inherit the actual paging loop
    # from their platform base class, so inspect the complete local MRO.
    source = "\n".join(
        inspect.getsource(cls)
        for cls in crawler_cls.mro()
        if cls.__module__.startswith("crawlers.")
    )
    page_size = getattr(crawler_cls, "PAGE_SIZE", "")
    max_pages = getattr(crawler_cls, "MAX_PAGES", "")
    page_loop = bool(re.search(r"\b(?:while|for)\b[\s\S]{0,140}\bpage", source, re.I))
    next_button = "pagination-next" in source or "btn-next" in source
    total_based = any(token in source for token in ("totalPage", "total_pages", "totalCount", "hasMore", "has_more"))

    if page_loop and total_based:
        strategy = "API_TOTAL_OR_HAS_MORE"
        risk = "需关注固定 MAX_PAGES 是否小于官网总页数" if max_pages else "按接口总数或 hasMore 翻页"
    elif page_loop or next_button:
        strategy = "UI_OR_HEURISTIC_PAGINATION"
        risk = "需用官网页数或去重结果复核，防止 UI 选择器失效"
    else:
        strategy = "SINGLE_RESPONSE_OR_STATIC_PAGE"
        risk = "页面若存在分页，当前实现可能只读取第一页，必须人工/接口复核"
    return {
        "strategy": strategy,
        "page_size": str(page_size),
        "max_pages": str(max_pages),
        "risk": risk,
    }


def main() -> None:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}
    rows = []
    for company in config.get("companies", []):
        audit = _classify(company.get("crawler", ""))
        rows.append({
            "company": company.get("name", ""),
            "crawler": company.get("crawler", ""),
            "careers_url": company.get("careers_url", ""),
            **audit,
        })

    output = ROOT / "outputs" / "crawler_pagination_audit.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = ["company", "crawler", "careers_url", "strategy", "page_size", "max_pages", "risk"]
    with output.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    summary: dict[str, int] = {}
    for row in rows:
        summary[row["strategy"]] = summary.get(row["strategy"], 0) + 1
    print(f"audited={len(rows)} output={output}")
    print(summary)


if __name__ == "__main__":
    main()
