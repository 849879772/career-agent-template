import logging
import os
import sys
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import yaml

import analyzer
import db as db_module
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


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# 并发爬取的 worker 数（每 worker 独立 Playwright 浏览器）。公司扩到数百家后
# 串行会撑爆 CI 时长，故并发；可用 CRAWL_WORKERS 环境变量覆盖。
_CRAWL_WORKERS = int(os.environ.get("CRAWL_WORKERS", "5"))


def _crawl_one(company: dict) -> tuple[str, list[dict]]:
    """跑单家爬虫，返回 (公司名, 岗位列表)。异常吞掉返回空，不影响其他公司。"""
    key = company["crawler"]
    cls = CRAWLER_MAP.get(key)
    if not cls:
        logger.warning("未找到爬虫: %s，跳过 %s", key, company["name"])
        return company["name"], []
    try:
        jobs = cls(company["name"], company["careers_url"]).fetch()
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

    # Tencent Docs is a public lead source. Check it before the fixed company
    # crawl without changing config automatically; new entries still require
    # crawler validation before they become a daily source.
    try:
        source_monitor = qq_docs_27_autumn_monitor.run(config["companies"])
        qq_docs_27_autumn_monitor.write_report(
            source_monitor,
            Path(__file__).parent / "outputs" / "qq_docs_27_autumn_monitor.json",
        )
        logger.info(
            "Tencent Docs 27-autumn precheck: %d rows, covered %d, needs integration %d",
            len(source_monitor["rows"]),
            source_monitor["covered"],
            source_monitor["needs_integration"],
        )
    except Exception as exc:
        logger.warning("Tencent Docs 27-autumn precheck failed: %s", exc)

    profile_path = Path(os.environ.get("PROFILE_PATH", Path(__file__).parent / "profile.yaml"))
    try:
        profile = load_profile(profile_path)
    except ValueError as exc:
        logger.error("用户画像配置无效: %s", exc)
        sys.exit(1)
    llm_cfg = config.get("deepseek") or config.get("claude")

    # 2. 初始化数据库
    db_path = Path(__file__).parent / "data" / "jobs.db"
    conn = db_module.init_db(str(db_path))
    logger.info("数据库已就绪: %s", db_path)

    list_link_crawlers = {"render", "static_html", "hotjob", "bilibili"}
    list_link_companies = {
        company["name"] for company in config["companies"]
        if company.get("crawler") in list_link_crawlers
    }
    marked = db_module.mark_listing_links_for_companies(conn, list_link_companies)
    migrated_jd_links = db_module.migrate_jd_detail_urls(conn)
    purged = db_module.purge_nonformal_campus_jobs(conn)
    if migrated_jd_links:
        logger.info("Repaired %d legacy JD detail links", migrated_jd_links)
    if marked:
        logger.info("已标记 %d 条招聘列表链接，报告不再将其显示为岗位详情", marked)
    if purged:
        logger.info("已清理 %d 条历史实习/社招岗位及其分析", purged)

    # 3. 运行爬虫
    logger.info("开始抓取 %d 家企业...", len(config["companies"]))
    all_jobs, successful_companies = run_crawlers(config["companies"])
    logger.info("共抓取到 %d 个岗位（成功公司：%s）", len(all_jobs), successful_companies)

    # 4. Only formal, profile-relevant campus jobs enter the database.
    # Internship/social jobs are deterministic noise; direction-out jobs are
    # blocked by the cheap AI coarse screen before upsert so the DB stays clean.
    all_jobs, dropped_jobs = job_filters.filter_formal_campus_jobs(all_jobs)
    if dropped_jobs:
        logger.info("已过滤 %d 个非正式校招岗位（实习/社招），不入库", len(dropped_jobs))

    # 已入库岗位直接刷新；未入库但筛过的岗位复用缓存。只有真正首次出现
    # 的岗位才调用 DeepSeek，避免每天对全量抓取结果重复消耗 token。
    known_jobs = []
    cached_relevant = []
    cached_irrelevant = []
    unseen_jobs = []
    for job in all_jobs:
        if db_module.find_job_id(conn, job) is not None:
            known_jobs.append(job)
            continue
        decision = db_module.get_screening_decision(conn, job)
        if decision is True:
            cached_relevant.append(job)
        elif decision is False:
            cached_irrelevant.append(job)
        else:
            unseen_jobs.append(job)

    newly_relevant = []
    newly_irrelevant = []
    if unseen_jobs:
        logger.info("调用 DeepSeek 粗筛 %d 个首次出现的正式校招岗位...", len(unseen_jobs))
        flags = analyzer.classify_relevant_titles(
            [j["title"] for j in unseen_jobs],
            profile,
            model=llm_cfg["model"],
            max_tokens=llm_cfg["max_tokens"],
        )
        decisions = list(zip(unseen_jobs, flags))
        db_module.save_screening_decisions(conn, decisions)
        for job, relevant in decisions:
            (newly_relevant if relevant else newly_irrelevant).append(job)
        logger.info(
            "首次岗位粗筛结果：%d 相关入库、%d 方向外丢弃",
            len(newly_relevant),
            len(newly_irrelevant),
        )
    logger.info(
        "增量筛选：%d 已入库、%d 命中相关缓存、%d 命中方向外缓存、%d 首次出现",
        len(known_jobs), len(cached_relevant), len(cached_irrelevant), len(unseen_jobs),
    )
    all_jobs = known_jobs + cached_relevant + newly_relevant

    # Upsert：新增插入 + 已存在的刷新 last_seen_at
    new_jobs = []
    for job in all_jobs:
        was_inserted, jid = db_module.upsert_job(conn, job)
        if was_inserted:
            new_jobs.append({**job, "id": jid})

    # 5. 检测下线（仅在成功爬取该公司时）
    disappeared = db_module.get_disappeared_jobs(conn, successful_companies)

    # 6. 细分析活跃岗位
    active = db_module.get_active_jobs(conn)
    unanalyzed = [j for j in active if not db_module.has_analysis(conn, j["id"])]

    logger.info("活跃 %d 个岗位 → 未细分析 %d 个", len(active), len(unanalyzed))
    if unanalyzed:
        logger.info("开始 DeepSeek 细分析 %d 个岗位...", len(unanalyzed))
        analyzer.batch_analyze(
            unanalyzed,
            profile,
            conn,
            model=llm_cfg["model"],
            max_tokens=llm_cfg["max_tokens"],
        )

    # 7. 生成报告
    reports_dir = str(Path(__file__).parent / "reports")
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
    notify_new = [j for j in active if j.get("crawled_at") == latest_crawl]
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
