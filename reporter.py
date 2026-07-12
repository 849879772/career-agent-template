"""HTML 报告生成器 — 单文件 SPA 风格，左侧导航 + 多页面切换。

设计参考：扁平卡片 + 蓝紫主色 (#6C63FF) + 圆角阴影 + 响应式。
6 个页面：
  - recommended (默认): 推荐岗位（≥70 大卡片 + 60-69 紧凑表格）
  - today: 今日新增岗位
  - companies: 公司排行（按公司聚合统计）
  - favorites / applications / messages: 占位"敬请期待"
"""
import html
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import job_filters
from db import APPLICATION_STAGES, KANBAN_COLUMNS, STAGE_TO_COLUMN

# 细阶段标签 + 看板列标签都并进来，并兜底老库可能存的旧 key（旧的 assessment/interview）
_STAGE_LABELS = dict(APPLICATION_STAGES)
for _k, _v in KANBAN_COLUMNS:
    _STAGE_LABELS.setdefault(_k, _v)
_STAGE_LABELS.setdefault("assessment", "笔试")  # 旧库 测评/笔试测评 → 现在统称笔试
_DEFAULT_STAGE_KEY = APPLICATION_STAGES[0][0]  # "applied"
# 列归并兜底：老库里 current_stage 直接是列 key 时，映射到自身
_STAGE_COLUMN = dict(STAGE_TO_COLUMN)
for _k, _v in KANBAN_COLUMNS:
    _STAGE_COLUMN.setdefault(_k, _k)


# ──────────────────────────────────────────────────────────────────────────
# 公用 helper
# ──────────────────────────────────────────────────────────────────────────

_PRIMARY = "#6C63FF"
_SUCCESS = "#10B981"
_WARN = "#F59E0B"
_GRAY = "#9CA3AF"
_HIGH_MATCH_THRESHOLD = 70

# 公司 avatar 配色（按公司名哈希挑一个色）
_AVATAR_COLORS = [
    "#EF4444", "#F97316", "#F59E0B", "#10B981", "#06B6D4",
    "#3B82F6", "#6366F1", "#8B5CF6", "#EC4899", "#14B8A6",
]


def _is_intern(title: str) -> bool:
    return job_filters.is_intern_title(title)


def _score_color(score) -> str:
    """根据分数返回主色（用于色块/数字）"""
    try:
        s = int(score)
    except (TypeError, ValueError):
        return _GRAY
    if s >= 80:
        return _SUCCESS
    if s >= 60:
        return _WARN
    return _GRAY


def _score_bg(score) -> str:
    """色块背景（淡色）"""
    try:
        s = int(score)
    except (TypeError, ValueError):
        return "#F3F4F6"
    if s >= 80:
        return "#ECFDF5"
    if s >= 60:
        return "#FFFBEB"
    return "#F3F4F6"


def _avatar_color(company: str) -> str:
    h = sum(ord(c) for c in (company or "")) % len(_AVATAR_COLORS)
    return _AVATAR_COLORS[h]


def _avatar_text(company: str) -> str:
    """取 1-2 个 CJK 字或英文首字母"""
    s = (company or "").strip()
    return s[:2] if s else "?"


def _city_short(city: str, max_len: int = 30) -> str:
    s = (city or "").strip()
    return s if len(s) <= max_len else s[:max_len] + "…"


_FAIL_SUMMARY = "分析失败，请检查API配置"
# 「未评估」= 粗筛判方向外、只收录不细评分的岗位（新文案 + 兼容旧库文案）。
_UNEVAL_PREFIXES = ("未评估", "AI 粗筛", "Claude 粗筛")


def _is_unevaluated(analysis: dict | None) -> bool:
    """方向外、未细评分的「未评估」岗位。"""
    if not analysis:
        return False
    if analysis.get("recommendation") == "未评估":
        return True
    summary = analysis.get("summary") or ""
    return any(summary.startswith(p) for p in _UNEVAL_PREFIXES)


def _platform_of(jd_url: str) -> str:
    """从 jd_url 推断招聘平台（用于前端筛选）。"""
    u = (jd_url or "").lower()
    if "mokahr.com" in u:
        return "Moka"
    if "zhiye.com" in u:
        return "北森"
    if "feishu.cn" in u or "mioffice" in u:
        return "飞书"
    return "自建"


def _is_unresolved_beisen_url(jd_url: str) -> bool:
    u = (jd_url or "").lower()
    return "zhiye.com/campus/jobs#" in u


def _is_detail_link(job: dict) -> bool:
    return bool(job.get("jd_url")) and job.get("link_kind", "detail") != "list"


def _cohort_label(job: dict) -> str:
    year = job_filters.cohort_year(job)
    if year == 2027:
        return "27届"
    if year is None:
        return "届别待确认"
    return f"{str(year)[-2:]}届"


def _job_title_html(job: dict) -> str:
    title = html.escape(job.get("title", ""))
    badge = f'<span class="cohort-badge">{html.escape(_cohort_label(job))}</span>'
    if _is_detail_link(job):
        return f'<a href="{html.escape(job["jd_url"])}" target="_blank" rel="noopener" class="cell-job-link">{title}</a> {badge}'
    return f'<span class="cell-job-link">{title}</span> {badge}'


def _job_action_html(job: dict) -> str:
    if not job.get("jd_url"):
        return ""
    is_detail = _is_detail_link(job)
    label = "去投递" if is_detail else "打开招聘列表"
    return (
        f'<a href="{html.escape(job["jd_url"])}" target="_blank" rel="noopener" '
        f'class="cell-action" title="{label}">'
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" '
        f'stroke="{_PRIMARY}" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/>'
        '<polygon points="22 2 15 22 11 13 2 9 22 2"/></svg></a>'
    )


def _jobs_payload(items: list, app_index=None) -> list[dict]:
    """前端搜索/筛选/分页用的紧凑岗位数组（短键减体积）。

    c=公司 t=岗位 ct=城市 s=匹配分(未评估为 None) r=推荐 p=平台 u=链接 e=是否已评分
    id=岗位ID ap=已投阶段标签(未投为"")——供前端「我投了」按钮 / 已投徽标用
    """
    app_index = app_index or {}
    out = []
    for it in items:
        job = it["job"]
        a = it.get("analysis") or {}
        evaluated = bool(a) and not _is_unevaluated(a)
        pending = not bool(a)  # 无分析记录 = 待评估（区别于方向外「未评估」stub）
        app = app_index.get(job.get("id"))
        ap = _STAGE_LABELS.get(app.get("current_stage"), app.get("current_stage") or "已投递") if app else ""
        out.append({
            "c": job.get("company", ""),
            "t": job.get("title", ""),
            "ct": _city_short(job.get("city", "") or "", 40),
            "s": a.get("match_score") if evaluated else None,
            "r": a.get("recommendation") if evaluated else ("待评估" if pending else "未评估"),
            "p": _platform_of(job.get("jd_url", "")),
            "u": job.get("jd_url", ""),
            "k": job.get("link_kind", "detail"),
            "cy": _cohort_label(job),
            "e": evaluated,
            "id": job.get("id"),
            "ap": ap,
        })
    return out


def _filter_items(all_items: list) -> tuple[list, list, int]:
    """Split current and previous cohorts while hiding invalid rows.

    原始岗位仍保留在数据库里；这里控制默认报告/本地看板的展示范围。
    返回 (展示项, 隐藏数)。
    """
    hidden = 0
    current, previous = [], []
    for it in all_items:
        a = it.get("analysis")
        title = it["job"].get("title", "")
        if job_filters.is_intern_job(it["job"]):
            hidden += 1
            continue
        if a and (a.get("summary") or "") == _FAIL_SUMMARY:
            hidden += 1
            continue
        if _is_unevaluated(a):
            hidden += 1
            continue
        if _is_unresolved_beisen_url(it["job"].get("jd_url", "")):
            hidden += 1
            continue
        year = job_filters.cohort_year(it["job"])
        (previous if year is not None and year <= 2026 else current).append(it)
    return current, previous, hidden


# ──────────────────────────────────────────────────────────────────────────
# 组件渲染
# ──────────────────────────────────────────────────────────────────────────

def _stat_card(value, label, icon_svg, accent_bg, accent_color) -> str:
    return f"""
<div class="stat-card">
  <div class="stat-icon" style="background:{accent_bg};color:{accent_color}">{icon_svg}</div>
  <div class="stat-text">
    <div class="stat-value">{value}</div>
    <div class="stat-label">{html.escape(label)}</div>
  </div>
</div>"""


def _company_avatar(company: str) -> str:
    color = _avatar_color(company)
    text = _avatar_text(company)
    return f'<div class="avatar" style="background:{color}">{html.escape(text)}</div>'


def _app_badge(app: dict) -> str:
    """已投递徽标（两种模式都显示）。"""
    if not app:
        return ""
    label = _STAGE_LABELS.get(app.get("current_stage"), app.get("current_stage") or "已投递")
    return f'<span class="app-badge">📋 {html.escape(label)}</span>'


