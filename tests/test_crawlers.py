import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler
from crawlers.baidu import BaiduCrawler
from crawlers.beisen import BeisenRecruitCrawler
from crawlers.bytedance import ByteDanceCrawler
from crawlers.dji import DJICrawler
from crawlers.huawei import HuaweiCrawler
from crawlers.hotjob import HotjobRecruitCrawler, fetch_hotjob_position_detail
from crawlers.inovance import InovanceRecruitCrawler
from crawlers.itek import ItekCrawler
from crawlers.jd import JDCrawler
from crawlers.feishu import FeishuRecruitCrawler
from crawlers.generic_render import GenericRenderCrawler
from crawlers.greenvalley import GreenvalleyCrawler
from crawlers.static_html import StaticHtmlCrawler
from crawlers.xtimes import XTimesCrawler
from crawlers.tencent import TencentCrawler
from crawlers.kuaishou import KuaishouCrawler
from crawlers.unitree import UnitreeCrawler
from crawlers.xiaomi import XiaomiCrawler
from crawlers.bilibili import BilibiliCrawler
from crawlers.oppo import OppoCrawler
from crawlers.meituan import MeituanCrawler
from crawlers.moka import MokaRecruitCrawler
from crawlers.huayan import HuayanCrawler


def test_itek_detail_parser_extracts_city_duties_and_requirements():
    html = """
    <html><head><title>嵌入式开发工程师-校园招聘-埃科光电招聘官方网站</title></head>
    <body>
      <h1>嵌入式开发工程师</h1><div>软件/嵌入式类</div><div>合肥,成都</div>
      <h2>岗位职责</h2><p>负责 Linux 驱动与 RTOS 开发。</p>
      <h2>任职要求</h2><p>熟悉 C/C++ 和嵌入式系统。</p><div>尚无简历</div>
      <h2>相关推荐岗位</h2><p>销售工程师</p>
    </body></html>
    """

    title, city, detail = ItekCrawler._parse_detail(html)

    assert title == "嵌入式开发工程师"
    assert city == "合肥,成都"
    assert detail == (
        "招聘类型：校园招聘\n岗位职责\n负责 Linux 驱动与 RTOS 开发。\n"
        "任职要求\n熟悉 C/C++ 和嵌入式系统。"
    )


def test_base_crawler_normalizes_51job_application_intermediary():
    crawler = BaseCrawler("Example", "https://example.com/campus")

    job = crawler._make_job(
        title="Algorithm Engineer",
        jd_url=(
            "https://xyz.51job.com/external/apply.aspx"
            "?jobid=140887255&ctmid=6293090"
        ),
        link_kind="list",
    )

    assert job["jd_url"] == "https://jobs.51job.com/all/140887255.html"
    assert job["link_kind"] == "detail"


def test_oppo_detail_url_uses_path_route():
    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"total": 1, "records": [{
                "idProjPosition": 1728,
                "positionName": "software engineer",
                "workCityName": "Shenzhen",
            }]}}

    with patch("crawlers.oppo.requests.post", return_value=Resp()):
        jobs = OppoCrawler("OPPO", "https://careers.oppo.com/university/oppo/recruitment/post").fetch()

    assert jobs[0]["jd_url"] == "https://careers.oppo.com/university/oppo/campus/post/1728"


def test_meituan_uses_formal_campus_filter_and_real_detail_route():
    class Resp:
        def json(self):
            return {"data": {"page": {"totalPage": 1}, "list": [
                {
                    "jobUnionId": "4091103193",
                    "name": "具身智能数据算法工程师",
                    "jobType": "1",
                    "cityList": [{"name": "北京市"}],
                    "jobDuty": "负责具身智能模型训练",
                },
                {
                    "jobUnionId": "999",
                    "name": "社招岗位",
                    "jobType": "3",
                },
            ]}}

    with patch("crawlers.meituan.requests.post", return_value=Resp()) as post:
        jobs = MeituanCrawler("美团", "https://zhaopin.meituan.com/web/campus").fetch()

    assert [job["title"] for job in jobs] == ["具身智能数据算法工程师"]
    assert jobs[0]["jd_url"] == (
        "https://zhaopin.meituan.com/web/position/detail"
        "?jobUnionId=4091103193&highlightType=campus"
    )
    request_body = post.call_args.kwargs["json"]
    assert request_body["jobType"] == [{"code": "1", "subCode": []}]
    assert "recruitmentType" not in request_body


