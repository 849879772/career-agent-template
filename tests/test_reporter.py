import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import reporter

MOCK_DATA = {
    "date": "2026-05-13",
    "items": [
        {
            "job": {
                "id": 1,
                "company": "宇树科技",
                "title": "视觉算法工程师",
                "city": "杭州",
                "jd_url": "https://www.unitree.com/jobs/visual",
                "job_type": "校招",
                "crawled_at": "2026-05-13",
            },
            "analysis": {
                "match_score": 88,
                "advantages": ["ROS完整项目经验", "深度相机实战"],
                "gaps": ["CUDA", "TensorRT"],
                "summary": "机械臂视觉引导抓取，需要ROS+视觉经验",
                "recommendation": "推荐",
            },
        },
        {
            "job": {
                "id": 2,
                "company": "宇树科技",
                "title": "嵌入式软件工程师",
                "city": "深圳",
                "jd_url": "https://www.unitree.com/jobs/embedded",
                "job_type": "校招",
                "crawled_at": "2026-05-13",
            },
            "analysis": {
                "match_score": 55,
                "advantages": ["C++经验"],
                "gaps": ["RTOS", "驱动开发"],
                "summary": "嵌入式底层开发",
                "recommendation": "不推荐",
            },
        },
        {
            "job": {
                "id": 3,
                "company": "宇树科技",
                "title": "机械臂控制工程师",
                "city": "杭州",
                "jd_url": "https://www.unitree.com/jobs/arm",
                "job_type": "校招",
                "crawled_at": "2026-05-13",
            },
            "analysis": {
                "match_score": 70,
                "advantages": ["SCARA实战"],
                "gaps": ["六轴机械臂"],
                "summary": "机械臂控制方向",
                "recommendation": "考虑",
            },
        },
    ],
}


def test_generate_report_creates_file(tmp_path):
    path = reporter.generate_report("2026-05-13", MOCK_DATA, reports_dir=str(tmp_path))
    assert os.path.exists(path)
    assert path.endswith(".html")


def test_intern_filter_does_not_match_international():
    assert reporter._is_intern("Software Engineer Intern")
    assert reporter._is_intern("推荐算法实习生")
    assert not reporter._is_intern("International E-commerce Engineer")


def test_report_shows_all_real_analyses(tmp_path):
    """所有真实 AI 分析的岗位都应展示，无论 recommendation 是什么。"""
    path = reporter.generate_report("2026-05-13", MOCK_DATA, reports_dir=str(tmp_path))
    content = Path(path).read_text(encoding="utf-8")
    assert "视觉算法工程师" in content      # 88 推荐 → 大卡片
    assert "机械臂控制工程师" in content    # 70 考虑 → 高匹配
    assert "嵌入式软件工程师" in content    # 55 不推荐，但是真实分析 → 仍展示


def test_report_filters_stub_analyses(tmp_path):
    """隐藏实习岗、分析失败、方向外「未评估」和未解析详情链接。"""
    data = {
    "date": "2026-05-13",
        "items": [
            {
                "job": {"id": 10, "company": "字节跳动", "title": "数据标注实习生",
                        "city": "北京", "jd_url": "https://x.com/1", "job_type": "实习",
                        "crawled_at": "2026-05-13"},
                "analysis": {"match_score": 0, "advantages": [], "gaps": [],
                             "summary": "实习岗位（用户偏好正式校招，自动过滤）",
                             "recommendation": "不推荐"},
            },
            {
                "job": {"id": 11, "company": "字节跳动", "title": "品牌市场经理",
                        "city": "北京", "jd_url": "https://x.com/2", "job_type": "校招",
                        "crawled_at": "2026-05-13"},
                "analysis": {"match_score": 0, "advantages": [], "gaps": [],
                             "summary": "AI 粗筛判定与目标方向不符",
                             "recommendation": "不推荐"},
            },
            {
                "job": {"id": 12, "company": "宇树科技", "title": "视觉算法工程师",
                        "city": "杭州", "jd_url": "https://x.com/3", "job_type": "校招",
                        "crawled_at": "2026-05-13"},
                "analysis": {"match_score": 85, "advantages": ["ROS"], "gaps": ["CUDA"],
                             "summary": "真实分析摘要", "recommendation": "推荐"},
            },
        ],
    }
    path = reporter.generate_report("2026-05-13", data, reports_dir=str(tmp_path))
    content = Path(path).read_text(encoding="utf-8")
    assert "数据标注实习生" not in content   # 实习岗，仍过滤
    assert "品牌市场经理" not in content     # 方向外「未评估」，默认报告隐藏
    assert "视觉算法工程师" in content       # 真实分析，展示
    assert "已隐藏 2 个过滤项" in content


def test_report_contains_match_scores(tmp_path):
    path = reporter.generate_report("2026-05-13", MOCK_DATA, reports_dir=str(tmp_path))
    content = Path(path).read_text(encoding="utf-8")
    assert "88" in content
    assert "70" in content


def test_report_contains_statistics(tmp_path):
    path = reporter.generate_report("2026-05-13", MOCK_DATA, reports_dir=str(tmp_path))
    content = Path(path).read_text(encoding="utf-8")
    assert "宇树科技" in content