def _apply_control(job: dict, app_index, editable: bool) -> str:
    """岗位卡上的投递控件：已投递→徽标；可编辑且未投→[我投了]表单；否则空。"""
    job_id = job.get("id")
    app = (app_index or {}).get(job_id) if job_id is not None else None
    if app:
        return _app_badge(app)
    if editable and job_id is not None:
        return (
            f'<form class="apply-form" method="post" action="/apply">'
            f'<input type="hidden" name="job_id" value="{job_id}">'
            f'<input type="hidden" name="company" value="{html.escape(job.get("company","") or "", quote=True)}">'
            f'<input type="hidden" name="title" value="{html.escape(job.get("title","") or "", quote=True)}">'
            f'<input type="hidden" name="city" value="{html.escape(job.get("city","") or "", quote=True)}">'
            f'<button type="submit" class="mark-btn">✅ 我投了</button></form>'
        )
    return ""


def _big_job_card(item: dict, app_index=None, editable: bool = False) -> str:
    job = item["job"]
    a = item["analysis"]
    score = a.get("match_score", 0)
    summary = a.get("summary") or ""
    advantages = a.get("advantages") or []
    gaps = a.get("gaps") or []
    city = _city_short(job.get("city", "") or "—")
    try:
        _pct = max(0, min(100, int(score)))
    except (TypeError, ValueError):
        _pct = 0

    adv_html = "".join(
        f'<li><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="{_SUCCESS}" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>'
        f'<span>{html.escape(a)}</span></li>'
        for a in advantages
    ) or '<li class="empty">—</li>'

    gaps_html = "".join(
        f'<li><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="{_WARN}" stroke-width="3"><circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>'
        f'<span>{html.escape(g)}</span></li>'
        for g in gaps
    ) or '<li class="empty">无明显短板</li>'

    return f"""
<article class="big-card">
  <div class="big-card-head">
    {_company_avatar(job['company'])}
    <div class="big-card-title">
      <h3>{html.escape(job['title'])}</h3>
      <div class="big-card-company">{html.escape(job['company'])}</div>
    </div>
    <div class="big-card-meta">
      <div class="location"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg> {html.escape(city)}</div>
      <div class="score-chip" style="background:{_score_bg(score)};color:{_score_color(score)}">
        <strong>{score}</strong> 匹配度
      </div>
      {_apply_control(job, app_index, editable)}
      {f'<a class="apply-btn" href="{html.escape(job["jd_url"])}" target="_blank" rel="noopener">立即投递</a>' if _is_detail_link(job) else '<span class="listing-hint">仅提供招聘列表</span>'}
    </div>
  </div>
  <p class="big-card-summary">{html.escape(summary) or '—'}</p>
  <div class="match-meter" title="匹配度 {score}/100">
    <div class="match-meter-marker" style="left:{_pct}%"></div>
  </div>
  <div class="big-card-grid">
    <div class="adv-block">
      <div class="block-title"><span style="color:{_SUCCESS}">●</span> 我的优势</div>
      <ul class="adv-list">{adv_html}</ul>
    </div>
    <div class="gap-block">
      <div class="block-title"><span style="color:{_WARN}">●</span> 缺失技能</div>
      <ul class="gap-list">{gaps_html}</ul>
    </div>
  </div>
  <div class="big-card-foot">
    {f'<a href="{html.escape(job["jd_url"])}" target="_blank" rel="noopener" class="detail-link">查看岗位详情 <span>›</span></a>' if _is_detail_link(job) else f'<a href="{html.escape(job["jd_url"])}" target="_blank" rel="noopener" class="detail-link">查看招聘列表 <span>›</span></a>'}
  </div>
</article>"""


def _table_job_row(item: dict, app_index=None, editable: bool = False) -> str:
    job = item["job"]
    a = item.get("analysis") or {}
    score = a.get("match_score", "—")
    city = _city_short(job.get("city", "") or "—", 50)
    control = _apply_control(job, app_index, editable)
    return f"""
<tr>
  <td class="cell-company">{_company_avatar(job['company'])} <span>{html.escape(job['company'])}</span></td>
  <td>{_job_title_html(job)} {control}</td>
  <td><span class="cell-score" style="background:{_score_bg(score)};color:{_score_color(score)}">{score}</span></td>
  <td class="cell-city">{html.escape(city)}</td>
  <td>{_job_action_html(job)}</td>
</tr>"""


# ──────────────────────────────────────────────────────────────────────────
# 页面构建
# ──────────────────────────────────────────────────────────────────────────

def _page_recommended(items: list, hidden_count: int, date_str: str,
                      app_index=None, editable: bool = False) -> tuple[str, dict]:
    """总体岗位页：高匹配大卡片置顶 + 全部岗位走前端搜索/筛选/分页表。"""
    items_with_a = [it for it in items if it.get("analysis")]
    evaluated = [it for it in items_with_a if not _is_unevaluated(it["analysis"])]
    recommended = sorted(
        [it for it in evaluated if (it["analysis"].get("match_score") or 0) >= _HIGH_MATCH_THRESHOLD],
        key=lambda x: x["analysis"].get("match_score") or 0,
        reverse=True,
    )
    uneval_count = sum(1 for it in items_with_a if _is_unevaluated(it["analysis"]))
    company_count = len({it["job"]["company"] for it in items})

    stats = {
        "active": len(items),
        "companies": company_count,
        "high_match": len(recommended),
        "unevaluated": uneval_count,
        "recommended": sum(1 for it in evaluated if it["analysis"].get("recommendation") == "推荐"),
        "hidden": hidden_count,
    }

    rec_html = (
        "\n".join(_big_job_card(it, app_index, editable) for it in recommended)
        if recommended
        else f'<div class="empty-state">📭 暂无高匹配岗位（≥{_HIGH_MATCH_THRESHOLD} 分）</div>'
    )

    # 前端表数据 + 公司下拉选项（去重排序）
    payload = _jobs_payload(items, app_index)
    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    editable_js = "true" if editable else "false"
    companies = sorted({j["c"] for j in payload})
    company_opts = "".join(f'<option value="{html.escape(c)}">{html.escape(c)}</option>' for c in companies)

    page = f"""
<section class="page active" data-page="recommended">
  <div class="page-head">
    <div>
      <h1>27届校招岗位</h1>
      <p class="page-sub">明确 27 届与届别待确认的正式校招岗位 · ≥{_HIGH_MATCH_THRESHOLD} 分置顶推荐</p>
    </div>
    <div class="page-meta">
      <span class="meta-pill">📅 扫描日期：{html.escape(date_str)}</span>
      <span class="meta-pill muted">已隐藏 {hidden_count} 个过滤项</span>
    </div>
  </div>

  <div class="stat-grid">
    {_stat_card(stats['active'], '岗位总数', _ICON_BAG, '#EEF0FF', _PRIMARY)}
    {_stat_card(stats['companies'], '覆盖企业数', _ICON_BUILDING, '#E0F2FE', '#0284C7')}
    {_stat_card(stats['high_match'], f'高匹配 (≥{_HIGH_MATCH_THRESHOLD})', _ICON_THUMBS, '#ECFDF5', _SUCCESS)}
    {_stat_card(stats['hidden'], '已隐藏过滤项', _ICON_STAR, '#F3F4F6', _GRAY)}
  </div>

  <h2 class="section-title">🎯 高匹配岗位（≥{_HIGH_MATCH_THRESHOLD} 分）</h2>
  <div class="big-card-list">
    {rec_html}
  </div>

  <h2 class="section-title">📋 全部岗位（搜索 / 筛选 / 分页）</h2>
  <div class="job-toolbar">
    <input type="search" id="jobSearch" class="jt-search" placeholder="搜索 公司 / 岗位 / 城市…">
    <select id="fCompany" class="jt-sel"><option value="">全部公司</option>{company_opts}</select>
    <select id="fPlatform" class="jt-sel">
      <option value="">全部平台</option><option>Moka</option><option>北森</option><option>飞书</option><option>自建</option>
    </select>
    <select id="fEval" class="jt-sel">
      <option value="">全部已展示</option><option value="scored">仅已评分</option>
    </select>
    <select id="fScore" class="jt-sel">
      <option value="">不限分数</option><option value="70">≥70</option><option value="60">60–69</option><option value="0">&lt;60</option>
    </select>
  </div>
  <div class="table-wrap">
    <table class="job-table">
      <thead>
        <tr><th>公司</th><th>岗位</th><th>匹配度</th><th>工作地点</th><th>平台</th><th>操作</th></tr>
      </thead>
      <tbody id="jobTbody"></tbody>
    </table>
  </div>
  <div class="job-pager">
    <button id="jpPrev" class="jp-btn">‹ 上一页</button>
    <span id="jpInfo" class="jp-info"></span>
    <button id="jpNext" class="jp-btn">下一页 ›</button>
  </div>
  <script>window.__JOBS = {data_json}; window.__EDITABLE = {editable_js};</script>
</section>"""
    return page, stats


def _page_previous_cohort(items: list, app_index=None, editable: bool = False) -> str:
    items = sorted(
        items,
        key=lambda item: (item.get("analysis") or {}).get("match_score", -1),
        reverse=True,
    )
    rows = "\n".join(_table_job_row(it, app_index, editable) for it in items)
    body = f"""
<div class="table-wrap"><table class="job-table"><thead>
  <tr><th>公司</th><th>岗位</th><th>匹配度</th><th>工作地点</th><th>操作</th></tr>
</thead><tbody>{rows}</tbody></table></div>""" if rows else '<div class="empty-state big-empty">暂无明确标注的往届校招岗位</div>'
    return f"""
<section class="page" data-page="previous-cohort">
  <div class="page-head"><div><h1>往届校招岗位</h1>
    <p class="page-sub">明确标注为 2026 届及更早届别的正式校招岗位 · 共 {len(items)} 个</p>
  </div></div>
  {body}
</section>"""


