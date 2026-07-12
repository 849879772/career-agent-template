import json
import sys
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
    "jd_raw": "要求熟悉ROS，有深度相机经验，掌握YOLO目标检测",
}


def test_analyze_job_returns_valid_structure():
    response = json.dumps({
        "match_score": 85,
        "advantages": ["ROS经验", "深度相机实战"],
        "gaps": ["CUDA"],
        "summary": "视觉引导抓取岗位",
        "recommendation": "推荐",
    }, ensure_ascii=False)

    with patch("analyzer.call_deepseek_api", return_value=response):
        result = analyzer.analyze_job(JOB, PROFILE)

    assert result["match_score"] == 85
    assert "ROS经验" in result["advantages"]
    assert result["recommendation"] in ("推荐", "考虑", "不推荐")


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
    response = "```json\n" + json.dumps({
        "match_score": 70,
        "advantages": ["Python"],
        "gaps": [],
        "summary": "测试岗位",
        "recommendation": "考虑",
    }, ensure_ascii=False) + "\n```"

    with patch("analyzer.call_deepseek_api", return_value=response):
        result = analyzer.analyze_job(JOB, PROFILE)

    assert result["match_score"] == 70


def test_analyze_job_returns_default_on_api_error():
    with patch("analyzer.call_deepseek_api", side_effect=Exception("API 连接失败")):
        result = analyzer.analyze_job(JOB, PROFILE)

    assert result["match_score"] == 0
    assert result["recommendation"] == "考虑"
    assert result["summary"] == "分析失败，请检查API配置"


def test_analyze_job_normalizes_invalid_recommendation():
    response = json.dumps({
        "match_score": 60,
        "advantages": [],
        "gaps": [],
        "summary": "测试",
        "recommendation": "一般",  # invalid value — should be normalized to "考虑"
    }, ensure_ascii=False)

    with patch("analyzer.call_deepseek_api", return_value=response):
        result = analyzer.analyze_job(JOB, PROFILE)

    assert result["recommendation"] == "考虑"


def test_classify_relevant_titles_returns_bools():
    titles = ["视觉算法工程师", "律师", "嵌入式工程师"]
    response = "[true, false, true]"
    with patch("analyzer.call_deepseek_api", return_value=response):
        result = analyzer.classify_relevant_titles(titles, PROFILE)
    assert result == [True, False, True]


def test_classify_relevant_titles_handles_markdown_wrapping():
    titles = ["A", "B"]
    response = "```json\n[true, false]\n```"
    with patch("analyzer.call_deepseek_api", return_value=response):
        result = analyzer.classify_relevant_titles(titles, PROFILE)
    assert result == [True, False]


def test_classify_relevant_titles_keeps_keyword_relevant_model_false():
    titles = ["跨境支付后端架构师", "预训练数据算法研究员"]
    response = "[false, false]"
    with patch("analyzer.call_deepseek_api", return_value=response):
        result = analyzer.classify_relevant_titles(titles, PROFILE)
    assert result == [True, True]


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


def test_profile_keyword_extends_local_relevance_fallback():
    profile = {
        **PROFILE,
        "target_roles": [{"name": "芯片设计", "keywords": ["FPGA验证"]}],
    }
    with patch("analyzer.call_deepseek_api", return_value="[false]"):
        result = analyzer.classify_relevant_titles(["FPGA验证工程师"], profile)

    assert result == [True]


def test_profile_thresholds_control_recommendation():
    profile = {
        **PROFILE,
        "score_thresholds": {"recommend": 90, "consider": 70},
    }
    response = json.dumps({
        "match_score": 85,
        "advantages": [],
        "gaps": [],
        "summary": "匹配",
        "recommendation": "推荐",
    }, ensure_ascii=False)

    with patch("analyzer.call_deepseek_api", return_value=response):
        result = analyzer.analyze_job(JOB, profile)

    assert result["recommendation"] == "考虑"


def test_classify_relevant_titles_chunks_large_input():
    """>40 条标题应分批多次调用并拼接，避免单次撑爆请求/响应。"""
    titles = [f"岗位{i}" for i in range(95)]
    batch_sizes = []

    def fake(system, user, *a, **k):
        n = len(user.strip().splitlines())
        batch_sizes.append(n)
        return "[" + ",".join(["true"] * n) + "]"

    with patch("analyzer.call_deepseek_api", side_effect=fake):
        result = analyzer.classify_relevant_titles(titles, PROFILE)
    assert len(result) == 95 and all(result)
    assert batch_sizes == [40, 40, 15]  # 分 3 批


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
        "jd_raw": "测试",
        "published_at": "",
        "source": "宇树",
    }
    _, job_id = db.insert_job(conn, job)
    db.save_analysis(conn, job_id, {
        "match_score": 80,
        "advantages": [],
        "gaps": [],
        "summary": "已分析",
        "recommendation": "推荐",
    })

    jobs = db.get_new_jobs_today(conn)

    with patch("analyzer.call_deepseek_api") as mock_call:
        results = analyzer.batch_analyze(jobs, PROFILE, conn)

    # 已分析过 → call_deepseek_api 不应被调用
    mock_call.assert_not_called()
    assert results == []
    conn.close()
