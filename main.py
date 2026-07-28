import logging
import os
import sys
import webbrowser
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import yaml

import analyzer
import db as db_module
import job_cohorts
import job_filters
import notifier
import reporter
from profile_config import load_profile
from scripts import qq_docs_27_autumn_monitor
from crawlers import CRAWLER_MAP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _resolve_llm_models(llm_cfg: dict | None) -> tuple[str, str]:
    """Return screening and detailed-analysis models with legacy compatibility."""
    cfg = llm_cfg or {}
    legacy_model = cfg.get("model")
    screening_model = cfg.get("screening_model") or legacy_model or "deepseek-v4-flash"
    analysis_model = cfg.get("analysis_model") or legacy_model or "deepseek-v4-pro"
    return screening_model, analysis_model


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# 并发爬取的 worker 数（每 worker 独立 Playwright 浏览器）。公司扩到数百家后
# 串行会撑爆 CI 时长，故并发；可用 CRAWL_WORKERS 环境变量覆盖。
_CRAWL_WORKERS = int(os.environ.get("CRAWL_WORKERS", "5"))


def _normalize_configured_listing_links(company: dict, jobs: list[dict]) -> list[dict]:
    """Make configured list-only jobs open the official list without DB collisions."""
    if company.get("link_kind") != "list":
        return jobs
    base = company["careers_url"]
    parts = urlsplit(base)
    for job in jobs:
        identity = hashlib.sha1(
            f"{job.get('title', '')}|{job.get('city', '')}|{job.get('jd_url', '')}".encode("utf-8")
        ).hexdigest()[:12]
        marker = f"job-ref={identity}"
        if parts.fragment:
            separator = "&" if "?" in parts.fragment else "?"
            fragment = f"{parts.fragment}{separator}{marker}"
        else:
            fragment = marker
        job["jd_url"] = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, fragment))
        job["link_kind"] = "list"
    return jobs


def _crawl_one(company: dict) -> tuple[str, list[dict]]:
    """跑单家爬虫，返回 (公司名, 岗位列表)。异常吞掉返回空，不影响其他公司。"""
    key = company["crawler"]
    cls = CRAWLER_MAP.get(key)
    if not cls:
        logger.warning("未找到爬虫: %s，跳过 %s", key, company["name"])
        return company["name"], []
    try:
        crawler = cls(company["name"], company["careers_url"])
        jobs = crawler.fetch()
        if (
            hasattr(crawler, "pagination_complete")
            and not crawler.pagination_complete
        ):
            logger.error(
                "[%s] 分页未完整结束（%s），丢弃 %d 条部分结果",
                company["name"],
                getattr(crawler, "pagination_termination_reason", "unknown"),
                len(jobs),
            )
            return company["name"], []
        configured_campaign = str(company.get("campaign_text") or "").strip()
        if configured_campaign:
            for job in jobs:
                if not str(job.get("campaign_text") or "").strip():
                    job["campaign_text"] = configured_campaign
        jobs = _normalize_configured_listing_links(company, jobs)
        logger.info("[%s] 抓取完成，获得 %d 个岗位", company["name"], len(jobs))
        return company["name"], jobs
    except Exception as e:
        logger.error("[%s] 爬取异常: %s", company["name"], e)
        return company["name"], []


def run_crawlers(companies: list[dict]) -> tuple[list[dict], set[str]]:
    """并发运行所有爬虫。返回 (所有岗位, 成功公司集合)。

    "成功" = 爬虫返回 >= 1 个岗位（避免网络/WAF 故障误判岗位下线）。
    每个 worker 线程跑独立爬虫、各自起 Playwright，互不干扰。
    """
    all_jobs: list[dict] = []
    successful: set[str] = set()
    workers = max(1, min(_CRAWL_WORKERS, len(companies) or 1))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for name, jobs in ex.map(_crawl_one, companies):
            all_jobs.extend(jobs)
            if jobs:
                successful.add(name)
    return all_jobs, successful