def _page_today(items: list, date_str: str, app_index=None, editable: bool = False) -> str:
    """今日新增页（crawled_at == 最新批次日期）。

    用最新批次（MAX(crawled_at)）而非日历 date_str，避免本地批量导入 / CI / 时区
    错位时「新增」塌成 0。
    """
    latest = max(
        (it["job"].get("crawled_at") for it in items if it["job"].get("crawled_at")),
        default=date_str,
    )
    new_items = [
        it for it in items
        if it.get("analysis") and it["job"].get("crawled_at") == latest
    ]
    new_items.sort(
        key=lambda x: x["analysis"].get("match_score", 0),
        reverse=True,
    )
    if not new_items:
        body = '<div class="empty-state big-empty">📭 今日暂无新增岗位<p>明天 08:00 会自动重新扫描</p></div>'
    else:
        rows = "\n".join(_table_job_row(it, app_index, editable) for it in new_items)
        body = f"""
<div class="table-wrap">
  <table class="job-table">
    <thead>
      <tr><th>公司</th><th>岗位</th><th>匹配度</th><th>工作地点</th><th>操作</th></tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""
    return f"""
<section class="page" data-page="today">
  <div class="page-head">
    <div>
      <h1>今日新增</h1>
      <p class="page-sub">本次扫描首次出现的岗位（共 {len(new_items)} 个）</p>
    </div>
    <div class="page-meta">
      <span class="meta-pill">📅 扫描日期：{html.escape(date_str)}</span>
    </div>
  </div>
  {body}
</section>"""


def _page_companies(items: list) -> str:
    """公司排行页 — 客户端渲染（聚合 / 分页 / 搜索均在前端从 window.__JOBS 计算）。

    每行可点击进入「公司详情页」(data-page=company-detail)。
    """
    return """
<section class="page" data-page="companies">
  <div class="page-head">
    <div>
      <h1>公司排行</h1>
      <p class="page-sub">按平均匹配度排序 · 点击任一公司查看其全部岗位</p>
    </div>
  </div>
  <div class="job-toolbar">
    <input type="search" id="companySearch" class="jt-search" placeholder="搜索公司名…">
  </div>
  <div class="table-wrap">
    <table class="job-table">
      <thead>
        <tr><th>公司</th><th>岗位数</th><th>平均匹配度</th><th>最高分</th><th>最高分岗位</th></tr>
      </thead>
      <tbody id="companyTbody"></tbody>
    </table>
  </div>
  <div class="job-pager">
    <button id="cpPrev" class="jp-btn">‹ 上一页</button>
    <span id="cpInfo" class="jp-info"></span>
    <button id="cpNext" class="jp-btn">下一页 ›</button>
  </div>
</section>"""


def _page_company_detail() -> str:
    """公司详情页（单个复用区块，内容由 JS 的 openCompany() 实时填充）。"""
    return """
<section class="page" data-page="company-detail">
  <div class="page-head">
    <div>
      <button id="cdBack" class="back-btn">← 返回公司排行</button>
      <div id="cdHead"></div>
    </div>
  </div>
  <div class="table-wrap">
    <table class="job-table">
      <thead>
        <tr><th>岗位</th><th>匹配度</th><th>工作地点</th><th>平台</th><th>操作</th></tr>
      </thead>
      <tbody id="cdTbody"></tbody>
    </table>
  </div>
</section>"""


_STAGE_RESULTS = ["待", "进行中", "通过", "挂"]
# 结果配色（淡背景, 前景）
_RESULT_STYLE = {
    "待": ("#F3F4F6", "#6B7280"),
    "进行中": ("#EFF6FF", "#3B82F6"),
    "通过": ("#ECFDF5", "#10B981"),
    "挂": ("#FEF2F2", "#EF4444"),
}


def _result_chip(result: str) -> str:
    bg, fg = _RESULT_STYLE.get(result, _RESULT_STYLE["待"])
    return f'<span class="result-chip" style="background:{bg};color:{fg}">{html.escape(result or "待")}</span>'


# 看板列配色 (key -> 淡背景, 主色)
_COL_STYLE = {
    "applied": ("#EEF0FF", "#6C63FF"),
    "written": ("#FEF3C7", "#B45309"),
    "interview": ("#E0E7FF", "#4338CA"),
    "offer": ("#DCFCE7", "#15803D"),
    "rejected": ("#F3F4F6", "#6B7280"),
}
_EVENT_TYPES = ["笔试", "测评", "一面", "二面", "三面", "HR面", "其他"]


def _event_sort_key(event: dict) -> tuple[str, str, str]:
    return (
        event.get("event_date") or "9999-12-31",
        event.get("event_time") or "99:99",
        event.get("company") or "",
    )


def _event_when(event: dict) -> str:
    date_part = event.get("event_date") or "日期待定"
    time_part = event.get("event_time") or ""
    return f"{date_part} {time_part}".strip()


def _collect_schedule_events(applications: list) -> list[dict]:
    events = []
    for app in applications:
        for event in app.get("events", []) or []:
            events.append({
                **event,
                "app_id": app.get("id"),
                "company": app.get("company", ""),
                "title": app.get("title", ""),
                "city": app.get("city", ""),
                "current_stage": app.get("current_stage") or _DEFAULT_STAGE_KEY,
            })
    return sorted(events, key=_event_sort_key)


def _event_form(app: dict) -> str:
    opts = "".join(f'<option>{html.escape(t)}</option>' for t in _EVENT_TYPES)
    return f"""
<form class="event-form" method="post" action="/application/{app['id']}/event">
  <select name="event_type">{opts}</select>
  <input type="date" name="event_date" required>
  <input type="time" name="event_time">
  <input name="note" placeholder="地点 / 链接 / 备注">
  <button type="submit">添加日程</button>
</form>"""


def _app_card(app: dict, job_index=None, editable: bool = False) -> str:
    """看板单卡。步骤由所在列体现，卡面只突出"结果"；面试列额外用小标显示第几轮。"""
    company = app.get("company", "") or "—"
    title = app.get("title", "") or "—"
    city = _city_short(app.get("city", "") or "", 40)
    note = app.get("note", "") or ""
    job_id = app.get("job_id")
    jinfo = (job_index or {}).get(job_id) if job_id is not None else None

    cur_stage = app.get("current_stage") or _DEFAULT_STAGE_KEY
    col = _STAGE_COLUMN.get(cur_stage, "applied")
    stages = app.get("stages", [])
    cur_result = stages[-1].get("result") if stages else "待"

    score_html = ""
    jd_link = ""
    if jinfo:
        sc = jinfo.get("match_score")
        if sc is not None:
            score_html = f'<span class="cell-score" style="background:{_score_bg(sc)};color:{_score_color(sc)}">{sc}</span>'
        if jinfo.get("jd_url"):
            label = "回看岗位 ›" if jinfo.get("link_kind", "detail") != "list" else "打开招聘列表 ›"
            jd_link = f'<a href="{html.escape(jinfo["jd_url"])}" target="_blank" rel="noopener" class="detail-link">{label}</a>'

    # 轮次小标：仅「面试」列显示第几面；「已挂」列显示挂在哪一轮（其余列步骤靠位置，不显示）
    round_chip = ""
    if col == "interview":
        round_chip = f'<span class="round-chip">{html.escape(_STAGE_LABELS.get(cur_stage, ""))}</span>'
    elif col == "rejected":
        cut = next((s.get("stage") for s in reversed(stages)
                    if s.get("stage") not in (None, "rejected", "applied")), None)
        if cut:
            round_chip = f'<span class="round-chip muted">{html.escape(_STAGE_LABELS.get(cut, cut))}挂</span>'

    # 阶段历史（可展开）
    hist_rows = "".join(
        f'<li>{html.escape(_STAGE_LABELS.get(s.get("stage"), s.get("stage") or ""))}'
        f' · {html.escape(s.get("result","") or "")}'
        f' · {html.escape(s.get("date","") or "")}'
        f'{(" · " + html.escape(s["note"])) if s.get("note") else ""}</li>'
        for s in stages
    )
    history = f'<details class="app-history"><summary>阶段历史 ({len(stages)})</summary><ul>{hist_rows}</ul></details>' if stages else ""
    events = sorted(app.get("events", []) or [], key=_event_sort_key)
    next_event = events[0] if events else None
    event_hint = ""
    if next_event:
        event_hint = (
            f'<div class="app-card-event">📅 {html.escape(_event_when(next_event))}'
            f' · {html.escape(next_event.get("event_type", "日程"))}'
            f'{(" · " + html.escape(next_event["note"])) if next_event.get("note") else ""}</div>'
        )

    edit_html = ""
    if editable:
        stage_opts = "".join(
            f'<option value="{k}"{" selected" if k == cur_stage else ""}>{html.escape(v)}</option>'
            for k, v in APPLICATION_STAGES
        )
        result_opts = "".join(
            f'<option{" selected" if r == cur_result else ""}>{html.escape(r)}</option>'
            for r in _STAGE_RESULTS
        )
        edit_html = f"""