def test_jd_uses_public_spa_detail_route():
    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"body": {"totalNumber": 1, "items": [{
                "positionName": "C++ engineer", "publishId": 7870,
                "requirementVoList": [{"workCity": "Beijing"}],
            }]}}

    crawler = JDCrawler("JD", "https://campus.jd.com/")
    with patch("crawlers.jd.requests.post", return_value=Resp()) as post:
        jobs = crawler._fetch_type("talent")

    assert jobs[0]["jd_url"] == "https://campus.jd.com/#/details?type=talent&id=7870"
    assert jobs[0]["link_kind"] == "detail"
    request_body = post.call_args.kwargs["json"]
    assert request_body["pageIndex"] == 0
    assert request_body["parameter"]["planIdList"] == []


def test_jd_does_not_fetch_internship_track():
    assert "internship" not in JDCrawler.TYPES


def test_huayan_crawler_reads_every_official_campus_page():
    class Response:
        apparent_encoding = "utf-8"
        encoding = "utf-8"

        def __init__(self, title, next_page=""):
            self.text = f"""
            <ul><li class='sec-move'>
              <div class='item-title'>{title}</div><div class='item-site'>深圳</div>
              <div class='item-txt2'>岗位职责：机器人算法开发</div>
            </li></ul>
            {f'<a href="?type=60&pagenum={next_page}">{next_page}</a>' if next_page else ''}
            """

    crawler = HuayanCrawler(
        "大族机器人",
        "https://www.huayan-robotics.com/about-us/talent-recruitment?type=60",
    )
    with patch.object(crawler, "_get", side_effect=[Response("算法工程师", "2"), Response("软件工程师")]):
        jobs = crawler.fetch()

    assert [job["title"] for job in jobs] == ["算法工程师", "软件工程师"]
    assert jobs[1]["jd_url"].endswith("type=60&pagenum=2")
    assert all(job["link_kind"] == "list" for job in jobs)


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
    with patch("crawlers.base.requests.get") as mock_get, \
         patch("crawlers.base.time.sleep"):
        import requests as req
        mock_get.side_effect = req.exceptions.ConnectionError("网络错误")
        result = crawler._get("https://example.com")
    assert result is None
    assert mock_get.call_count == crawler.REQUEST_ATTEMPTS


def test_base_crawler_get_retries_transient_error():
    class Response:
        def raise_for_status(self):
            return None

    crawler = BaseCrawler("测试", "https://example.com")
    import requests as req
    with patch(
        "crawlers.base.requests.get",
        side_effect=[req.exceptions.ConnectionError("临时错误"), Response()],
    ) as mock_get, patch("crawlers.base.time.sleep"):
        result = crawler._get("https://example.com")

    assert isinstance(result, Response)
    assert mock_get.call_count == 2


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


def test_feishu_parser_preserves_campaign_label():
    crawler = FeishuRecruitCrawler("MiniMax", "https://example.jobs.feishu.cn")
    crawler.HOST = "https://example.jobs.feishu.cn"
    soup = BeautifulSoup(
        """
        <a href="/campus/position/123/detail">
          <span class="positionItem-title-text">大模型算法工程师-2027届</span>
          <div class="positionItem-subTitle"><span>北京、上海</span></div>
          <div>校招 实习 研发 - 算法 2027届校园招聘</div>
        </a>
        """,
        "html.parser",
    )

    jobs = crawler._parse_anchors(soup.find_all("a"))

    assert len(jobs) == 1
    assert jobs[0]["campaign_text"] == "2027届校园招聘"


