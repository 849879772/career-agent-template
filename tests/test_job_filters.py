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


def test_formal_filter_ignores_social_recruitment_navigation_text():
    job = {
        "title": "AI应用工程师",
        "job_type": "校招",
        "jd_url": "https://example.com/campus/job/1",
        "jd_raw": "岗位职责：负责AI应用开发。\n校园招聘\n社会招聘\n关于我们",
    }
    assert job_filters.is_formal_campus_job(job)


def test_formal_filter_drops_explicit_social_metadata():
    job = {
        "title": "软件开发工程师",
        "job_type": "校招",
        "jd_url": "https://example.com/job/2",
        "jd_raw": "招聘类型：社会招聘\n岗位职责：负责业务系统开发。",
    }
    assert job_filters.is_social_job(job)
    assert not job_filters.is_formal_campus_job(job)


def test_formal_filter_drops_greenvalley_social_campaign_page():
    job = {
        "title": "点云算法工程师",
        "jd_url": "https://campus.51job.com/greenvalley/si.html#job-ref=abc",
        "jd_raw": "负责点云算法开发，熟悉 C++ 和 PCL。",
    }
    assert not job_filters.is_formal_campus_job(job)


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


def test_formal_filter_uses_internship_url_when_title_is_shared():
    job = {
        "title": "测试开发工程师",
        "job_type": "校招",
        "jd_url": "https://campus.example/#/details?type=internship&id=4856",
    }
    assert job_filters.is_intern_job(job)
    assert not job_filters.is_formal_campus_job(job)


def test_formal_filter_uses_page_metadata_when_title_looks_formal():
    job = {
        "title": "AI应用部-Agent开发工程师",
        "job_type": "校园招聘",
        "jd_url": "https://example.com/campus/3",
        "jd_raw": "实习 实习 | 北京\n岗位职责：负责智能体应用开发。",
    }
    assert job_filters.internship_reason(job) == "页面头部元数据明确标注实习"
    assert not job_filters.is_formal_campus_job(job)


def test_formal_project_still_excludes_explicit_internship_metadata():
    job = {
        "title": "大模型算法工程师-2027届",
        "job_type": "校招",
        "campaign_text": "2027届校园招聘",
        "jd_url": "https://example.com/campus/2027/1",
        "jd_raw": (
            "大模型算法工程师-2027届 北京、上海 校招 实习 "
            "研发-算法 2027届校园招聘 负责大模型训练与推理优化"
        ),
    }

    assert job_filters.internship_reason(job) == "页面头部元数据明确标注实习"
    assert not job_filters.is_formal_campus_job(job)


def test_explicit_intern_title_still_wins_inside_2027_project():
    job = {
        "title": "大模型推理研发实习生-2027届",
        "job_type": "校招",
        "campaign_text": "2027届校园招聘",
        "jd_raw": "2027届校园招聘 参与大模型推理框架开发",
    }

    assert job_filters.internship_reason(job) == "标题明确标注实习"
    assert not job_filters.is_formal_campus_job(job)


def test_formal_filter_uses_current_internship_duration_requirement():
    job = {
        "title": "助理测试工程师",
        "job_type": "校园招聘",
        "jd_url": "https://example.com/campus/4",
        "jd_raw": "全日制本科在校生，能至少实习6个月，每周到岗5天。",
    }
    assert job_filters.internship_reason(job) == "岗位要求当前候选人连续实习"
    assert not job_filters.is_formal_campus_job(job)


def test_formal_filter_catches_nonstandard_internship_project_copy():
    jobs = [
        {"title": "T-Star Lab 算法工程师", "job_type": "校招",
         "jd_raw": "首次开设实习生专项招聘，面向在校优秀技术同学。"},
        {"title": "智慧座椅算法开发", "job_type": "校招",
         "jd_raw": "技术类 | 研发总院20027实习生 | 本科及以上"},
        {"title": "大模型算法工程师", "job_type": "校招",
         "jd_raw": "我们能提供你：丰富的实习薪酬津贴和导师辅导。"},
        {"title": "AI Technical Builder", "job_type": "校招",
         "jd_raw": "真实战场，极高杠杆；同时提供转正机会。"},
        {"title": "Forward Youth Program", "job_type": "campus",
         "jd_raw": "Candidates should complete an internship in China before conversion."},
    ]
    assert all(job_filters.is_intern_job(job) for job in jobs)


def test_formal_filter_keeps_english_past_internship_experience():
    job = {
        "title": "Channel Operations Specialist",
        "job_type": "campus",
        "jd_raw": "Internship experience in e-commerce is preferred.",
    }
    assert job_filters.internship_reason(job) is None
    assert job_filters.is_formal_campus_job(job)


def test_formal_filter_keeps_past_internship_experience_preference():
    job = {
        "title": "C++开发工程师",
        "job_type": "校招 正式",
        "jd_url": "https://example.com/campus/5",
        "jd_raw": "有相关实习经历者优先，具备扎实的 C++ 编程能力。",
    }
    assert job_filters.internship_reason(job) is None
    assert job_filters.is_formal_campus_job(job)


def test_formal_filter_drops_explicit_early_batch_but_keeps_formal_talent_plan():
    early = {
        "title": "27届算法工程师",
        "job_type": "校招",
        "jd_raw": "本岗位属于27届研发类校招提前批。",
        "jd_url": "https://example.com/campus/early",
    }
    formal_talent = {
        "title": "应届生-TOP Talent-大模型算法工程师",
        "job_type": "校招 正式",
        "jd_raw": "面向2027届毕业生的专项人才计划。",
        "jd_url": "https://example.com/campus/talent",
    }
    assert job_filters.is_early_batch_job(early)
    assert not job_filters.is_formal_campus_job(early)
    assert not job_filters.is_early_batch_job(formal_talent)
    assert job_filters.is_formal_campus_job(formal_talent)