<form class="stage-form" method="post" action="/application/{app['id']}/stage">
  <select name="stage">{stage_opts}</select>
  <select name="result">{result_opts}</select>
  <input name="note" placeholder="备注（可选）">
  <button type="submit">更新</button>
</form>
<form class="del-form" method="post" action="/application/{app['id']}/delete" onsubmit="return confirm('删除这条投递记录？')">
  <button type="submit" class="del-btn">删除</button>
</form>"""

    return f"""
<div class="app-card">
  <div class="app-card-head">
    {_company_avatar(company)}
    <div class="app-card-title">
      <div class="app-card-job">{html.escape(title)}</div>
      <div class="app-card-co">{html.escape(company)}{(" · " + html.escape(city)) if city else ""}</div>
    </div>
    {score_html}
  </div>
  <div class="app-card-status">{round_chip}{_result_chip(cur_result)}</div>
  {f'<div class="app-card-note">📝 {html.escape(note)}</div>' if note else ''}
  {event_hint}
  <div class="app-card-foot">{jd_link}{history}</div>
  {_event_form(app) if editable else ''}
  {edit_html}
</div>"""


def _page_applications(applications: list, job_index=None, editable: bool = False) -> str:
    """投递记录看板：5 列 + 顶部漏斗统计条 + 已挂列默认折叠。"""
    by_col: dict[str, list] = {k: [] for k, _ in KANBAN_COLUMNS}
    for app in applications:
        stage = app.get("current_stage") or _DEFAULT_STAGE_KEY
        col = _STAGE_COLUMN.get(stage, "applied")
        by_col.setdefault(col, []).append(app)

    # 顶部漏斗统计条
    funnel = "".join(
        f'<div class="funnel-item" style="border-top-color:{_COL_STYLE[k][1]}">'
        f'<div class="funnel-num" style="color:{_COL_STYLE[k][1]}">{len(by_col.get(k, []))}</div>'
        f'<div class="funnel-lbl">{html.escape(lbl)}</div></div>'
        for k, lbl in KANBAN_COLUMNS
    )
    funnel_bar = f'<div class="funnel-bar">{funnel}</div>'

    def _cards_html(cards):
        return ("\n".join(_app_card(a, job_index, editable) for a in cards)
                if cards else '<div class="kanban-empty">—</div>')

    main_cols = []
    rejected_col = ""
    for key, label in KANBAN_COLUMNS:
        cards = by_col.get(key, [])
        bg, fg = _COL_STYLE.get(key, ("#F9FAFB", "#374151"))
        if key == "rejected":
            # 已挂列：默认折叠（<details> 不带 open），灰化分隔
            rejected_col = f"""
<details class="kanban-col rejected-col">
  <summary class="kanban-col-head" style="background:{bg};color:{fg}">已挂 <span class="kanban-count">{len(cards)}</span></summary>
  <div class="kanban-body">{_cards_html(cards)}</div>
</details>"""
        else:
            main_cols.append(f"""
<div class="kanban-col" data-stage="{key}">
  <div class="kanban-col-head" style="background:{bg};color:{fg};border-bottom:2px solid {fg}">{html.escape(label)} <span class="kanban-count">{len(cards)}</span></div>
  <div class="kanban-body">{_cards_html(cards)}</div>
</div>""")

    manual_form = ""
    if editable:
        manual_form = """
<form class="manual-form" method="post" action="/application/new">
  <input name="company" placeholder="公司名" required>
  <input name="title" placeholder="岗位" required>
  <input name="city" placeholder="城市（可选）">
  <button type="submit">+ 手动添加库外投递</button>
</form>"""

    total = len(applications)
    return f"""
<section class="page" data-page="applications">
  <div class="page-head">
    <div>
      <h1>投递记录</h1>
      <p class="page-sub">步骤看所在列、卡面只看结果 · 共 {total} 条{'' if editable else '（只读，编辑请用本地"管理"模式）'}</p>
    </div>
  </div>
  {funnel_bar}
  {manual_form}
  <div class="kanban">
    {"".join(main_cols)}
    <div class="kanban-sep"></div>
    {rejected_col}
  </div>
</section>"""


def _page_schedule(applications: list, editable: bool = False) -> str:
    """投递日程：按日期聚合笔试/面试安排，并提供快速录入入口。"""
    events = _collect_schedule_events(applications)
    if events:
        days: dict[str, list] = defaultdict(list)
        for event in events:
            days[event.get("event_date") or "日期待定"].append(event)
        day_blocks = []
        for day, day_events in days.items():
            cards = []
            for event in day_events:
                note = event.get("note") or ""
                stage_label = _STAGE_LABELS.get(event.get("current_stage"), event.get("current_stage") or "")
                delete_form = ""
                if editable:
                    delete_form = (
                        f'<form method="post" action="/application/{event["app_id"]}/event/{event["id"]}/delete" '
                        f'class="event-delete" onsubmit="return confirm(\'删除这条日程？\')">'
                        f'<button type="submit">删除</button></form>'
                    )
                cards.append(f"""
<div class="schedule-card">
  <div class="schedule-time">{html.escape(event.get("event_time") or "全天")}</div>
  <div class="schedule-main">
    <div class="schedule-title">{html.escape(event.get("event_type") or "日程")} · {html.escape(event.get("company") or "—")}</div>
    <div class="schedule-job">{html.escape(event.get("title") or "—")}</div>
    <div class="schedule-meta">{html.escape(stage_label)}{(" · " + html.escape(event.get("city") or "")) if event.get("city") else ""}</div>
    {f'<div class="schedule-note">{html.escape(note)}</div>' if note else ''}
  </div>
  {delete_form}
</div>""")
            day_blocks.append(f"""
<section class="schedule-day">
  <div class="schedule-date">{html.escape(day)} <span>{len(day_events)} 项</span></div>
  <div class="schedule-stack">{"".join(cards)}</div>
</section>""")
        timeline = "".join(day_blocks)
    else:
        timeline = '<div class="empty-state big-empty">📭 暂无日程<p>在投递卡片或右侧表单中添加笔试、面试安排。</p></div>'

    quick_forms = ""
    if editable:
        form_cards = []
        for app in applications:
            form_cards.append(f"""
<div class="schedule-form-card">
  <div class="schedule-form-title">{html.escape(app.get("company", "") or "—")}</div>
  <div class="schedule-form-sub">{html.escape(app.get("title", "") or "—")}</div>
  {_event_form(app)}
</div>""")
        quick_forms = f"""
<aside class="schedule-side">
  <div class="schedule-side-title">快速添加</div>
  <div class="schedule-form-list">{"".join(form_cards) if form_cards else '<div class="kanban-empty">暂无投递记录</div>'}</div>
</aside>"""

    return f"""
<section class="page" data-page="schedule">
  <div class="page-head">
    <div>
      <h1>日程安排</h1>
      <p class="page-sub">按日期展示投递后的笔试、面试和其他后续安排 · 共 {len(events)} 项</p>
    </div>
  </div>
  <div class="schedule-layout">
    <div class="schedule-timeline">{timeline}</div>
    {quick_forms}
  </div>
</section>"""


def _page_placeholder(slug: str, title: str, hint: str) -> str:
    return f"""
<section class="page" data-page="{slug}">
  <div class="page-head">
    <div>
      <h1>{html.escape(title)}</h1>
      <p class="page-sub">{html.escape(hint)}</p>
    </div>
  </div>
  <div class="empty-state big-empty">
    <div style="font-size:48px;margin-bottom:12px">🛠</div>
    <div style="font-size:18px;font-weight:600;color:#374151">敬请期待</div>
    <p>这个功能正在路上。</p>
  </div>
</section>"""


# ──────────────────────────────────────────────────────────────────────────
# 图标 SVG（行内，避免外部依赖）
# ──────────────────────────────────────────────────────────────────────────

_ICON_BAG = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 7h-3V5a2 2 0 0 0-2-2H9a2 2 0 0 0-2 2v2H4a1 1 0 0 0-1 1v11a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8a1 1 0 0 0-1-1z"/></svg>'
_ICON_BUILDING = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/></svg>'
_ICON_THUMBS = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 0 0-6 0v4H4v11h13l3-8V9h-6z"/></svg>'
_ICON_STAR = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15 9 22 10 17 15 18 22 12 18 6 22 7 15 2 10 9 9 12 2"/></svg>'


# 侧栏导航分两组：发现（来自抓取，只读）/ 我的（投递动作）
_ICON_RANK = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l-3 3 3 3M18 9l3 3-3 3M9 4l-2 16M15 4l2 16"/></svg>'
_ICON_CLOCK = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><polyline points="12 6 12 12 16 14"/></svg>'
_ICON_BARS = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>'
_ICON_KANBAN = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="6" height="18" rx="1"/><rect x="11" y="3" width="6" height="12" rx="1"/><rect x="19" y="3" width="2" height="9" rx="1"/></svg>'
_ICON_CALENDAR = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="17" rx="2"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>'

_NAV_GROUPS = [
    ("发现", [
        ("recommended", "27届校招", _ICON_RANK),
        ("today", "今日新增", _ICON_CLOCK),
        ("companies", "公司排行", _ICON_BARS),
        ("previous-cohort", "往届校招岗位", _ICON_CLOCK),
    ]),
    ("我的", [
        ("applications", "投递记录", _ICON_KANBAN),
        ("schedule", "日程安排", _ICON_CALENDAR),
    ]),
]


def _render_sidebar() -> str:
    blocks = []
    first = True
    for group_label, items in _NAV_GROUPS:
        lis = []
        for slug, label, icon in items:
            active = " active" if first else ""
            first = False
            lis.append(
                f'<li class="nav-item{active}" data-target="{slug}">'
                f'<span class="nav-icon">{icon}</span><span class="nav-label">{label}</span>'
                f'</li>'
            )
        blocks.append(
            f'<div class="nav-group-label">{html.escape(group_label)}</div>'
            f'<ul class="nav-list">{"".join(lis)}</ul>'
        )
    return f"""
