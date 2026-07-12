import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler
from crawlers.beisen import BeisenRecruitCrawler
from crawlers.bytedance import ByteDanceCrawler
from crawlers.dji import DJICrawler
from crawlers.huawei import HuaweiCrawler
from crawlers.generic_render import GenericRenderCrawler
from crawlers.static_html import StaticHtmlCrawler
from crawlers.tencent import TencentCrawler
from crawlers.unitree import UnitreeCrawler
from crawlers.xiaomi import XiaomiCrawler


# ── BaseCrawler ──────────────────────────────────────────────────────────────

def test_base_crawler_fetch_raises():
    crawler = BaseCrawler("测试", "https://example.com")
    try:
        crawler.fetch()
        assert False, "应该抛出 NotImplementedError"
    except NotImplementedError:
        pass


def test_base_crawler_get_returns_none_on_error():
    crawler = BaseCrawler("测试", "https://example.com")
    with patch("crawlers.base.requests.get") as mock_get:
        import requests as req
        mock_get.side_effect = req.exceptions.ConnectionError("网络错误")
        result = crawler._get("https://example.com")
    assert result is None


def test_base_crawler_make_job_defaults():
    crawler = BaseCrawler("宇树科技", "https://www.unitree.com/jobs/")
    job = crawler._make_job("视觉工程师", city="杭州")
    assert job["company"] == "宇树科技"
    assert job["title"] == "视觉工程师"
    assert job["city"] == "杭州"
    assert job["job_type"] == "校招"
    assert job["source"] == "宇树科技"
    assert job["jd_url"] == "https://www.unitree.com/jobs/"
    assert job["jd_raw"] == ""
    assert job["published_at"] == ""
    assert job["link_kind"] == "detail"


def test_tencent_skips_intern_project_even_when_title_is_shared():
    class Resp:
        def json(self):
            return {"data": {"count": 1, "positionList": [{
                "postId": "1001", "positionTitle": "软件开发-后台开发方向",
                "workCities": "深圳", "bgs": "TEG", "projectName": "应届实习",
                "recruitLabelName": "应届实习",
            }]}}

    with patch("crawlers.tencent.requests.post", return_value=Resp()):
        jobs = TencentCrawler("腾讯", "https://join.qq.com/").fetch()

    assert jobs == []


def test_generic_render_uses_nearby_real_detail_anchor():
    crawler = GenericRenderCrawler("测试公司", "https://example.com/campus/jobs")
    html = """
    <div><a class="job" href="/campus/detail/1">视觉算法工程师</a></div>
    <div><a class="job" href="/campus/detail/2">C++开发工程师</a></div>
    <div><a class="job" href="/campus/detail/3">软件测试工程师</a></div>
    """
    jobs = []
    crawler._parse(html, "a.job", jobs, set())
    assert jobs[0]["jd_url"] == "https://example.com/campus/detail/1"
    assert jobs[0]["link_kind"] == "detail"


def test_static_html_marks_text_only_jobs_as_listing_links():
    class Response:
        text = "<html><body><p>算法工程师</p><p>C++开发工程师</p></body></html>"
        apparent_encoding = "utf-8"
        encoding = "utf-8"

    crawler = StaticHtmlCrawler("测试公司", "https://example.com/campus/jobs")
    with patch.object(crawler, "_get", return_value=Response()):
        jobs = crawler.fetch()
    assert jobs
    assert all(job["link_kind"] == "list" for job in jobs)


# ── UnitreeCrawler ───────────────────────────────────────────────────────────

UNITREE_HTML = """
<html><body>
<ul>
  <li>
    <a href="/position/2047604504966201344">
      <p class="title">视觉算法工程师 <span class="icon hot">热招</span></p>
      <p class="base-info">杭州市 | 技术类 | 研发部</p>
      <div class="duty"><p>负责机器人视觉算法研发</p></div>
    </a>
  </li>
  <li>
    <a href="/position/2047604504966201345">
      <p class="title">运动控制工程师</p>
      <p class="base-info">深圳市 | 技术类 | 研发部</p>
      <div class="duty"><p>负责机器人运动规划与控制</p></div>
    </a>
  </li>
</ul>
</body></html>
"""


def test_unitree_render_failure_returns_empty():
    with patch("crawlers.unitree.render_page", return_value=None):
        jobs = UnitreeCrawler("宇树科技", "https://www.unitree.com/careers/").fetch()
    assert jobs == []


