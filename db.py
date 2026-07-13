import json
import hashlib
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent / "data" / "jobs.db"

# "活跃"判定窗口（天）：含今天在内向前数 N 天。
# >1 让单家爬虫某天网络/WAF 抖动时，该公司岗位不会整批从报告消失。
ACTIVE_WINDOW_DAYS = 3

# 投递阶段（改进自师兄 Excel 漏斗）。current_stage 存"细阶段"key，
# 看板按 STAGE_TO_COLUMN 归并到 5 列展示——这样一面/二面/三面/HR面都在「面试中」列里，
# 列数不爆，又能在卡片上看清当前到第几面。
# APPLICATION_STAGES: 细阶段 (key, 显示名)，用于下拉选择 + 卡面轮次标签。
# 笔试/测评合并为「笔试」一个阶段（实务里常是同一道关）。
APPLICATION_STAGES = [
    ("applied", "已投递"),
    ("written", "笔试"),
    ("interview1", "一面"),
    ("interview2", "二面"),
    ("interview3", "三面"),
    ("hr", "HR面"),
    ("offer", "Offer"),
    ("rejected", "已挂"),
]
# KANBAN_COLUMNS: 看板列 (key, 显示名)。一面/二面/三面/HR面 都归「面试」列。
KANBAN_COLUMNS = [
    ("applied", "已投递"),
    ("written", "笔试"),
    ("interview", "面试"),
    ("offer", "Offer"),
    ("rejected", "已挂"),
]
# 细阶段 → 看板列。含旧库兼容（老的 assessment/interview 列级 key）。
STAGE_TO_COLUMN = {
    "applied": "applied",
    "written": "written",
    "interview1": "interview",
    "interview2": "interview",
    "interview3": "interview",
    "hr": "interview",
    "offer": "offer",
    "rejected": "rejected",
    # 旧库兼容
    "assessment": "written",
    "interview": "interview",
}
_VALID_STAGES = {k for k, _ in APPLICATION_STAGES}
_DEFAULT_STAGE = "applied"


# These routes expose a recruitment list.  A fragment appended to them is only
# a crawler-side identifier and cannot be opened as an individual job page.
_LISTING_URL_MARKERS = (
    "/campus/jobs#",
    "/campus/positions#",
    "/pb/school.html#",
    "/mc/position/campus#",
    "/position#",
    "/positions#",
    "/job-campus",
    "/officialportal/#/campuslist",
    "/personal/personal_applyjob.aspx",
    "/external/apply.aspx",
    "young.yingjiesheng.com/xyzlogin",
    "login.dangdang.com",
    "/invoiceapply/",
)


def is_listing_url(jd_url: str) -> bool:
    """Return whether a URL is a list route rather than a job-detail route."""
    return any(marker in (jd_url or "").casefold() for marker in _LISTING_URL_MARKERS)


def normalize_listing_link_kinds(conn: sqlite3.Connection) -> int:
    """Correct historical rows whose list URLs were stored as job details."""
    rows = conn.execute("SELECT id, jd_url FROM jobs WHERE link_kind <> 'list'").fetchall()
    ids = [(row["id"],) for row in rows if is_listing_url(row["jd_url"])]
    if not ids:
        return 0
    conn.executemany("UPDATE jobs SET link_kind = 'list' WHERE id = ?", ids)
    conn.commit()
    return len(ids)


def migrate_oppo_detail_urls(conn: sqlite3.Connection) -> int:
    """Repair the former OPPO query-string links to the real SPA detail route."""
    cursor = conn.execute(
        """UPDATE jobs
           SET jd_url = REPLACE(
               jd_url,
               'https://careers.oppo.com/university/oppo/campus/post?id=',
               'https://careers.oppo.com/university/oppo/campus/post/'
           )
           WHERE jd_url LIKE 'https://careers.oppo.com/university/oppo/campus/post?id=%'"""
    )
    conn.commit()
    return cursor.rowcount


