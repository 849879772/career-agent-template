from unittest.mock import patch

import job_cohorts


def test_explicit_job_cohort_requires_recruitment_context():
    assert job_cohorts.explicit_job_cohort(
        {"title": "27届秋招-C++开发工程师"}
    )["cohort"] == 2027
    assert job_cohorts.explicit_job_cohort(
        {"title": "C++开发工程师", "published_at": "2026-07-26"}
    )["cohort_status"] == "unknown"
    assert job_cohorts.explicit_job_cohort(
        {"title": "Agent应用开发工程师-campus-2026"}
    )["cohort"] == 2026
    assert job_cohorts.explicit_job_cohort(
        {"title": "2027 Campus Recruitment - Robotics Engineer"}
    )["cohort"] == 2027
    assert job_cohorts.explicit_job_cohort({
        "title": "Java开发工程师",
        "jd_raw": "岗位要求：2027年应届毕业，本科及以上学历",
    })["cohort"] == 2027
    assert job_cohorts.explicit_job_cohort({
        "title": "机器人系统研发工程师",
        "job_type": "校招",
        "jd_raw": "Posted on 2025-08-20 Campus recruiting interview station",
    })["cohort_status"] == "unknown"


def test_explicit_job_cohort_accepts_graduation_date_range():
    result = job_cohorts.explicit_job_cohort(
        {
            "title": "算法工程师-具身智能",
            "jd_raw": (
                "任职要求：毕业时间：2026年10月1日至2027年9月30日期间毕业，"
                "统招本科及以上学历。"
            ),
        }
    )

    assert result["cohort"] == 2027
    assert result["cohort_status"] == "confirmed"

    result_without_label = job_cohorts.explicit_job_cohort(
        {
            "title": "后端开发工程师",
            "jd_raw": (
                "任职要求：2026年10月1日至2027年9月30日期间毕业，"
                "熟练掌握 C++、Java 或 Go。"
            ),
        }
    )

    assert result_without_label["cohort"] == 2027
    assert result_without_label["cohort_status"] == "confirmed"


def test_conflicting_cohort_evidence_stays_unconfirmed():
    decision = job_cohorts.explicit_job_cohort({
        "title": "27届算法工程师",
        "job_type": "2026届校园招聘",
    })
    assert decision["cohort"] == 0
    assert decision["cohort_status"] == "conflict"


def test_official_campaign_can_confirm_unlabelled_jobs():
    jobs = [{"title": "C++开发工程师", "job_type": "校招", "jd_raw": ""}]
    campaign = {
        "cohort": 2027,
        "cohort_status": "confirmed",
        "cohort_source": "公司校招入口",
        "cohort_evidence": "2027届校园招聘正式启动",
        "campaign_scope": "exclusive",
    }
    with patch("job_cohorts.inspect_official_campaign", return_value=campaign):
        result = job_cohorts.annotate_company_jobs(
            jobs,
            "https://example.com/campus",
        )
    assert job_cohorts.is_confirmed_current(result[0])
    assert result[0]["cohort_source"] == "公司校招入口"


def test_campaign_evidence_ignores_dates_and_employee_stories():
    text = (
        "2027“招疆者”校园招聘正式启动 "
        "2026年6月25日开启 "
        "员工故事：我是2022届毕业生"
    )

    assert job_cohorts.campaign_years_in_text(text) == {
        2027: "2027“招疆者”校园招聘正式启动 2026年6月25日开启 员工故事：我是2022届毕业生"
    }
    assert job_cohorts.campaign_years_in_text(
        "首页 社会招聘 校园招聘 ©2026 高标招聘 京ICP备05051632号"
    ) == {}
    decision = job_cohorts._campaign_decision(
        text,
        "公司校招活动页（渲染）",
        "https://example.com/campus",
    )
    assert decision["cohort"] == 2027
    assert decision["cohort_status"] == "confirmed"


def test_campaign_decision_ignores_job_publish_dates():
    decision = job_cohorts._campaign_decision(
        (
            "2027届秋招 游戏系统策划 发布于2026-07-24 "
            "2027届暑期实习 日常实习"
        ),
        "公司校招活动页（渲染）",
        "https://example.com/campus",
    )

    assert decision["cohort"] == 2027
    assert decision["cohort_status"] == "confirmed"


def test_mixed_campaign_does_not_promote_unlabelled_jobs():
    jobs = [{"title": "C++开发工程师", "job_type": "校招", "jd_raw": ""}]
    campaign = {
        "cohort": 2027,
        "cohort_status": "confirmed",
        "cohort_source": "公司校招活动页（渲染）",
        "cohort_evidence": "2027届秋招 2027届暑期实习",
        "campaign_scope": "mixed",
    }

    result = job_cohorts.annotate_company_jobs(
        jobs,
        campaign=campaign,
        inspect_page=False,
    )

    assert result[0]["cohort_status"] == "unknown"