def _print_delta(new_jobs: list[dict], disappeared: list[dict]) -> None:
    print(f"\n{'='*50}")
    print(f"今日变化：新增 {len(new_jobs)} 个 / 下线 {len(disappeared)} 个")
    print(f"{'='*50}")

    if new_jobs:
        print(f"\n新增 {len(new_jobs)} 个岗位：")
        for j in new_jobs:
            city = f"  ({j.get('city','')})" if j.get("city") else ""
            print(f"  + [{j['company']}] {j['title']}{city}")
    if disappeared:
        print(f"\n下线 {len(disappeared)} 个岗位：")
        for j in disappeared:
            city = f"  ({j.get('city','')})" if j.get("city") else ""
            print(f"  - [{j['company']}] {j['title']}{city}")
    if not new_jobs and not disappeared:
        print("\n无变化")
    print()


def main():
    # 1. 加载配置
    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        logger.error("找不到 config.yaml，请确认文件存在")
        sys.exit(1)
    config = load_config(str(config_path))

    # Public Tencent Docs is a lead source. It is read before the fixed company
    # crawl; only a lead that returns formal campus jobs may update config.
    try:
        source_monitor = qq_docs_27_autumn_monitor.run(config["companies"])
        attached_campaigns = qq_docs_27_autumn_monitor.attach_official_campaign_urls(
            source_monitor["rows"],
            config["companies"],
        )
        logger.info(
            "已为 %d 家腾讯文档公司绑定官方校招活动页，用于届别证据检查",
            attached_campaigns,
        )
        approved_entries, onboarding_attempts = qq_docs_27_autumn_monitor.validate_unconfigured_rows(
            source_monitor["rows"]
        )
        if approved_entries:
            qq_docs_27_autumn_monitor.append_verified_companies(config_path, approved_entries)
            config["companies"].extend(approved_entries)
            approved_names = {entry["name"].casefold() for entry in approved_entries}
            for row in source_monitor["rows"]:
                if row["canonical_name"].casefold() in approved_names:
                    row["in_config"] = True
            source_monitor["covered"] = sum(row["in_config"] for row in source_monitor["rows"])
            source_monitor["needs_integration"] = sum(
                not row["in_config"] for row in source_monitor["rows"]
            )
            logger.info(
                "腾讯文档自动验证通过 %d 家，已写入配置并加入本轮抓取：%s",
                len(approved_entries),
                ", ".join(entry["name"] for entry in approved_entries),
            )
        trusted_cohorts = qq_docs_27_autumn_monitor.attach_trusted_cohort_evidence(
            source_monitor["rows"],
            config["companies"],
        )
        logger.info(
            "已为 %d 家公司绑定腾讯文档27届正式秋招兜底证据",
            trusted_cohorts,
        )
        if onboarding_attempts:
            qq_docs_27_autumn_monitor.update_integration_status(
                Path(__file__).parent / "outputs" / "company_integration_status.md",
                onboarding_attempts,
            )
        source_monitor["auto_onboarding"] = onboarding_attempts
        qq_docs_27_autumn_monitor.write_report(
            source_monitor,
            Path(__file__).parent / "outputs" / "qq_docs_27_autumn_monitor.json",
        )
        logger.info(
            "腾讯文档 27届秋招前置检查：%d 条，已覆盖 %d，待接入 %d",
            len(source_monitor["rows"]),
            source_monitor["covered"],
            source_monitor["needs_integration"],
        )
    except Exception as exc:  # A source outage must not block the daily crawl.
        logger.warning("腾讯文档 27届秋招前置检查失败：%s", exc)

    profile_path = Path(
        os.environ.get("PROFILE_PATH", Path(__file__).parent / "profile.yaml")
    )
    try:
        profile = load_profile(profile_path)
    except ValueError as exc:
        logger.error("用户画像配置无效: %s", exc)
        sys.exit(1)
    llm_cfg = config.get("deepseek") or config.get("claude")
    screening_model, analysis_model = _resolve_llm_models(llm_cfg)
    logger.info(
        "DeepSeek 混合模式：岗位粗筛=%s，JD 细分析=%s",
        screening_model,
        analysis_model,
    )

    # 2. 初始化数据库
    db_path = Path(
        os.environ.get("JOBS_DB_PATH", Path(__file__).parent / "data" / "jobs.db")
    )
    conn = db_module.init_db(str(db_path))
    logger.info("数据库已就绪: %s", db_path)

    # Crawlers with stable detail routes set ``link_kind=detail`` per row.
    # Only explicitly configured list-only sources are force-marked here.
    list_link_crawlers = set()
    list_link_companies = {
        company["name"] for company in config["companies"]
        if company.get("crawler") in list_link_crawlers or company.get("link_kind") == "list"
    }
    marked = db_module.mark_listing_links_for_companies(conn, list_link_companies)
    migrated_oppo_links = db_module.migrate_oppo_detail_urls(conn)
    migrated_jd_links = db_module.migrate_jd_detail_urls(conn)
    migrated_bilibili_links = db_module.migrate_bilibili_detail_links(conn)
    purged = db_module.purge_nonformal_campus_jobs(conn)
    purged_direction_out = db_module.purge_direction_out_jobs(conn)
    purged_incomplete_analysis = db_module.purge_incomplete_jd_analyses(conn)
    cohort_backfill = db_module.backfill_job_cohorts(conn, config["companies"])
    purged_noncurrent_analysis = db_module.purge_noncurrent_cohort_analyses(conn)
    if migrated_jd_links:
        logger.info("Repaired %d legacy JD detail links", migrated_jd_links)
    if migrated_bilibili_links:
        logger.info("已恢复 %d 条哔哩哔哩真实岗位详情链接", migrated_bilibili_links)
    if marked:
        logger.info("已标记 %d 条招聘列表链接，报告不再将其显示为岗位详情", marked)
    if purged:
        logger.info("已清理 %d 条历史实习/提前批/社招岗位及其分析", purged)
    if purged_direction_out:
        logger.info("已清理 %d 条历史明确方向外岗位及其分析", purged_direction_out)
    if purged_incomplete_analysis:
        logger.info("已清理 %d 条缺少完整 JD 的历史评分", purged_incomplete_analysis)
    logger.info(
        "历史届别迁移：确认27届 %d、确认往届 %d、届别待确认 %d",
        cohort_backfill["current"],
        cohort_backfill["previous"],
        cohort_backfill["unknown"],
    )
    if purged_noncurrent_analysis:
        logger.info("已清理 %d 条非确认27届岗位的历史评分", purged_noncurrent_analysis)

    # 3. 运行爬虫
    logger.info("开始抓取 %d 家企业...", len(config["companies"]))
    all_jobs, successful_companies = run_crawlers(config["companies"])
    logger.info("共抓取到 %d 个岗位（成功公司：%s）", len(all_jobs), successful_companies)

    # 4. Only formal, profile-relevant campus jobs enter the database.
    # Internship/social jobs and explicit direction-out roles are deterministic
    # noise. Block them before cache lookup and upsert so the DB stays clean.
    all_jobs, dropped_jobs = job_filters.filter_formal_campus_jobs(all_jobs)
    if dropped_jobs:
        logger.info("已过滤 %d 个非正式校招岗位（实习/提前批/社招），不入库", len(dropped_jobs))
    all_jobs, dropped_direction_out = job_filters.filter_target_direction_jobs(all_jobs)
    if dropped_direction_out:
        logger.info("已过滤 %d 个明确方向外岗位，不进入缓存与数据库", len(dropped_direction_out))

    # 届别证据必须先于任何模型筛选。岗位字段没有明确届别时，再读取公司
    # 官方校招入口；仍无法确认的岗位保留到待确认页，但不调用任何模型。
    all_jobs = job_cohorts.annotate_crawled_jobs(
        config["companies"],
        all_jobs,
        workers=int(os.environ.get("COHORT_INSPECTION_WORKERS", "10")),
    )
    current_cohort_jobs = [
        job for job in all_jobs if job_cohorts.is_confirmed_current(job)
    ]
    noncurrent_jobs = [
        job for job in all_jobs if not job_cohorts.is_confirmed_current(job)
    ]
    previous_count = sum(
        job.get("cohort_status") == "confirmed"
        and int(job.get("cohort") or 0) <= 2026
        for job in noncurrent_jobs
    )
    logger.info(
        "本轮届别分流：确认27届 %d、确认往届 %d、届别待确认 %d；"
        "仅确认27届进入筛选、JD补全与评分",
        len(current_cohort_jobs),
        previous_count,
        len(noncurrent_jobs) - previous_count,
    )

    # A=进入 Pro，B=保留展示但不调 Pro，C=方向外不入库。新版缓存包含
    # JD 指纹与筛选版本，避免旧的宽泛布尔结果继续放行大量低匹配岗位。
    tiered_jobs = noncurrent_jobs[:]
    cached_tiers = []
    unscreened_jobs = []
    for job in current_cohort_jobs:
        tier = db_module.get_screening_tier(
            conn, job, analyzer.SCREENING_VERSION
        )
        if tier:
            cached_tiers.append((job, tier))
        else:
            unscreened_jobs.append(job)

    fresh_tiers = []
    if unscreened_jobs:
        logger.info(
            "对 %d 个无新版缓存的岗位执行 A/B/C 分级；仅模糊 B 档调用 Flash...",
            len(unscreened_jobs),
        )
        tiers = analyzer.classify_job_tiers(
            unscreened_jobs,
            profile,
            model=screening_model,
            max_tokens=int(llm_cfg.get("screening_max_tokens", 600)),
        )
        fresh_tiers = list(zip(unscreened_jobs, tiers))
        db_module.save_screening_tiers(
            conn, fresh_tiers, analyzer.SCREENING_VERSION
        )

    decisions = cached_tiers + fresh_tiers
    db_module.update_existing_job_screening_tiers(conn, decisions)
    tier_counts = {tier: 0 for tier in ("A", "B", "C")}
    for job, tier in decisions:
        tier_counts[tier] += 1
        job["screening_tier"] = tier
        if tier != "C":
            tiered_jobs.append(job)
    if decisions:
        logger.info(
            "岗位分级结果：A档 %d、B档 %d、C档 %d；仅A档允许进入Pro",
            tier_counts["A"], tier_counts["B"], tier_counts["C"],
        )
    purged_tier_c = db_module.purge_screening_tier_c_jobs(conn)
    if purged_tier_c:
        logger.info("已从正式库移除 %d 条重新判定为 C 档的历史岗位", purged_tier_c)
    purged_tier_b_analysis = db_module.purge_screening_tier_b_analyses(conn)
    if purged_tier_b_analysis:
        logger.info("已清理 %d 条 B 档岗位的历史 Pro 评分，岗位仍保留展示", purged_tier_b_analysis)
    all_jobs = tiered_jobs

    # Upsert：新增插入 + 已存在的刷新 last_seen_at
    new_jobs = []
    for job in all_jobs:
        was_inserted, jid = db_module.upsert_job(conn, job)
        if was_inserted:
            new_jobs.append({**job, "id": jid})

    # 5. 检测下线（仅在成功爬取该公司时）
    # The older pre-crawl repair was overwritten by fresh upserts. Reapply after
    # persistence so legacy list/API links cannot be displayed as job details.
    repaired_listing_links = db_module.mark_listing_links_for_companies(conn, list_link_companies)
    normalized_listing_links = db_module.normalize_listing_link_kinds(conn)
    if repaired_listing_links:
        logger.info("Repaired %d legacy listing links after upsert", repaired_listing_links)
    if normalized_listing_links:
        logger.info("Normalized %d legacy list URLs after upsert", normalized_listing_links)

    disappeared = db_module.get_disappeared_jobs(conn, successful_companies)

    # 6. 细分析活跃岗位
    active = db_module.get_active_jobs(conn)
    active_current = [
        job for job in active if job_cohorts.is_confirmed_current(job)
    ]
    unanalyzed = [
        job for job in active_current
        if analyzer.needs_detailed_analysis(
            conn, job, profile, analysis_model
        )
    ]

    logger.info(
        "活跃岗位 %d 个，其中确认27届 %d 个 → 待新增/更新细分析 %d 个",
        len(active),
        len(active_current),
        len(unanalyzed),
    )
    if unanalyzed:
        logger.info("开始 DeepSeek 细分析 %d 个岗位...", len(unanalyzed))
        analyzer.batch_analyze(
            unanalyzed,
            profile,
            conn,
            model=analysis_model,
            max_tokens=int(llm_cfg.get("analysis_max_tokens", 1200)),
            max_jobs=(
                None
                if os.environ.get("ALLOW_FULL_PRO_ANALYSIS") == "1"
                else int(llm_cfg.get("max_pro_jobs_per_run", 0))
            ),
            max_jobs_per_day=(
                None
                if os.environ.get("ALLOW_FULL_PRO_ANALYSIS") == "1"
                else int(llm_cfg.get("max_pro_jobs_per_day", 0))
            ),
        )

    # A list card can look like a campus role while the full detail reveals an
    # internship track or current-internship attendance requirement. Hydration
    # happens immediately before Pro analysis, so enforce the deterministic
    # filters once more before reports are generated.
    post_hydration_nonformal = db_module.purge_nonformal_campus_jobs(conn)
    post_hydration_direction = db_module.purge_direction_out_jobs(conn)
    post_hydration_incomplete = db_module.purge_incomplete_jd_analyses(conn)
    post_hydration_noncurrent = db_module.purge_noncurrent_cohort_analyses(conn)
    if post_hydration_nonformal:
        logger.info("JD 补全后二次清理 %d 个非正式校招岗位", post_hydration_nonformal)
    if post_hydration_direction:
        logger.info("JD 补全后二次清理 %d 个方向外岗位", post_hydration_direction)
    if post_hydration_incomplete:
        logger.info("JD 验收后二次清理 %d 条无完整正文的评分", post_hydration_incomplete)
    if post_hydration_noncurrent:
        logger.info("届别验收后二次清理 %d 条非确认27届评分", post_hydration_noncurrent)

    # 7. 生成报告
    reports_dir = os.environ.get("REPORTS_DIR", str(Path(__file__).parent / "reports"))
    today_iso = date.today().isoformat()
    # 7.1 当日活跃快照（历史留档：reports/YYYY-MM-DD.html）
    report_data = db_module.get_active_report_data(conn)
    report_path = reporter.generate_report(today_iso, report_data, reports_dir)
    # 7.2 累计首页（reports/index.html）：「总体岗位」=全部岗位按匹配度排序、
    #     「今日新增」=crawled_at==最新批次、「投递记录」=DB 投递看板（只读）。
    #     gh-pages 根路径稳定入口，每天覆盖刷新。
    all_items = db_module.get_all_jobs_with_analysis(conn)
    reporter.generate_report(
        today_iso,
        {
            "items": all_items,
            "applications": db_module.get_applications(conn),
            "date": today_iso,
        },
        reports_dir,
        out_name="index",
    )

    # 8. 飞书推送（FEISHU_WEBHOOK 未设置则静默跳过）
    #    「今日新增」用「最新批次 crawled_at」判定，而非本次运行新插入 new_jobs——
    #    否则本地批量导入+提交后，次日 CI 重爬岗位已存在，new_jobs=[] 会推「今日新增 0」。
    all_jobs_with_analysis = db_module.get_all_jobs_with_analysis(conn)
    latest_crawl = db_module.get_latest_crawl_date(conn)
    notify_new = [
        j for j in active_current if j.get("crawled_at") == latest_crawl
    ]
    if not os.environ.get("SKIP_NOTIFY"):
        notifier.send(notify_new, all_jobs_with_analysis, report_data)

    conn.close()

    # 9. 终端输出 delta + 报告路径
    _print_delta(new_jobs, disappeared)
    print(f"活跃岗位总数：{len(active)}  →  {report_path}")
    print()

    # 10. 本地运行才自动打开浏览器（CI 环境跳过）
    if not os.environ.get("CI"):
        webbrowser.open(f"file:///{report_path.replace(os.sep, '/')}")


if __name__ == "__main__":
    main()
