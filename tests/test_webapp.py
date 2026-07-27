import webapp


def test_health_exposes_current_frontend_build():
    response = webapp.app.test_client().get("/api/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "build": "company-cohort-ranking-v3",
    }


def test_jobs_api_filters_and_paginates(monkeypatch):
    items = [
        {
            "job": {
                "id": index,
                "company": "目标公司" if index <= 3 else "其他公司",
                "title": f"C++ 工程师 {index}",
                "city": "深圳",
                "jd_url": f"https://example.com/{index}",
                "link_kind": "detail",
            },
            "analysis": {
                "match_score": 90 - index,
                "advantages": [],
                "gaps": [],
                "summary": "匹配",
                "recommendation": "推荐",
            },
        }
        for index in range(1, 6)
    ]
    snapshot = {
        "current": items,
        "previous": [],
        "app_index": {},
    }
    monkeypatch.setattr(webapp, "_get_snapshot", lambda: (snapshot, ()))

    response = webapp.app.test_client().get(
        "/api/jobs?company=目标公司&page=2&per_page=2"
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["total"] == 3
    assert payload["page"] == 2
    assert len(payload["jobs"]) == 1
    assert payload["jobs"][0]["c"] == "目标公司"


def test_jobs_api_filters_by_job_category(monkeypatch):
    items = [
        {
            "job": {"id": 1, "company": "甲", "title": "大模型算法工程师", "city": "北京", "jd_url": "u1"},
            "analysis": {"match_score": 80, "summary": "匹配", "recommendation": "推荐"},
        },
        {
            "job": {"id": 2, "company": "乙", "title": "C++开发工程师", "city": "上海", "jd_url": "u2"},
            "analysis": {"match_score": 75, "summary": "匹配", "recommendation": "推荐"},
        },
    ]
    monkeypatch.setattr(
        webapp,
        "_get_snapshot",
        lambda: ({"current": items, "previous": [], "app_index": {}}, ()),
    )

    response = webapp.app.test_client().get("/api/jobs?category=llm_agent")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["total"] == 1
    assert payload["jobs"][0]["t"] == "大模型算法工程师"


def test_index_reuses_rendered_html_cache(monkeypatch):
    snapshot = {"items": [], "applications": []}
    signature = ((1, 1), (1, 1))
    calls = []
    monkeypatch.setattr(webapp, "_get_snapshot", lambda: (snapshot, signature))
    monkeypatch.setattr(
        webapp.reporter,
        "render_html",
        lambda *_args, **_kwargs: calls.append(1) or "cached page",
    )
    webapp._page_cache.update(signature=signature, snapshot=snapshot, html=None)

    client = webapp.app.test_client()
    assert client.get("/").get_data(as_text=True) == "cached page"
    assert client.get("/").get_data(as_text=True) == "cached page"
    assert len(calls) == 1
