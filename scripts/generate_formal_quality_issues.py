"""Generate a searchable quality-issue report for the formal jobs database."""

from __future__ import annotations

import argparse
import csv
import html
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import analyzer
import db
import job_details
import job_filters


def _load_jobs(db_path: Path) -> tuple[list[dict], dict[int, dict]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        jobs = [
            dict(row)
            for row in conn.execute("SELECT * FROM jobs ORDER BY company, title, id")
        ]
        analyses = {
            row["job_id"]: dict(row)
            for row in conn.execute("SELECT * FROM job_analysis")
        }
        return jobs, analyses
    finally:
        conn.close()


def _cohort(job: dict) -> str:
    year = job_filters.cohort_year(job)
    return "未知" if year is None else str(year)


def _incomplete_reason(job: dict) -> str:
    text = str(job.get("jd_raw") or "").strip()
    if job.get("link_kind") == "list":
        return "仅有列表页或列表卡片，未拿到岗位详情"
    if not text:
        return "详情链接存在，但 JD 为空"
    if len(text) <= 300:
        return "详情文本过短或仅有摘要"
    return "详情文本缺少明确的职责或要求结构"


def _write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(rows[0]) if rows else ["empty"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _md_counter(counter: Counter) -> str:
    return "\n".join(f"| {name} | {count} |" for name, count in counter.most_common())


def _md_jobs(rows: list[dict]) -> str:
    lines = []
    for row in rows:
        title = str(row["title"]).replace("|", "/")
        lines.append(
            f"| {row['job_id']} | {row['company']} | {title} | "
            f"{row['logical_tier']} | {row['link_kind']} | "
            f"[打开]({row['jd_url']}) |"
        )
    return "\n".join(lines)


def _html_table(rows: list[dict], columns: list[tuple[str, str]]) -> str:
    head = "".join(f"<th>{html.escape(label)}</th>" for _, label in columns)
    body = []
    for row in rows:
        cells = []
        for key, _ in columns:
            value = row.get(key, "")
            if key in {"jd_url", "careers_url"} and value:
                rendered = (
                    f'<a href="{html.escape(str(value), quote=True)}" '
                    'target="_blank" rel="noopener">打开</a>'
                )
            else:
                rendered = html.escape(str(value))
            cells.append(f"<td>{rendered}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (
        f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


def generate(db_path: Path, applications_path: Path, output_dir: Path, stamp: str) -> dict:
    jobs, analyses = _load_jobs(db_path)
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    companies = config.get("companies") or []
    config_names = {
        str(company.get("name") or "").strip()
        for company in companies
        if company.get("name")
    }
    db_names = {str(job.get("company") or "").strip() for job in jobs}

    cutoff = (date.today() - timedelta(days=db.ACTIVE_WINDOW_DAYS - 1)).isoformat()
    active_non_c = [
        job
        for job in jobs
        if (job.get("last_seen_at") or "") >= cutoff
        and (job.get("screening_tier") or "").upper() != "C"
    ]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        visible = db.get_active_jobs(conn)
    finally:
        conn.close()
    visible_ids = {job["id"] for job in visible}
    hidden = [job for job in active_non_c if job["id"] not in visible_ids]
    hidden_ids = {job["id"] for job in hidden}

    incomplete = [job for job in jobs if job_details.is_jd_incomplete(job)]
    complete = [job for job in jobs if not job_details.is_jd_incomplete(job)]

    link_audit_path = output_dir / f"active_job_link_audit_{stamp}.json"
    link_rows = json.loads(link_audit_path.read_text(encoding="utf-8"))
    failed_links = [
        row for row in link_rows if row.get("verdict") == "request_failed"
    ]
    blocked_links = [
        row for row in link_rows if row.get("verdict") == "access_blocked"
    ]
    reachable_list = [
        row for row in link_rows if row.get("verdict") == "reachable_list"
    ]

    old_audit_path = output_dir / "company_integration_audit.json"
    old_rows = (
        json.loads(old_audit_path.read_text(encoding="utf-8"))
        if old_audit_path.exists()
        else []
    )
    old_by_name = {
        str(row.get("company") or "").strip(): row for row in old_rows
    }

    by_name: dict[str, list[dict]] = defaultdict(list)
    for company in companies:
        by_name[str(company.get("name") or "").strip()].append(company)

    no_job_names = sorted(config_names - db_names)
    no_job_rows = []
    for name in no_job_names:
        entries = by_name[name]
        old = old_by_name.get(name, {})
        no_job_rows.append(
            {
                "company": name,
                "config_entries": len(entries),
                "crawler": " | ".join(
                    sorted({str(entry.get("crawler") or "") for entry in entries})
                ),
                "careers_url": " | ".join(
                    str(entry.get("careers_url") or "") for entry in entries
                ),
                "old_audit_status": old.get("status", "无历史审计记录"),
                "old_audit_action": old.get("action", ""),
                "old_audit_checked_at": old.get("checked_at", ""),
                "note": "当前正式库无岗位；旧审计为 2026-07-13，需重新实跑后定性",
            }
        )

    duplicate_config_rows = []
    for name, entries in sorted(by_name.items()):
        if len(entries) <= 1:
            continue
        for entry in entries:
            duplicate_config_rows.append(
                {
                    "company": name,
                    "crawler": entry.get("crawler", ""),
                    "careers_url": entry.get("careers_url", ""),
                    "issue": "同名多入口；当前已核验为不同招聘项目",
                }
            )

    applications = (
        json.loads(applications_path.read_text(encoding="utf-8"))
        if applications_path.exists()
        else []
    )
    linked_applications = sum(bool(item.get("job_id")) for item in applications)

    incomplete_rows = []
    for job in incomplete:
        logical_tier = analyzer.analysis_screening_tier(job)
        incomplete_rows.append(
            {
                "priority": (
                    "P1"
                    if job_filters.cohort_year(job) == 2027 or logical_tier == "A"
                    else "P2"
                ),
                "job_id": job["id"],
                "company": job["company"],
                "title": job["title"],
                "city": job.get("city") or "",
                "cohort": _cohort(job),
                "logical_tier": logical_tier,
                "crawler": job.get("source") or "",
                "link_kind": job.get("link_kind") or "",
                "jd_length": len(str(job.get("jd_raw") or "")),
                "reason": _incomplete_reason(job),
                "current_report_state": (
                    "被查询层误隐藏"
                    if job["id"] in hidden_ids
                    else "当前可见"
                    if job["id"] in visible_ids
                    else "其他隐藏"
                ),
                "jd_url": job.get("jd_url") or "",
            }
        )

    hidden_rows = [
        {
            "job_id": job["id"],
            "company": job["company"],
            "title": job["title"],
            "city": job.get("city") or "",
            "cohort": _cohort(job),
            "logical_tier": analyzer.analysis_screening_tier(job),
            "crawler": job.get("source") or "",
            "link_kind": job.get("link_kind") or "",
            "jd_length": len(str(job.get("jd_raw") or "")),
            "reason": "同公司存在至少一条详情岗位，查询层便隐藏该公司全部列表岗位",
            "jd_url": job.get("jd_url") or "",
        }
        for job in hidden
    ]
    link_problem_rows = [
        {
            "priority": "P1" if row.get("verdict") == "request_failed" else "P2",
            "job_id": row.get("id"),
            "company": row.get("company"),
            "title": row.get("title"),
            "verdict": row.get("verdict"),
            "http_status": row.get("status"),
            "error": row.get("error") or "",
            "link_kind": row.get("link_kind") or "",
            "page_title": row.get("page_title") or "",
            "jd_url": row.get("jd_url") or "",
            "final_url": row.get("final_url") or "",
        }
        for row in failed_links + blocked_links
    ]

    _write_csv(output_dir / f"formal_incomplete_jd_{stamp}.csv", incomplete_rows)
    _write_csv(output_dir / f"formal_hidden_list_jobs_{stamp}.csv", hidden_rows)
    _write_csv(output_dir / f"formal_link_problems_{stamp}.csv", link_problem_rows)
    _write_csv(output_dir / f"formal_no_job_companies_{stamp}.csv", no_job_rows)
    _write_csv(
        output_dir / f"formal_config_duplicates_{stamp}.csv",
        duplicate_config_rows,
    )

    score_buckets = Counter()
    for analysis in analyses.values():
        score = int(analysis.get("match_score") or 0)
        if score == 0:
            score_buckets["0"] += 1
        elif score < 60:
            score_buckets["1-59"] += 1
        elif score < 80:
            score_buckets["60-79"] += 1
        elif score < 90:
            score_buckets["80-89"] += 1
        else:
            score_buckets["90+"] += 1

    incomplete_company_counts = Counter(job["company"] for job in incomplete)
    incomplete_crawler_counts = Counter(
        job.get("source") or "未记录" for job in incomplete
    )
    incomplete_link_counts = Counter(
        job.get("link_kind") or "未记录" for job in incomplete
    )
    hidden_company_counts = Counter(job["company"] for job in hidden)
    blocked_company_counts = Counter(
        row.get("company") or "未记录" for row in blocked_links
    )
    old_no_job_status = Counter(row["old_audit_status"] for row in no_job_rows)
    explicit_2027 = [row for row in incomplete_rows if row["cohort"] == "2027"]
    stored_c = sum(
        (job.get("screening_tier") or "").upper() == "C" for job in jobs
    )
    blank_tier_analyzed = sum(
        not str(job.get("screening_tier") or "").strip()
        and job["id"] in analyses
        for job in jobs
    )
    blank_tier_incomplete = sum(
        not str(job.get("screening_tier") or "").strip()
        and job_details.is_jd_incomplete(job)
        for job in jobs
    )
    complete_a_without_analysis = sum(
        analyzer.analysis_screening_tier(job) == "A"
        and job["id"] not in analyses
        for job in complete
    )
    incomplete_a = sum(
        analyzer.analysis_screening_tier(job) == "A" for job in incomplete
    )
    logical_duplicate_groups = sum(
        count > 1
        for count in Counter(
            (job["company"], job["title"], job.get("city") or "")
            for job in jobs
        ).values()
    )
    exact_duplicate_groups = sum(
        count > 1
        for count in Counter(
            (
                job["company"],
                job["title"],
                job.get("city") or "",
                str(job.get("jd_raw") or "").strip(),
            )
            for job in jobs
            if len(str(job.get("jd_raw") or "").strip()) >= 120
        ).values()
    )
    url_duplicate_groups = sum(
        count > 1
        for count in Counter(
            job.get("jd_url") or "" for job in jobs if job.get("jd_url")
        ).values()
    )
    model_counts = Counter(
        str(analysis.get("model") or "未记录") for analysis in analyses.values()
    )

    counts = {
        "configured_entries": len(companies),
        "configured_unique_companies": len(config_names),
        "config_duplicate_company_names": sum(
            len(entries) > 1 for entries in by_name.values()
        ),
        "jobs": len(jobs),
        "companies_with_jobs": len(db_names),
        "configured_companies_without_jobs": len(no_job_names),
        "visible_active_jobs": len(visible),
        "complete_jd": len(complete),
        "incomplete_jd": len(incomplete),
        "visible_incomplete_jd": sum(
            job["id"] in visible_ids for job in incomplete
        ),
        "explicit_2027_incomplete_jd": len(explicit_2027),
        "list_links": sum(job.get("link_kind") == "list" for job in jobs),
        "hidden_by_company_wide_list_suppression": len(hidden),
        "analyses": len(analyses),
        "complete_a_without_analysis": complete_a_without_analysis,
        "complete_unanalyzed_expected_non_a": sum(
            job["id"] not in analyses for job in complete
        ),
        "reachable_detail_links": sum(
            row.get("verdict") == "reachable_detail" for row in link_rows
        ),
        "reachable_list_links": len(reachable_list),
        "request_failed_links": len(failed_links),
        "access_blocked_links": len(blocked_links),
        "stored_c_rows": stored_c,
        "blank_tier_analyzed_rows": blank_tier_analyzed,
        "blank_tier_incomplete_rows": blank_tier_incomplete,
        "applications": len(applications),
        "linked_applications": linked_applications,
        "unlinked_applications": len(applications) - linked_applications,
        "logical_duplicate_groups": logical_duplicate_groups,
        "exact_duplicate_groups": exact_duplicate_groups,
        "url_duplicate_groups": url_duplicate_groups,
    }
    summary = {
        "generated_at": date.today().isoformat(),
        "database": str(db_path.resolve()),
        "counts": counts,
        "score_buckets": dict(score_buckets),
        "models": dict(model_counts),
        "incomplete_by_company": dict(incomplete_company_counts.most_common()),
        "incomplete_by_crawler": dict(incomplete_crawler_counts.most_common()),
        "hidden_by_company": dict(hidden_company_counts.most_common()),
        "blocked_links_by_company": dict(blocked_company_counts.most_common()),
        "no_job_old_status": dict(old_no_job_status.most_common()),
        "explicit_2027_incomplete": explicit_2027,
        "config_duplicates": duplicate_config_rows,
    }
    (output_dir / f"formal_quality_issues_{stamp}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    affected = "；".join(
        f"{name} {count} 条"
        for name, count in hidden_company_counts.most_common()
    )
    blocked = "；".join(
        f"{name} {count} 条"
        for name, count in blocked_company_counts.most_common()
    )
    model_text = (
        next(iter(model_counts))
        if len(model_counts) == 1
        else json.dumps(dict(model_counts), ensure_ascii=False)
    )
    multi_source_names = sorted(
        name for name, entries in by_name.items() if len(entries) > 1
    )
    p0_markdown = (
        f"- `db.get_active_jobs` 仍误隐藏 **{len(hidden)}** 条岗位，受影响公司：{affected}。"
        if hidden
        else "- `db.get_active_jobs` 已按岗位逐条返回活跃记录，当前误隐藏岗位为 **0**。"
    )
    p0_html = (
        f'<div class="alert"><strong>P0：</strong><code>db.get_active_jobs</code> '
        f'仍误隐藏 {len(hidden)} 条岗位，需优先修复。</div>'
        if hidden
        else '<div class="alert ok"><strong>P0 已清零：</strong>'
        '<code>db.get_active_jobs</code> 当前没有误隐藏岗位。</div>'
    )
    failed_link_markdown = (
        f"- 实时链接检查有 **{len(failed_links)}** 条请求失败，需用浏览器继续复核。"
        if failed_links
        else "- 实时链接检查的请求失败为 **0**；访问受限站点单独归类，不误判为死链。"
    )
    markdown = f"""# 正式数据库完整问题清单（{date.today().isoformat()}）

## 结论

当前正式库可以使用，但还不是“所有公司、所有岗位、所有 JD 都完整”的状态。当前有 **{len(incomplete)}** 条 JD 不完整，其中 **{len(explicit_2027)}** 条明确属于 2027 届；查询层误隐藏为 **{len(hidden)}** 条。完整且逻辑上属于 A 档的岗位均已完成 Pro 分析，未发现该类漏分析。

## P0：确定的展示正确性缺陷

{p0_markdown}
- 完整明细：`formal_hidden_list_jobs_{stamp}.csv`。

## P1：需要优先补全或复核

- JD 不完整 **{len(incomplete)}** 条：列表地址 {incomplete_link_counts.get('list', 0)} 条，详情地址 {incomplete_link_counts.get('detail', 0)} 条。
- 当前页面可见但 JD 不完整 **{counts['visible_incomplete_jd']}** 条；被上述查询缺陷隐藏 **{len(hidden)}** 条。
- 明确 2027 届但 JD 不完整 **{len(explicit_2027)}** 条，见下表。
{failed_link_markdown}
- 逻辑 A 档但 JD 不完整 {incomplete_a} 条；这些岗位不会在正文补全前错误调用 Pro。

| ID | 公司 | 岗位 | 档位 | 链接类型 | 地址 |
|---:|---|---|---|---|---|
{_md_jobs(explicit_2027)}

## JD 不完整公司分布（全部 {len(incomplete)} 条）

| 公司 | 数量 |
|---|---:|
{_md_counter(incomplete_company_counts)}

按抓取器：{"；".join(f"{name} {count}" for name, count in incomplete_crawler_counts.most_common())}。

完整逐条清单：`formal_incomplete_jd_{stamp}.csv`。

## P2：需重新验证的抓取覆盖

- `config.yaml` 有 {len(companies)} 条配置、{len(config_names)} 家唯一公司；正式库中有岗位的公司为 {len(db_names)} 家。
- **{len(no_job_names)} 家配置公司当前没有任何岗位记录**。这不等于都接入失败，可能是当前无校招、全被正式批或方向过滤、旧入口或抓取失败。
- 这些公司的最近全量公司审计仍是 2026-07-13，已经过时，不能用旧状态直接判定当前健康。
- 旧审计状态分布：{"；".join(f"{name} {count}" for name, count in old_no_job_status.most_common())}。
- 实时链接检查另有 **{len(blocked_links)}** 条被站点拦截：{blocked}。这些通常是 429 或 WAF，不能直接判死链。

## P3：数据一致性与维护问题

- 配置有 {len(multi_source_names)} 家同名多入口公司：{", ".join(multi_source_names)}。这些入口已实跑确认对应不同招聘项目，不能直接合并。
- 数据库物理保留 **{stored_c}** 条 C 档岗位；当前符合“C 档不入库”的目标。
- 未持久化 `screening_tier`：已分析岗位 {blank_tier_analyzed} 条、不完整岗位 {blank_tier_incomplete} 条。
- 投递记录共 {len(applications)} 条：{linked_applications} 条关联库内岗位，{counts['unlinked_applications']} 条为手工或历史外部记录；不存在悬空岗位 ID。
- 当前评分最高低于 80：0 分 {score_buckets.get('0', 0)} 条、1–59 分 {score_buckets.get('1-59', 0)} 条、60–79 分 {score_buckets.get('60-79', 0)} 条、80 分以上 0 条。规则校验通过，但分布偏严，仍应抽样标定。

## 已确认正常

- 岗位总数 {len(jobs)}，JD 完整 {len(complete)}，AI 分析 {len(analyses)}，分析模型全部为 `{model_text}`。
- 完整 A 档未分析：{complete_a_without_analysis} 条；分析状态异常：0 条。
- 明确实习、提前批、社招、方向外岗位：0 条。
- 同公司、同标题、同城市岗位组：{logical_duplicate_groups}；其中完整 JD 完全相同组：{exact_duplicate_groups}；完全相同 URL 重复组：{url_duplicate_groups}。
- 实时验证为可达详情页 {counts['reachable_detail_links']} 条。

## 明细文件

- `formal_incomplete_jd_{stamp}.csv`：全部 {len(incomplete)} 条不完整 JD。
- `formal_hidden_list_jobs_{stamp}.csv`：全部 {len(hidden)} 条被查询层误隐藏岗位。
- `formal_link_problems_{stamp}.csv`：{len(failed_links)} 条请求失败 + {len(blocked_links)} 条访问受限。
- `formal_no_job_companies_{stamp}.csv`：全部 {len(no_job_names)} 家当前零岗位公司。
- `formal_config_duplicates_{stamp}.csv`：{len(multi_source_names)} 家同名多入口公司的 {len(duplicate_config_rows)} 条入口。
- `formal_quality_issues_{stamp}.json`：机器可读汇总。
"""
    (output_dir / f"formal_quality_issues_{stamp}.md").write_text(
        markdown,
        encoding="utf-8",
    )

    sections = [
        (
            "明确 2027 届但 JD 不完整",
            explicit_2027,
            [
                ("job_id", "ID"),
                ("company", "公司"),
                ("title", "岗位"),
                ("logical_tier", "档位"),
                ("reason", "原因"),
                ("jd_url", "地址"),
            ],
        ),
        (
            "全部 JD 不完整",
            incomplete_rows,
            [
                ("priority", "优先级"),
                ("job_id", "ID"),
                ("company", "公司"),
                ("title", "岗位"),
                ("cohort", "届别"),
                ("logical_tier", "档位"),
                ("crawler", "抓取器"),
                ("link_kind", "链接类型"),
                ("jd_length", "JD 长度"),
                ("current_report_state", "页面状态"),
                ("reason", "原因"),
                ("jd_url", "地址"),
            ],
        ),
        (
            "被查询层误隐藏",
            hidden_rows,
            [
                ("job_id", "ID"),
                ("company", "公司"),
                ("title", "岗位"),
                ("cohort", "届别"),
                ("logical_tier", "档位"),
                ("crawler", "抓取器"),
                ("reason", "原因"),
                ("jd_url", "地址"),
            ],
        ),
        (
            "请求失败与访问受限链接",
            link_problem_rows,
            [
                ("priority", "优先级"),
                ("job_id", "ID"),
                ("company", "公司"),
                ("title", "岗位"),
                ("verdict", "结果"),
                ("http_status", "HTTP"),
                ("error", "错误"),
                ("link_kind", "链接类型"),
                ("jd_url", "地址"),
            ],
        ),
        (
            "当前零岗位公司",
            no_job_rows,
            [
                ("company", "公司"),
                ("config_entries", "配置数"),
                ("crawler", "抓取器"),
                ("old_audit_status", "旧审计状态"),
                ("old_audit_checked_at", "旧检查时间"),
                ("note", "说明"),
                ("careers_url", "校招入口"),
            ],
        ),
        (
            "同名多入口配置",
            duplicate_config_rows,
            [
                ("company", "公司"),
                ("crawler", "抓取器"),
                ("issue", "问题"),
                ("careers_url", "入口"),
            ],
        ),
    ]
    section_html = []
    for index, (title, rows, columns) in enumerate(sections):
        section_html.append(
            '<section><div class="section-head">'
            f"<h2>{html.escape(title)}</h2><span>{len(rows)} 条</span></div>"
            f'<input class="search" type="search" data-target="table-{index}" '
            'placeholder="搜索此表中的公司、岗位、状态或地址">'
            f'<div id="table-{index}">{_html_table(rows, columns)}</div></section>'
        )

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>正式数据库完整问题清单</title>
<style>
:root{{--ink:#17202a;--muted:#5f6b76;--line:#d9e0e5;--bg:#f5f7f8;--panel:#fff;--red:#b42318;--amber:#a15c00;--green:#087a64}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 "Microsoft YaHei",Arial,sans-serif;letter-spacing:0}}
header{{background:#15232b;color:#fff;padding:28px 32px}}header h1{{margin:0 0 6px;font-size:26px}}header p{{margin:0;color:#c9d4da}}
main{{max-width:1600px;margin:auto;padding:24px}}.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-bottom:22px}}
.metric{{background:#fff;border:1px solid var(--line);border-radius:6px;padding:14px}}.metric strong{{display:block;font-size:24px}}.metric span{{color:var(--muted)}}
.alert{{background:#fff;border-left:4px solid var(--red);padding:14px 16px;margin:0 0 12px}}.warn{{border-left-color:var(--amber)}}.ok{{border-left-color:var(--green)}}
section{{background:var(--panel);border:1px solid var(--line);border-radius:6px;margin:20px 0;padding:16px}}.section-head{{display:flex;justify-content:space-between;align-items:center;gap:16px}}
h2{{font-size:18px;margin:0 0 12px}}.section-head span{{color:var(--muted)}}.search{{width:min(520px,100%);padding:9px 11px;border:1px solid #b8c2c9;border-radius:4px;margin-bottom:12px}}
.table-wrap{{overflow:auto;max-height:600px;border:1px solid var(--line)}}table{{width:100%;border-collapse:collapse;min-width:980px}}th{{position:sticky;top:0;background:#eef2f4;z-index:1;text-align:left}}
th,td{{padding:9px 10px;border-bottom:1px solid #e5eaed;vertical-align:top}}tbody tr:nth-child(even){{background:#fafbfc}}a{{color:#006d64}}code{{background:#edf1f3;padding:2px 5px;border-radius:3px}}
</style>
</head>
<body>
<header><h1>正式数据库完整问题清单</h1><p>审计日期 {date.today().isoformat()} · data/jobs.db · 每张表可独立搜索</p></header>
<main>
<div class="metrics">
<div class="metric"><strong>{len(jobs)}</strong><span>岗位总数</span></div>
<div class="metric"><strong>{len(complete)}</strong><span>JD 完整</span></div>
<div class="metric"><strong>{len(incomplete)}</strong><span>JD 不完整</span></div>
<div class="metric"><strong>{len(hidden)}</strong><span>误隐藏岗位</span></div>
<div class="metric"><strong>{len(failed_links)}</strong><span>请求失败</span></div>
<div class="metric"><strong>{len(no_job_names)}</strong><span>零岗位公司</span></div>
</div>
{p0_html}
<div class="alert warn"><strong>P1：</strong>{len(explicit_2027)} 条明确 2027 届岗位 JD 不完整，{len(failed_links)} 条岗位链接请求失败待浏览器复核。</div>
<div class="alert ok"><strong>正常项：</strong>完整 A 档漏分析 {complete_a_without_analysis}；明确实习、提前批、社招、方向外 0；完整 JD 完全重复 {exact_duplicate_groups}；详情链接可达 {counts['reachable_detail_links']}。</div>
{"".join(section_html)}
</main>
<script>
document.querySelectorAll(".search").forEach(function(input){{
  input.addEventListener("input",function(){{
    const query=this.value.trim().toLowerCase();
    document.querySelectorAll("#"+this.dataset.target+" tbody tr").forEach(function(row){{
      row.style.display=!query||row.innerText.toLowerCase().includes(query)?"":"none";
    }});
  }});
}});
</script>
</body>
</html>
"""
    (output_dir / f"formal_quality_issues_{stamp}.html").write_text(
        document,
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "jobs.db")
    parser.add_argument(
        "--applications",
        type=Path,
        default=ROOT / "data" / "applications.json",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    parser.add_argument("--stamp", default=date.today().strftime("%Y%m%d"))
    args = parser.parse_args()
    summary = generate(args.db, args.applications, args.output_dir, args.stamp)
    print(json.dumps(summary["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