def migrate_jd_detail_urls(conn: sqlite3.Connection) -> int:
    """Repair legacy JD API URLs into browser-openable SPA detail routes."""
    rows = conn.execute(
        "SELECT id, jd_url FROM jobs WHERE jd_url LIKE 'https://campus.jd.com/api/wx/position/index?type=%#/details?type=%&id=%'"
    ).fetchall()
    updates = []
    for row in rows:
        match = re.search(r"#/details\?type=([^&]+)&id=([^&]+)", row["jd_url"])
        if not match:
            continue
        recruit_type, publish_id = match.groups()
        updates.append((
            f"https://campus.jd.com/#/details?type={recruit_type}&id={publish_id}",
            row["id"],
        ))
    if not updates:
        return 0
    conn.executemany(
        "UPDATE jobs SET jd_url = ?, link_kind = 'detail' WHERE id = ?",
        updates,
    )
    conn.commit()
    return len(updates)


def init_db(db_path=None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            company      TEXT,
            title        TEXT,
            city         TEXT,
            job_type     TEXT,
            jd_url       TEXT UNIQUE,
            jd_raw       TEXT,
            published_at TEXT,
            source       TEXT,
            crawled_at   TEXT,
            last_seen_at TEXT,
            link_kind    TEXT DEFAULT 'detail',
            is_new       INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS job_analysis (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id         INTEGER UNIQUE,
            match_score    INTEGER,
            advantages     TEXT,
            gaps           TEXT,
            summary        TEXT,
            recommendation TEXT,
            analyzed_at    TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS job_screening_cache (
            fingerprint TEXT PRIMARY KEY,
            company     TEXT,
            title       TEXT,
            city        TEXT,
            relevant    INTEGER NOT NULL,
            screened_at TEXT
        )
    """)
    # 投递记录已迁出 jobs.db → data/applications.json（本地权属、文本可合并），
    # 见文件末尾 applications 区。此处不再建 applications 表（旧库残留表无害、不再读写）。
    # 兼容老库：last_seen_at 缺列时补上，并用 crawled_at 回填
    cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "last_seen_at" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN last_seen_at TEXT")
        conn.execute("UPDATE jobs SET last_seen_at = crawled_at WHERE last_seen_at IS NULL")
    if "link_kind" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN link_kind TEXT DEFAULT 'detail'")
        conn.execute("UPDATE jobs SET link_kind = 'list' WHERE jd_url GLOB '*#[0-9]*' OR jd_url LIKE '%/campus/jobs#%'")
    normalize_listing_link_kinds(conn)
    conn.commit()
    return conn


def mark_listing_links_for_companies(conn: sqlite3.Connection, companies: set[str]) -> int:
    """Mark legacy list-page links so the report never labels them as job details."""
    if not companies:
        return 0
    cursor = conn.executemany(
        "UPDATE jobs SET link_kind = 'list' WHERE company = ?",
        [(name,) for name in companies],
    )
    conn.commit()
    return cursor.rowcount


def purge_nonformal_campus_jobs(conn: sqlite3.Connection) -> int:
    """Remove old internship/social rows that were inserted before stricter filters."""
    from job_filters import is_formal_campus_job

    rows = [dict(row) for row in conn.execute("SELECT * FROM jobs").fetchall()]
    ids = [row["id"] for row in rows if not is_formal_campus_job(row)]
    if not ids:
        return 0
    conn.executemany("DELETE FROM job_analysis WHERE job_id = ?", [(job_id,) for job_id in ids])
    conn.executemany("DELETE FROM jobs WHERE id = ?", [(job_id,) for job_id in ids])
    conn.commit()
    return len(ids)


def _job_fingerprint(job: dict) -> str:
    """Stable identity for reusing an AI screening decision across daily crawls."""
    parts = [
        " ".join(str(job.get(field) or "").split()).casefold()
        for field in ("company", "title", "city")
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def find_job_id(conn: sqlite3.Connection, job: dict) -> int | None:
    """Return an existing job by URL or by company/title/city."""
    row = conn.execute(
        "SELECT id FROM jobs WHERE jd_url = ?", (job["jd_url"],)
    ).fetchone()
    if row:
        return row["id"]
    row = conn.execute(
        "SELECT id FROM jobs WHERE company = ? AND title = ? AND IFNULL(city, '') = ?",
        (job["company"], job["title"], job.get("city") or ""),
    ).fetchone()
    return row["id"] if row else None


def get_screening_decision(conn: sqlite3.Connection, job: dict) -> bool | None:
    row = conn.execute(
        "SELECT relevant FROM job_screening_cache WHERE fingerprint = ?",
        (_job_fingerprint(job),),
    ).fetchone()
    return bool(row["relevant"]) if row else None


def save_screening_decision(
    conn: sqlite3.Connection, job: dict, relevant: bool
) -> None:
    save_screening_decisions(conn, [(job, relevant)])


def save_screening_decisions(
    conn: sqlite3.Connection, decisions: list[tuple[dict, bool]]
) -> None:
    """Persist a screening batch in one transaction for large first runs."""
    if not decisions:
        return
    conn.executemany(
        """INSERT OR REPLACE INTO job_screening_cache
           (fingerprint, company, title, city, relevant, screened_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [
            (
                _job_fingerprint(job),
                job.get("company", ""),
                job.get("title", ""),
                job.get("city", ""),
                int(relevant),
                datetime.now().isoformat(),
            )
            for job, relevant in decisions
        ],
    )
    conn.commit()


def upsert_job(conn: sqlite3.Connection, job: dict) -> tuple[bool, int]:
    """新岗位则插入；已存在则刷新 last_seen_at = 今天。

    匹配优先级：
        1. jd_url 完全匹配 → 仅刷新 last_seen_at
        2. (company, title, city) 匹配 → 更新 jd_url + last_seen_at
           （处理 URL 格式升级，例如华为从 #title 锚点改成 advertisementId；
            带 city 区分同公司同名但多城市的不同岗位，避免错误塌缩成一行）
        3. 都没匹配 → INSERT

    Returns: (是否新插入, job_id)
    """
    today = date.today().isoformat()

    # 1. 按 jd_url 找
    row = conn.execute(
        "SELECT id FROM jobs WHERE jd_url = ?", (job["jd_url"],)
    ).fetchone()
    if row:
        conn.execute(
            """UPDATE jobs
               SET city = ?, job_type = ?, jd_raw = CASE WHEN ? <> '' THEN ? ELSE jd_raw END,
                   published_at = CASE WHEN ? <> '' THEN ? ELSE published_at END,
                   source = ?, last_seen_at = ?, link_kind = ?
               WHERE id = ?""",
            (
                job.get("city", ""), job.get("job_type", "校招"), job.get("jd_raw", ""), job.get("jd_raw", ""),
                job.get("published_at", ""), job.get("published_at", ""), job.get("source", job["company"]),
                today, job.get("link_kind", "detail"), row["id"],
            ),
        )
        conn.commit()
        return False, row["id"]

    # 2. 按 (company, title, city) 找（URL 格式变更时仍能识别为同一岗位；
    #    带 city 避免把同公司同名但多城市的不同岗位错误合并成一行）
    row = conn.execute(
        "SELECT id FROM jobs WHERE company = ? AND title = ? AND IFNULL(city, '') = ?",
        (job["company"], job["title"], job.get("city") or ""),
    ).fetchone()
    if row:
        try:
            conn.execute(
                """UPDATE jobs
                   SET jd_url = ?, city = ?, job_type = ?, jd_raw = CASE WHEN ? <> '' THEN ? ELSE jd_raw END,
                       published_at = CASE WHEN ? <> '' THEN ? ELSE published_at END,
                       source = ?, last_seen_at = ?, link_kind = ?
                   WHERE id = ?""",
                (
                    job["jd_url"], job.get("city", ""), job.get("job_type", "校招"),
                    job.get("jd_raw", ""), job.get("jd_raw", ""), job.get("published_at", ""),
                    job.get("published_at", ""), job.get("source", job["company"]),
                    today, job.get("link_kind", "detail"), row["id"],
                ),
            )
            conn.commit()
            return False, row["id"]
        except sqlite3.IntegrityError:
            # 新 jd_url 跟另一行冲突（罕见，例如重命名碰撞）→ 回落到 INSERT 路径
            pass

    # 3. INSERT
    try:
        cursor = conn.execute(
            """INSERT INTO jobs
               (company, title, city, job_type, jd_url, jd_raw, published_at, source,
                crawled_at, last_seen_at, link_kind)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job["company"], job["title"], job["city"], job["job_type"],
                job["jd_url"], job["jd_raw"], job["published_at"], job["source"],
                today, today, job.get("link_kind", "detail"),
            ),
        )
        conn.commit()
        return True, cursor.lastrowid
    except sqlite3.IntegrityError:
        # 并发或竞态：jd_url 此时已存在 → 当作刷新
        conn.execute(
            "UPDATE jobs SET last_seen_at = ? WHERE jd_url = ?",
            (today, job["jd_url"]),
        )
        row = conn.execute(
            "SELECT id FROM jobs WHERE jd_url = ?", (job["jd_url"],)
        ).fetchone()
        conn.commit()
        return False, row["id"]


# 向后兼容别名（旧代码/测试用）
insert_job = upsert_job


def get_active_jobs(conn: sqlite3.Connection) -> list[dict]:
    """当前活跃岗位（last_seen_at 在最近 ACTIVE_WINDOW_DAYS 天内）。

    用窗口而非精确 == today，避免单家爬虫某天抓取失败时该公司岗位
    （last_seen_at 没刷到今天）整批从活跃快照里消失。
    """
    cutoff = (date.today() - timedelta(days=ACTIVE_WINDOW_DAYS - 1)).isoformat()
    rows = conn.execute(
        """SELECT * FROM jobs AS job
           WHERE job.last_seen_at >= ?
             AND (
                 job.link_kind <> 'list'
                 OR NOT EXISTS (
                     SELECT 1 FROM jobs AS detail
                     WHERE detail.company = job.company
                       AND detail.last_seen_at >= ?
                       AND detail.link_kind <> 'list'
                 )
             )""",
        (cutoff, cutoff),
    ).fetchall()
    return [dict(row) for row in rows]


def get_latest_crawl_date(conn: sqlite3.Connection) -> str | None:
    """最近一次抓取日期（MAX(crawled_at)）。

    「今日新增」据此判定（crawled_at == 最新批次），而非与日历 today 比较、
    也不依赖「本次运行新插入」——否则本地批量导入+提交后，次日 CI 重爬时
    岗位已存在，新增会塌成 0（曾导致飞书推送「今日新增 0」）。MAX 每天抓到
    新岗自然递进，无此问题。
    """
    row = conn.execute("SELECT MAX(crawled_at) AS d FROM jobs").fetchone()
    return row["d"] if row else None


def get_new_jobs_today(conn: sqlite3.Connection) -> list[dict]:
    """今日首次出现的岗位（crawled_at == today）。"""
    today = date.today().isoformat()
    rows = conn.execute(
        "SELECT * FROM jobs WHERE crawled_at = ?", (today,)
    ).fetchall()
    return [dict(row) for row in rows]


def get_disappeared_jobs(
    conn: sqlite3.Connection, successful_companies: set
) -> list[dict]:
    """本次扫描中"下线"的岗位：在上一次成功扫到该公司时还存在，但今天没扫到。

    只考虑本次成功爬取（successful_companies）的公司，避免把爬虫故障误判为下线。
    """
    today = date.today().isoformat()
    disappeared = []
    for company in successful_companies:
        prev = conn.execute(
            """SELECT MAX(last_seen_at) AS prev
               FROM jobs WHERE company = ? AND last_seen_at < ?""",
            (company, today),
        ).fetchone()
        if not prev or not prev["prev"]:
            continue
        rows = conn.execute(
            "SELECT * FROM jobs WHERE company = ? AND last_seen_at = ?",
            (company, prev["prev"]),
        ).fetchall()
        disappeared.extend(dict(row) for row in rows)
    return disappeared


def save_analysis(conn: sqlite3.Connection, job_id: int, analysis: dict) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO job_analysis
           (job_id, match_score, advantages, gaps, summary, recommendation, analyzed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            job_id,
            analysis["match_score"],
            json.dumps(analysis["advantages"], ensure_ascii=False),
            json.dumps(analysis["gaps"], ensure_ascii=False),
            analysis["summary"],
            analysis["recommendation"],
            datetime.now().isoformat(),
        ),
    )
    conn.commit()


def has_analysis(conn: sqlite3.Connection, job_id: int) -> bool:
    row = conn.execute(
        "SELECT id FROM job_analysis WHERE job_id = ?", (job_id,)
    ).fetchone()
    return row is not None


def _join_analysis(conn: sqlite3.Connection, jobs: list[dict]) -> dict:
    items = []
    for job in jobs:
        analysis_row = conn.execute(
            "SELECT * FROM job_analysis WHERE job_id = ?", (job["id"],)
        ).fetchone()
        if analysis_row:
            analysis = dict(analysis_row)
            analysis["advantages"] = json.loads(analysis["advantages"] or "[]")
            analysis["gaps"] = json.loads(analysis["gaps"] or "[]")
        else:
            analysis = None
        items.append({"job": job, "analysis": analysis})
    return {"items": items}


def get_active_report_data(conn: sqlite3.Connection) -> dict:
    """报告数据：当前活跃岗位 + 各自分析。"""
    jobs = get_active_jobs(conn)
    data = _join_analysis(conn, jobs)
    data["date"] = date.today().isoformat()
    return data


def get_all_jobs_with_analysis(conn: sqlite3.Connection) -> list[dict]:
    """所有 DB 岗位 + 各自分析（已 join），用于飞书 '全部追踪' 推送。"""
    rows = conn.execute(
        """SELECT * FROM jobs AS job
           WHERE job.link_kind <> 'list'
              OR NOT EXISTS (
                  SELECT 1 FROM jobs AS detail
                  WHERE detail.company = job.company
                    AND detail.link_kind <> 'list'
              )
           ORDER BY job.id"""
    ).fetchall()
    return _join_analysis(conn, [dict(r) for r in rows])["items"]


def get_today_report_data(conn: sqlite3.Connection, date_str: str) -> dict:
    """旧接口（用于向后兼容）：仅今日新增。"""
    rows = conn.execute(
        "SELECT * FROM jobs WHERE crawled_at = ?", (date_str,)
    ).fetchall()
    data = _join_analysis(conn, [dict(r) for r in rows])
    data["date"] = date_str
    return data


# ──────────────────────────────────────────────────────────────────────────
# 投递记录（applications）—— 存 data/applications.json（本地录入、文本可合并）
#
# 与 jobs.db 解耦：jobs.db 由 CI 每天爬取/分析回写（云端权属，二进制 merge=ours）；
# 投递记录由本地 管理.bat 录入（本地权属，JSON 文本 git 干净合并、永不冲突），
# 推送后云端 CI 生成报告时一并读入 → 手机上可见。所有函数保留 conn 形参以兼容
# 旧调用方，但 conn 不再使用（投递不进 jobs.db）。
# ──────────────────────────────────────────────────────────────────────────

APPLICATIONS_PATH = Path(__file__).parent / "data" / "applications.json"


def _load_apps() -> list[dict]:
    if APPLICATIONS_PATH.exists():
        try:
            return json.loads(APPLICATIONS_PATH.read_text(encoding="utf-8")) or []
        except Exception:  # noqa: BLE001
            return []
    return []


def _save_apps(apps: list[dict]) -> None:
    APPLICATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    APPLICATIONS_PATH.write_text(
        json.dumps(apps, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def upsert_application(
    conn,
    job_id,
    company: str,
    title: str,
    city: str = "",
    stage: str = _DEFAULT_STAGE,
    note: str = "",
) -> int:
    """从岗位创建投递记录；若该 job_id 已有记录则直接返回原 id（不重复创建）。

    job_id 为 None 时是手填的库外公司投递。Returns: application id。
    """
    if stage not in _VALID_STAGES:
        stage = _DEFAULT_STAGE
    apps = _load_apps()
    if job_id is not None:
        for a in apps:
            if a.get("job_id") == job_id:
                return a["id"]
    today = date.today().isoformat()
    new_id = max((a["id"] for a in apps), default=0) + 1
    apps.append({
        "id": new_id, "job_id": job_id, "company": company, "title": title, "city": city,
        "current_stage": stage,
        "stages": [{"stage": stage, "result": "待", "date": today, "note": note}],
        "events": [],
        "note": note, "applied_at": today, "updated_at": datetime.now().isoformat(),
    })
    _save_apps(apps)
    return new_id


def add_manual_application(
    conn, company: str, title: str, city: str = "",
    stage: str = _DEFAULT_STAGE, note: str = "",
) -> int:
    """手填一条库外公司的投递记录（job_id = None）。"""
    return upsert_application(conn, None, company, title, city, stage, note)


def update_application_stage(
    conn, app_id: int, stage: str, result: str = "待", note: str = "",
) -> bool:
    """更新当前阶段，并把本次变更追加进 stages 历史。Returns: 是否命中记录。"""
    if stage not in _VALID_STAGES:
        return False
    apps = _load_apps()
    for a in apps:
        if a["id"] == app_id:
            a.setdefault("stages", []).append({
                "stage": stage, "result": result,
                "date": date.today().isoformat(), "note": note,
            })
            # 结果为"挂"时自动归入「已挂」列；具体挂在哪一轮仍保留在 stages 里。
            a["current_stage"] = "rejected" if result == "挂" else stage
            if note:
                a["note"] = note  # 填了备注则同步顶层 note；空备注保留原备注
            a["updated_at"] = datetime.now().isoformat()
            _save_apps(apps)
            return True
    return False


def update_application_note(conn, app_id: int, note: str) -> None:
    apps = _load_apps()
    for a in apps:
        if a["id"] == app_id:
            a["note"] = note
            a["updated_at"] = datetime.now().isoformat()
            _save_apps(apps)
            return


def add_application_event(
    conn,
    app_id: int,
    event_type: str,
    event_date: str,
    event_time: str = "",
    note: str = "",
) -> bool:
    """给一条投递记录追加笔试/面试等日程。Returns: 是否命中记录。"""
    event_date = (event_date or "").strip()
    if not event_date:
        return False
    event_type = (event_type or "").strip() or "笔试"
    event_time = (event_time or "").strip()
    note = (note or "").strip()
    apps = _load_apps()
    for a in apps:
        if a["id"] == app_id:
            events = a.setdefault("events", [])
            event_id = max((e.get("id", 0) for e in events), default=0) + 1
            events.append({
                "id": event_id,
                "event_type": event_type,
                "event_date": event_date,
                "event_time": event_time,
                "note": note,
                "created_at": datetime.now().isoformat(),
            })
            a["updated_at"] = datetime.now().isoformat()
            _save_apps(apps)
            return True
    return False


def delete_application_event(conn, app_id: int, event_id: int) -> bool:
    """删除一条投递日程。Returns: 是否命中记录。"""
    apps = _load_apps()
    for a in apps:
        if a["id"] == app_id:
            before = len(a.get("events", []))
            a["events"] = [e for e in a.get("events", []) if e.get("id") != event_id]
            if len(a["events"]) == before:
                return False
            a["updated_at"] = datetime.now().isoformat()
            _save_apps(apps)
            return True
    return False


def delete_application(conn, app_id: int) -> None:
    apps = [a for a in _load_apps() if a["id"] != app_id]
    _save_apps(apps)


def get_applications(conn=None) -> list[dict]:
    """全部投递记录（含 stages 历史），按最近更新降序。"""
    return sorted(_load_apps(), key=lambda a: a.get("updated_at", ""), reverse=True)


def get_application_by_job(conn, job_id) -> dict | None:
    """某岗位的投递记录（用于在岗位卡上显示"已投递"徽标）。无则 None。"""
    if job_id is None:
        return None
    for a in _load_apps():
        if a.get("job_id") == job_id:
            return a
    return None
