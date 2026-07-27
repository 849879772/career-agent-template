import job_details


def test_sparse_list_card_jd_is_incomplete():
    assert job_details.is_jd_incomplete({
        "title": "软件算法工程师（校招1005）",
        "jd_raw": "软件算法工程师（校招1005） 发布于 2025-09-08",
    })


def test_full_responsibility_and_requirement_jd_is_complete():
    assert not job_details.is_jd_incomplete({
        "title": "软件算法工程师",
        "jd_raw": "职位描述\n岗位职责：负责三维轨迹算法开发和性能优化。\n"
                  "任职要求：硕士学历，熟悉 C++、计算机几何和优化算法。" * 3,
    })


def test_short_but_structured_jd_is_complete():
    assert not job_details.is_jd_incomplete({
        "title": "测试开发工程师",
        "jd_raw": "岗位职责\n负责自动化测试平台开发和质量保障。\n"
                  "任职要求\n熟悉 Python、Linux、接口测试和持续集成。",
    })


def test_empty_detail_shell_with_navigation_is_incomplete():
    assert job_details.is_jd_incomplete({
        "title": "AI应用工程师",
        "jd_raw": (
            "岗位职责\n岗位要求\n工作地点\n部门意向\n申请\n分享\n收藏\n"
            "构建万物互联的智能世界\n校园招聘\n社会招聘\n关于我们\n"
            "公司简介\n法律声明\n隐私条款\nCookie政策"
        ),
    })


def test_long_listing_card_without_detail_markers_is_incomplete():
    assert job_details.is_jd_incomplete({
        "title": "机器人算法工程师",
        "jd_raw": "机器人算法工程师 深圳 校招 算法类 " + "列表摘要" * 30,
    })


def test_extract_rendered_jd_stops_before_company_information():
    html = """
    <html><body><nav>首页 校园招聘</nav><main>
      <h1>软件算法工程师</h1><h2>职位描述</h2>
      <p>招聘要求：硕士学历，熟悉 C++。</p>
      <p>岗位职责：负责 CAM 软件相关算法。</p>
      <h2>职位信息</h2><p>发布日期 2025-09-08</p>
      <h2>公司信息</h2><p>很长的企业介绍。</p>
    </main></body></html>
    """
    detail = job_details.extract_rendered_jd(html, "软件算法工程师")
    assert detail.startswith("职位描述")
    assert "招聘要求" in detail
    assert "岗位职责" in detail
    assert "职位信息" not in detail
    assert "企业介绍" not in detail


def test_extract_rendered_jd_collapses_duplicate_responsive_content():
    html = """
    <html><body><h2>职位描述</h2>
      <p>招聘要求：熟悉 C++ 和算法。</p><p>岗位职责：负责软件开发。</p>
      <p>招聘要求：熟悉 C++ 和算法。</p><p>岗位职责：负责软件开发。</p>
      <h2>职位信息</h2>
    </body></html>
    """
    detail = job_details.extract_rendered_jd(html)
    assert detail.count("招聘要求") == 1
    assert detail.count("岗位职责") == 1


def test_tencent_sparse_detail_does_not_open_browser(monkeypatch):
    monkeypatch.setattr(job_details, "_fetch_feishu_job_description", lambda _url: "")
    monkeypatch.setattr(
        job_details,
        "fetch_tencent_job_description_status",
        lambda _url: ("", "official_unavailable"),
    )
    monkeypatch.setattr(
        job_details,
        "render_page",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not render")),
    )
    assert job_details.fetch_full_job_description({
        "title": "青云研究课题",
        "jd_raw": "CDG 应届毕业生 青云计划",
        "jd_url": "https://join.qq.com/post_detail.html?postId=123",
        "link_kind": "detail",
    }) == ""


def test_tencent_qingyun_detail_uses_topic_fields(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {
                "topicDetail": "研究通用 VLA 模型与机器人操作学习。",
                "topicRequirement": "熟悉强化学习、PyTorch 和机械臂实验。",
            }}

    monkeypatch.setattr(job_details.requests, "get", lambda *_args, **_kwargs: Response())

    detail, status = job_details.fetch_tencent_job_description_status(
        "https://join.qq.com/post_detail.html?postId=123"
    )

    assert status == "complete"
    assert detail == (
        "岗位职责\n研究通用 VLA 模型与机器人操作学习。\n"
        "任职要求\n熟悉强化学习、PyTorch 和机械臂实验。"
    )


