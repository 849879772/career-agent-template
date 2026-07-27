import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import analyzer

PROFILE = {
    "skills": ["ROS Noetic", "C++", "Python", "YOLOv8", "RealSense深度相机"],
    "direction": "机器人视觉 / 机械臂控制",
    "degree": "研究生",
    "job_type": "校招",
}

JOB = {
    "id": 1,
    "company": "宇树科技",
    "title": "视觉算法工程师",
    "city": "杭州",
    "cohort": 2027,
    "cohort_status": "confirmed",
    "jd_raw": (
        "岗位职责：负责机器人视觉算法开发、目标检测模型训练和深度相机点云处理，"
        "完成视觉引导机械臂抓取功能。任职要求：熟悉 ROS、C++、Python，"
        "具有 RealSense 深度相机、YOLO 目标检测和机械臂项目经验。" * 2
    ),
}


def analysis_response(score_breakdown=None, **overrides):
    payload = {
        "score_breakdown": score_breakdown or {
            "core_direction": 23,
            "required_skills": 22,
            "project_evidence": 21,
            "engineering_stack": 12,
            "basic_criteria": 7,
        },
        "evidence_level": "direct",
        "evidence": [
            {
                "jd_requirement": "机器人视觉算法开发",
                "profile_evidence": "YOLO 与 RealSense 项目",
                "relation": "direct",
                "requirement_type": "core",
            },
            {
                "jd_requirement": "机械臂抓取",
                "profile_evidence": "机械臂控制项目",
                "relation": "direct",
                "requirement_type": "core",
            },
        ],
        "missing_core_requirements": [],
        "advantages": ["ROS经验", "深度相机实战"],
        "gaps": [],
        "summary": "视觉引导抓取岗位",
    }
    payload.update(overrides)
    return payload


def test_analyze_job_returns_valid_structure():
    response = json.dumps(analysis_response(), ensure_ascii=False)

    with patch("analyzer.call_deepseek_api", return_value=response) as mock_call:
        result = analyzer.analyze_job(JOB, PROFILE)

    assert result["match_score"] == 85
    assert "ROS经验" in result["advantages"]
    assert result["recommendation"] in ("推荐", "考虑", "不推荐")
    assert mock_call.call_args.args[2] == "deepseek-v4-pro"


def test_deepseek_request_uses_official_endpoint_and_disables_thinking(monkeypatch):
    class Response:
        status_code = 200
        content = b'{"content":[{"type":"text","text":"{}"}]}'
        text = content.decode()

    seen = {}
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen["payload"] = kwargs["json"]
        return Response()

    with patch("analyzer.requests.post", side_effect=fake_post):
        analyzer.call_deepseek_api("system", "user")

    assert seen["url"].startswith("https://api.deepseek.com/anthropic/")
    assert seen["payload"]["model"] == "deepseek-v4-flash"
    assert seen["payload"]["thinking"] == {"type": "disabled"}


def test_analyze_job_strips_markdown_codeblock():
    response = "```json\n" + json.dumps(analysis_response(
        {
            "core_direction": 20,
            "required_skills": 18,
            "project_evidence": 15,
            "engineering_stack": 10,
            "basic_criteria": 7,
        },
        evidence_level="partial",
        advantages=["Python"],
        summary="测试岗位",
    ), ensure_ascii=False) + "\n```"

    with patch("analyzer.call_deepseek_api", return_value=response):
        result = analyzer.analyze_job(JOB, PROFILE)

    assert result["match_score"] == 70


def test_analyze_job_returns_default_on_api_error():
    with patch("analyzer.call_deepseek_api", side_effect=Exception("API 连接失败")):
        result = analyzer.analyze_job(JOB, PROFILE)

    assert result["match_score"] == 0
    assert result["recommendation"] == "考虑"
    assert result["summary"] == "分析失败，请检查API配置"


def test_analyze_job_derives_recommendation_from_deterministic_score():
    response = json.dumps(analysis_response(
        {
            "core_direction": 18,
            "required_skills": 15,
            "project_evidence": 12,
            "engineering_stack": 10,
            "basic_criteria": 5,
        },
        evidence_level="partial",
        recommendation="推荐",
    ), ensure_ascii=False)

    with patch("analyzer.call_deepseek_api", return_value=response):
        result = analyzer.analyze_job(JOB, PROFILE)

    assert result["recommendation"] == "考虑"