<aside class="sidebar">
  <div class="brand">
    <div class="brand-icon">🤖</div>
    <div class="brand-text">
      <div class="brand-title">AI 秋招情报</div>
      <div class="brand-sub">智能匹配 · 精准推荐</div>
    </div>
  </div>
  {"".join(blocks)}
</aside>"""


# ──────────────────────────────────────────────────────────────────────────
# CSS / JS
# ──────────────────────────────────────────────────────────────────────────

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
               "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  background: #F5F6FA; color: #1F2937; min-height: 100vh;
  font-size: 14px; line-height: 1.55;
}
a { color: inherit; text-decoration: none; }
ul { list-style: none; }

/* ── Layout ─────────────────────────────────────── */
.layout { display: flex; min-height: 100vh; }
.sidebar {
  width: 240px; background: #FFFFFF; border-right: 1px solid #E5E7EB;
  padding: 24px 16px; flex-shrink: 0; position: sticky; top: 0;
  height: 100vh; overflow-y: auto;
}
.main { flex: 1; padding: 28px 32px; max-width: 100%; overflow-x: hidden; }

/* ── Sidebar ────────────────────────────────────── */
.brand { display: flex; align-items: center; gap: 12px; padding: 0 8px 24px;
         border-bottom: 1px solid #F1F2F6; margin-bottom: 16px; }
.brand-icon { width: 40px; height: 40px; border-radius: 10px;
              background: linear-gradient(135deg, #6C63FF, #8B7FFF);
              display: grid; place-items: center; font-size: 22px; }
.brand-title { font-size: 15px; font-weight: 700; color: #111827; }
.brand-sub { font-size: 12px; color: #9CA3AF; margin-top: 2px; }
.nav-list { display: flex; flex-direction: column; gap: 4px; margin-bottom: 14px; }
.nav-group-label { font-size: 11px; font-weight: 600; color: #9CA3AF;
                   text-transform: uppercase; letter-spacing: .5px;
                   padding: 0 12px 6px; margin-top: 4px; }
.nav-item { position: relative; display: flex; align-items: center; gap: 12px;
            padding: 10px 12px; border-radius: 8px; cursor: pointer;
            color: #6B7280; font-size: 14px; user-select: none;
            transition: background .15s, color .15s; }
.nav-item:hover { background: #F5F6FA; color: #374151; }
.nav-item.active { background: #EEF0FF; color: #6C63FF; font-weight: 600; }
.nav-item.active::before { content: ""; position: absolute; left: 0; top: 50%;
            transform: translateY(-50%); width: 3px; height: 18px;
            border-radius: 0 3px 3px 0; background: #6C63FF; }
.nav-icon { display: inline-grid; place-items: center; flex-shrink: 0; }

/* ── Page Head ──────────────────────────────────── */
.page { display: none; animation: fadeIn .2s ease-out; }
.page.active { display: block; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(4px); }
                    to   { opacity: 1; transform: none; } }
.page-head { display: flex; justify-content: space-between; align-items: flex-start;
             gap: 20px; flex-wrap: wrap; margin-bottom: 24px; }
.page-head h1 { font-size: 24px; font-weight: 700; color: #111827; }
.page-sub { color: #6B7280; margin-top: 4px; font-size: 13px; }
.page-meta { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
.meta-pill { background: #FFFFFF; border: 1px solid #E5E7EB; padding: 6px 12px;
             border-radius: 20px; font-size: 12px; color: #4B5563; }
.meta-pill.muted { color: #9CA3AF; }

/* ── Stat Cards ─────────────────────────────────── */
.stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;
             margin-bottom: 28px; }
.stat-card { background: #FFFFFF; border: 1px solid #ECEDF3; border-radius: 14px;
             padding: 18px 22px; display: flex; align-items: center; gap: 16px;
             box-shadow: 0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.03);
             transition: box-shadow .18s ease, transform .18s ease; }
.stat-card:hover { box-shadow: 0 4px 16px rgba(16,24,40,.08); transform: translateY(-2px); }
.stat-icon { width: 48px; height: 48px; border-radius: 12px;
             display: grid; place-items: center; flex-shrink: 0; }
.stat-value { font-size: 28px; font-weight: 700; color: #111827; line-height: 1; }
.stat-label { font-size: 13px; color: #6B7280; margin-top: 4px; }

/* ── Section Title ──────────────────────────────── */
.section-title { font-size: 16px; font-weight: 600; color: #1F2937;
                 margin: 20px 0 14px; }

/* ── Big Job Card ───────────────────────────────── */
.big-card { background: #FFFFFF; border-radius: 14px; padding: 22px 24px;
            margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
            border-left: 4px solid #6C63FF; }
.big-card-head { display: flex; align-items: flex-start; gap: 14px;
                 margin-bottom: 12px; flex-wrap: wrap; }
.big-card-title { flex: 1; min-width: 180px; }
.big-card-title h3 { font-size: 18px; font-weight: 700; color: #111827; }
.big-card-company { color: #6B7280; font-size: 13px; margin-top: 2px; }
.big-card-meta { display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
                 margin-left: auto; }
.location { color: #6B7280; font-size: 13px; display: inline-flex;
            align-items: center; gap: 4px; }
.score-chip { padding: 6px 12px; border-radius: 8px; font-size: 13px;
              font-weight: 500; white-space: nowrap;
              box-shadow: inset 0 0 0 1px rgba(0,0,0,.05); }
.score-chip strong { font-size: 16px; margin-right: 2px; }
.apply-btn { background: #6C63FF; color: #FFF !important; padding: 8px 18px;
             border-radius: 8px; font-size: 13px; font-weight: 500;
             transition: background .15s; }
.apply-btn:hover { background: #5A52E8; }
.listing-hint { color: #6B7280; font-size: 12px; white-space: nowrap; }
.big-card-summary { color: #4B5563; font-size: 14px; margin: 8px 0 16px;
                    line-height: 1.7; }
/* 匹配度渐变量度条（红→橙→黄→绿，参考 21st.dev Performance Benchmark Card） */
.match-meter { position: relative; height: 7px; border-radius: 5px; margin: 2px 0 18px;
               background: linear-gradient(90deg,#EF4444 0%,#F59E0B 38%,#FACC15 60%,#10B981 100%); }
.match-meter-marker { position: absolute; top: 50%; width: 14px; height: 14px;
               border-radius: 50%; background: #FFF; border: 3px solid #111827;
               transform: translate(-50%,-50%); box-shadow: 0 1px 4px rgba(0,0,0,.25); }
.big-card-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
.block-title { font-weight: 600; color: #374151; margin-bottom: 8px;
               font-size: 13px; display: flex; align-items: center; gap: 6px; }
.adv-list li, .gap-list li { display: flex; align-items: flex-start; gap: 8px;
                             padding: 4px 0; font-size: 13px; color: #4B5563; }
.adv-list li svg, .gap-list li svg { flex-shrink: 0; margin-top: 3px; }
.adv-list li.empty, .gap-list li.empty { color: #9CA3AF; padding-left: 22px; }
.big-card-foot { display: flex; justify-content: flex-end; margin-top: 14px;
                 padding-top: 12px; border-top: 1px solid #F3F4F6; }
.detail-link { color: #6C63FF; font-size: 13px; font-weight: 500;
               display: inline-flex; align-items: center; gap: 4px; }
.detail-link span { font-size: 18px; line-height: 1; }

/* ── Job Table ─────────────────────────────────── */
.table-wrap { background: #FFFFFF; border-radius: 14px; overflow: hidden;
              box-shadow: 0 1px 3px rgba(0,0,0,0.04); overflow-x: auto; }
.job-table { width: 100%; min-width: 760px; border-collapse: collapse; table-layout: fixed; }
.job-table thead { background: #F9FAFB; }
.job-table th { text-align: left; padding: 12px 16px; font-size: 13px;
                font-weight: 600; color: #6B7280; border-bottom: 1px solid #E5E7EB; }
.job-table td { padding: 14px 16px; font-size: 13px; color: #1F2937;
                border-bottom: 1px solid #F3F4F6; vertical-align: middle; }
.job-table tbody tr:hover { background: #FAFBFC; }
.job-table tbody tr:last-child td { border-bottom: none; }
.cell-company { display: flex; align-items: center; gap: 10px; min-width: 100px; }
.job-table th:nth-child(1), .job-table td:nth-child(1) { width: 150px; }
.job-table th:nth-child(2), .job-table td:nth-child(2) { width: 260px; }
.job-table th:nth-child(3), .job-table td:nth-child(3) { width: 96px; }
.job-table th:nth-child(4), .job-table td:nth-child(4) { width: 180px; }
.job-table th:nth-child(5), .job-table td:nth-child(5) { width: 90px; }
.job-table th:nth-child(6), .job-table td:nth-child(6) { width: 120px; }
.avatar { width: 28px; height: 28px; border-radius: 8px; color: #FFF;
          display: grid; place-items: center; font-size: 11px;
          font-weight: 600; flex-shrink: 0; letter-spacing: -0.3px; }
.cell-job-link { color: #1F2937; font-weight: 500; }
.cell-job-link:hover { color: #6C63FF; }
.cell-score { display: inline-block; padding: 4px 10px; border-radius: 7px;
              font-weight: 600; font-size: 13px; min-width: 36px; text-align: center;
              box-shadow: inset 0 0 0 1px rgba(0,0,0,.04); }
.cell-city { color: #6B7280; font-size: 13px; max-width: 320px;
             overflow: hidden; text-overflow: ellipsis; }
.cell-num { color: #1F2937; font-weight: 500; }
.cell-job-name { color: #4B5563; max-width: 280px; overflow: hidden;
                 text-overflow: ellipsis; }
.cell-action { display: inline-grid; place-items: center; width: 32px; height: 32px;
               border-radius: 8px; background: #F5F6FA; }
.cell-action:hover { background: #EEF0FF; }
.cohort-badge { display: inline-block; margin-left: 6px; padding: 1px 6px; border-radius: 5px;
                background: #F3F4F6; color: #6B7280; font-size: 11px; white-space: nowrap; }

/* ── Empty State ────────────────────────────────── */
.empty-state { color: #9CA3AF; text-align: center; padding: 28px;
               font-size: 14px; background: #FFFFFF; border-radius: 12px; }
.empty-state.big-empty { padding: 60px 28px; }
.empty-state.big-empty p { color: #9CA3AF; font-size: 13px; margin-top: 6px; }

/* ── 投递徽标 / 我投了按钮 ──────────────────────── */
.app-badge { display: inline-block; background: #ECFDF5; color: #10B981;
             border-radius: 6px; padding: 2px 8px; font-size: 12px; font-weight: 600;
             white-space: nowrap; }
.apply-form { display: inline; }
.mark-btn { background: #10B981; color: #FFF; border: none; cursor: pointer;
            padding: 6px 12px; border-radius: 8px; font-size: 12px; font-weight: 500; }
.mark-btn:hover { background: #0E9F6E; }

/* ── 顶部漏斗统计条 ─────────────────────────────── */
.funnel-bar { display: flex; gap: 10px; margin-bottom: 18px; }
.funnel-item { flex: 1; background: #FFFFFF; border: 1px solid #E5E7EB;
               border-top: 3px solid #6C63FF; border-radius: 10px;
               padding: 12px 8px; text-align: center;
               box-shadow: 0 1px 2px rgba(0,0,0,0.04); }
.funnel-num { font-size: 24px; font-weight: 700; line-height: 1; }
.funnel-lbl { font-size: 12px; color: #6B7280; margin-top: 5px; }

/* ── 投递看板 (Kanban) ──────────────────────────── */
.kanban { display: flex; gap: 10px; align-items: flex-start; }
.kanban-col { flex: 1; min-width: 0; background: #FFFFFF; border: 1px solid #E5E7EB;
              border-radius: 10px; overflow: hidden; }
.kanban-col-head { font-size: 13px; font-weight: 700; padding: 8px 10px; }
.kanban-count { float: right; background: rgba(0,0,0,0.07); border-radius: 10px;
                padding: 0 8px; font-size: 11px; font-weight: 600; }
.kanban-body { padding: 8px; }
.kanban-empty { color: #C7CBD1; text-align: center; font-size: 12px; padding: 12px; }
/* 已挂列：虚线分隔 + 灰化 + 默认折叠 */
.kanban-sep { align-self: stretch; border-left: 2px dashed #D1D5DB; }
.rejected-col { flex: 0.85; background: #F9FAFB; border: 1px dashed #9CA3AF;
                border-radius: 10px; overflow: hidden; opacity: .8; }
.rejected-col > summary { list-style: none; cursor: pointer; }
.rejected-col > summary::-webkit-details-marker { display: none; }

.app-card { background: #FFFFFF; border: 1px solid #F3F4F6; border-radius: 10px;
            padding: 12px; margin-bottom: 10px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
.app-card:last-child { margin-bottom: 0; }
.app-card-head { display: flex; align-items: center; gap: 8px; }
.app-card-title { flex: 1; min-width: 0; }
.app-card-job { font-weight: 600; font-size: 13px; color: #111827; }
.app-card-co { font-size: 12px; color: #6B7280; margin-top: 2px;
               white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
/* 状态行：轮次小标 + 结果（醒目，单独一行）*/
.app-card-status { display: flex; align-items: center; gap: 6px; margin-top: 10px; }
.round-chip { display: inline-block; padding: 3px 9px; border-radius: 6px;
              background: #6366F1; color: #FFF; font-size: 12px; font-weight: 700; }
.round-chip.muted { background: #E5E7EB; color: #6B7280; }
.result-chip { display: inline-block; padding: 3px 11px; border-radius: 7px;
               font-size: 13px; font-weight: 700; white-space: nowrap;
               box-shadow: inset 0 0 0 1px rgba(0,0,0,.05); }
.app-card-note { font-size: 12px; color: #4B5563; margin-top: 8px;
                 background: #FFFBEB; border-radius: 6px; padding: 6px 8px; }
.app-card-event { font-size: 12px; color: #1F2937; margin-top: 8px;
                  background: #EEF2FF; border-radius: 6px; padding: 6px 8px; }
.app-card-foot { display: flex; justify-content: space-between; align-items: center;
                 gap: 8px; margin-top: 8px; flex-wrap: wrap; }
.app-history { font-size: 12px; color: #6B7280; }
.app-history summary { cursor: pointer; color: #6C63FF; }
.app-history ul { margin: 6px 0 0; padding-left: 14px; list-style: disc; }
.app-history li { padding: 2px 0; }
.stage-form, .manual-form, .event-form { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.stage-form select, .stage-form input, .manual-form input,
.event-form select, .event-form input {
  border: 1px solid #E5E7EB; border-radius: 6px; padding: 5px 8px; font-size: 12px; }
/* 两个下拉等宽各占半行、备注+更新同一行，使每张卡的表单布局/高度一致，不再参差 */
.stage-form select { flex: 1 1 calc(50% - 3px); min-width: 0; }
.stage-form input { flex: 1 1 60%; min-width: 0; }
.stage-form button, .manual-form button, .event-form button {
  background: #6C63FF; color: #FFF; border: none; border-radius: 6px;
  padding: 5px 12px; font-size: 12px; cursor: pointer; }
.event-form select { flex: 1 1 70px; min-width: 0; }
.event-form input[type="date"] { flex: 1 1 120px; min-width: 0; }
.event-form input[type="time"] { flex: 1 1 86px; min-width: 0; }
.event-form input[name="note"] { flex: 1 1 100%; min-width: 0; }
.manual-form { background: #FFFFFF; padding: 12px; border-radius: 10px;
               margin-bottom: 16px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }
.del-form { display: inline; }
.del-btn { background: none; border: none; color: #EF4444; font-size: 12px;
           cursor: pointer; padding: 2px 4px; }

/* ── 日程安排 ─────────────────────────────────── */
.schedule-layout { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 18px; align-items: start; }
.schedule-timeline, .schedule-side { min-width: 0; }
.schedule-day { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 10px;
                margin-bottom: 14px; overflow: hidden; }
.schedule-date { display: flex; justify-content: space-between; align-items: center;
                 padding: 10px 14px; background: #F9FAFB; font-weight: 700; color: #111827; }
.schedule-date span { font-size: 12px; color: #6B7280; font-weight: 500; }
.schedule-stack { padding: 10px; display: grid; gap: 10px; }
.schedule-card { display: grid; grid-template-columns: 72px minmax(0, 1fr) auto; gap: 12px;
                 align-items: start; border: 1px solid #F3F4F6; border-radius: 8px; padding: 10px; }
.schedule-time { color: #6C63FF; font-weight: 700; font-size: 13px; }
.schedule-title { color: #111827; font-weight: 700; font-size: 14px; }
.schedule-job, .schedule-meta { color: #6B7280; font-size: 12px; margin-top: 2px; }
.schedule-note { color: #374151; font-size: 12px; margin-top: 6px; background: #FFFBEB;
                 border-radius: 6px; padding: 6px 8px; }
.event-delete button { background: none; border: none; color: #EF4444; cursor: pointer;
                       font-size: 12px; padding: 2px 4px; }
.schedule-side { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 10px;
                 padding: 12px; position: sticky; top: 20px; max-height: calc(100vh - 40px); overflow: auto; }
.schedule-side-title { font-weight: 700; color: #111827; margin-bottom: 10px; }
.schedule-form-list { display: grid; gap: 10px; }
.schedule-form-card { border: 1px solid #F3F4F6; border-radius: 8px; padding: 10px; }
.schedule-form-title { font-weight: 700; color: #111827; font-size: 13px; }
.schedule-form-sub { color: #6B7280; font-size: 12px; margin-top: 2px; }

/* ── 岗位搜索 / 筛选 / 分页 ─────────────────────── */
.job-toolbar { display: flex; flex-wrap: wrap; gap: 10px; margin: 8px 0 16px; }
.jt-search { flex: 1 1 240px; min-width: 180px; padding: 9px 12px; font-size: 14px;
             border: 1px solid #E5E7EB; border-radius: 8px; background: #FFF; }
.jt-search:focus, .jt-sel:focus { outline: none; border-color: #6C63FF;
             box-shadow: 0 0 0 3px rgba(108,99,255,.12); }
.jt-sel { padding: 9px 10px; font-size: 13px; border: 1px solid #E5E7EB;
          border-radius: 8px; background: #FFF; color: #374151; cursor: pointer; }
.cell-score.uneval { background: #F3F4F6; color: #9CA3AF; font-weight: 500; }
.cell-plat { display: inline-block; padding: 2px 8px; border-radius: 6px;
             background: #F1F5F9; color: #475569; font-size: 12px; font-weight: 500; }
.job-pager { display: flex; align-items: center; justify-content: center; gap: 16px;
             margin: 16px 0 8px; }
.jp-btn { padding: 7px 16px; font-size: 13px; border: 1px solid #E5E7EB;
          border-radius: 8px; background: #FFF; color: #374151; cursor: pointer; }
.jp-btn:hover:not(:disabled) { border-color: #6C63FF; color: #6C63FF; }
.jp-btn:disabled { opacity: .45; cursor: not-allowed; }
.jp-info { font-size: 13px; color: #6B7280; }
/* 公司排行：可点击行 */
.company-row { cursor: pointer; }
.company-row:hover { background: #F5F6FA; }
/* 公司详情页 */
.back-btn { display: inline-flex; align-items: center; padding: 6px 12px; margin-bottom: 12px;
            font-size: 13px; border: 1px solid #E5E7EB; border-radius: 8px;
            background: #FFF; color: #374151; cursor: pointer; }
.back-btn:hover { border-color: #6C63FF; color: #6C63FF; }
.cd-title { display: flex; align-items: center; gap: 12px; }
.cd-title h1 { font-size: 24px; font-weight: 700; color: #111827; }
.cd-stats { display: flex; gap: 18px; margin-top: 10px; flex-wrap: wrap; }
.cd-stat { font-size: 13px; color: #6B7280; }
.cd-stat b { font-size: 16px; color: #111827; margin: 0 2px; }

/* ── Responsive ─────────────────────────────────── */
@media (max-width: 1500px) and (min-width: 769px) {
  /* 带侧边栏的常见 1366/1440 桌面宽度下，五列会把卡片压得过窄。
     四个进行中阶段固定为 2x2，已挂列单独占一行。 */
  .kanban { flex-wrap: wrap; }
  .kanban-col { flex: 1 1 calc(50% - 5px); min-width: 320px; }
  .kanban-sep { display: none; }
  .rejected-col { flex: 1 1 100%; }
}
@media (max-width: 1024px) {
  .stat-grid { grid-template-columns: repeat(2, 1fr); }
  .big-card-grid { grid-template-columns: 1fr; gap: 16px; }
  .kanban { flex-wrap: wrap; }
  .kanban-col { flex: 1 1 calc(50% - 5px); }
  .funnel-bar { flex-wrap: wrap; }
  .funnel-item { flex: 1 1 28%; }
  .schedule-layout { grid-template-columns: 1fr; }
  .schedule-side { position: static; max-height: none; }
}
@media (max-width: 768px) {
  .layout { flex-direction: column; }
  .kanban { flex-direction: column; }
  .kanban-col, .rejected-col { flex: 1 1 auto; width: 100%; }
  .kanban-sep { display: none; }
  .sidebar { width: 100%; height: auto; position: relative;
             border-right: none; border-bottom: 1px solid #E5E7EB; }
  .nav-list { flex-direction: row; overflow-x: auto; gap: 8px;
              padding-bottom: 4px; -webkit-overflow-scrolling: touch; }
  .nav-item { flex-shrink: 0; white-space: nowrap; padding: 8px 12px; }
  .main { padding: 16px; }
  .page-head { flex-direction: column; align-items: stretch; }
  .page-meta { align-items: flex-start; }
  .stat-grid { grid-template-columns: 1fr; }
  .big-card-meta { margin-left: 0; }
  .table-wrap { margin-left: -16px; margin-right: -16px; border-radius: 0; }
  .job-table { min-width: 720px; }
  .schedule-card { grid-template-columns: 1fr; gap: 6px; }
  .schedule-time { font-size: 12px; }
}
"""


