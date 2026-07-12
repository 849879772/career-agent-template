import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import job_filters


def test_intern_filter_does_not_match_international():
    assert job_filters.is_intern_title("Software Engineer Intern")
    assert job_filters.is_intern_title("推荐算法实习生")
    assert not job_filters.is_intern_title("International E-commerce Engineer")


def test_formal_campus_filter_drops_intern_and_social_jobs():
    jobs = [
        {"title": "视觉算法工程师", "jd_url": "https://example.com/campus/1"},
        {"title": "算法实习生", "jd_url": "https://example.com/campus/2"},
        {"title": "嵌入式软件工程师", "jd_url": "https://example.com/social-recruitment/3"},
    ]
    kept, dropped = job_filters.filter_formal_campus_jobs(jobs)
    assert [j["title"] for j in kept] == ["视觉算法工程师"]
    assert [j["title"] for j in dropped] == ["算法实习生", "嵌入式软件工程师"]


def test_formal_campus_filter_keeps_experience_preferred_in_jd_body():
    job = {
        "title": "算法工程师",
        "jd_url": "https://example.com/campus/1",
        "jd_raw": "有机器人项目经验者优先，具备良好工程能力",
    }
    assert job_filters.is_formal_campus_job(job)


def test_formal_filter_uses_project_label_when_title_is_shared():
    job = {
        "title": "软件开发-后台开发方向",
        "job_type": "应届实习",
        "jd_raw": "TEG 应届实习",
        "jd_url": "https://join.qq.com/post_detail.html?postId=1",
    }
    assert job_filters.is_intern_job(job)
    assert not job_filters.is_formal_campus_job(job)


def test_cohort_year_requires_recruitment_context():
    assert job_filters.cohort_year({"title": "算法工程师（27届）"}) == 2027
    assert job_filters.cohort_year({"title": "26届春招-C++开发工程师"}) == 2026
    assert job_filters.cohort_year({"title": "发布时间 2026-07-10"}) is None
