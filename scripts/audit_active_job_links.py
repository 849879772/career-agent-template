"""Audit every currently active job URL and aggregate failures by route template.

The audit is intentionally read-only. URL fragments are kept for per-job
classification, while HTTP requests are de-duplicated after removing fragments
because SPA detail pages often share one network document.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import threading
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db as db_module

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
)
MAX_BODY_BYTES = 512 * 1024
ERROR_MARKERS = (
    "没有找到页面",
    "页面不存在",
    "页面未找到",
    "找不到页面",
    "访问的页面不存在",
    "职位不存在",
    "岗位不存在",
    "职位已下线",
    "岗位已下线",
    "职位已关闭",
    "职位已失效",
    "招聘已结束",
    "job not found",
    "page not found",
    "job expired",
)
LOGIN_MARKERS = ("/login", "passport", "/signin", "auth/login", "account/login")
KNOWN_BAD_ROUTES = (
    ("zhaopin.meituan.com", "/web/campus/position-detail", "美团旧路由会显示没有找到页面"),
    ("careers.oppo.com", "/university/oppo/campus/post?id=", "OPPO 旧查询路由会打开岗位列表"),
    ("order.dangdang.com", "/invoiceapply/", "发票补开页面不是招聘岗位"),
)
BROWSER_ONLY_HOSTS = {
    # Verified with Chromium on 2026-07-25. Requests fails because of legacy
    # TLS or intermittent gateway timeouts, but the official pages render.
    "runjob.crc.com.cn",
    "campus.topband.com.cn",
}

_local = threading.local()


def _session() -> requests.Session:
    if not hasattr(_local, "session"):
        session = requests.Session()
        session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
            "Range": f"bytes=0-{MAX_BODY_BYTES - 1}",
        })
        _local.session = session
    return _local.session


def _network_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def _jd_detail_id(url: str) -> str:
    parts = urlsplit(url)
    if parts.netloc.casefold() != "campus.jd.com" or "?/details?" in url:
        return ""
    fragment_query = parts.fragment.split("?", 1)[1] if "?" in parts.fragment else ""
    values = parse_qs(fragment_query).get("id", [])
    return values[0] if values and values[0].isdigit() else ""


def _fetch_jd_detail(publish_id: str, timeout: float) -> dict:
    """Validate JD SPA routes against the job-detail API, not its 200 shell."""
    result = {"semantic_check": "request_failed", "semantic_detail": ""}
    try:
        response = _session().post(
            f"https://campus.jd.com/api/wx/position/detail/{publish_id}",
            json={},
            headers={"Referer": "https://campus.jd.com/"},
            timeout=(8, timeout),
        )
        response.raise_for_status()
        body = (response.json().get("body") or {})
        if str(body.get("publishId") or "") == publish_id and body.get("positionName"):
            result["semantic_check"] = "reachable"
            result["semantic_detail"] = str(body["positionName"])[:160]
        else:
            result["semantic_check"] = "expired"
            result["semantic_detail"] = "京东详情接口未返回岗位"
    except (requests.RequestException, ValueError) as exc:
        result["semantic_detail"] = str(exc)[:240]
    return result


def _known_bad_reason(url: str) -> str:
    folded = url.casefold()
    for host, marker, reason in KNOWN_BAD_ROUTES:
        if host in folded and marker in folded:
            return reason
    return ""


def _has_detail_identity(url: str) -> bool:
    parts = urlsplit(url)
    combined = f"{parts.path}?{parts.query}#{parts.fragment}".casefold()
    query = {key.casefold() for key in parse_qs(parts.query)}
    if "?" in parts.fragment:
        query.update(key.casefold() for key in parse_qs(parts.fragment.split("?", 1)[1]))
    id_keys = {
        "id", "jobid", "job_id", "jobadid", "postid", "positionid",
        "advertisementid", "jobunionid", "publishid", "code", "contentid",
        "weizhi",
    }
    if query & id_keys:
        return True
    if re.search(r"(?:^|[/#])(?:job|jobs|post|position|detail)[s-]*/[^/?#]+", combined):
        return True
    if re.search(r"/[0-9a-f]{8}-[0-9a-f-]{20,}(?:/|$)", combined):
        return True
    if re.search(r"/(?:\d{2,}|[0-9a-f]{16,})(?:[./?#]|$)", combined):
        return True
    return False


def _title_matches_page(job_title: str, page_title: str) -> bool:
    def normalize(value: str) -> str:
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (value or "").casefold())

    job = normalize(job_title)
    page = normalize(page_title)
    return len(job) >= 4 and (job in page or (len(page) >= 4 and page in job))


def _fetch(url: str, timeout: float) -> dict:
    result = {
        "status": "",
        "final_url": "",
        "page_title": "",
        "http_verdict": "request_failed",
        "error": "",
    }
    try:
        response = _session().get(
            url,
            timeout=(8, timeout),
            allow_redirects=True,
            stream=True,
        )
        chunks = []
        size = 0
        for chunk in response.iter_content(32768):
            if not chunk:
                continue
            remaining = MAX_BODY_BYTES - size
            chunks.append(chunk[:remaining])
            size += len(chunks[-1])
            if size >= MAX_BODY_BYTES:
                break
        response.close()

        body = b"".join(chunks)
        content_type = response.headers.get("Content-Type", "")
        charset_match = re.search(r"charset=([\w.-]+)", content_type, re.I)
        encoding = response.encoding or (charset_match.group(1) if charset_match else "utf-8")
        text = body.decode(encoding, errors="replace")
        soup = BeautifulSoup(text, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        visible = soup.get_text(" ", strip=True)[:12000].casefold()
        final = response.url

        result.update({
            "status": response.status_code,
            "final_url": final,
            "page_title": title[:160],
        })
        final_folded = final.casefold()
        title_visible = f"{title} {visible}".casefold()
        if response.status_code in (401, 403, 429):
            result["http_verdict"] = "access_blocked"
        elif response.status_code >= 400:
            result["http_verdict"] = "http_error"
        elif any(marker in final_folded for marker in LOGIN_MARKERS):
            result["http_verdict"] = "login_redirect"
        elif any(marker in title_visible for marker in ERROR_MARKERS):
            result["http_verdict"] = "expired_or_error_page"
        else:
            result["http_verdict"] = "reachable"
    except requests.RequestException as exc:
        result["error"] = str(exc)[:240]
    return result


def _round_robin_by_host(urls: set[str]) -> list[str]:
    """Interleave domains so one large platform does not monopolize workers."""
    grouped: dict[str, deque[str]] = defaultdict(deque)
    for url in sorted(urls):
        grouped[urlsplit(url).netloc.casefold()].append(url)
    ordered = []
    hosts = deque(sorted(grouped))
    while hosts:
        host = hosts.popleft()
        ordered.append(grouped[host].popleft())
        if grouped[host]:
            hosts.append(host)
    return ordered


def _load_active_rows(db_path: Path, active_days: int) -> tuple[str, list[dict]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    latest = conn.execute("SELECT MAX(last_seen_at) FROM jobs").fetchone()[0]
    anchor = date.fromisoformat(latest) if latest else date.today()
    cutoff = (anchor - timedelta(days=active_days - 1)).isoformat()
    rows = conn.execute(
        """SELECT id, company, title, jd_url, link_kind, last_seen_at
           FROM jobs
           WHERE last_seen_at >= ? AND jd_url <> ''
           ORDER BY company, id""",
        (cutoff,),
    ).fetchall()
    conn.close()
    return cutoff, [dict(row) for row in rows]


def _route_template(url: str) -> str:
    parts = urlsplit(url)
    path = re.sub(r"[0-9a-f]{8}-[0-9a-f-]{20,}", "{uuid}", parts.path, flags=re.I)
    path = re.sub(r"\d{6,}", "{id}", path)
    fragment = re.sub(r"[0-9a-f]{8}-[0-9a-f-]{20,}", "{uuid}", parts.fragment, flags=re.I)
    fragment = re.sub(r"\d{6,}", "{id}", fragment)
    keys = ",".join(sorted(parse_qs(parts.query)))
    return f"{parts.netloc}{path}?{keys}#{fragment}"[:360]


def _merge(row: dict, fetched: dict, semantic: dict | None = None) -> dict:
    result = dict(row)
    result.update(fetched)
    result["network_url"] = _network_url(row["jd_url"])
    result["route_template"] = _route_template(row["jd_url"])
    result["known_bad_reason"] = _known_bad_reason(row["jd_url"])
    result["has_detail_identity"] = "yes" if _has_detail_identity(row["jd_url"]) else "no"

    semantic = semantic or {"semantic_check": "", "semantic_detail": ""}
    result.update(semantic)

    if semantic.get("semantic_check") == "expired":
        verdict = "expired_or_error_page"
    elif result["known_bad_reason"]:
        verdict = "known_bad_route"
    elif (
        fetched["http_verdict"] == "request_failed"
        and urlsplit(row["jd_url"]).netloc.casefold() in BROWSER_ONLY_HOSTS
    ):
        verdict = "access_blocked"
    elif fetched["http_verdict"] != "reachable":
        verdict = fetched["http_verdict"]
    elif row["link_kind"] == "list":
        verdict = "reachable_list"
    elif not _has_detail_identity(row["jd_url"]) and not _title_matches_page(
        row["title"], fetched.get("page_title", "")
    ):
        verdict = "detail_route_review"
    else:
        verdict = "reachable_detail"
    result["verdict"] = verdict
    return result


def _write_summary(path: Path, rows: list[dict], cutoff: str, request_count: int) -> None:
    verdicts = Counter(row["verdict"] for row in rows)
    companies = defaultdict(Counter)
    routes = defaultdict(Counter)
    for row in rows:
        companies[row["company"]][row["verdict"]] += 1
        routes[(row["company"], row["route_template"])][row["verdict"]] += 1

    attention = {
        "known_bad_route", "http_error", "expired_or_error_page",
        "login_redirect", "request_failed", "detail_route_review",
    }
    lines = [
        "# 当前活跃岗位链接全量审计",
        "",
        f"- 活跃窗口起点：`{cutoff}`",
        f"- 岗位链接：**{len(rows)}** 条",
        f"- 实际 HTTP 请求：**{request_count}** 次（SPA 片段地址已去重）",
        f"- 公司：**{len(companies)}** 家",
        "",
        "## 结论统计",
        "",
        "| 结论 | 数量 |",
        "| --- | ---: |",
    ]
    lines.extend(f"| `{key}` | {value} |" for key, value in verdicts.most_common())
    lines.extend(["", "## 需要处理的路由模板", "", "| 公司 | 路由模板 | 结论 | 岗位数 |", "| --- | --- | --- | ---: |"])
    flagged = []
    for (company, template), counts in routes.items():
        for verdict, count in counts.items():
            if verdict in attention:
                flagged.append((count, company, template, verdict))
    for count, company, template, verdict in sorted(flagged, reverse=True):
        safe_template = template.replace("|", "\\|")
        lines.append(f"| {company} | `{safe_template}` | `{verdict}` | {count} |")
    if not flagged:
        lines.append("| - | - | 无 | 0 |")

    lines.extend([
        "",
        "> `access_blocked` 表示站点拒绝自动请求，不等同于岗位失效；需按公司和路由模板用浏览器抽样复核。",
        "> `reachable_detail` 表示地址和详情标识结构正常且页面可达；动态页面的岗位标题一致性仍由 crawler/API 返回的岗位 ID 保证。",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/jobs.db")
    parser.add_argument("--out-prefix", default="outputs/active_job_link_audit")
    parser.add_argument("--active-days", type=int, default=3)
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--reuse-json", default="")
    parser.add_argument("--write-status", action="store_true")
    args = parser.parse_args()

    cutoff, source_rows = _load_active_rows(Path(args.db), args.active_days)
    all_network_urls = {_network_url(row["jd_url"]) for row in source_rows}
    fetched: dict[str, dict] = {}
    eligible_urls = {url for url in all_network_urls if not _known_bad_reason(url)}
    if args.reuse_json:
        reuse_path = Path(args.reuse_json)
        if reuse_path.exists():
            previous = json.loads(reuse_path.read_text(encoding="utf-8"))
            for item in previous:
                url = item.get("network_url") or _network_url(item.get("jd_url", ""))
                if url not in eligible_urls or item.get("http_verdict") == "request_failed":
                    continue
                fetched[url] = {
                    key: item.get(key, "")
                    for key in ("status", "final_url", "page_title", "http_verdict", "error")
                }
    network_urls = _round_robin_by_host(eligible_urls - set(fetched))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_fetch, url, args.timeout): url for url in network_urls}
        for index, future in enumerate(as_completed(futures), 1):
            url = futures[future]
            try:
                fetched[url] = future.result()
            except Exception as exc:  # noqa: BLE001 - an audit must finish despite one malformed response
                fetched[url] = {
                    "status": "",
                    "final_url": "",
                    "page_title": "",
                    "http_verdict": "request_failed",
                    "error": f"audit_error: {exc}"[:240],
                }
            if index % 250 == 0 or index == len(futures):
                print(f"checked_http={index}/{len(futures)}", flush=True)

    known_bad_fetch = {
        "status": "",
        "final_url": "",
        "page_title": "",
        "http_verdict": "not_requested_known_bad",
        "error": "",
    }

    jd_ids = sorted({detail_id for row in source_rows if (detail_id := _jd_detail_id(row["jd_url"]))})
    jd_semantic = {}
    with ThreadPoolExecutor(max_workers=min(args.workers, 8)) as pool:
        futures = {pool.submit(_fetch_jd_detail, detail_id, args.timeout): detail_id for detail_id in jd_ids}
        for future in as_completed(futures):
            detail_id = futures[future]
            try:
                jd_semantic[detail_id] = future.result()
            except Exception as exc:  # noqa: BLE001
                jd_semantic[detail_id] = {
                    "semantic_check": "request_failed",
                    "semantic_detail": str(exc)[:240],
                }
    rows = [
        _merge(
            row,
            fetched.get(_network_url(row["jd_url"]), known_bad_fetch),
            jd_semantic.get(_jd_detail_id(row["jd_url"])),
        )
        for row in source_rows
    ]
    if args.write_status:
        status_conn = db_module.init_db(args.db)
        db_module.update_job_link_statuses(
            status_conn,
            [(row["id"], row["verdict"]) for row in rows],
        )
        status_conn.close()
    prefix = Path(args.out_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id", "company", "title", "last_seen_at", "link_kind", "jd_url",
        "network_url", "status", "final_url", "page_title", "verdict",
        "http_verdict", "has_detail_identity", "known_bad_reason",
        "route_template", "error",
        "semantic_check", "semantic_detail",
    ]
    with prefix.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    prefix.with_suffix(".json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_summary(prefix.with_suffix(".md"), rows, cutoff, len(eligible_urls) + len(jd_ids))

    print(
        f"audited_rows={len(rows)} unique_http={len(eligible_urls)} "
        f"requested_now={len(network_urls)} semantic_checks={len(jd_ids)}"
    )
    print(json.dumps(Counter(row["verdict"] for row in rows), ensure_ascii=False))
    print(f"output={prefix.with_suffix('.md')}")


if __name__ == "__main__":
    main()