_JS = """
document.addEventListener('DOMContentLoaded', () => {
  const navItems = document.querySelectorAll('.nav-item');
  const pages = document.querySelectorAll('.page');
  function activate(target) {
    const page = document.querySelector(`.page[data-page="${target}"]`);
    if (!page) return;
    navItems.forEach(i => i.classList.toggle('active', i.dataset.target === target));
    pages.forEach(p => p.classList.remove('active'));
    page.classList.add('active');
  }
  navItems.forEach(item => {
    item.addEventListener('click', () => {
      activate(item.dataset.target);
      if (history.replaceState) history.replaceState(null, '', '#' + item.dataset.target);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  });
  const initialHash = (window.location.hash || '').replace('#', '');
  if (initialHash) activate(initialHash);
  // ── 共享数据 + 渲染助手（全部岗位表 / 公司排行 / 公司详情 共用）──
  const JOBS = window.__JOBS || [];
  const el = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g,
    c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const AVATAR_COLORS = ['#EF4444','#F97316','#F59E0B','#10B981','#06B6D4','#3B82F6','#6366F1','#8B5CF6','#EC4899','#14B8A6'];
  function avatar(name) {
    const s = String(name || '').trim();
    let h = 0; for (const ch of s) h += ch.codePointAt(0);
    const color = AVATAR_COLORS[h % AVATAR_COLORS.length];
    return '<div class="avatar" style="background:' + color + '">' + esc(s.slice(0, 2) || '?') + '</div>';
  }
  function scoreCell(s) {
    let bg, fg;
    if (s >= 80) { bg = '#ECFDF5'; fg = '#10B981'; }
    else if (s >= 60) { bg = '#FFFBEB'; fg = '#F59E0B'; }
    else { bg = '#F3F4F6'; fg = '#9CA3AF'; }
    return '<span class="cell-score" style="background:' + bg + ';color:' + fg + '">' + s + '</span>';
  }
  function badge(j) {
    if (!j.e) return '<span class="cell-score uneval">' + esc(j.r || '未评估') + '</span>';
    return scoreCell(j.s || 0);
  }
  function opCell(j) {
    var link = j.u ? '<a href="' + esc(j.u) + '" target="_blank" rel="noopener" class="cell-action" title="' + (j.k === 'list' ? '打开招聘列表' : '去投递') + '">↗</a>' : '';
    if (j.ap) return '<span class="app-badge">📋 ' + esc(j.ap) + '</span> ' + link;
    if (window.__EDITABLE && j.id != null) {
      return '<form class="apply-form" method="post" action="/apply" style="display:inline-flex;align-items:center;gap:6px">' +
        '<input type="hidden" name="job_id" value="' + esc(j.id) + '">' +
        '<input type="hidden" name="company" value="' + esc(j.c) + '">' +
        '<input type="hidden" name="title" value="' + esc(j.t) + '">' +
        '<input type="hidden" name="city" value="' + esc(j.ct) + '">' +
        '<button type="submit" class="mark-btn">✅ 我投了</button>' + link + '</form>';
    }
    return link;
  }
  function jobName(j) {
    var name = esc(j.t) + ' <span class="cohort-badge">' + esc(j.cy || '届别待确认') + '</span>';
    return j.k === 'list' ? '<span class="cell-job-link">' + name + '</span>' :
      '<a href="' + esc(j.u) + '" target="_blank" rel="noopener" class="cell-job-link">' + name + '</a>';
  }

  // ── 全部岗位：搜索 / 筛选 / 分页（客户端，应对数千岗位）──
  const tbody = document.getElementById('jobTbody');
  if (tbody) {
    const PAGE = 50;
    let page = 1;
    function filtered() {
      const q = (el('jobSearch').value || '').trim().toLowerCase();
      const co = el('fCompany').value, pl = el('fPlatform').value,
            ev = el('fEval').value, sc = el('fScore').value;
      let r = JOBS.filter(j => {
        if (co && j.c !== co) return false;
        if (pl && j.p !== pl) return false;
        if (ev === 'scored' && !j.e) return false;
        if (ev === 'uneval' && j.e) return false;
        if (sc) {
          if (!j.e) return false;
          const s = j.s || 0;
          if (sc === '70' && s < 70) return false;
          if (sc === '60' && (s < 60 || s >= 70)) return false;
          if (sc === '0' && s >= 60) return false;
        }
        if (q) {
          const h = (j.c + ' ' + j.t + ' ' + (j.ct || '')).toLowerCase();
          if (h.indexOf(q) < 0) return false;
        }
        return true;
      });
      r.sort((a, b) => (b.e ? (b.s || 0) : -1) - (a.e ? (a.s || 0) : -1));
      return r;
    }
    function render() {
      const rows = filtered(), total = rows.length;
      const pages = Math.max(1, Math.ceil(total / PAGE));
      if (page > pages) page = pages;
      if (page < 1) page = 1;
      const slice = rows.slice((page - 1) * PAGE, page * PAGE);
      tbody.innerHTML = slice.length ? slice.map(j =>
        '<tr><td class="cell-company"><span>' + esc(j.c) + '</span></td>' +
        '<td>' + jobName(j) + '</td>' +
        '<td>' + badge(j) + '</td>' +
        '<td class="cell-city">' + esc(j.ct || '—') + '</td>' +
        '<td><span class="cell-plat">' + esc(j.p) + '</span></td>' +
        '<td class="cell-op">' + opCell(j) + '</td></tr>'
      ).join('') : '<tr><td colspan="6" class="empty-state">无匹配岗位</td></tr>';
      el('jpInfo').textContent = '第 ' + page + ' / ' + pages + ' 页 · 共 ' + total + ' 条';
      el('jpPrev').disabled = page <= 1;
      el('jpNext').disabled = page >= pages;
    }
    ['jobSearch', 'fCompany', 'fPlatform', 'fEval', 'fScore'].forEach(id => {
      const e = el(id);
      e.addEventListener('input', () => { page = 1; render(); });
      e.addEventListener('change', () => { page = 1; render(); });
    });
    el('jpPrev').addEventListener('click', () => { if (page > 1) { page--; render(); } });
    el('jpNext').addEventListener('click', () => { page++; render(); });
    render();
  }

  // ── 公司排行：前端聚合 + 搜索 + 分页；行可点击进入公司详情 ──
  const cTbody = document.getElementById('companyTbody');
  if (cTbody) {
    const agg = {};
    JOBS.forEach(j => {
      const a = agg[j.c] || (agg[j.c] = { total: 0, scores: [], topS: null, topT: '—' });
      a.total++;
      if (j.e) {
        const s = j.s || 0;
        a.scores.push(s);
        if (a.topS === null || s > a.topS) { a.topS = s; a.topT = j.t; }
      }
    });
    let companies = Object.keys(agg).map(c => {
      const a = agg[c];
      const avg = a.scores.length ? a.scores.reduce((x, y) => x + y, 0) / a.scores.length : null;
      return { c, total: a.total, avg, topS: a.topS, topT: a.topT };
    });
    // 有评分的按均分降序在前；全待评估的按岗位数降序排在后（口径同后端）
    companies.sort((x, y) =>
      ((x.avg === null) - (y.avg === null)) || ((y.avg || 0) - (x.avg || 0)) || (y.total - x.total));

    const CPAGE = 30;
    let cpage = 1;
    function cfiltered() {
      const q = (el('companySearch').value || '').trim().toLowerCase();
      return q ? companies.filter(o => o.c.toLowerCase().indexOf(q) >= 0) : companies;
    }
    function crender() {
      const rows = cfiltered(), total = rows.length;
      const pages = Math.max(1, Math.ceil(total / CPAGE));
      if (cpage > pages) cpage = pages;
      if (cpage < 1) cpage = 1;
      const slice = rows.slice((cpage - 1) * CPAGE, cpage * CPAGE);
      cTbody.innerHTML = slice.length ? slice.map(o =>
        '<tr class="company-row" data-company="' + esc(o.c) + '">' +
        '<td class="cell-company">' + avatar(o.c) + ' <span>' + esc(o.c) + '</span></td>' +
        '<td class="cell-num">' + o.total + '</td>' +
        '<td>' + (o.avg === null ? '<span class="cell-score uneval">待评估</span>' : scoreCell(Math.round(o.avg))) + '</td>' +
        '<td>' + (o.topS === null ? '—' : scoreCell(o.topS)) + '</td>' +
        '<td class="cell-job-name">' + esc(o.topT) + '</td></tr>'
      ).join('') : '<tr><td colspan="5" class="empty-state">无匹配公司</td></tr>';
      el('cpInfo').textContent = '第 ' + cpage + ' / ' + pages + ' 页 · 共 ' + total + ' 家';
      el('cpPrev').disabled = cpage <= 1;
      el('cpNext').disabled = cpage >= pages;
    }
    el('companySearch').addEventListener('input', () => { cpage = 1; crender(); });
    el('cpPrev').addEventListener('click', () => { if (cpage > 1) { cpage--; crender(); } });
    el('cpNext').addEventListener('click', () => { cpage++; crender(); });
    cTbody.addEventListener('click', e => {
      const tr = e.target.closest('.company-row');
      if (tr) openCompany(tr.dataset.company);
    });
    crender();

    // ── 公司详情：从 JOBS 过滤该公司岗位实时渲染 ──
    function openCompany(name) {
      const list = JOBS.filter(j => j.c === name)
        .sort((a, b) => (b.e ? (b.s || 0) : -1) - (a.e ? (a.s || 0) : -1));
      const scores = list.filter(j => j.e).map(j => j.s || 0);
      const avg = scores.length ? Math.round(scores.reduce((x, y) => x + y, 0) / scores.length) : null;
      const topS = scores.length ? Math.max.apply(null, scores) : null;
      el('cdHead').innerHTML =
        '<div class="cd-title">' + avatar(name) + '<h1>' + esc(name) + '</h1></div>' +
        '<div class="cd-stats">' +
        '<span class="cd-stat"><b>' + list.length + '</b> 个岗位</span>' +
        '<span class="cd-stat">平均匹配 <b>' + (avg === null ? '待评估' : avg) + '</b></span>' +
        '<span class="cd-stat">最高分 <b>' + (topS === null ? '—' : topS) + '</b></span>' +
        '</div>';
      el('cdTbody').innerHTML = list.length ? list.map(j =>
        '<tr><td>' + jobName(j) + '</td>' +
        '<td>' + badge(j) + '</td>' +
        '<td class="cell-city">' + esc(j.ct || '—') + '</td>' +
        '<td><span class="cell-plat">' + esc(j.p) + '</span></td>' +
        '<td class="cell-op">' + opCell(j) + '</td></tr>'
      ).join('') : '<tr><td colspan="5" class="empty-state">暂无岗位</td></tr>';
      activate('company-detail');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    const cdBack = el('cdBack');
    if (cdBack) cdBack.addEventListener('click', () => {
      activate('companies');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  // 本地编辑器 POST 后重定向到 /#applications 等，按 hash 打开对应页
  if (location.hash) activate(location.hash.slice(1));
});
"""