def test_cohort_year_requires_recruitment_context():
    assert job_filters.cohort_year({"title": "算法工程师（27届）"}) == 2027
    assert job_filters.cohort_year({"title": "26届春招-C++开发工程师"}) == 2026
    assert job_filters.cohort_year({"title": "发布时间 2026-07-10"}) is None


def test_direction_filter_drops_explicit_non_target_roles():
    jobs = [
        {"title": "AI 产品经理"},
        {"title": "产品总经理储备计划（软件方向）-27届秋招"},
        {"title": "广告投放策略运营"},
        {"title": "销售工程师"},
        {"title": "财务 BP"},
        {"title": "招聘助理"},
        {"title": "供应链计划"},
        {"title": "高中物理竞赛教练"},
        {"title": "2027届校园大使"},
        {"title": "生态合作专员"},
        {"title": "商业产品规划培训生"},
        {"title": "虚拟世界架构师（游戏任务策划）"},
        {"title": "【2027届秋招】游戏系统策划"},
        {"title": "游戏设计师（技术策划）"},
        {"title": "游戏发行运营"},
        {"title": "策略分析师（数据科学方向）"},
        {"title": "品牌管理培训生"},
        {"title": "美术项目管理"},
        {"title": "Application Product Manager"},
        {"title": "游戏安全运营"},
        {"title": "游戏交互/体验设计师"},
        {"title": "技术型销售"},
        {"title": "游戏原画设计（广告方向）"},
        {"title": "3D角色模型"},
        {"title": "Spine动画师"},
        {"title": "【校招】策划管培生"},
        {"title": "游戏数据分析师"},
        {"title": "User Growth Marketing Campaigns"},
        {"title": "Marketing Trainee (Brand Strategy)-2027校招"},
        {"title": "开发者区域"},
        {"title": "闪购-非食日化PB商品开发（个护美妆、家清）"},
    ]
    kept, dropped = job_filters.filter_target_direction_jobs(jobs)
    assert kept == []
    assert [job["title"] for job in dropped] == [job["title"] for job in jobs]


def test_direction_filter_drops_parser_and_chatbot_noise():
    jobs = [
        {"title": "您好，欢迎使用帆一云AI助理👏"},
        {"title": "【原始职位】AI智能外呼测试"},
    ]
    kept, dropped = job_filters.filter_target_direction_jobs(jobs)
    assert kept == []
    assert dropped == jobs


def test_verified_campus_marker_preserves_advanced_doctor_role():
    job = {
        "title": "高级嵌入式开发工程师",
        "job_type": "校招",
        "jd_raw": "招聘类型：校园招聘\n岗位职责\n负责嵌入式系统研发\n任职要求\n博士学历",
        "jd_url": "https://example.com/campus/detail/1",
    }
    assert job_filters.is_formal_campus_job(job)
    assert not job_filters.is_formal_campus_job({**job, "jd_raw": "负责嵌入式系统研发"})


def test_direction_filter_drops_branded_product_role_from_jd():
    job = {
        "title": "商家智能-AI Builder",
        "jd_raw": "本岗位负责商家智能AI产品的规划与设计，并推动新产品上线。",
    }
    assert job_filters.is_direction_out_job(job)


def test_direction_filter_keeps_engineer_who_collaborates_with_product_team():
    job = {
        "title": "AI平台开发工程师",
        "jd_raw": "与产品经理合作，负责AI平台功能开发、测试和性能优化。",
    }
    assert not job_filters.is_direction_out_job(job)


def test_direction_filter_keeps_technical_research_role_with_product_planning_jd():
    job = {
        "title": "基础产品研究岗（软件设计方向）",
        "jd_raw": "负责基础产品的规划与设计，开展软件架构研究和核心代码开发。",
    }
    assert not job_filters.is_direction_out_job(job)


def test_direction_filter_keeps_technical_roles_with_business_context():
    jobs = [
        {"title": "腾讯营销-多模态大模型算法研究"},
        {"title": "软件开发-运营开发方向"},
        {"title": "供应链数智化开发工程师"},
        {"title": "供应链管理系统开发工程师"},
        {"title": "市场质量工程师"},
        {"title": "AI 解决方案工程师"},
        {"title": "机器人应用项目工程师"},
        {"title": "混元-视频编辑和统一生成模型探索"},
    ]
    kept, dropped = job_filters.filter_target_direction_jobs(jobs)
    assert [job["title"] for job in kept] == [job["title"] for job in jobs]
    assert dropped == []


def test_job_category_uses_specific_rules_before_general_software_terms():
    cases = {
        "大模型推理优化开发工程师": "llm_agent",
        "具身智能VLA算法工程师": "robotics",
        "自动驾驶视觉感知算法工程师": "vision_auto",
        "软件测试开发工程师": "testing_quality",
        "嵌入式软件开发工程师": "embedded_control",
        "芯片验证工程师": "hardware_mechanical",
        "推荐算法工程师": "algorithm_ml",
        "数据平台开发工程师": "data_platform",
        "C++客户端开发工程师": "software_cpp",
        "解决方案技术工程师": "other_technical",
    }
    assert {
        title: job_filters.job_category({"title": title}) for title in cases
    } == cases