def test_moka_preserves_project_filter_and_fetches_all_pages():
    def page_html(start: int, count: int) -> str:
        anchors = "".join(
            (
                f'<a href="#/job/00000000-0000-0000-0000-{index:012d}">'
                f'<div class="position-title">算法工程师{index}</div></a>'
            )
            for index in range(start, start + count)
        )
        return (
            "<html><body><div>31 结果</div>"
            f'<section class="jobs-list">{anchors}</section>'
            '<aside><a href="#/job/99999999-0000-0000-0000-000000000001">'
            "其他项目最新岗位</a></aside></body></html>"
        )

    url = (
        "https://www.envision-career.com/campus-recruitment/envisiongroup/43123/"
        "#/jobs?project%5B0%5D=100124183&page=1&anchorName=jobsList"
    )
    crawler = MokaRecruitCrawler("远景科技", url)
    with patch(
        "crawlers.moka.render_page",
        side_effect=[page_html(1, 30), page_html(31, 1)],
    ) as render:
        jobs = crawler.fetch()

    assert len(jobs) == 31
    assert "project%5B0%5D=100124183" in render.call_args_list[0].args[0]
    assert "page=1" in render.call_args_list[0].args[0]
    assert "page=2" in render.call_args_list[1].args[0]
    assert crawler.pagination_complete is True


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


def test_tencent_fetches_complete_job_detail():
    class ListResp:
        def json(self):
            return {"data": {"count": 1, "positionList": [{
                "postId": "1002", "positionTitle": "C++开发工程师",
                "workCities": "深圳", "bgs": "TEG", "projectName": "2027校园招聘",
                "recruitLabelName": "2027校园招聘",
            }]}}

    class DetailResp:
        def json(self):
            return {"data": {
                "desc": "<p>负责客户端核心模块开发与性能优化。</p>",
                "request": "<p>熟悉 C++、Linux 和多线程编程。</p>",
            }}

    with patch("crawlers.tencent.requests.post", return_value=ListResp()), \
         patch("crawlers.tencent.requests.get", return_value=DetailResp()) as mock_get:
        jobs = TencentCrawler("腾讯", "https://join.qq.com/").fetch()

    assert len(jobs) == 1
    assert jobs[0]["jd_raw"] == (
        "岗位职责\n负责客户端核心模块开发与性能优化。\n"
        "任职要求\n熟悉 C++、Linux 和多线程编程。"
    )
    assert mock_get.call_args.kwargs["params"]["postId"] == "1002"


def test_tencent_skips_position_when_detail_api_says_offline():
    class ListResp:
        def json(self):
            return {"data": {"count": 1, "positionList": [{
                "postId": "1003", "positionTitle": "C++开发工程师",
                "workCities": "深圳", "bgs": "TEG",
                "recruitLabelName": "2027校园招聘",
            }]}}

    class DetailResp:
        def json(self):
            return {"status": 404, "message": "岗位已下架", "data": None}

    with patch("crawlers.tencent.requests.post", return_value=ListResp()), \
         patch("crawlers.tencent.requests.get", return_value=DetailResp()):
        jobs = TencentCrawler("腾讯", "https://join.qq.com/").fetch()

    assert jobs == []


def test_baidu_keeps_both_duties_and_requirements():
    class Resp:
        def json(self):
            return {"status": "ok", "data": {"pages": 1, "list": [{
                "postId": "b1", "name": "C++开发工程师", "workPlace": "北京",
                "workContent": "负责客户端核心模块开发。",
                "serviceCondition": "熟悉 C++ 和 Linux。",
            }]}}

    with patch("crawlers.baidu.requests.post", return_value=Resp()):
        jobs = BaiduCrawler("百度", "https://talent.baidu.com/jobs/list").fetch()

    assert jobs[0]["jd_raw"] == (
        "岗位职责\n负责客户端核心模块开发。\n"
        "任职要求\n熟悉 C++ 和 Linux。"
    )


