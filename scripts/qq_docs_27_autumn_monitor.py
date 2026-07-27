"""Read the public Tencent Docs smart sheet before the daily campus crawl.

The document exposes its initial smart-sheet state through the public
``dop-api/opendoc`` JSONP endpoint.  This module intentionally reads only the
shared sheet; it never sends edits to Tencent Docs.
"""

from __future__ import annotations

import base64
import html
import json
import re
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import job_filters
from crawlers import CRAWLER_MAP


SOURCE_URL = "https://docs.qq.com/smartsheet/DY3pHYkNvb0ZRSHdi?tab=t0gmEC&viewId=vUQPXH"
TARGET_TAG = "27届秋招"
EXCLUDED_TAGS = {"27届秋招提前批", "27届暑期实习", "日常实习", "可转正实习"}
AUTO_STATUS_START = "<!-- TENCENT_DOCS_AUTO_ONBOARDING_START -->"
AUTO_STATUS_END = "<!-- TENCENT_DOCS_AUTO_ONBOARDING_END -->"
PAGE_SIZE = 60
MAX_PAGE_REQUESTS = 20
_NON_JOB_TITLE_RE = re.compile(
    r"^(校园招聘|社会招聘|职位列表|职位类别|岗位类别|招聘岗位|全部岗位|技术类|产品类|运营类|了解更多)$",
    re.I,
)
_AUTO_ONBOARD_BLOCKED_URLS = {
    # 2022 专题页当前只剩发票补开等导航内容，不是招聘岗位入口。
    "https://static.dangdang.com/topic/contents/1119/202265.shtml": "已确认是过期专题页",
}

# Names in the shared sheet are often campaign names rather than the canonical
# company names used by config.yaml.
ALIASES = {
    "DJI大疆": "大疆",
    "科大讯飞-飞凡计划": "科大讯飞",
    "京东-TET管理培训生": "京东",
    "百度-校招&管培生": "百度",
    "思特威-岗位陆续上新": "思特威",
    "思特威-(未官宣岗位陆续上新)": "思特威",
    "MiniMax Top Talent 计划": "MiniMax",
    "远景能源-看备注，主要C9": "远景科技",
    "学而思-陆续上新": "学而思",
    "卓驭-原大疆车载": "卓驭",
    "文远知行WeRid(未官宣)": "文远知行",
    "文远知行WeRid": "文远知行",
    "Momenta-M Star": "Momenta",
    "影石Insta360": "影石",
    "搜狐畅游-下周一官宣": "搜狐畅游",
    "柠檬微趣-下周官宣": "柠檬微趣",
}


def _text(cell: dict[str, Any] | None) -> str:
    if not isinstance(cell, dict):
        return ""
    value = cell.get("k1") or []
    if not isinstance(value, list):
        return ""
    return "".join(str(part.get("k2") or "") for part in value if isinstance(part, dict)).strip()


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _parse_jsonp(text: str) -> dict[str, Any]:
    prefix = "clientVarsCallback("
    content = text.strip()
    if not content.startswith(prefix) or not content.endswith(")"):
        raise ValueError("腾讯文档返回内容不是预期的 JSONP")
    return json.loads(content[len(prefix):-1])


def _decode_sheet_payload(text: str) -> Any:
    client_vars = _parse_jsonp(text)["clientVars"]
    compressed = client_vars["collab_client_vars"]["initialAttributedText"]["text"][0]["smartsheet"]
    # Tencent Docs may omit base64 padding and occasionally uses URL-safe
    # alphabet characters in the compressed sheet payload.
    padded = compressed + "=" * (-len(compressed) % 4)
    return json.loads(zlib.decompress(base64.urlsafe_b64decode(padded)))