def test_formal_campaign_with_other_internship_year_can_confirm_jobs():
    decision = job_cohorts._campaign_decision(
        "招聘项目 2028届实习生招聘 2027届校园招聘 日常实习",
        "公司校招活动页（渲染）",
        "https://example.com/campus",
    )
    jobs = [{"title": "C++开发工程师", "job_type": "校招", "jd_raw": ""}]

    result = job_cohorts.annotate_company_jobs(
        jobs,
        campaign=decision,
        inspect_page=False,
    )

    assert decision["cohort"] == 2027
    assert decision["campaign_scope"] == "formal_with_internships"
    assert job_cohorts.is_confirmed_current(result[0])


def test_project_cohort_does_not_spread_to_another_project():
    campaign = {
        "cohort": 2027,
        "cohort_status": "confirmed",
        "cohort_source": "公司校招活动页（渲染）",
        "cohort_evidence": "2027届校园招聘",
        "campaign_scope": "formal_with_internships",
    }
    jobs = [
        {
            "title": "大模型算法工程师",
            "job_type": "校招",
            "campaign_text": "2027届校园招聘",
            "jd_raw": "",
        },
        {
            "title": "大模型算法工程师-应届生-TOP Talent",
            "job_type": "校招",
            "campaign_text": "MiniMax TOP Talent",
            "jd_raw": "",
        },
    ]

    result = job_cohorts.annotate_company_jobs(
        jobs,
        campaign=campaign,
        inspect_page=False,
    )

    assert job_cohorts.is_confirmed_current(result[0])
    assert result[1]["cohort_status"] == "unknown"


def test_tencent_docs_fallback_confirms_unlabelled_formal_jobs():
    campaign = job_cohorts.trusted_source_campaign({
        "source_cohort": 2027,
        "source_cohort_source": "腾讯文档27届秋招",
        "source_cohort_evidence": "测试公司：27届秋招",
        "source_cohort_url": "https://docs.qq.com/example",
    })
    jobs = [{"title": "C++开发工程师", "job_type": "校招", "jd_raw": ""}]

    result = job_cohorts.annotate_company_jobs(
        jobs,
        campaign=campaign,
        inspect_page=False,
    )

    assert job_cohorts.is_confirmed_current(result[0])
    assert result[0]["cohort_source"] == "腾讯文档27届秋招"


def test_tencent_docs_fallback_never_overrides_previous_job_evidence():
    campaign = job_cohorts.trusted_source_campaign({
        "source_cohort": 2027,
        "source_cohort_source": "腾讯文档27届秋招",
        "source_cohort_evidence": "测试公司：27届秋招",
    })
    jobs = [{"title": "2026届春招-C++工程师", "job_type": "校招", "jd_raw": ""}]

    result = job_cohorts.annotate_company_jobs(
        jobs,
        campaign=campaign,
        inspect_page=False,
    )

    assert result[0]["cohort"] == 2026
    assert result[0]["cohort_status"] == "confirmed"


def test_tencent_docs_fallback_requires_current_source_attachment():
    assert job_cohorts.trusted_source_campaign({
        "source_cohort": 2027,
        "source_cohort_source": "其他来源",
        "source_cohort_evidence": "27届秋招",
    }) is None
    assert job_cohorts.trusted_source_campaign({
        "source_cohort": 2027,
        "source_cohort_source": "腾讯文档27届秋招",
        "source_cohort_evidence": "",
    }) is None


def test_campaign_render_failure_stays_unknown():
    with (
        patch("job_cohorts.requests.Session.get", side_effect=RuntimeError("network")),
        patch("job_cohorts.render_page", side_effect=RuntimeError("browser")),
    ):
        result = job_cohorts.inspect_official_campaign(
            "https://example.com/campus"
        )

    assert result["cohort_status"] == "unknown"
    assert result["campaign_url"] == "https://example.com/campus"


def test_one_27_job_does_not_promote_unlabelled_sibling_without_page_evidence():
    jobs = [
        {"title": "27届算法工程师", "job_type": "校招", "jd_raw": ""},
        {"title": "C++开发工程师", "job_type": "校招", "jd_raw": ""},
    ]
    with patch(
        "job_cohorts.inspect_official_campaign",
        return_value=job_cohorts.unknown_cohort(),
    ):
        result = job_cohorts.annotate_company_jobs(jobs, "https://example.com/campus")
    assert job_cohorts.is_confirmed_current(result[0])
    assert result[1]["cohort_status"] == "unknown"


def test_previous_and_unknown_jobs_never_require_jd():
    jobs = [
        {"title": "26届春招-C++工程师", "job_type": "校招", "jd_raw": ""},
        {"title": "C++工程师", "job_type": "校招", "jd_raw": ""},
    ]
    with patch(
        "job_cohorts.inspect_official_campaign",
        return_value=job_cohorts.unknown_cohort(),
    ):
        result = job_cohorts.annotate_company_jobs(jobs, "https://example.com/campus")
    assert [job["jd_status"] for job in result] == ["not_required", "not_required"]