def test_kuaishou_keeps_both_duties_and_requirements():
    class Resp:
        def json(self):
            return {"result": {"pages": 1, "list": [{
                "code": "k1", "name": "测试开发工程师",
                "workLocationDicts": [{"name": "深圳"}],
                "description": "负责自动化测试平台开发。",
                "positionDemand": "熟悉 Python 和接口测试。",
            }]}}

    with patch("crawlers.kuaishou.requests.post", return_value=Resp()):
        jobs = KuaishouCrawler("快手", "https://campus.kuaishou.cn/").fetch()

    assert jobs[0]["jd_raw"] == (
        "岗位职责\n负责自动化测试平台开发。\n"
        "任职要求\n熟悉 Python 和接口测试。"
    )


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


def test_generic_render_extracts_only_known_cities_from_card_copy():
    crawler = GenericRenderCrawler("测试公司", "https://example.com/campus/jobs")
    text = "职位类别 算法类 工作地点 杭州 岗位职责 负责模型开发，可在上海市办公"
    assert crawler._extract_city(text) == "杭州、上海"
    assert crawler._extract_job_city("算法工程师", text) == "杭州"
    assert crawler._extract_job_city("算法工程师（北京/深圳）", text) == "北京、深圳"


def test_feishu_removes_share_token_from_detail_url():
    crawler = FeishuRecruitCrawler("影石", "https://arashivision.jobs.feishu.cn/campus")
    crawler.HOST = "https://arashivision.jobs.feishu.cn"
    soup = BeautifulSoup(
        '<a href="/campus/position/123/detail?share_token=abc">'
        '<span class="positionItem-title-text">C++开发工程师</span>'
        '<div class="positionItem-subTitle"><span>深圳</span></div></a>',
        "html.parser",
    )
    jobs = crawler._parse_anchors(soup.find_all("a"))
    assert jobs[0]["jd_url"] == (
        "https://arashivision.jobs.feishu.cn/campus/position/123/detail"
    )


def test_feishu_treats_missing_paginator_as_complete_single_page():
    class Locator:
        def count(self):
            return 0

    class Page:
        def locator(self, selector):
            assert selector == ".atsx-pagination-next"
            return Locator()

    assert FeishuRecruitCrawler._next_button(Page()) is None


def test_xtimes_parses_reader_markdown_with_full_jd():
    markdown = """
Markdown Content:
在线投递

软件研发工程师

南京/上海/成都

![Image 1](https://example.com/arrow.png)

工作职责：
1.负责 EDA 软件核心模块开发。

资格要求：
1.熟悉 C++、Python 和 Linux。
"""
    crawler = XTimesCrawler(
        "芯行纪",
        "https://www.xtimes-da.com/index.php/Mobile?a=page&p=joinus_school",
    )
    jobs = crawler._parse_markdown(markdown)

    assert len(jobs) == 1
    assert jobs[0]["title"] == "软件研发工程师"
    assert jobs[0]["city"] == "南京、上海、成都"
    assert "资格要求" in jobs[0]["jd_raw"]
    assert jobs[0]["link_kind"] == "list"
    assert jobs[0]["jd_url"] == crawler.careers_url


def test_bytedance_api_item_includes_full_jd_and_recruitment_track():
    crawler = ByteDanceCrawler("字节跳动", "https://jobs.bytedance.com/campus")
    job = crawler._parse_api_job({
        "id": "123",
        "title": "C++开发工程师",
        "description": "负责客户端基础架构开发。",
        "requirement": "熟悉 C++ 与 Linux。",
        "recruit_type": {"name": "校招"},
        "job_subject": {"name": {"zh_cn": "27届秋招"}},
        "city_list": [{"name": "北京"}, {"name": "上海"}],
    })

    assert job["job_type"] == "校招 27届秋招"
    assert job["city"] == "北京 / 上海"
    assert "职位描述\n负责客户端基础架构开发。" in job["jd_raw"]
    assert "任职要求\n熟悉 C++ 与 Linux。" in job["jd_raw"]
    assert job["jd_url"] == (
        "https://jobs.bytedance.com/campus/position/123/detail"
    )


