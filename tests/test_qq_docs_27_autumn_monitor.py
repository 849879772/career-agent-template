import yaml

from scripts.qq_docs_27_autumn_monitor import (
    attach_official_campaign_urls,
    attach_trusted_cohort_evidence,
    append_verified_companies,
    compare_with_config,
    infer_crawler,
    parse_rows,
    update_integration_status,
    validate_unconfigured_rows,
)


def test_parse_rows_keeps_links_and_marks_mixed_records():
    payload = [{
        "f_company": {"k30": "公司名称"},
        "f_type": {"k30": "招聘类型", "k9": {"k3": [
            {"k1": "formal", "k2": "27届秋招"},
            {"k1": "intern", "k2": "27届暑期实习"},
        ]}},
        "f_link": {"k30": "投递链接"},
        "row": {"k1": {
            "f_company": {"k1": [{"k2": "DJI大疆"}]},
            "f_type": {"k9": ["formal", "intern"]},
            "f_link": {"k8": [{"k3": "https://example.com/jobs"}]},
        }},
    }]

    rows = parse_rows(payload)

    assert rows == [{
        "source_name": "DJI大疆",
        "canonical_name": "大疆",
        "tags": ["27届秋招", "27届暑期实习"],
        "links": ["https://example.com/jobs"],
        "source_status": "mixed_or_excluded",
        "excluded_tags": ["27届暑期实习"],
    }]


def test_parse_rows_accepts_later_pagination_payloads_without_field_definitions():
    first_page = [{
        "f_company": {"k30": "公司名称"},
        "f_type": {"k30": "招聘类型", "k9": {"k3": [
            {"k1": "formal", "k2": "27届秋招"},
        ]}},
        "f_link": {"k30": "投递链接"},
        "row": {"k1": {
            "f_company": {"k1": [{"k2": "First Co"}]},
            "f_type": {"k9": ["formal"]},
            "f_link": {"k8": [{"k3": "https://first.example/jobs"}]},
        }},
    }]
    later_page = [{"row": {"k1": {
        "f_company": {"k1": [{"k2": "Second Co"}]},
        "f_type": {"k9": ["formal"]},
        "f_link": {"k8": [{"k3": "https://second.example/jobs"}]},
    }}}]

    rows = parse_rows([first_page, later_page])

    assert [row["source_name"] for row in rows] == ["First Co", "Second Co"]


def test_compare_with_config_uses_campaign_aliases():
    rows = [
        {"source_name": "DJI大疆", "canonical_name": "大疆"},
        {"source_name": "卓驭-原大疆车载", "canonical_name": "卓驭"},
        {"source_name": "思特威-(未官宣岗位陆续上新)", "canonical_name": "思特威"},
        {"source_name": "文远知行WeRid(未官宣)", "canonical_name": "文远知行"},
        {"source_name": "柠檬微趣-下周官宣", "canonical_name": "柠檬微趣"},
    ]
    result = compare_with_config(rows, [
        {"name": "大疆"},
        {"name": "卓驭"},
        {"name": "思特威"},
        {"name": "文远知行"},
        {"name": "柠檬微趣"},
    ])
    assert all(row["in_config"] for row in result)


def test_compare_with_config_recognizes_same_feishu_company_host():
    rows = [{
        "source_name": "Momenta-M Star",
        "canonical_name": "Momenta",
        "links": ["https://momenta.jobs.feishu.cn/s/gIkCsB4KZiA"],
    }]
    result = compare_with_config(rows, [{
        "name": "Momenta",
        "careers_url": "https://momenta.jobs.feishu.cn/campus/position",
        "crawler": "feishu",
    }])

    assert result[0]["in_config"] is True
    assert result[0]["matched_company"] == "Momenta"


def test_attach_official_campaign_urls_keeps_explicit_config():
    companies = [
        {"name": "大疆", "campaign_url": "https://official.example/campaign"},
        {"name": "Momenta"},
    ]
    rows = [
        {
            "canonical_name": "大疆",
            "links": ["https://lead.example/dji"],
        },
        {
            "canonical_name": "Momenta",
            "links": ["https://momenta.jobs.feishu.cn/s/campus"],
        },
    ]

    attached = attach_official_campaign_urls(rows, companies)

    assert attached == 1
    assert companies[0]["campaign_url"] == "https://official.example/campaign"
    assert companies[1]["campaign_url"] == "https://momenta.jobs.feishu.cn/s/campus"


