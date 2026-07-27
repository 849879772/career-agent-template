from crawlers.iguopin import IGuopinCrawler


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return {"code": 200, "msg": "OK", "data": self._data}


def test_iguopin_crawler_uses_all_pages_and_direct_detail_url(monkeypatch):
    calls = []

    def fake_request(_self, method, url, timeout, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith("/activity/exclusive/v1/info"):
            return FakeResponse({
                "company_id": "company-1",
                "content": (
                    '{"params":{"nav":[{"route":"/job-campus",'
                    '"props":{"nature":"campus-a,campus-b"}}]}}'
                ),
            })
        return FakeResponse({
            "total": 1,
            "list": [{
                "job_id": "job-27",
                "job_name": "【27届校招】软件工程师",
                "nature_cn": "校招",
                "recruitment_type_cn": "校园招聘",
                "district_list": [{"area_cn": "成都-郫都区"}],
                "contents": "职责描述：负责嵌入式软件开发。\n任职要求：熟悉 C++ 和 Linux。",
                "start_time": "2026-07-01 00:00:00",
            }],
        })

    monkeypatch.setattr("requests.Session.request", fake_request)
    jobs = IGuopinCrawler(
        "中国电科", "https://cetc.iguopin.com/job-campus"
    ).fetch()

    assert len(jobs) == 1
    assert jobs[0]["link_kind"] == "detail"
    assert jobs[0]["jd_url"] == "https://www.iguopin.com/job/detail?id=job-27"
    assert jobs[0]["city"] == "成都-郫都区"
    assert jobs[0]["jd_raw"].startswith("职位描述")
    assert "任职要求" in jobs[0]["jd_raw"]
    list_body = calls[1][2]["json"]
    assert list_body["page_size"] == 100
    assert list_body["nature"] == ["campus-a", "campus-b"]