def test_generic_render_retries_transient_navigation_error():
    class NavigationTimeout(Exception):
        pass

    class Page:
        def __init__(self):
            self.calls = 0
            self.waits = []

        def goto(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise NavigationTimeout("temporary timeout")

        def wait_for_timeout(self, value):
            self.waits.append(value)

    crawler = GenericRenderCrawler("测试公司", "https://example.com/campus/jobs")
    page = Page()

    assert crawler._goto_with_retry(page, NavigationTimeout)
    assert page.calls == 2
    assert page.waits == [1500]


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


def test_static_html_rejects_product_research_navigation_as_job():
    class Response:
        text = '<html><body><a href="/research/index.html">主控研发</a></body></html>'
        apparent_encoding = "utf-8"
        encoding = "utf-8"

    crawler = StaticHtmlCrawler("德明利", "https://example.com/job/index.html")
    with patch.object(crawler, "_get", return_value=Response()):
        assert crawler.fetch() == []


def test_generic_render_rejects_developer_forum_navigation():
    crawler = GenericRenderCrawler("昂瑞微", "https://example.com/campus")
    assert crawler._clean_title("开发者论坛") == ""
    assert crawler._clean_title("开发者区域") == ""
    assert crawler._clean_title("Developers") == ""


def test_generic_render_rejects_social_media_job_links():
    crawler = GenericRenderCrawler("测试公司", "https://example.com/campus/jobs")
    html = '<a class="job" href="https://www.youtube.com/@demo">视觉算法工程师</a>'
    jobs = []
    crawler._parse(html, "a.job", jobs, set())
    assert jobs[0]["jd_url"] == "https://example.com/campus/jobs"
    assert jobs[0]["link_kind"] == "list"


def test_static_html_rejects_linkedin_search_result():
    class Response:
        text = '<a href="https://www.linkedin.com/jobs/search?keywords=test">测试工程师</a>'
        apparent_encoding = "utf-8"
        encoding = "utf-8"

    crawler = StaticHtmlCrawler("测试公司", "https://example.com/campus/jobs")
    with patch.object(crawler, "_get", return_value=Response()):
        assert crawler.fetch() == []


def test_hotjob_marks_hash_urls_as_listing_links():
    crawler = HotjobRecruitCrawler("test", "https://example.hotjob.cn/SU123/pb/account.html")
    jobs = crawler._parse_pb(
        '<div class="list-row-item"><div class="list-cell pos-name"><span class="list-cell-span">C++ developer</span></div></div>',
        "https://example.hotjob.cn/SU123/pb/school.html",
    )
    assert jobs[0]["link_kind"] == "list"


def test_hotjob_detail_uses_public_api(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "state": "200",
                "data": {
                    "workContent": "<p>负责点云检测与算法工程化。</p>",
                    "serviceCondition": "熟悉 C++、Python 和深度学习。",
                },
            }

    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["data"] = kwargs["data"]
        return Response()

    monkeypatch.setattr("crawlers.hotjob.requests.post", fake_post)
    detail, detail_url = fetch_hotjob_position_detail(
        "https://demo.hotjob.cn/SU123abc/pb/school.html#post-42"
    )

    assert captured["url"].endswith(
        "/wecruit/positionInfo/listPositionDetail/SU123abc"
    )
    assert captured["data"] == {"postId": "post-42"}
    assert detail == (
        "职位描述\n负责点云检测与算法工程化。\n"
        "任职要求\n熟悉 C++、Python 和深度学习。"
    )
    assert detail_url == (
        "https://demo.hotjob.cn/SU123abc/pb/posDetail.html?"
        "postId=post-42&postType=campus"
    )


def test_greenvalley_reads_complete_campus_jd_and_skips_internship(monkeypatch):
    class Response:
        apparent_encoding = "utf-8"
        encoding = "utf-8"
        text = """
        var jobs=[
          {lb: '软件研发类', gw: '点云算法工程师',
           ms: '负责点云分割与检测。', yq: '熟悉C++和PCL。',
           lj: 'https://jobs.example/1?type=CAMPUSRECRUITMENT'},
          {lb: '工程数据类', gw: '数据处理实习生',
           ms: '负责数据处理。', yq: '在校生。',
           lj: 'https://jobs.example/2?type=INTERNSHIPRECRUITMENT'}
        ]
        """

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        "crawlers.greenvalley.requests.get",
        lambda *_args, **_kwargs: Response(),
    )
    jobs = GreenvalleyCrawler(
        "数字绿土", "https://campus.51job.com/greenvalley/san.html"
    ).fetch()

    assert len(jobs) == 1
    assert jobs[0]["title"] == "点云算法工程师"
    assert jobs[0]["jd_url"] == (
        "https://campus.51job.com/greenvalley/san.html#job-ref=1"
    )
    assert jobs[0]["link_kind"] == "list"
    assert "职位描述" in jobs[0]["jd_raw"]
    assert "任职要求" in jobs[0]["jd_raw"]


