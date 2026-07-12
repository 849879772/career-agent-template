"""Automatically classify crawler URL rows to reduce manual review.

The validator combines:
- config entry reachability and simple page signals;
- existing live crawler audit counts from data/campus_crawl_audit.json;
- crawler/access type risk rules.

It does not replace human review for suspicious rows; it prioritizes it.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.generate_effective_url_rows import infer  # noqa: E402

import yaml  # noqa: E402


OUT_DIR = Path("outputs/crawler_effective_urls")
JSON_OUT = OUT_DIR / "auto_validation_results.json"
CSV_OUT = OUT_DIR / "auto_validation_results.csv"
AUDIT_PATH = Path("data/campus_crawl_audit.json")

CAMPUS_RE = re.compile(
    r"校园招聘|校招|应届生|毕业生|校园职位|校招岗位|campus|graduate|fresh\s*graduate|"
    r"university|student|school",
    re.I,
)
JOB_RE = re.compile(r"职位|岗位|在招|招聘|position|job|opening|recruit", re.I)
RISK_RE = re.compile(r"社会招聘|社招|experienced|实习生招聘|internship", re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
PLATFORM_CRAWLERS = {"moka", "beisen", "feishu", "hotjob", "render", "unitree"}


def dedupe_rows(rows: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for row in rows:
        key = (
            str(row.get("crawler", "")).strip().lower(),
            str(row.get("config_url", "")).strip().rstrip("/").lower(),
            str(row.get("effective_url", "")).strip().rstrip("/").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def load_rows() -> list[dict]:
    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    return dedupe_rows([infer(company) for company in cfg.get("companies", [])])


def load_audit() -> dict[str, dict]:
    if not AUDIT_PATH.exists():
        return {}
    rows = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    return {row.get("name", ""): row for row in rows}


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def fetch_entry(url: str) -> dict:
    result = {
        "status": "",
        "final_url": "",
        "title": "",
        "campus_signal": False,
        "job_signal": False,
        "risk_signal": False,
        "fetch_error": "",
    }
    if not url.startswith(("http://", "https://")):
        result["fetch_error"] = "not http url"
        return result
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            timeout=12,
            allow_redirects=True,
        )
        text = resp.text[:200000]
        title_match = TITLE_RE.search(text)
        title = clean_text(title_match.group(1))[:120] if title_match else ""
        combined = f"{url} {resp.url} {title} {text[:50000]}"
        result.update(
            status=resp.status_code,
            final_url=resp.url,
            title=title,
            campus_signal=bool(CAMPUS_RE.search(combined)),
            job_signal=bool(JOB_RE.search(combined)),
            risk_signal=bool(RISK_RE.search(combined)),
        )
    except Exception as exc:  # noqa: BLE001
        result["fetch_error"] = f"{type(exc).__name__}: {exc}"
    return result


def classify(row: dict, audit: dict, entry: dict) -> tuple[str, str, str]:
    crawler = row.get("crawler", "")
    access_type = row.get("access_type", "")
    effective = row.get("effective_url", "")
    status = entry.get("status")
    audit_verdict = audit.get("verdict", "")
    formal = int(audit.get("formal_count") or 0)
    raw = int(audit.get("raw_count") or 0)
    dropped = int(audit.get("dropped_count") or 0)
    status_ok = isinstance(status, int) and status < 400
    status_bad = isinstance(status, int) and status >= 400
    entry_has_signal = bool(entry.get("campus_signal") and entry.get("job_signal"))
    is_api = "API" in access_type

    if "PlaceholderCrawler" in effective or access_type == "无":
        return "疑似错误", "高", "当前是占位 crawler，没有真实访问职位页"
    if audit_verdict in {"ERROR", "UNREGISTERED"}:
        return "疑似错误", "高", f"实抓审计失败：{audit_verdict} {audit.get('reason', '')}".strip()
    if audit_verdict == "PASS" and formal > 0:
        if status_bad:
            return "需人工确认", "中", f"crawler 已抓到 {formal} 个正式岗位，但配置入口 HTTP {status}"
        if crawler in PLATFORM_CRAWLERS or is_api:
            return "自动通过", "高", f"crawler 已抓到 {formal} 个正式岗位；平台/API 型入口无需逐页人工确认"
        if entry_has_signal:
            return "自动通过", "高", f"crawler 已抓到 {formal} 个正式岗位，配置入口有校招/岗位信号"
        return "需人工确认", "中", f"crawler 已抓到 {formal} 个正式岗位，但配置入口静态文本校招信号不足"
    if audit_verdict == "ONLY_FILTERED" or (raw > 0 and formal == 0 and dropped > 0):
        return "需人工确认", "中", "crawler 只抓到被过滤的实习/社招岗位，需确认当前是否秋招未开或入口不对"
    if audit_verdict == "EMPTY":
        if status_bad:
            return "疑似错误", "高", f"crawler 抓 0 且配置入口 HTTP {status}"
        if status_ok and entry_has_signal:
            return "需人工确认", "中", "配置入口像校招页但 crawler 抓 0，需确认页面结构或秋招状态"
        return "需人工确认", "低", "crawler 抓 0，配置入口未发现足够岗位信号，可能秋招未开"
    if status_bad:
        return "疑似错误", "中", f"配置入口 HTTP {status}"
    return "需人工确认", "低", "缺少实抓审计结果或信号不足"


def validate_one(row: dict, audit_by_name: dict[str, dict]) -> dict:
    entry = fetch_entry(row.get("config_url", ""))
    audit = audit_by_name.get(row.get("company", ""), {})
    verdict, confidence, reason = classify(row, audit, entry)
    return {
        **row,
        "auto_verdict": verdict,
        "confidence": confidence,
        "auto_reason": reason,
        "http_status": entry.get("status", ""),
        "final_url": entry.get("final_url", ""),
        "page_title": entry.get("title", ""),
        "campus_signal": "是" if entry.get("campus_signal") else "否",
        "job_signal": "是" if entry.get("job_signal") else "否",
        "risk_signal": "是" if entry.get("risk_signal") else "否",
        "fetch_error": entry.get("fetch_error", ""),
        "audit_verdict": audit.get("verdict", ""),
        "raw_count": audit.get("raw_count", ""),
        "formal_count": audit.get("formal_count", ""),
        "dropped_count": audit.get("dropped_count", ""),
        "audit_reason": audit.get("reason", ""),
    }


def save(rows: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = [
        "company", "crawler", "config_url", "effective_url", "access_type",
        "auto_verdict", "confidence", "auto_reason", "http_status", "final_url",
        "page_title", "campus_signal", "job_signal", "risk_signal", "fetch_error",
        "audit_verdict", "raw_count", "formal_count", "dropped_count", "audit_reason",
    ]
    with CSV_OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def main() -> None:
    rows = load_rows()
    audit_by_name = load_audit()
    done = []
    with ThreadPoolExecutor(max_workers=16) as executor:
        future_map = {executor.submit(validate_one, row, audit_by_name): row for row in rows}
        for idx, future in enumerate(as_completed(future_map), start=1):
            result = future.result()
            done.append(result)
            if idx % 25 == 0:
                print(f"validated {idx}/{len(rows)}", flush=True)
    order = {(
        row.get("crawler", ""),
        row.get("config_url", ""),
        row.get("effective_url", ""),
        row.get("company", ""),
    ): i for i, row in enumerate(rows)}
    done.sort(key=lambda r: order.get((r.get("crawler", ""), r.get("config_url", ""), r.get("effective_url", ""), r.get("company", "")), 10**9))
    save(done)
    counts = {}
    for row in done:
        counts[row["auto_verdict"]] = counts.get(row["auto_verdict"], 0) + 1
    print(JSON_OUT.resolve())
    print(counts)


if __name__ == "__main__":
    main()