def test_report_contains_advantages_and_gaps(tmp_path):
    """高匹配大卡片应展示优势与缺口列表。"""
    path = reporter.generate_report("2026-05-13", MOCK_DATA, reports_dir=str(tmp_path))
    content = Path(path).read_text(encoding="utf-8")
    assert "CUDA" in content
    assert "ROS完整项目经验" in content


def test_report_has_expected_pages(tmp_path):
    """重构后应有 5 个页面：总体岗位/今日新增/公司排行/投递记录/日程安排。"""
    path = reporter.generate_report("2026-05-13", MOCK_DATA, reports_dir=str(tmp_path))
    content = Path(path).read_text(encoding="utf-8")
    for slug in ("recommended", "today", "companies", "previous-cohort", "applications", "schedule"):
        assert f'data-page="{slug}"' in content
        assert f'data-target="{slug}"' in content
    # 已砍掉的占位页不应再出现
    assert 'data-page="favorites"' not in content
    assert 'data-page="messages"' not in content
    assert "27届校招" in content
    assert "投递记录" in content
    assert "日程安排" in content


def test_report_moves_explicit_2026_jobs_to_previous_cohort(tmp_path):
    data = {
        "items": [
            {"job": {"id": 1, "company": "甲", "title": "27届算法工程师", "city": "北京",
                     "jd_url": "https://example.com/27", "job_type": "校招", "jd_raw": "", "link_kind": "detail"},
             "analysis": {"match_score": 80, "advantages": [], "gaps": [], "summary": "", "recommendation": "推荐"}},
            {"job": {"id": 2, "company": "乙", "title": "26届春招-C++开发工程师", "city": "上海",
                     "jd_url": "https://example.com/26", "job_type": "校招", "jd_raw": "", "link_kind": "detail"},
             "analysis": {"match_score": 80, "advantages": [], "gaps": [], "summary": "", "recommendation": "推荐"}},
        ]
    }
    content = Path(reporter.generate_report("2026-05-13", data, reports_dir=str(tmp_path))).read_text(encoding="utf-8")
    current, previous, _ = reporter._filter_items(data["items"])
    assert [item["job"]["title"] for item in current] == ["27届算法工程师"]
    assert [item["job"]["title"] for item in previous] == ["26届春招-C++开发工程师"]
    assert 'data-page="previous-cohort"' in content


def test_previous_cohort_sorts_by_match_score_descending():
    items = [
        {"job": {"company": "低分", "title": "26届春招-C++", "jd_url": "u1"},
         "analysis": {"match_score": 60}},
        {"job": {"company": "高分", "title": "26届春招-算法", "jd_url": "u2"},
         "analysis": {"match_score": 90}},
    ]
    html = reporter._page_previous_cohort(items)
    assert html.index("高分") < html.index("低分")


def test_report_labels_listing_link_instead_of_detail_apply_link(tmp_path):
    data = {"items": [{
        "job": {"id": 1, "company": "甲", "title": "算法工程师", "city": "北京",
                "jd_url": "https://example.com/campus/jobs#1", "job_type": "校招", "jd_raw": "", "link_kind": "list"},
        "analysis": {"match_score": 80, "advantages": [], "gaps": [], "summary": "", "recommendation": "推荐"},
    }]}
    content = Path(reporter.generate_report("2026-05-13", data, reports_dir=str(tmp_path))).read_text(encoding="utf-8")
    assert "仅提供招聘列表" in content
    assert "打开招聘列表" in content


def test_report_today_page_shows_today_jobs(tmp_path):
    """今日新增页应统计最新批次 crawled_at 的岗位。"""
    path = reporter.generate_report("2026-05-13", MOCK_DATA, reports_dir=str(tmp_path))
    content = Path(path).read_text(encoding="utf-8")
    # 今日新增页面里"共 N 个"
    assert "今日新增" in content


def _item(company, title, score, crawled_at):
    return {
        "job": {"company": company, "title": title, "city": "深圳",
                "jd_url": f"https://e.com/{title}", "crawled_at": crawled_at,
                "last_seen_at": "2026-05-13"},
        "analysis": {"match_score": score, "advantages": [], "gaps": [],
                     "summary": "", "recommendation": "推荐"},
    }


def test_today_page_uses_latest_batch_not_date_str():
    """「今日新增」取最新批次 MAX(crawled_at)，与传入 date_str 无关——

    复现并锁定 bug：本地批量导入(crawled_at=旧日期)+提交后，次日推送 date_str
    对不上导致新增塌成 0。现应仍能显示最新批次。
    """
    items = [
        _item("A", "最新岗", 80, "2026-05-13"),
        _item("B", "旧岗",   70, "2026-05-10"),
    ]
    # date_str 故意给一个谁都不等于的日期
    html = reporter._page_today(items, "2026-05-20")
    assert "最新岗" in html      # 最新批次(05-13)入选
    assert "旧岗" not in html     # 旧批次(05-10)排除
    assert "共 1 个" in html