def test_analyze_job_does_not_call_pro_for_incomplete_jd():
    sparse_job = {**JOB, "jd_raw": "视觉算法工程师 发布于 2026-07-22"}
    with patch("analyzer.call_deepseek_api") as mock_call:
        result = analyzer.analyze_job(sparse_job, PROFILE)
    mock_call.assert_not_called()
    assert result["analysis_status"] == "jd_incomplete"
    assert result["summary"] == "JD不完整，待补全后评分"


def test_analyze_job_caps_tool_only_or_adjacent_match_at_64():
    response = json.dumps(analysis_response(
        {
            "core_direction": 25,
            "required_skills": 25,
            "project_evidence": 25,
            "engineering_stack": 15,
            "basic_criteria": 10,
        },
        evidence_level="adjacent",
        evidence=[{
            "jd_requirement": "C++ 和 Qt",
            "profile_evidence": "C++ 和 Qt",
            "relation": "direct",
            "requirement_type": "supporting",
        }],
    ), ensure_ascii=False)
    with patch("analyzer.call_deepseek_api", return_value=response):
        result = analyzer.analyze_job(JOB, PROFILE)
    assert result["match_score"] == 64


def test_analyze_job_caps_missing_core_requirements():
    one_missing = json.dumps(analysis_response(
        evidence_level="direct",
        missing_core_requirements=["三维重建"],
    ), ensure_ascii=False)
    with patch("analyzer.call_deepseek_api", return_value=one_missing):
        assert analyzer.analyze_job(JOB, PROFILE)["match_score"] == 74

    two_missing = json.dumps(analysis_response(
        evidence_level="direct",
        missing_core_requirements=["三维重建", "目标跟踪"],
    ), ensure_ascii=False)
    with patch("analyzer.call_deepseek_api", return_value=two_missing):
        assert analyzer.analyze_job(JOB, PROFILE)["match_score"] == 64


def test_analysis_fingerprint_changes_with_jd_profile_and_version():
    base = analyzer.analysis_metadata(JOB, PROFILE, "deepseek-v4-pro")
    assert analyzer.analysis_metadata({**JOB, "jd_raw": JOB["jd_raw"] + "新增要求"}, PROFILE, "deepseek-v4-pro")["jd_fingerprint"] != base["jd_fingerprint"]
    assert analyzer.analysis_metadata(JOB, {**PROFILE, "degree": "本科"}, "deepseek-v4-pro")["profile_fingerprint"] != base["profile_fingerprint"]
    assert base["analysis_version"] == analyzer.ANALYSIS_VERSION


def test_classify_relevant_titles_returns_bools():
    titles = ["视觉算法工程师", "律师", "嵌入式工程师"]
    response = '[{"id":1,"relevant":true},{"id":2,"relevant":false},{"id":3,"relevant":true}]'
    with patch("analyzer.call_deepseek_api", return_value=response) as mock_call:
        result = analyzer.classify_relevant_titles(titles, PROFILE)
    assert result == [True, False, True]
    assert mock_call.call_args.args[2] == "deepseek-v4-flash"


def test_classify_relevant_titles_handles_markdown_wrapping():
    titles = ["Python开发工程师", "研发工程师"]
    response = "```json\n[true, false]\n```"
    with patch("analyzer.call_deepseek_api", return_value=response):
        result = analyzer.classify_relevant_titles(titles, PROFILE)
    assert result == [True, False]


def test_classify_relevant_titles_does_not_force_generic_keyword_true():
    titles = ["跨境支付后端架构师", "预训练数据算法研究员"]
    response = "[false, false]"
    with patch("analyzer.call_deepseek_api", return_value=response):
        result = analyzer.classify_relevant_titles(titles, PROFILE)
    assert result == [True, False]


