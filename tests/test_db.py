import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import db

TEST_DB = "tests/test_jobs.db"
TEST_APPS = "tests/test_applications.json"

def setup_function():
    for p in (TEST_DB, TEST_APPS):
        if os.path.exists(p):
            os.remove(p)
    db.APPLICATIONS_PATH = Path(TEST_APPS)  # 隔离投递 JSON，避免读到真实 data/applications.json

def teardown_function():
    for p in (TEST_DB, TEST_APPS):
        if os.path.exists(p):
            os.remove(p)

def test_init_db_creates_tables():
    conn = db.init_db(TEST_DB)
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {row[0] for row in tables}
    assert "jobs" in names
    assert "job_analysis" in names
    assert "job_screening_cache" in names
    assert "link_kind" in {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
    conn.close()


def test_screening_cache_reuses_company_title_city_across_url_changes():
    conn = db.init_db(TEST_DB)
    job = {
        "company": "宇树", "title": "视觉算法工程师", "city": "杭州",
        "jd_url": "https://example.com/old",
    }
    assert db.get_screening_decision(conn, job) is None
    db.save_screening_decision(conn, job, False)
    assert db.get_screening_decision(conn, {**job, "jd_url": "https://example.com/new"}) is False
    conn.close()


def test_save_screening_decisions_writes_a_batch():
    conn = db.init_db(TEST_DB)
    jobs = [
        {"company": "甲", "title": "算法工程师", "city": "杭州", "jd_url": "u1"},
        {"company": "乙", "title": "销售", "city": "上海", "jd_url": "u2"},
    ]
    db.save_screening_decisions(conn, [(jobs[0], True), (jobs[1], False)])
    assert db.get_screening_decision(conn, jobs[0]) is True
    assert db.get_screening_decision(conn, jobs[1]) is False
    conn.close()


def test_find_job_id_matches_url_or_company_title_city():
    conn = db.init_db(TEST_DB)
    job = {
        "company": "宇树", "title": "控制算法工程师", "city": "杭州",
        "job_type": "校招", "jd_url": "https://example.com/job/find",
        "jd_raw": "", "published_at": "", "source": "宇树",
    }
    _, job_id = db.upsert_job(conn, job)
    assert db.find_job_id(conn, job) == job_id
    assert db.find_job_id(conn, {**job, "jd_url": "https://example.com/job/new"}) == job_id
    conn.close()

def test_insert_job_new():
    conn = db.init_db(TEST_DB)
    job = {
        "company": "测试公司",
        "title": "测试岗位",
        "city": "深圳",
        "job_type": "校招",
        "jd_url": "https://example.com/job/1",
        "jd_raw": "岗位描述",
        "published_at": "",
        "source": "测试公司",
    }
    inserted, job_id = db.insert_job(conn, job)
    assert inserted is True
    assert job_id > 0
    row = conn.execute("SELECT link_kind FROM jobs WHERE id = ?", (job_id,)).fetchone()
    assert row["link_kind"] == "detail"
    conn.close()


def test_normalize_listing_link_kinds_marks_legacy_list_urls():
    conn = db.init_db(TEST_DB)
    job = {
        "company": "test", "title": "role", "city": "", "job_type": "campus",
        "jd_url": "https://example.zhiye.com/campus/jobs#123", "jd_raw": "",
        "published_at": "", "source": "test", "link_kind": "detail",
    }
    _, job_id = db.upsert_job(conn, job)
    assert db.normalize_listing_link_kinds(conn) == 1
    assert conn.execute("SELECT link_kind FROM jobs WHERE id = ?", (job_id,)).fetchone()[0] == "list"
    conn.close()


def test_migrate_oppo_detail_urls_uses_path_parameter():
    conn = db.init_db(TEST_DB)
    job = {
        "company": "OPPO", "title": "role", "city": "", "job_type": "campus",
        "jd_url": "https://careers.oppo.com/university/oppo/campus/post?id=1728", "jd_raw": "",
        "published_at": "", "source": "test", "link_kind": "detail",
    }
    _, job_id = db.upsert_job(conn, job)
    assert db.migrate_oppo_detail_urls(conn) == 1
    url = conn.execute("SELECT jd_url FROM jobs WHERE id = ?", (job_id,)).fetchone()[0]
    assert url.endswith("/campus/post/1728")
    conn.close()


def test_migrate_jd_detail_urls_uses_public_spa_route():
    conn = db.init_db(TEST_DB)
    job = {
        "company": "JD", "title": "role", "city": "", "job_type": "campus",
        "jd_url": "https://campus.jd.com/api/wx/position/index?type=talent#/details?type=talent&id=7870",
        "jd_raw": "", "published_at": "", "source": "test", "link_kind": "list",
    }
    _, job_id = db.upsert_job(conn, job)
    assert db.migrate_jd_detail_urls(conn) == 1
    row = conn.execute("SELECT jd_url, link_kind FROM jobs WHERE id = ?", (job_id,)).fetchone()
    assert row["jd_url"] == "https://campus.jd.com/#/details?type=talent&id=7870"
    assert row["link_kind"] == "detail"
    conn.close()


def test_get_active_jobs_hides_list_rows_when_company_has_details():
    conn = db.init_db(TEST_DB)
    detail = {
        "company": "test", "title": "detail", "city": "", "job_type": "campus",
        "jd_url": "https://example.com/campus/detail?jobAdId=1", "jd_raw": "",
        "published_at": "", "source": "test", "link_kind": "detail",
    }
    listing = {
        "company": "test", "title": "legacy listing", "city": "", "job_type": "campus",
        "jd_url": "https://example.com/campus/jobs#1", "jd_raw": "",
        "published_at": "", "source": "test", "link_kind": "list",
    }
    db.upsert_job(conn, detail)
    db.upsert_job(conn, listing)
    assert [job["title"] for job in db.get_active_jobs(conn)] == ["detail"]
    assert [item["job"]["title"] for item in db.get_all_jobs_with_analysis(conn)] == ["detail"]
    conn.close()


def test_purge_nonformal_campus_jobs_removes_old_project_label_rows():
    conn = db.init_db(TEST_DB)
    formal = {"company": "甲", "title": "正式岗", "city": "北京", "job_type": "校招",
              "jd_url": "https://example.com/formal", "jd_raw": "", "published_at": "", "source": "甲"}
    intern = {"company": "腾讯", "title": "软件开发", "city": "深圳", "job_type": "应届实习",
              "jd_url": "https://example.com/intern", "jd_raw": "TEG 应届实习", "published_at": "", "source": "腾讯"}
    db.upsert_job(conn, formal)
    db.upsert_job(conn, intern)
    assert db.purge_nonformal_campus_jobs(conn) == 1
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
    conn.close()

def test_get_latest_crawl_date():
    conn = db.init_db(TEST_DB)
    assert db.get_latest_crawl_date(conn) is None  # 空库

    for i, d in enumerate(["2026-05-10", "2026-05-13", "2026-05-11"]):
        conn.execute(
            "INSERT INTO jobs (company, title, city, job_type, jd_url, jd_raw, "
            "published_at, source, crawled_at, last_seen_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("公司", f"岗位{i}", "深圳", "校招", f"u{i}", "", "", "公司", d, d),
        )
    conn.commit()
    assert db.get_latest_crawl_date(conn) == "2026-05-13"  # 取最大，非插入顺序
    conn.close()


def test_insert_job_duplicate():
    conn = db.init_db(TEST_DB)
    job = {
        "company": "测试公司",
        "title": "测试岗位",
        "city": "深圳",
        "job_type": "校招",
        "jd_url": "https://example.com/job/2",
        "jd_raw": "岗位描述",
        "published_at": "",
        "source": "测试公司",
    }
    inserted1, id1 = db.insert_job(conn, job)
    inserted2, id2 = db.insert_job(conn, job)
    assert inserted1 is True
    assert inserted2 is False
    assert id1 == id2
    conn.close()

def test_get_new_jobs_today():
    conn = db.init_db(TEST_DB)
    from datetime import date
    job = {
        "company": "宇树",
        "title": "视觉工程师",
        "city": "杭州",
        "job_type": "校招",
        "jd_url": "https://example.com/job/3",
        "jd_raw": "需要ROS",
        "published_at": "",
        "source": "宇树",
    }
    db.insert_job(conn, job)
    jobs = db.get_new_jobs_today(conn)
    assert len(jobs) == 1
    assert jobs[0]["title"] == "视觉工程师"
    conn.close()

def test_save_and_has_analysis():
    conn = db.init_db(TEST_DB)
    job = {
        "company": "宇树",
        "title": "算法工程师",
        "city": "杭州",
        "job_type": "校招",
        "jd_url": "https://example.com/job/4",
        "jd_raw": "需要Python",
        "published_at": "",
        "source": "宇树",
    }
    _, job_id = db.insert_job(conn, job)
    assert db.has_analysis(conn, job_id) is False

    analysis = {
        "match_score": 85,
        "advantages": ["ROS经验"],
        "gaps": ["CUDA"],
        "summary": "视觉引导抓取",
        "recommendation": "推荐",
    }
    db.save_analysis(conn, job_id, analysis)
    assert db.has_analysis(conn, job_id) is True
    conn.close()

def test_upsert_refreshes_last_seen_at():
    conn = db.init_db(TEST_DB)
    from datetime import date
    today = date.today().isoformat()

    # 制造一个"上次见到 = 昨天"的旧岗位
    job = {
        "company": "宇树", "title": "旧岗位", "city": "杭州", "job_type": "校招",
        "jd_url": "https://example.com/job/upsert1", "jd_raw": "", "published_at": "",
        "source": "宇树",
    }
    db.upsert_job(conn, job)
    conn.execute("UPDATE jobs SET last_seen_at = '2020-01-01' WHERE jd_url = ?",
                 (job["jd_url"],))
    conn.commit()

    # 再次 upsert 应把 last_seen_at 刷成今天
    inserted, _ = db.upsert_job(conn, job)
    assert inserted is False
    row = conn.execute("SELECT last_seen_at FROM jobs WHERE jd_url = ?",
                       (job["jd_url"],)).fetchone()
    assert row["last_seen_at"] == today
    conn.close()


def test_get_active_jobs_returns_only_today():
    conn = db.init_db(TEST_DB)
    # active: 今天见到
    active_job = {
        "company": "宇树", "title": "活跃岗", "city": "杭州", "job_type": "校招",
        "jd_url": "https://example.com/job/active", "jd_raw": "", "published_at": "",
        "source": "宇树",
    }
    db.upsert_job(conn, active_job)
    # stale: last_seen_at 在过去
    stale_job = {
        "company": "宇树", "title": "下线岗", "city": "杭州", "job_type": "校招",
        "jd_url": "https://example.com/job/stale", "jd_raw": "", "published_at": "",
        "source": "宇树",
    }
    db.upsert_job(conn, stale_job)
    conn.execute("UPDATE jobs SET last_seen_at = '2020-01-01' WHERE jd_url = ?",
                 (stale_job["jd_url"],))
    conn.commit()

    active = db.get_active_jobs(conn)
    titles = [j["title"] for j in active]
    assert "活跃岗" in titles
    assert "下线岗" not in titles
    conn.close()


def test_upsert_smart_match_by_company_title():
    """jd_url 变了但 (company, title) 同 → 更新 jd_url + last_seen_at，不新增。"""
    conn = db.init_db(TEST_DB)
    from datetime import date
    today = date.today().isoformat()

    job = {
        "company": "华为", "title": "客户经理", "city": "深圳", "job_type": "校招",
        "jd_url": "https://career.huawei.com/...#客户经理",  # 旧 URL 格式
        "jd_raw": "", "published_at": "", "source": "华为",
    }
    inserted, jid = db.upsert_job(conn, job)
    assert inserted is True

    # 模拟 crawler 升级后用新 URL 格式
    job_new_url = {**job, "jd_url": "https://career.huawei.com/cn/job-details?advertisementId=123"}
    inserted2, jid2 = db.upsert_job(conn, job_new_url)
    assert inserted2 is False  # 应识别为已存在
    assert jid2 == jid  # 同一行

    # jd_url 已更新
    row = conn.execute("SELECT jd_url FROM jobs WHERE id = ?", (jid,)).fetchone()
    assert "advertisementId=123" in row["jd_url"]
    conn.close()


def test_upsert_distinct_city_not_merged():
    """同公司同标题但不同城市、不同 URL → 应是两条独立岗位，不被合并。"""
    conn = db.init_db(TEST_DB)
    bj = {
        "company": "字节跳动", "title": "后端开发工程师", "city": "北京", "job_type": "校招",
        "jd_url": "https://jobs.bytedance.com/campus/position/111/detail",
        "jd_raw": "", "published_at": "", "source": "字节跳动",
    }
    sh = {
        "company": "字节跳动", "title": "后端开发工程师", "city": "上海", "job_type": "校招",
        "jd_url": "https://jobs.bytedance.com/campus/position/222/detail",
        "jd_raw": "", "published_at": "", "source": "字节跳动",
    }
    ins1, id1 = db.upsert_job(conn, bj)
    ins2, id2 = db.upsert_job(conn, sh)
    assert ins1 is True
    assert ins2 is True            # 上海岗位是新增，不该被北京岗位吞掉
    assert id1 != id2
    count = conn.execute("SELECT COUNT(*) FROM jobs WHERE title = ?",
                         ("后端开发工程师",)).fetchone()[0]
    assert count == 2
    conn.close()


def test_get_disappeared_jobs():
    conn = db.init_db(TEST_DB)
    # 老岗位：上次见到 = 昨天
    old_job = {
        "company": "宇树", "title": "已下线岗位", "city": "杭州", "job_type": "校招",
        "jd_url": "https://example.com/job/disappeared", "jd_raw": "", "published_at": "",
        "source": "宇树",
    }
    db.upsert_job(conn, old_job)
    conn.execute("UPDATE jobs SET last_seen_at = '2026-05-13' WHERE jd_url = ?",
                 (old_job["jd_url"],))
    conn.commit()

    # 今天该公司爬虫成功（successful_companies 含"宇树"）但没拿到这个岗位
    disappeared = db.get_disappeared_jobs(conn, {"宇树"})
    assert len(disappeared) == 1
    assert disappeared[0]["title"] == "已下线岗位"

    # 该公司爬虫失败 → 不应返回
    disappeared_fail = db.get_disappeared_jobs(conn, set())
    assert disappeared_fail == []
    conn.close()


def test_get_active_report_data():
    conn = db.init_db(TEST_DB)
    job = {
        "company": "宇树", "title": "活跃岗", "city": "杭州", "job_type": "校招",
        "jd_url": "https://example.com/job/r1", "jd_raw": "", "published_at": "",
        "source": "宇树",
    }
    _, jid = db.upsert_job(conn, job)
    db.save_analysis(conn, jid, {
        "match_score": 70, "advantages": ["ROS"], "gaps": [],
        "summary": "测试", "recommendation": "考虑",
    })
    data = db.get_active_report_data(conn)
    assert len(data["items"]) == 1
    assert data["items"][0]["analysis"]["match_score"] == 70
    conn.close()


def test_get_all_jobs_with_analysis():
    """全量返回（含未分析的 + 已分析的，按 id 排序）。"""
    conn = db.init_db(TEST_DB)
    # 1 个已分析 + 1 个未分析
    j1 = {
        "company": "宇树", "title": "已分析岗", "city": "杭州", "job_type": "校招",
        "jd_url": "https://example.com/all/1", "jd_raw": "", "published_at": "",
        "source": "宇树",
    }
    j2 = {
        "company": "宇树", "title": "未分析岗", "city": "杭州", "job_type": "校招",
        "jd_url": "https://example.com/all/2", "jd_raw": "", "published_at": "",
        "source": "宇树",
    }
    _, id1 = db.upsert_job(conn, j1)
    _, id2 = db.upsert_job(conn, j2)
    db.save_analysis(conn, id1, {
        "match_score": 75, "advantages": ["ROS"], "gaps": ["CUDA"],
        "summary": "测试", "recommendation": "考虑",
    })

    items = db.get_all_jobs_with_analysis(conn)
    assert len(items) == 2
    by_title = {i["job"]["title"]: i for i in items}
    assert by_title["已分析岗"]["analysis"]["match_score"] == 75
    assert by_title["已分析岗"]["analysis"]["advantages"] == ["ROS"]
    assert by_title["未分析岗"]["analysis"] is None
    conn.close()


def test_get_today_report_data():
    conn = db.init_db(TEST_DB)
    from datetime import date
    today = date.today().isoformat()
    job = {
        "company": "宇树",
        "title": "感知工程师",
        "city": "杭州",
        "job_type": "校招",
        "jd_url": "https://example.com/job/5",
        "jd_raw": "激光雷达",
        "published_at": "",
        "source": "宇树",
    }
    _, job_id = db.insert_job(conn, job)
    analysis = {
        "match_score": 75,
        "advantages": ["点云处理"],
        "gaps": [],
        "summary": "感知方向",
        "recommendation": "考虑",
    }
    db.save_analysis(conn, job_id, analysis)
    data = db.get_today_report_data(conn, today)
    assert data["date"] == today
    assert len(data["items"]) == 1
    assert data["items"][0]["analysis"]["match_score"] == 75
    conn.close()


# ── 投递记录（applications）──────────────────────────────────────

def _insert_job(conn, jd_url="https://example.com/job/app"):
    job = {
        "company": "测试公司", "title": "视觉算法", "city": "深圳",
        "job_type": "校招", "jd_url": jd_url, "jd_raw": "JD",
        "published_at": "", "source": "测试公司",
    }
    _, job_id = db.insert_job(conn, job)
    return job_id


def test_applications_decoupled_to_json():
    """投递记录已迁出 jobs.db → applications.json（本地权属、文本可合并）。"""
    conn = db.init_db(TEST_DB)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "applications" not in names  # 不再在 jobs.db 建表
    conn.close()
    db.upsert_application(None, 1, "测试公司", "视觉算法", "深圳")
    assert len(db.get_applications()) == 1
    assert Path(TEST_APPS).exists()  # 写进了 JSON


def test_upsert_application_from_job():
    conn = db.init_db(TEST_DB)
    job_id = _insert_job(conn)
    app_id = db.upsert_application(conn, job_id, "测试公司", "视觉算法", "深圳")
    assert app_id > 0
    apps = db.get_applications(conn)
    assert len(apps) == 1
    assert apps[0]["current_stage"] == "applied"
    assert apps[0]["stages"][0]["stage"] == "applied"
    conn.close()


def test_upsert_application_dedups_by_job():
    conn = db.init_db(TEST_DB)
    job_id = _insert_job(conn)
    a1 = db.upsert_application(conn, job_id, "测试公司", "视觉算法")
    a2 = db.upsert_application(conn, job_id, "测试公司", "视觉算法")
    assert a1 == a2  # 同一岗位不重复建
    assert len(db.get_applications(conn)) == 1
    conn.close()


def test_get_application_by_job():
    conn = db.init_db(TEST_DB)
    job_id = _insert_job(conn)
    assert db.get_application_by_job(conn, job_id) is None
    db.upsert_application(conn, job_id, "测试公司", "视觉算法")
    found = db.get_application_by_job(conn, job_id)
    assert found is not None and found["job_id"] == job_id
    assert db.get_application_by_job(conn, None) is None
    conn.close()


def test_update_application_stage_appends_history():
    conn = db.init_db(TEST_DB)
    job_id = _insert_job(conn)
    app_id = db.upsert_application(conn, job_id, "测试公司", "视觉算法")
    ok = db.update_application_stage(conn, app_id, "interview2", "进行中", "约了周三二面")
    assert ok is True
    app = db.get_applications(conn)[0]
    assert app["current_stage"] == "interview2"
    assert db.STAGE_TO_COLUMN[app["current_stage"]] == "interview"  # 二面归入「面试中」列
    assert len(app["stages"]) == 2
    assert app["stages"][-1]["result"] == "进行中"
    # 非法阶段被拒
    assert db.update_application_stage(conn, app_id, "不存在的阶段") is False
    # 结果为"挂"时自动归入 rejected 列，但历史保留挂在哪一轮
    db.update_application_stage(conn, app_id, "interview3", "挂", "三面挂")
    app2 = db.get_applications(conn)[0]
    assert app2["current_stage"] == "rejected"
    assert app2["stages"][-1]["stage"] == "interview3"  # 历史记得是三面挂的
    assert app2["stages"][-1]["result"] == "挂"
    conn.close()


def test_update_stage_note_updates_card_note():
    """阶段表单填的备注应同步到顶层 note（卡面展示的就是它）；空备注保留原值。"""
    conn = db.init_db(TEST_DB)
    job_id = _insert_job(conn)
    app_id = db.upsert_application(conn, job_id, "测试公司", "视觉算法")
    db.update_application_stage(conn, app_id, "interview1", "进行中", "约了周三一面")
    assert db.get_applications(conn)[0]["note"] == "约了周三一面"
    # 不填备注更新阶段，原备注应保留
    db.update_application_stage(conn, app_id, "interview2", "进行中", "")
    assert db.get_applications(conn)[0]["note"] == "约了周三一面"
    conn.close()


def test_add_manual_application_and_delete():
    conn = db.init_db(TEST_DB)
    app_id = db.add_manual_application(conn, "库外公司", "嵌入式", "杭州")
    apps = db.get_applications(conn)
    assert len(apps) == 1
    assert apps[0]["job_id"] is None
    db.delete_application(conn, app_id)
    assert db.get_applications(conn) == []
    conn.close()


def test_application_events_add_and_delete():
    conn = db.init_db(TEST_DB)
    app_id = db.add_manual_application(conn, "测试公司", "算法工程师", "深圳")
    ok = db.add_application_event(conn, app_id, "笔试", "2026-08-15", "19:00", "线上")
    assert ok is True
    app = db.get_applications(conn)[0]
    assert app["events"][0]["event_type"] == "笔试"
    assert app["events"][0]["event_date"] == "2026-08-15"
    assert app["events"][0]["event_time"] == "19:00"
    event_id = app["events"][0]["id"]
    assert db.delete_application_event(conn, app_id, event_id) is True
    assert db.get_applications(conn)[0]["events"] == []
    conn.close()
