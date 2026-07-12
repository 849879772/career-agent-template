import logging
import os
from collections import Counter
from datetime import date

import job_filters
import requests

logger = logging.getLogger(__name__)

# Feishu webhook 单条消息上限为 30KB。除了限制岗位数量，还要限制每条文本，
# 否则大量新增岗位或异常长的 AI 分析仍可能让整条消息被拒绝。
_MAX_NEW_JOB_DETAILS = 8
_MAX_HIGH_SCORE_ROWS = 20
_HIGH_SCORE_THRESHOLD = 60
_CITY_TRUNCATE_LEN = 20
_JOB_LABEL_TRUNCATE_LEN = 60
_ANALYSIS_TRUNCATE_LEN = 120

# 高频缺口统计的噪声词：以这些开头或含这些关键字的 gap 不计入 Top5
_GAP_NOISE_KEYWORDS = ("专业方向", "学历要求", "经验要求", "工作年限", "不限")


def _is_intern_title(title: str) -> bool:
    return job_filters.is_intern_title(title)


def _is_current_cohort(job: dict) -> bool:
    """与主页面一致：仅保留 27 届或届别尚未明确的岗位。"""
    year = job_filters.cohort_year(job)
    return year is None or year >= 2027


def _truncate(text: str, max_len: int = _CITY_TRUNCATE_LEN) -> str:
    """超过 max_len 字符截断并追加 …。"""
    s = (text or "").strip()
    return s if len(s) <= max_len else s[: max_len] + "…"