def test_classify_relevant_titles_keeps_target_directions_model_false():
    titles = [
        "C++软件开发工程师",
        "软件测试工程师",
        "大模型应用开发工程师",
        "智能体Agent工程师",
        "具身智能算法工程师",
        "机械臂运动控制工程师",
        "机器视觉算法工程师",
        "VLA算法研究员",
        "强化学习算法工程师",
        "模仿学习研究员",
    ]
    response = "[" + ",".join(["false"] * len(titles)) + "]"
    with patch("analyzer.call_deepseek_api", return_value=response):
        result = analyzer.classify_relevant_titles(titles, PROFILE)
    assert result == [True] * len(titles)


def test_classify_relevant_titles_filters_strong_negative_even_if_model_true():
    titles = ["多端产品经理", "销售管培生"]
    response = "[true, true]"
    with patch("analyzer.call_deepseek_api", return_value=response):
        result = analyzer.classify_relevant_titles(titles, PROFILE)
    assert result == [False, False]


def test_classify_relevant_titles_keeps_research_about_sales_scenario():
    titles = ["面向销售的Agentic强化学习研究", "销售工程师"]
    response = "[false, false]"
    with patch("analyzer.call_deepseek_api", return_value=response):
        result = analyzer.classify_relevant_titles(titles, PROFILE)
    assert result == [True, False]


def test_classify_relevant_titles_uses_keyword_fallback_on_error():
    """API 失败时使用本地关键词兜底，避免把全部岗位送入细分析。"""
    titles = ["视觉算法工程师", "销售管培生", "嵌入式软件工程师"]
    with patch("analyzer.call_deepseek_api", side_effect=Exception("API down")):
        result = analyzer.classify_relevant_titles(titles, PROFILE)
    assert result == [True, False, True]


def test_classify_relevant_titles_uses_keyword_fallback_on_length_mismatch():
    titles = ["Python开发工程师", "行政专员", "机器人控制工程师"]
    # DeepSeek 返回长度不对的响应
    with patch("analyzer.call_deepseek_api", return_value="[true, false]"):
        result = analyzer.classify_relevant_titles(titles, PROFILE)
    assert result == [True, False, True]


def test_classify_relevant_titles_empty_input():
    with patch("analyzer.call_deepseek_api") as mock:
        result = analyzer.classify_relevant_titles([], PROFILE)
    assert result == []
    mock.assert_not_called()


def test_classify_relevant_titles_chunks_large_input():
    """>40 条标题应分批多次调用并拼接，避免单次撑爆请求/响应。"""
    titles = [f"研发岗位{i}" for i in range(95)]
    batch_sizes = []

    def fake(system, user, *a, **k):
        n = user.count("标题：")
        batch_sizes.append(n)
        return json.dumps([
            {"id": index, "tier": "B"}
            for index in range(1, n + 1)
        ])

    with patch("analyzer.call_deepseek_api", side_effect=fake):
        result = analyzer.classify_relevant_titles(titles, PROFILE)
    assert len(result) == 95 and all(result)
    assert batch_sizes == [20, 20, 20, 20, 15]


def test_classify_job_tiers_separates_pro_display_and_reject():
    jobs = [
        {"title": "C++客户端开发工程师", "jd_raw": ""},
        {"title": "大模型训练研究员", "jd_raw": "负责基座模型预训练"},
        {"title": "Java后端研发工程师", "jd_raw": "Spring Cloud微服务"},
    ]
    response = '[{"id":1,"tier":"B"},{"id":2,"tier":"C"}]'
    with patch("analyzer.call_deepseek_api", return_value=response):
        tiers = analyzer.classify_job_tiers(jobs, PROFILE)
    assert tiers == ["A", "B", "C"]


def test_classify_relevant_titles_only_falls_back_for_missing_ids():
    titles = ["视觉算法工程师", "销售管培生", "嵌入式软件工程师"]
    response = '[{"id":1,"relevant":false},{"id":2,"relevant":true}]'
    with patch("analyzer.call_deepseek_api", return_value=response):
        result = analyzer.classify_relevant_titles(titles, PROFILE)
    assert result == [True, False, True]


def test_classify_relevant_titles_ignores_trailing_model_output():
    with patch(
        "analyzer.call_deepseek_api",
        return_value='[{"id":1,"relevant":true}]\n额外说明',
    ):
        result = analyzer.classify_relevant_titles(["C++开发工程师"], PROFILE)
    assert result == [True]