def test_attach_trusted_cohort_evidence_records_tencent_source():
    companies = [{"name": "远景科技"}]
    rows = [{
        "source_name": "远景能源-看备注，主要C9",
        "canonical_name": "远景科技",
        "tags": ["27届秋招"],
        "links": ["https://example.com/envision/2027"],
    }]

    attached = attach_trusted_cohort_evidence(rows, companies)

    assert attached == 1
    assert companies[0]["source_cohort"] == 2027
    assert companies[0]["source_cohort_source"] == "腾讯文档27届秋招"
    assert companies[0]["source_cohort_url"] == "https://example.com/envision/2027"


def test_infer_crawler_reuses_supported_platforms_and_render_fallback():
    assert infer_crawler("https://app.mokahr.com/campus_apply/example/1") == "moka"
    assert infer_crawler("https://example.zhiye.com/campus/jobs") == "beisen"
    assert infer_crawler("https://campus.example.com/campus/jobs") == "beisen"
    assert infer_crawler("https://example.jobs.feishu.cn/campus/position") == "feishu"
    assert infer_crawler("https://careers.example.com/campus") == "render"


def test_auto_onboarding_requires_a_real_formal_job():
    rows = [{
        "source_name": "New Co",
        "canonical_name": "New Co",
        "in_config": False,
        "links": ["https://app.mokahr.com/campus_apply/newco/1"],
    }]

    approved, attempts = validate_unconfigured_rows(
        rows,
        fetcher=lambda entry: [{"title": "Software Engineer", "jd_url": entry["careers_url"]}],
    )

    assert approved == [{
        "name": "New Co",
        "careers_url": "https://app.mokahr.com/campus_apply/newco/1",
        "crawler": "moka",
    }]
    assert attempts[0]["status"] == "approved"


def test_auto_onboarding_rejects_intern_only_results():
    rows = [{
        "source_name": "Intern Co",
        "canonical_name": "Intern Co",
        "in_config": False,
        "links": ["https://careers.example.com/campus"],
    }]

    approved, attempts = validate_unconfigured_rows(
        rows,
        fetcher=lambda entry: [{"title": "Software Engineering Intern", "jd_url": entry["careers_url"]}],
    )

    assert approved == []
    assert attempts[0]["status"] == "needs_review"
    assert "均被实习/社招/非具体岗位/方向规则过滤" in attempts[0]["reason"]


def test_auto_onboarding_rejects_direction_out_results():
    rows = [{
        "source_name": "Campus Ambassador Co",
        "canonical_name": "Campus Ambassador Co",
        "in_config": False,
        "links": ["https://careers.example.com/campus"],
    }]

    approved, attempts = validate_unconfigured_rows(
        rows,
        fetcher=lambda entry: [{"title": "2027届校园大使", "jd_url": entry["careers_url"]}],
    )

    assert approved == []
    assert attempts[0]["status"] == "needs_review"


def test_auto_onboarding_rejects_known_expired_source_without_fetching():
    rows = [{
        "source_name": "Dangdang",
        "canonical_name": "Dangdang",
        "in_config": False,
        "links": ["https://static.dangdang.com/topic/contents/1119/202265.shtml"],
    }]

    approved, attempts = validate_unconfigured_rows(
        rows,
        fetcher=lambda entry: (_ for _ in ()).throw(AssertionError("must not fetch")),
    )

    assert approved == []
    assert "过期专题页" in attempts[0]["reason"]


def test_verified_company_and_pending_status_are_written(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("companies:\ndeepseek:\n  model: test\n", encoding="utf-8")
    append_verified_companies(config_path, [{
        "name": "New Co",
        "careers_url": "https://careers.example.com/campus",
        "crawler": "render",
    }])
    config = config_path.read_text(encoding="utf-8")
    assert 'name: "New Co"' in config
    assert config.index('name: "New Co"') < config.index("deepseek:")
    assert yaml.safe_load(config)["companies"][0]["name"] == "New Co"

    status_path = tmp_path / "status.md"
    update_integration_status(status_path, [{
        "name": "Pending Co",
        "url": "https://careers.example.com/campus",
        "crawler": "render",
        "status": "needs_review",
        "reason": "render 返回 0 个岗位",
    }])
    status = status_path.read_text(encoding="utf-8")
    assert "Pending Co" in status
    assert "待人工接入" in status


def test_verified_company_does_not_duplicate_existing_source(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "companies:\n"
        "- name: Momenta\n"
        "  careers_url: https://momenta.jobs.feishu.cn/campus/position\n"
        "  crawler: feishu\n"
        "deepseek:\n"
        "  model: test\n",
        encoding="utf-8",
    )

    append_verified_companies(config_path, [{
        "name": "Momenta-M Star",
        "careers_url": "https://momenta.jobs.feishu.cn/s/gIkCsB4KZiA",
        "crawler": "feishu",
    }])

    assert len(yaml.safe_load(config_path.read_text(encoding="utf-8"))["companies"]) == 1