# ──────────────────────────────────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────────────────────────────────

def render_html(date_str: str, report_data: dict, editable: bool = False) -> str:
    """组装整页 HTML（不落盘）。

    report_data 可含 "items"（岗位+分析）与 "applications"（投递记录列表）。
    editable=True 时在岗位卡/看板注入编辑表单（供本地 webapp 复用）。
    """
    all_items = report_data.get("items", [])
    shown_items, previous_items, hidden_count = _filter_items(all_items)

    applications = report_data.get("applications", []) or []
    # job_id -> application（用于岗位卡"已投递"徽标）
    app_index = {a["job_id"]: a for a in applications if a.get("job_id") is not None}
    # job_id -> {jd_url, match_score}（用于看板卡回看岗位/显示匹配分）
    job_index = {}
    for it in all_items:
        job = it.get("job", {})
        jid = job.get("id")
        if jid is not None:
            job_index[jid] = {
                "jd_url": job.get("jd_url", ""),
                "link_kind": job.get("link_kind", "detail"),
                "match_score": (it.get("analysis") or {}).get("match_score"),
            }

    page_rec_html, _stats = _page_recommended(shown_items, hidden_count, date_str, app_index, editable)
    page_today_html = _page_today(shown_items, date_str, app_index, editable)
    page_companies_html = _page_companies(shown_items)
    page_previous_html = _page_previous_cohort(previous_items, app_index, editable)
    page_company_detail_html = _page_company_detail()
    page_apps_html = _page_applications(applications, job_index, editable)
    page_schedule_html = _page_schedule(applications, editable)

    sidebar = _render_sidebar()

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI 秋招情报 · {html.escape(date_str)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="layout">
  {sidebar}
  <main class="main">
    {page_rec_html}
    {page_today_html}
    {page_companies_html}
    {page_previous_html}
    {page_company_detail_html}
    {page_apps_html}
    {page_schedule_html}
  </main>
</div>
<script>{_JS}</script>
</body>
</html>"""


def generate_report(date_str: str, report_data: dict, reports_dir: str = "reports",
                    out_name: str | None = None) -> str:
    """生成静态 HTML 报告（只读）并落盘。

    date_str: 用于「今日新增」过滤（crawled_at == date_str）和页面顶部"扫描日期"显示。
    out_name: 输出文件名（不含 .html）。默认 None 时用 date_str，
              传 "index" 可产出固定首页 index.html 而不受 date_str 影响。
    """
    Path(reports_dir).mkdir(parents=True, exist_ok=True)
    html_content = render_html(date_str, report_data, editable=False)

    output_path = Path(reports_dir) / f"{out_name or date_str}.html"
    output_path.write_text(html_content, encoding="utf-8")
    return str(output_path.resolve())