def _endpoint_with_row_range(endpoint: str, start: int, end: int) -> str:
    parts = urlsplit(endpoint)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({"startrow": str(start), "endrow": str(end)})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _field_id(payload: Any, field_name: str) -> str | None:
    for item in _walk(payload):
        if not isinstance(item, dict):
            continue
        for field_id, definition in item.items():
            if isinstance(definition, dict) and definition.get("k30") == field_name:
                return field_id
    return None


def _row_names(payload: Any, company_field_id: str) -> set[str]:
    names: set[str] = set()
    for item in _walk(payload):
        cells = item.get("k1") if isinstance(item, dict) else None
        if isinstance(cells, dict) and company_field_id in cells:
            name = _text(cells.get(company_field_id))
            if name:
                names.add(name)
    return names


def _load_sheet_payload(session: requests.Session) -> Any:
    page = session.get(SOURCE_URL, timeout=30)
    page.raise_for_status()
    match = re.search(r'<link rel="preload" as="script" href="([^"]*opendoc[^"]+)', page.text)
    if not match:
        raise ValueError("未找到腾讯文档公开数据入口")

    endpoint = html.unescape(match.group(1))
    if endpoint.startswith("//"):
        endpoint = "https:" + endpoint
    response = session.get(endpoint, headers={"Referer": SOURCE_URL}, timeout=30)
    response.raise_for_status()
    first_payload = _decode_sheet_payload(response.text)
    company_field_id = _field_id(first_payload, "\u516c\u53f8\u540d\u79f0")
    if company_field_id is None:
        return first_payload

    # The public endpoint sends only 60 rows per response. Continue until two
    # consecutive windows introduce no new companies, retaining the initial
    # payload because it includes the field definitions used by parse_rows.
    payloads = [first_payload]
    seen_names = _row_names(first_payload, company_field_id)
    empty_windows = 0
    for start in range(PAGE_SIZE, PAGE_SIZE * MAX_PAGE_REQUESTS, PAGE_SIZE):
        page_endpoint = _endpoint_with_row_range(endpoint, start, start + PAGE_SIZE)
        page_response = session.get(page_endpoint, headers={"Referer": SOURCE_URL}, timeout=30)
        page_response.raise_for_status()
        page_payload = _decode_sheet_payload(page_response.text)
        page_names = _row_names(page_payload, company_field_id)
        if page_names - seen_names:
            empty_windows = 0
            seen_names.update(page_names)
            payloads.append(page_payload)
            continue
        empty_windows += 1
        if empty_windows >= 2:
            break
    return payloads


def parse_rows(payload: Any) -> list[dict[str, Any]]:
    """Return all rows carrying the exact 27届秋招 label and their real URLs."""
    field_names: dict[str, str] = {}
    options_by_field: dict[str, dict[str, str]] = {}
    needed = {"公司名称", "招聘类型", "投递链接"}
    for item in _walk(payload):
        for field_id, definition in item.items():
            if not isinstance(definition, dict) or definition.get("k30") not in needed:
                continue
            field_names[field_id] = definition["k30"]
            options: dict[str, str] = {}
            for option in ((definition.get("k9") or {}).get("k3") or []):
                if isinstance(option, dict):
                    options[str(option.get("k1") or "")] = str(option.get("k2") or "")
            options_by_field[field_id] = options

    if not needed.issubset(set(field_names.values())):
        raise ValueError("腾讯文档字段结构已变化")

    rows: dict[str, dict[str, Any]] = {}
    for item in _walk(payload):
        cells = item.get("k1") if isinstance(item, dict) else None
        if not isinstance(cells, dict):
            continue
        row_fields = {
            name: field_id
            for field_id, name in field_names.items()
            if field_id in cells
        }
        if not needed.issubset(row_fields):
            continue
        company_field = row_fields["公司名称"]
        type_field = row_fields["招聘类型"]
        link_field = row_fields["投递链接"]
        name = _text(cells[company_field])
        tags = [
            options_by_field[type_field].get(str(tag), str(tag))
            for tag in cells[type_field].get("k9", [])
        ]
        if not name or TARGET_TAG not in tags:
            continue
        links = [
            str(link.get("k3") or "")
            for link in cells.get(link_field, {}).get("k8", [])
            if isinstance(link, dict) and link.get("k3")
        ]
        row = {"source_name": name, "canonical_name": ALIASES.get(name, name), "tags": tags, "links": links}
        rows[name] = row

    for row in rows.values():
        excluded = set(row["tags"]) & EXCLUDED_TAGS
        # This status is informational only. A secondary internship or early
        # batch tag must not suppress a company carrying the 27-autumn tag.
        row["source_status"] = "strict_formal" if not excluded else "mixed_or_excluded"
        row["excluded_tags"] = sorted(excluded)
    return sorted(rows.values(), key=lambda row: row["source_name"])