def test_batch_analyze_skips_analyzed(tmp_path):
    import db
    db_path = str(tmp_path / "test.db")
    conn = db.init_db(db_path)

    job = {
        "company": "宇树",
        "title": "测试",
        "city": "杭州",
        "job_type": "校招",
        "jd_url": "https://example.com/job/batch1",
        "jd_raw": JOB["jd_raw"],
        "published_at": "",
        "source": "宇树",
    }
    _, job_id = db.insert_job(conn, job)
    stored_job = dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
    db.save_analysis(conn, job_id, {
        "match_score": 80,
        "score_breakdown": {},
        "evidence": [],
        "evidence_level": "direct",
        "analysis_status": "complete",
        "advantages": [],
        "gaps": [],
        "summary": "已分析",
        "recommendation": "推荐",
        **analyzer.analysis_metadata(stored_job, PROFILE, "deepseek-v4-pro"),
    })

    jobs = db.get_new_jobs_today(conn)

    with patch("analyzer.call_deepseek_api") as mock_call:
        results = analyzer.batch_analyze(jobs, PROFILE, conn)

    # 已分析过 → call_deepseek_api 不应被调用
    mock_call.assert_not_called()
    assert results == []
    conn.close()


def test_batch_analyze_skips_pro_when_jd_cannot_be_hydrated(tmp_path):
    import db
    conn = db.init_db(str(tmp_path / "incomplete.db"))
    job = {
        "company": "测试公司", "title": "视觉算法工程师", "city": "深圳",
        "job_type": "校招", "jd_url": "https://example.com/job/sparse",
        "jd_raw": "视觉算法工程师 发布于 2026-07-22", "published_at": "",
        "source": "测试公司",
    }
    _, job_id = db.insert_job(conn, job)
    stored = dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
    with patch("job_details.fetch_full_job_description", return_value=""), \
         patch("analyzer.call_deepseek_api") as mock_call:
        results = analyzer.batch_analyze([stored], PROFILE, conn)
    mock_call.assert_not_called()
    assert results == []
    assert not db.has_analysis(conn, job_id)
    conn.close()


def test_batch_analyze_hydrates_jd_before_pro(tmp_path):
    import db
    conn = db.init_db(str(tmp_path / "hydrated.db"))
    job = {
        "company": "测试公司", "title": "视觉算法工程师", "city": "深圳",
        "job_type": "校招", "jd_url": "https://example.com/job/hydrate",
        "jd_raw": "视觉算法工程师 发布于 2026-07-22", "published_at": "",
        "source": "测试公司", "cohort": 2027, "cohort_status": "confirmed",
    }
    _, job_id = db.insert_job(conn, job)
    stored = dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
    response = json.dumps(analysis_response(), ensure_ascii=False)
    with patch("job_details.fetch_full_job_description", return_value=JOB["jd_raw"]), \
         patch("analyzer.call_deepseek_api", return_value=response) as mock_call:
        results = analyzer.batch_analyze([stored], PROFILE, conn)
    assert len(results) == 1
    assert mock_call.call_args.args[2] == "deepseek-v4-pro"
    assert conn.execute("SELECT jd_raw FROM jobs WHERE id = ?", (job_id,)).fetchone()[0] == JOB["jd_raw"]
    assert db.has_analysis(conn, job_id)
    conn.close()


def test_batch_analyze_rechecks_formal_filter_after_hydration(tmp_path):
    import db
    conn = db.init_db(str(tmp_path / "intern-after-hydration.db"))
    job = {
        "company": "测试公司", "title": "系统工程师", "city": "深圳",
        "job_type": "校招", "jd_url": "https://example.com/job/intern-hidden",
        "jd_raw": "系统工程师 发布于 2026-07-22", "published_at": "",
        "source": "测试公司", "cohort": 2027, "cohort_status": "confirmed",
    }
    _, job_id = db.insert_job(conn, job)
    stored = dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
    hydrated = (
        "2027届寻梦实习招聘\n岗位职责\n负责系统软件开发和性能优化。\n"
        "任职要求\n熟悉 C++、Linux、操作系统和数据结构。"
    )
    with patch("job_details.fetch_full_job_description", return_value=hydrated), \
         patch("analyzer.call_deepseek_api") as mock_call:
        results = analyzer.batch_analyze([stored], PROFILE, conn)
    mock_call.assert_not_called()
    assert results == []
    assert not db.has_analysis(conn, job_id)
    conn.close()