def test_bilibili_marks_hash_urls_as_listing_links():
    crawler = BilibiliCrawler("bilibili", BilibiliCrawler.LIST_URL)
    jobs = []
    crawler._parse('<div class="item"><h4 class="item-title"><span class="text">algorithm engineer</span></h4></div>', jobs, set())
    assert jobs[0]["link_kind"] == "list"


def test_bilibili_api_rows_use_real_detail_urls_and_full_jd():
    crawler = BilibiliCrawler("bilibili", BilibiliCrawler.LIST_URL)
    jobs = []
    added = crawler._parse_api_payload(
        {
            "data": {
                "list": [
                    {
                        "id": 29442,
                        "positionName": "多模态数据平台研发工程师（校招）",
                        "workCity": "上海",
                        "positionDescription": (
                            "工作职责：负责多模态训练数据平台开发。"
                            "工作要求：熟悉 Python、分布式系统和大模型训练流程。"
                        ),
                        "pushTime": "2026-07-24 10:00:00",
                    }
                ]
            }
        },
        jobs,
        set(),
    )

    assert added == 1
    assert jobs[0]["jd_url"].endswith("/campus/positions/29442")
    assert jobs[0]["link_kind"] == "detail"
    assert "工作要求" in jobs[0]["jd_raw"]
    assert jobs[0]["published_at"] == "2026-07-24"


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
        assert j["jd_url"].startswith("https://apply.careers.dji.com/campus-recruitment/dji/143359?locale=zh-CN")
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


def test_inovance_uses_current_portal_api_and_detail_url():
    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "code": 200,
                "data": {
                    "hasMore": False,
                    "records": [{
                        "adId": "job-27",
                        "adJobName": "【27校招】嵌入式软件工程师",
                        "workLocation": [{"name": "苏州市"}, {"name": "深圳市"}],
                        "jobDescription": "岗位职责",
                        "jobRequirement": "2027届，熟悉 C++",
                        "publishTime": "2026-07-13T17:34:14",
                    }],
                },
            }

    with patch("crawlers.inovance.requests.post", return_value=Resp()) as post:
        jobs = InovanceRecruitCrawler("汇川技术", "https://recruit.inovance.com/#/campus/jobs").fetch()

    assert len(jobs) == 1
    assert jobs[0]["title"] == "【27校招】嵌入式软件工程师"
    assert jobs[0]["city"] == "苏州市 / 深圳市"
    assert jobs[0]["jd_url"] == "https://recruit.inovance.com/#/jobs/job-27"
    assert "2027届" in jobs[0]["jd_raw"]
    assert post.call_args.kwargs["json"]["recruitTypes"] == [1]


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
    assert jobs[0]["jd_raw"] == "岗位职责\n工作职责\n任职要求\n任职资格"
    assert payloads[0]["Category"] == ["2"]