def recruitment_source_identity(url: str, crawler: str | None = None) -> str:
    """Return a stable company-level identity for a recruitment entry URL."""
    parsed = urlparse(url)
    host = parsed.netloc.casefold()
    path = parsed.path.rstrip("/")
    crawler = crawler or infer_crawler(url)
    if not host or not crawler:
        return ""
    if crawler == "moka":
        match = re.search(r"/(?:campus_apply|campus-recruitment)/([^/?#]+)", path, re.I)
        return f"moka:{match.group(1).casefold()}" if match else f"moka:{host}:{path.casefold()}"
    if crawler == "hotjob":
        match = re.search(r"/(SU[0-9a-f]+)", path, re.I)
        return f"hotjob:{match.group(1).casefold()}" if match else f"hotjob:{host}:{path.casefold()}"
    if crawler in {"feishu", "beisen"}:
        return f"{crawler}:{host}"
    return f"{crawler}:{host}"


def compare_with_config(rows: list[dict[str, Any]], companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    configured = {str(company.get("name") or "").casefold() for company in companies}
    configured_sources: dict[str, str] = {}
    for company in companies:
        identity = recruitment_source_identity(
            str(company.get("careers_url") or ""),
            str(company.get("crawler") or "") or None,
        )
        if identity:
            configured_sources.setdefault(identity, str(company.get("name") or ""))
    for row in rows:
        matched_company = ""
        for link in row.get("links") or []:
            identity = recruitment_source_identity(str(link))
            if identity in configured_sources:
                matched_company = configured_sources[identity]
                break
        row["in_config"] = (
            row["canonical_name"].casefold() in configured
            or bool(matched_company)
        )
        if matched_company:
            row["matched_company"] = matched_company
    return rows


def attach_official_campaign_urls(
    rows: list[dict[str, Any]],
    companies: list[dict[str, Any]],
) -> int:
    """Attach official Tencent lead URLs as in-memory campaign evidence pages."""
    by_name = {
        str(company.get("name") or "").casefold(): company
        for company in companies
    }
    attached = 0
    for row in rows:
        name = str(row.get("matched_company") or row.get("canonical_name") or "")
        company = by_name.get(name.casefold())
        links = [str(link).strip() for link in row.get("links") or [] if str(link).strip()]
        if not company or not links or company.get("campaign_url"):
            continue
        company["campaign_url"] = links[0]
        attached += 1
    return attached


def attach_trusted_cohort_evidence(
    rows: list[dict[str, Any]],
    companies: list[dict[str, Any]],
) -> int:
    """Attach traceable 2027 evidence from exact Tencent Docs formal rows."""
    by_name = {
        str(company.get("name") or "").casefold(): company
        for company in companies
    }
    attached = 0
    for row in rows:
        if TARGET_TAG not in set(row.get("tags") or []):
            continue
        name = str(row.get("matched_company") or row.get("canonical_name") or "")
        company = by_name.get(name.casefold())
        if not company:
            continue
        links = [
            str(link).strip()
            for link in row.get("links") or []
            if str(link).strip()
        ]
        company["source_cohort"] = 2027
        company["source_cohort_source"] = "腾讯文档27届秋招"
        company["source_cohort_evidence"] = (
            f"{row.get('source_name') or name}：{TARGET_TAG}"
        )
        company["source_cohort_url"] = links[0] if links else SOURCE_URL
        attached += 1
    return attached


def infer_crawler(url: str) -> str | None:
    """Choose an existing production crawler from a Tencent Docs job link."""
    host = urlparse(url).netloc.casefold()
    path = urlparse(url).path.casefold()
    if "mokahr.com" in host:
        return "moka"
    if host.endswith(".zhiye.com") or "/campus/jobs" in path:
        return "beisen"
    if "feishu.cn" in host or "mioffice.cn" in host:
        return "feishu"
    if "hotjob.cn" in host:
        return "hotjob"
    if host:
        # The generic renderer is the controlled fallback for self-built sites.
        return "render"
    return None


def _fetch_candidate(entry: dict[str, str]) -> list[dict]:
    cls = CRAWLER_MAP[entry["crawler"]]
    return cls(entry["name"], entry["careers_url"]).fetch() or []


def _is_concrete_job(job: dict[str, Any]) -> bool:
    title = str(job.get("title") or "").strip()
    return len(title) >= 3 and _NON_JOB_TITLE_RE.fullmatch(title) is None


def validate_unconfigured_rows(
    rows: list[dict[str, Any]],
    fetcher=_fetch_candidate,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Validate new leads before they can enter config.yaml.

    A Tencent Docs link is only a lead. It is accepted when an existing crawler
    returns at least one formal campus job; otherwise the failure remains
    visible for follow-up without changing the live company list.
    """
    approved: list[dict[str, str]] = []
    attempts: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for row in rows:
        if row.get("in_config"):
            continue
        name = str(row["canonical_name"])
        normalized = name.casefold()
        if normalized in seen_names:
            continue
        seen_names.add(normalized)

        reasons: list[str] = []
        for url in dict.fromkeys(row.get("links") or []):
            if url in _AUTO_ONBOARD_BLOCKED_URLS:
                reasons.append(_AUTO_ONBOARD_BLOCKED_URLS[url])
                continue
            crawler = infer_crawler(url)
            if crawler is None:
                reasons.append("链接不是可识别的网页地址")
                continue
            entry = {"name": name, "careers_url": url, "crawler": crawler}
            try:
                jobs = fetcher(entry)
            except Exception as exc:  # A broken lead must not break daily crawling.
                reasons.append(f"{crawler} 抓取异常: {type(exc).__name__}")
                continue

            formal_jobs, _ = job_filters.filter_formal_campus_jobs(jobs)
            formal_jobs = [job for job in formal_jobs if _is_concrete_job(job)]
            target_jobs, _ = job_filters.filter_target_direction_jobs(formal_jobs)
            if target_jobs:
                approved.append(entry)
                attempts.append({
                    "name": name,
                    "url": url,
                    "crawler": crawler,
                    "status": "approved",
                    "job_count": len(jobs),
                    "formal_count": len(target_jobs),
                    "reason": "已抓到正式且方向相关的校招岗位",
                })
                break
            if jobs:
                reasons.append(f"{crawler} 返回 {len(jobs)} 条，但均被实习/社招/非具体岗位/方向规则过滤")
            else:
                reasons.append(f"{crawler} 返回 0 个岗位")
        else:
            attempts.append({
                "name": name,
                "url": (row.get("links") or [""])[0],
                "crawler": infer_crawler((row.get("links") or [""])[0]) or "unknown",
                "status": "needs_review",
                "job_count": 0,
                "formal_count": 0,
                "reason": "；".join(reasons) or "腾讯文档未提供可验证链接",
            })
    return approved, attempts


def append_verified_companies(config_path: Path, entries: list[dict[str, str]]) -> None:
    """Append only verified entries so existing config formatting stays intact."""
    if not entries:
        return
    existing_config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    existing_companies = existing_config.get("companies") or []
    existing_names = {
        str(company.get("name") or "").casefold()
        for company in existing_companies
    }
    existing_sources = {
        recruitment_source_identity(
            str(company.get("careers_url") or ""),
            str(company.get("crawler") or "") or None,
        )
        for company in existing_companies
    }
    filtered_entries: list[dict[str, str]] = []
    for entry in entries:
        name_key = entry["name"].casefold()
        source_key = recruitment_source_identity(entry["careers_url"], entry["crawler"])
        if name_key in existing_names or (source_key and source_key in existing_sources):
            continue
        filtered_entries.append(entry)
        existing_names.add(name_key)
        if source_key:
            existing_sources.add(source_key)
    if not filtered_entries:
        return

    lines = ["", "# 腾讯文档 27届秋招自动验证通过（真实抓到正式校招岗位后写入）"]
    for entry in filtered_entries:
        lines.extend([
            f"- name: {json.dumps(entry['name'], ensure_ascii=False)}",
            f"  careers_url: {json.dumps(entry['careers_url'], ensure_ascii=False)}",
            f"  crawler: {entry['crawler']}",
        ])
    content = config_path.read_text(encoding="utf-8")
    block = "\n".join(lines) + "\n"
    # The companies list precedes other top-level settings (currently
    # ``deepseek``), so append inside that list rather than at EOF.
    next_section = re.search(r"^deepseek:\s*$", content, re.M)
    updated = (
        content[:next_section.start()].rstrip() + block + content[next_section.start():]
        if next_section
        else content.rstrip() + block
    )
    config_path.write_text(updated, encoding="utf-8", newline="\n")


def update_integration_status(status_path: Path, attempts: list[dict[str, Any]]) -> None:
    """Keep a small managed section for unresolved Tencent Docs leads."""
    if not attempts:
        return
    pending = [item for item in attempts if item["status"] != "approved"]
    rows = [
        "## 腾讯文档自动接入状态（自动维护）",
        AUTO_STATUS_START,
        "| 公司 | 腾讯文档链接 | 识别爬虫 | 状态 | 原因 |",
        "| --- | --- | --- | --- | --- |",
    ]
    if pending:
        for item in pending:
            rows.append(
                f"| {item['name']} | {item['url']} | `{item['crawler']}` | 待人工接入 | {item['reason']} |"
            )
    else:
        rows.append("| 无 | - | - | - | 当前腾讯文档新线索均已自动验证并接入 |")
    rows.extend([AUTO_STATUS_END, ""])
    section = "\n".join(rows)

    content = status_path.read_text(encoding="utf-8") if status_path.exists() else "# 公司招聘接入状态\n"
    pattern = re.compile(
        rf"## 腾讯文档自动接入状态（自动维护）\n{re.escape(AUTO_STATUS_START)}.*?{re.escape(AUTO_STATUS_END)}\n?",
        re.S,
    )
    updated = pattern.sub(section, content) if pattern.search(content) else content.rstrip() + "\n\n" + section
    if updated != content:
        status_path.write_text(updated, encoding="utf-8", newline="\n")


def run(companies: list[dict[str, Any]]) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    rows = compare_with_config(parse_rows(_load_sheet_payload(session)), companies)
    return {
        "source_url": SOURCE_URL,
        "checked_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "rows": rows,
        "covered": sum(row["in_config"] for row in rows),
        "needs_integration": sum(not row["in_config"] for row in rows),
    }


def write_report(result: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    import yaml

    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    result = run(config["companies"])
    output = root / "outputs" / "qq_docs_27_autumn_monitor.json"
    write_report(result, output)
    print(f"腾讯文档 27届秋招：{len(result['rows'])} 条，已覆盖 {result['covered']}，待接入 {result['needs_integration']}")
    print(output)
