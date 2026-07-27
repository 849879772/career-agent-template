from main import _crawl_one, _normalize_configured_listing_links, _resolve_llm_models


def test_resolve_llm_models_uses_hybrid_defaults():
    assert _resolve_llm_models({}) == ("deepseek-v4-flash", "deepseek-v4-pro")


def test_resolve_llm_models_supports_explicit_and_legacy_config():
    assert _resolve_llm_models({
        "screening_model": "screening-model",
        "analysis_model": "analysis-model",
    }) == ("screening-model", "analysis-model")
    assert _resolve_llm_models({"model": "legacy-model"}) == (
        "legacy-model",
        "legacy-model",
    )


def test_configured_list_links_open_official_page_and_stay_unique():
    company = {
        "careers_url": "https://example.com/campus/jobs",
        "link_kind": "list",
    }
    jobs = [
        {"title": "算法工程师", "city": "深圳", "jd_url": "https://broken.example/1"},
        {"title": "软件工程师", "city": "深圳", "jd_url": "https://broken.example/2"},
    ]

    normalized = _normalize_configured_listing_links(company, jobs)

    assert all(job["jd_url"].startswith("https://example.com/campus/jobs#job-ref=") for job in normalized)
    assert len({job["jd_url"] for job in normalized}) == 2
    assert all(job["link_kind"] == "list" for job in normalized)


def test_configured_spa_list_link_preserves_route_fragment():
    company = {
        "careers_url": "https://example.com/#/positionList?campus=1",
        "link_kind": "list",
    }
    jobs = [{"title": "测试工程师", "city": "", "jd_url": "https://broken.example/3"}]

    result = _normalize_configured_listing_links(company, jobs)[0]["jd_url"]

    assert result.startswith("https://example.com/#/positionList?campus=1&job-ref=")


def test_crawl_one_discards_partial_paginated_results(monkeypatch):
    class PartialCrawler:
        def __init__(self, *_args):
            self.pagination_complete = False
            self.pagination_termination_reason = "safety_limit"

        def fetch(self):
            return [{"title": "C++开发工程师", "jd_url": "https://example.com/1"}]

    monkeypatch.setitem(__import__("main").CRAWLER_MAP, "partial", PartialCrawler)

    name, jobs = _crawl_one({
        "name": "测试公司",
        "careers_url": "https://example.com/campus",
        "crawler": "partial",
    })

    assert name == "测试公司"
    assert jobs == []


def test_crawl_one_attaches_configured_campaign_to_filtered_project(monkeypatch):
    class ProjectCrawler:
        def __init__(self, *_args):
            pass

        def fetch(self):
            return [{"title": "算法工程师", "campaign_text": ""}]

    monkeypatch.setitem(__import__("main").CRAWLER_MAP, "project", ProjectCrawler)

    _, jobs = _crawl_one({
        "name": "测试公司",
        "careers_url": "https://example.com/#/jobs?project=2027",
        "crawler": "project",
        "campaign_text": "2027届应届生",
    })

    assert jobs[0]["campaign_text"] == "2027届应届生"