def test_unitree_parses_jobs_from_rendered_html():
    with patch("crawlers.unitree.render_page", return_value=UNITREE_HTML):
        jobs = UnitreeCrawler("宇树科技", "https://www.unitree.com/careers/").fetch()
    assert len(jobs) == 2
    titles = [j["title"] for j in jobs]
    assert "视觉算法工程师" in titles  # 注意"热招"标签被剥离
    assert "运动控制工程师" in titles
    for j in jobs:
        assert j["company"] == "宇树科技"
        assert j["jd_url"].startswith("https://www.unitree.com/position/")
    assert jobs[0]["city"] == "杭州市"
    assert jobs[1]["city"] == "深圳市"


# ── DJICrawler ───────────────────────────────────────────────────────────────

# 2026-06 大疆迁到 Moka 平台：hash 路由 #/job/<uuid> + title-<hash> 结构
DJI_HTML = """
<html><body>
<div class="jobs-list-x">
  <a class="link-x" href="#/job/uuid-123">
    <div class="card-content-x">
      <span class="title-x target-color-container">嵌入式软件工程师</span>
      <span class="published-at-x">发布于 2026-06-24</span>
      技术类 | 广东·深圳市 广东·深圳市 负责嵌入式软件开发
    </div>
  </a>
  <a class="link-x" href="#/job/uuid-456">
    <div class="card-content-x">
      <span class="title-x target-color-container">视觉算法工程师</span>
      <span class="published-at-x">发布于 2026-06-22</span>
      技术类 | 上海市 上海市 负责视觉算法研发
    </div>
  </a>
</div>
</body></html>
"""


def test_dji_render_failure_returns_empty():
    with patch.object(DJICrawler, "_render_pages", return_value=[]):
        jobs = DJICrawler("大疆", "https://we.dji.com/zh-CN/campus").fetch()
    assert jobs == []


def test_dji_parses_jobs_from_rendered_html():
    with patch.object(DJICrawler, "_render_pages", return_value=[DJI_HTML]):
        jobs = DJICrawler("大疆", "https://we.dji.com/zh-CN/campus").fetch()
    titles = [j["title"] for j in jobs]
    assert "嵌入式软件工程师" in titles
    assert "视觉算法工程师" in titles
    for j in jobs:
        assert j["company"] == "大疆"
        assert "#/job/" in j["jd_url"]
    cities = {j["city"] for j in jobs}
    assert "广东·深圳市" in cities
    assert "上海市" in cities


def test_dji_deduplicates_jobs_across_pages():
    with patch.object(DJICrawler, "_render_pages", return_value=[DJI_HTML, DJI_HTML]):
        jobs = DJICrawler("大疆", "https://we.dji.com/zh-CN/campus").fetch()
    assert len(jobs) == 2


# ── XiaomiCrawler ────────────────────────────────────────────────────────────

XIAOMI_HTML = """
<html><body>
<div class="listItems__fca8c0">
  <a href="/campus/position/7630790508323752230/detail">
    <div class="positionItem">
      <div class="positionItem-title">
        <span class="positionItem-title-text">手机视觉算法工程师</span>
      </div>
      <div class="positionItem-subTitle">
        <span>北京</span>
        <span>校招</span>
        <span>市场类</span>
      </div>
    </div>
  </a>
  <a href="/campus/position/7624071092491471123/detail">
    <div class="positionItem">
      <div class="positionItem-title">
        <span class="positionItem-title-text">音频算法工程师</span>
      </div>
      <div class="positionItem-subTitle">
        <span>武汉</span>
        <span>校招</span>
      </div>
    </div>
  </a>
</div>
</body></html>
"""


def test_xiaomi_parses_anchors():
    """小米改成直接 Playwright 翻页后，只单测纯解析函数 _parse_anchors。"""
    crawler = XiaomiCrawler("小米", "https://xiaomi.jobs.f.mioffice.cn/")
    soup = BeautifulSoup(XIAOMI_HTML, "html.parser")
    anchors = [
        a for a in soup.find_all("a", href=True)
        if "/campus/position/" in a["href"] and "/detail" in a["href"]
    ]
    jobs = crawler._parse_anchors(anchors)
    titles = [j["title"] for j in jobs]
    assert "手机视觉算法工程师" in titles
    assert "音频算法工程师" in titles
    cities = {j["city"] for j in jobs}
    assert "北京" in cities
    assert "武汉" in cities
    for j in jobs:
        assert j["company"] == "小米"
        assert "/campus/position/" in j["jd_url"]


# ── ByteDanceCrawler ─────────────────────────────────────────────────────────
# 字节飞书招聘 DOM 与小米一致，只是 URL 前缀和 host 不同