def _report_url(date_str: str = "") -> str:
    """Cloudflare Pages 报告 URL。

    固定指向 index.html（始终最新）：报告只产出 index.html（main.py out_name=index、
    sync_report 也重生成 index.html），日期版快照不再单独生成，且本地事后录入的投递
    只会更新 index.html。故飞书链接指 index.html 才能看到最新岗位 + 投递记录。
    date_str 仅为兼容旧调用，已不参与拼接。
    """
    base_url = os.environ.get("REPORT_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
        if "/" in repository:
            owner, repo = repository.split("/", 1)
            base_url = f"https://{owner}.github.io/{repo}"
    return f"{base_url}/index.html" if base_url else ""


def _format_new_job(item: dict) -> list[list[dict]]:
    """渲染单条新增岗位 → Feishu post 内容里的若干行。"""
    job = item["job"]
    a = item.get("analysis") or {}
    score = a.get("match_score", "?")
    rec = a.get("recommendation", "未分析")
    advantages = _truncate("、".join(a.get("advantages", []) or []), _ANALYSIS_TRUNCATE_LEN) or "—"
    gaps = _truncate("、".join(a.get("gaps", []) or []), _ANALYSIS_TRUNCATE_LEN) or "—"
    city = _truncate(job.get("city", "")) or "—"
    company = _truncate(job.get("company", ""), _JOB_LABEL_TRUNCATE_LEN)
    title = _truncate(job.get("title", ""), _JOB_LABEL_TRUNCATE_LEN)

    head = f"🆕 [{company}] {title}  [{score}分][{rec}]"
    row1 = [{"tag": "text", "text": head}]
    row2 = [{"tag": "text", "text": f"   📍 {city}"}]
    row3 = [{"tag": "text", "text": f"   ✅ 优势: {advantages}"}]
    row4 = [{"tag": "text", "text": f"   ⚠️ 缺口: {gaps}"}]
    row5 = [{"tag": "text", "text": "   🔗 "},
            {"tag": "a", "text": "查看岗位", "href": job["jd_url"]}]
    return [row1, row2, row3, row4, row5]


def _format_high_score_row(item: dict) -> list[dict]:
    """高分岗位汇总单行：[分数][推荐] 公司 | 岗位 | 城市 | 链接"""
    job = item["job"]
    a = item["analysis"]
    city = _truncate(job.get("city", "")) or "—"
    company = _truncate(job.get("company", ""), _JOB_LABEL_TRUNCATE_LEN)
    title = _truncate(job.get("title", ""), _JOB_LABEL_TRUNCATE_LEN)
    line = f"[{a['match_score']}分][{a['recommendation']}] {company} | {title} | {city}  "
    return [
        {"tag": "text", "text": line},
        {"tag": "a", "text": "🔗", "href": job["jd_url"]},
    ]


def _collect_top_gaps(all_jobs: list[dict], top_n: int = 5) -> list[tuple[str, int]]:
    """只统计高分岗位（score >= 60）的 gaps；过滤"无XX"开头和噪声词。"""
    gaps: list[str] = []
    for it in all_jobs:
        a = it.get("analysis") or {}
        if a.get("match_score", 0) < _HIGH_SCORE_THRESHOLD:
            continue
        for g in (a.get("gaps", []) or []):
            g = (g or "").strip()
            if not g:
                continue
            if g.startswith("无"):
                continue
            if any(kw in g for kw in _GAP_NOISE_KEYWORDS):
                continue
            gaps.append(g)
    return Counter(gaps).most_common(top_n)


def _build_payload(new_jobs: list[dict],
                   all_jobs: list[dict],
                   report_data: dict) -> dict:
    """组装 Feishu post 富文本 payload。"""
    today = report_data.get("date") or date.today().isoformat()

    # 段 1：今日新增（按相同口径过滤：score >= 60 + 非实习 + Claude 未标不推荐）
    content_rows: list[list[dict]] = []
    analysis_by_url = {
        it["job"]["jd_url"]: it.get("analysis")
        for it in all_jobs
    }
    filtered_new = []
    for nj in new_jobs:
        if _is_intern_title(nj["title"]):
            continue
        if not _is_current_cohort(nj):
            continue
        a = analysis_by_url.get(nj["jd_url"])
        if not a:
            # 未分析的新增暂不展示（粗筛阶段会写 stub，下次再 evaluated）
            continue
        if a.get("recommendation") == "不推荐":
            continue
        if a.get("match_score", 0) < _HIGH_SCORE_THRESHOLD:
            continue
        filtered_new.append({"job": nj, "analysis": a})

    skipped = len(new_jobs) - len(filtered_new)
    header = f"━━━ 今日新增推荐 ({len(filtered_new)} 个)"
    if skipped:
        header += f"  ·  已过滤 {skipped} 个不相关"
    header += " ━━━"
    content_rows.append([{"tag": "text", "text": header}])

    displayed_new = filtered_new[:_MAX_NEW_JOB_DETAILS]
    if displayed_new:
        for item in displayed_new:
            content_rows.extend(_format_new_job(item))
            content_rows.append([{"tag": "text", "text": ""}])  # 空行分隔
        if len(filtered_new) > len(displayed_new):
            content_rows.append([{
                "tag": "text",
                "text": f"其余 {len(filtered_new) - len(displayed_new)} 个相关新增岗位请在完整报告中查看。",
            }])
    else:
        content_rows.append([{"tag": "text", "text": "今日无相关新增岗位"}])

    # 段 2：全部追踪高分岗位（score >= 60，过滤实习，降序）
    high = [
        it for it in all_jobs
        if it["analysis"]
        and it["analysis"].get("match_score", 0) >= _HIGH_SCORE_THRESHOLD
        and not _is_intern_title(it["job"]["title"])
        and _is_current_cohort(it["job"])
    ]
    high.sort(key=lambda x: x["analysis"]["match_score"], reverse=True)
    truncated = len(high) > _MAX_HIGH_SCORE_ROWS
    high = high[:_MAX_HIGH_SCORE_ROWS]

    title_suffix = f"（截断显示前 {_MAX_HIGH_SCORE_ROWS} 个）" if truncated else ""
    content_rows.append([{"tag": "text", "text": ""}])
    content_rows.append([{"tag": "text",
                          "text": f"━━━ 全部追踪高分岗位 (score≥{_HIGH_SCORE_THRESHOLD}, 共 {len(high)} 个){title_suffix} ━━━"}])
    if high:
        for it in high:
            content_rows.append(_format_high_score_row(it))
            content_rows.append([{"tag": "text", "text": ""}])  # 每个岗位间空行
    else:
        content_rows.append([{"tag": "text", "text": "暂无高分岗位"}])

    # 段 3：统计
    today_iso = date.today().isoformat()
    active_count = sum(1 for it in all_jobs if it["job"].get("last_seen_at") == today_iso)
    top_gaps = _collect_top_gaps(all_jobs)

    content_rows.append([{"tag": "text", "text": ""}])
    content_rows.append([{"tag": "text", "text": "━━━ 统计 ━━━"}])
    content_rows.append([{"tag": "text", "text": f"DB 共收录 {len(all_jobs)} 个岗位（活跃 {active_count} 个）"}])
    content_rows.append([{"tag": "text", "text": "高频缺口 Top5:"}])
    if top_gaps:
        for g, c in top_gaps:
            content_rows.append([{"tag": "text", "text": f"  • {g} ({c})"}])
    else:
        content_rows.append([{"tag": "text", "text": "  —"}])

    # 段 4：完整报告链接（CI 才有）
    url = _report_url(today)
    if url:
        content_rows.append([{"tag": "text", "text": ""}])
        content_rows.append([
            {"tag": "text", "text": "📄 "},
            {"tag": "a", "text": "完整报告", "href": url},
        ])

    return {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": f"🤖 AI 秋招情报 {today}",
                    "content": content_rows,
                }
            }
        },
    }


def send(new_jobs: list[dict],
         all_jobs: list[dict],
         report_data: dict) -> None:
    """推送到飞书。若未设置 FEISHU_WEBHOOK 静默跳过；网络失败只记 warning。"""
    webhook = os.environ.get("FEISHU_WEBHOOK", "").strip()
    if not webhook:
        logger.info("未设置 FEISHU_WEBHOOK，跳过推送")
        return

    payload = _build_payload(new_jobs, all_jobs, report_data)
    try:
        resp = requests.post(webhook, json=payload, timeout=15)
        if resp.status_code != 200:
            logger.warning("飞书推送返回 %d: %s", resp.status_code, resp.text[:200])
            return
        body = resp.json()
        if body.get("code", 0) != 0:
            logger.warning("飞书推送失败: %s", body)
        else:
            logger.info("飞书推送成功")
    except Exception as e:
        logger.warning("飞书推送异常: %s", e)
