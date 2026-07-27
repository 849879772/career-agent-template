from crawlers.leihuo import LeihuoCrawler


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "data": {
                "count_number": 1,
                "apply_job_list": [{
                    "ehr_job_id": "3738",
                    "job_name": "游戏客户端开发工程师",
                    "job_target": "2027届应届毕业生",
                    "type_name": "全职",
                    "job_description": "负责客户端功能开发",
                    "job_requirement": "熟悉 C++",
                    "work_place_name": "杭州",
                    "job_detail_url": "https://campus.163.com/app/detail/index?id=3738&projectId=77",
                }],
            }
        }


def test_leihuo_uses_current_full_time_project_and_official_detail_url(monkeypatch):
    requested = {}

    def fake_get(url, params, headers, timeout):
        requested.update(params)
        return _Response()

    monkeypatch.setattr("crawlers.leihuo.requests.get", fake_get)
    crawler = LeihuoCrawler("网易雷火", "https://leihuo.163.com/campus/#/full")

    jobs = crawler.fetch()

    assert requested["project_id"] == 77
    assert jobs[0]["jd_url"] == "https://campus.163.com/app/detail/index?id=3738&projectId=77"
    assert "2027届应届毕业生" in jobs[0]["jd_raw"]