BYTEDANCE_HTML = """
<html><body>
<div>
  <a href="/campus/position/7639267015820101941/detail">
    <div class="positionItem">
      <div class="positionItem-title">
        <span class="positionItem-title-text">推荐算法工程师-抖音</span>
      </div>
      <div class="positionItem-subTitle">
        <span>北京</span>
        <span>校招</span>
        <span>研发</span>
      </div>
    </div>
  </a>
  <a href="/campus/position/7637797349983635717/detail">
    <div class="positionItem">
      <div class="positionItem-title">
        <span class="positionItem-title-text">视觉算法工程师-TikTok</span>
      </div>
      <div class="positionItem-subTitle">
        <span>上海</span>
        <span>校招</span>
      </div>
    </div>
  </a>
</div>
</body></html>
"""


def test_bytedance_parses_anchors():
    """字节飞书招聘 DOM 与小米一致，nullsafe & URL host 拼接正确。"""
    crawler = ByteDanceCrawler("字节跳动", "https://jobs.bytedance.com/campus")
    soup = BeautifulSoup(BYTEDANCE_HTML, "html.parser")
    anchors = [
        a for a in soup.find_all("a", href=True)
        if "/campus/position/" in a["href"] and "/detail" in a["href"]
    ]
    jobs = crawler._parse_anchors(anchors)
    titles = [j["title"] for j in jobs]
    assert "推荐算法工程师-抖音" in titles
    assert "视觉算法工程师-TikTok" in titles
    cities = {j["city"] for j in jobs}
    assert "北京" in cities
    assert "上海" in cities
    for j in jobs:
        assert j["company"] == "字节跳动"
        assert j["jd_url"].startswith("https://jobs.bytedance.com/campus/position/")


# ── HuaweiCrawler ────────────────────────────────────────────────────────────
# 华为用 Playwright 拦截 API + 直接拿 JSON。无独立 _parse_items 函数。
# 集成测试由 tests/smoke_crawlers.py 覆盖，单测仅验证 URL 模板。


def test_huawei_detail_url_template():
    crawler = HuaweiCrawler(
        "华为",
        "https://career.huawei.com/reccampportal/portal5/campus-recruitment.html",
    )
    url = crawler.DETAIL_URL_TEMPLATE.format(ad_id=12345)
    assert url == "https://career.huawei.com/cn/job-details?advertisementId=12345"


# ── BeisenRecruitCrawler ─────────────────────────────────────────────────────
# 北森列表页的栏目标题（"热招职位"）也带 STJobTitle 类，必须剔除以免写成假岗位。

BEISEN_HTML = """
<html><body>
<div class="STListItem-x">
  <div class="STJobTitle-x">热招职位</div>
</div>
<div class="STListItem-y">
  <div class="STJobTitle-y">【J123】机器视觉算法工程师</div>
</div>
<div class="STListItem-z">
  <div class="STJobTitle-z">【J456】机械臂控制工程师</div>
</div>
</body></html>
"""


def test_beisen_forces_campus_path():
    # 即便给社招 URL，也强制走 /campus/jobs
    c = BeisenRecruitCrawler("某公司", "https://demo.zhiye.com/social/jobs")
    assert c._list_url() == "https://demo.zhiye.com/campus/jobs"


def test_beisen_skips_section_heading():
    with patch.object(BeisenRecruitCrawler, "_fetch_api_jobs", return_value=[]), \
         patch("crawlers.beisen.render_page", return_value=BEISEN_HTML):
        jobs = BeisenRecruitCrawler("某公司", "https://demo.zhiye.com/campus/jobs").fetch()
    titles = [j["title"] for j in jobs]
    assert "【J123】机器视觉算法工程师" in titles
    assert "【J456】机械臂控制工程师" in titles
    assert all("热招职位" not in t for t in titles)  # 栏目标题被过滤
    assert len(jobs) == 2


def test_beisen_api_uses_real_detail_guid():
    payloads = []

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "Code": 200,
                "Total": 1,
                "Data": [{
                    "Id": "928774b9-0f2c-4bcb-82d9-58d87a62c534",
                    "JobAdName": "吸尘器26校招-UI/UX设计师(J57269)",
                    "LocNames": ["江苏省·苏州市"],
                    "Duty": "工作职责",
                    "Require": "任职资格",
                }],
            }

    class Session:
        def post(self, url, json, headers, timeout):
            payloads.append(json)
            return Resp()

    with patch("crawlers.beisen.requests.Session", return_value=Session()):
        jobs = BeisenRecruitCrawler("追觅", "https://dreame.zhiye.com/campus/jobs").fetch()

    assert len(jobs) == 1
    assert jobs[0]["jd_url"] == (
        "https://dreame.zhiye.com/campus/detail"
        "?jobAdId=928774b9-0f2c-4bcb-82d9-58d87a62c534"
    )
    assert jobs[0]["city"] == "江苏省·苏州市"
    assert payloads[0]["Category"] == ["2"]