def test_batch_analyze_keeps_tier_b_without_calling_pro(tmp_path):
    import db
    conn = db.init_db(str(tmp_path / "tier-b.db"))
    job = {
        "company": "测试公司", "title": "大模型训练研究员", "city": "北京",
        "job_type": "校招", "jd_url": "https://example.com/job/tier-b",
        "jd_raw": (
            "岗位职责：负责基座大模型预训练和后训练研究。"
            "任职要求：具有分布式训练、模型优化和论文研究经验。" * 5
        ),
        "published_at": "", "source": "测试公司", "screening_tier": "B",
    }
    _, job_id = db.insert_job(conn, job)
    stored = dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
    with patch("analyzer.call_deepseek_api") as mock_call:
        results = analyzer.batch_analyze([stored], PROFILE, conn)
    mock_call.assert_not_called()
    assert results == []
    assert not db.has_analysis(conn, job_id)
    conn.close()


def test_batch_analyze_does_not_hydrate_incomplete_tier_b(tmp_path):
    import db
    conn = db.init_db(str(tmp_path / "tier-b-incomplete.db"))
    job = {
        "company": "测试公司", "title": "大模型训练研究员", "city": "北京",
        "job_type": "校招", "jd_url": "https://example.com/job/tier-b-incomplete",
        "jd_raw": "大模型训练研究员 发布于 2026-07-22",
        "published_at": "", "source": "测试公司", "screening_tier": "B",
    }
    _, job_id = db.insert_job(conn, job)
    stored = dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
    with patch("job_details.fetch_full_job_description") as mock_fetch, \
         patch("analyzer.call_deepseek_api") as mock_call:
        results = analyzer.batch_analyze([stored], PROFILE, conn)
    mock_fetch.assert_not_called()
    mock_call.assert_not_called()
    assert results == []
    conn.close()


def test_incomplete_list_and_recent_fetch_failure_do_not_reenter_hydration():
    base = {
        "company": "测试公司",
        "title": "C++开发工程师",
        "city": "深圳",
        "job_type": "校招",
        "jd_url": "https://example.com/job",
        "jd_raw": "C++开发工程师 发布于 2026-07-22",
        "screening_tier": "A",
        "cohort": 2027, "cohort_status": "confirmed",
    }

    assert not analyzer._can_hydrate_to_tier_a({
        **base,
        "link_kind": "list",
        "jd_status": "list_only",
    })
    assert not analyzer._can_hydrate_to_tier_a({
        **base,
        "jd_status": "fetch_failed",
        "jd_checked_at": datetime.now().isoformat(timespec="seconds"),
    })


def test_batch_analyze_enforces_per_run_cap(tmp_path):
    import db
    conn = db.init_db(str(tmp_path / "cap.db"))
    jobs = []
    for index in range(3):
        job = {
            "company": "测试公司", "title": f"C++客户端开发工程师{index}", "city": "深圳",
            "job_type": "校招", "jd_url": f"https://example.com/job/cap-{index}",
            "jd_raw": JOB["jd_raw"], "published_at": "", "source": "测试公司",
            "screening_tier": "A",
            "cohort": 2027, "cohort_status": "confirmed",
        }
        _, job_id = db.insert_job(conn, job)
        jobs.append(dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()))

    response = json.dumps(analysis_response(), ensure_ascii=False)
    with patch("analyzer.call_deepseek_api", return_value=response) as mock_call:
        results = analyzer.batch_analyze(jobs, PROFILE, conn, max_jobs=2)
    assert mock_call.call_count == 2
    assert len(results) == 2
    conn.close()


def test_parse_analysis_json_accepts_literal_control_character():
    parsed = analyzer._parse_analysis_json('{"summary":"第一行\n第二行"}')
    assert parsed["summary"] == "第一行\n第二行"