def test_tencent_detail_marks_offline_position(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": 404, "message": "岗位已下架", "data": None}

    monkeypatch.setattr(job_details.requests, "get", lambda *_args, **_kwargs: Response())

    assert job_details.fetch_tencent_job_description_status(
        "https://join.qq.com/post_detail.html?postId=123"
    ) == ("", "job_offline")


def test_feishu_detail_uses_public_api(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"code": 0, "data": {"job_post_detail": {
                "description": "负责机器人导航算法开发。",
                "requirement": "熟悉 C++、ROS 和路径规划。",
            }}}

    monkeypatch.setattr(job_details.requests, "get", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(
        job_details,
        "render_page",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not render")),
    )
    detail = job_details.fetch_full_job_description({
        "title": "机器人导航算法工程师",
        "jd_raw": "机器人导航算法工程师 武汉 深圳 正式 算法",
        "jd_url": "https://demo.jobs.feishu.cn/123/position/7542792351334746422/detail",
        "link_kind": "detail",
    })
    assert detail == (
        "岗位职责\n负责机器人导航算法开发。\n"
        "任职要求\n熟悉 C++、ROS 和路径规划。"
    )


def test_feishu_api_marks_existing_empty_detail_as_officially_unavailable(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "code": 0,
                "data": {
                    "job_post_detail": {
                        "id": "123",
                        "title": "Robot Algorithm Engineer",
                    }
                },
            }

    monkeypatch.setattr(job_details.requests, "get", lambda *_args, **_kwargs: Response())

    detail, status = job_details.fetch_feishu_job_description_status(
        "https://demo.jobs.feishu.cn/123/position/7542792351334746422/detail"
    )

    assert detail == ""
    assert status == "official_unavailable"


def test_huawei_detail_uses_position_intention_api(monkeypatch):
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    responses = iter([
        Response({"data": {"jobId": 123, "mainBusiness": "详见岗位意向"}}),
        Response({"data": [{
            "positionIntention": "AI技术应用",
            "jobResponsibilities": "负责大模型应用、RAG 与效果评估。",
            "jobDemand": "熟悉 Python、Transformer 和向量数据库。",
        }]}),
    ])
    monkeypatch.setattr(
        job_details.requests,
        "post",
        lambda *_args, **_kwargs: next(responses),
    )

    detail, status = job_details.fetch_huawei_job_description_status(
        "https://career.huawei.com/cn/job-details?advertisementId=36390"
    )

    assert status == "complete"
    assert "AI技术应用" in detail
    assert "岗位职责" in detail
    assert "任职要求" in detail


def test_extracts_embedded_51job_campaign_jd():
    html = """
    <script>
    obj = [{name: 'AI编译器工程师',
      value: '岗位职责：<br>负责编译器开发。<br>任职要求：<br>熟悉 C++ 和编译原理。',
      attr2: 'apply'}]
    </script>
    """
    detail = job_details.extract_configured_page_jd(html, "AI编译器工程师")
    assert "负责编译器开发" in detail
    assert "熟悉 C++" in detail


def test_hotjob_list_record_is_hydrated_and_promoted_to_detail(monkeypatch):
    monkeypatch.setattr(
        job_details,
        "fetch_hotjob_position_detail",
        lambda _url: (
            "职位描述\n负责机器人控制算法开发。\n"
            "任职要求\n熟悉 C++、控制理论和 ROS。",
            "https://demo.hotjob.cn/SU123/pb/posDetail.html?"
            "postId=abc&postType=campus",
        ),
    )
    job = {
        "title": "机器人控制算法工程师",
        "jd_raw": "研发类 | 校园招聘",
        "jd_url": "https://demo.hotjob.cn/SU123/pb/school.html#abc",
        "link_kind": "list",
    }

    detail = job_details.fetch_full_job_description(job)

    assert detail.startswith("职位描述")
    assert job["link_kind"] == "detail"
    assert "/pb/posDetail.html?" in job["jd_url"]


def test_moka_short_structured_detail_is_accepted_after_render(monkeypatch):
    monkeypatch.setattr(job_details, "_fetch_feishu_job_description", lambda _url: "")
    render_args = {}

    def fake_render_page(url, *, timeout_ms, extra_wait_ms):
        render_args.update({
            "url": url,
            "timeout_ms": timeout_ms,
            "extra_wait_ms": extra_wait_ms,
        })
        return """
        <html><body>
          <h1>测试开发工程师</h1>
          <h2>职位描述</h2>
          <p>1. 负责自动化测试平台开发、接口测试与质量保障；</p>
          <p>2. 与研发团队协作定位问题并完善持续集成流程。</p>
          <h2>任职要求</h2>
          <p>熟悉 Python、Linux、网络协议和常用测试框架。</p>
          <h2>职位信息</h2>
        </body></html>
        """

    monkeypatch.setattr(job_details, "render_page", fake_render_page)
    detail = job_details.fetch_full_job_description({
        "title": "测试开发工程师",
        "jd_raw": "测试开发工程师 校园招聘",
        "jd_url": "https://example.mokahr.com/campus-recruitment/demo/1#/job/2",
        "link_kind": "detail",
    })

    assert detail.startswith("职位描述")
    assert "任职要求" in detail
    assert render_args["timeout_ms"] == 45000
    assert render_args["extra_wait_ms"] == 5000
